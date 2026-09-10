from __future__ import annotations

import argparse
import asyncio
import copy
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

import httpx

from .api import create_app
from .config import Settings


@dataclass(frozen=True, slots=True)
class BuyerPersona:
    """A deterministic demand profile used to vary seller-side traffic."""

    name: str
    service_id: str
    budget: int
    complexity: float
    urgency: float
    reputation: float


PERSONAS = (
    BuyerPersona("budget_researcher", "a2a-interaction-trace", 18, 0.8, 0.8, 0.7),
    BuyerPersona("urgent_operator", "a2a-interaction-risk-report", 35, 1.2, 1.5, 0.8),
    BuyerPersona("new_agent", "a2a-interaction-trace", 25, 1.0, 1.0, 0.2),
    BuyerPersona("risk_auditor", "a2a-interaction-risk-report", 30, 1.1, 1.1, 0.9),
)


def _interaction_events(task_id: str, subject_agent_id: str, offset: int) -> list[dict[str, Any]]:
    started = datetime(2026, 9, 10, tzinfo=timezone.utc) + timedelta(seconds=offset)
    return [
        {
            "task_id": task_id,
            "subject_agent_id": subject_agent_id,
            "stage": "request_received",
            "occurred_at": started.isoformat(),
            # This deliberate spoof must be stripped by the public ingestion boundary.
            "provenance": "platform",
            "evidence_id": f"{task_id}:request",
            "request_hash": f"sha256:{task_id}:request",
        },
        {
            "task_id": task_id,
            "subject_agent_id": subject_agent_id,
            "stage": "task_started",
            "occurred_at": (started + timedelta(milliseconds=100)).isoformat(),
            "evidence_id": f"{task_id}:start",
        },
        {
            "task_id": task_id,
            "subject_agent_id": subject_agent_id,
            "stage": "artifact_delivered",
            "occurred_at": (started + timedelta(milliseconds=700)).isoformat(),
            "schema_valid": True,
            "evidence_id": f"{task_id}:artifact",
            "artifact_hash": f"sha256:{task_id}:artifact",
        },
        {
            "task_id": task_id,
            "subject_agent_id": subject_agent_id,
            "stage": "task_completed",
            "occurred_at": (started + timedelta(milliseconds=800)).isoformat(),
            "evidence_id": f"{task_id}:complete",
        },
    ]


async def _exercise_buyer(
    client: httpx.AsyncClient,
    persona: BuyerPersona,
    *,
    buyer_number: int,
    round_number: int,
) -> dict[str, Any]:
    buyer_id = f"{persona.name}-{round_number}-{buyer_number}"
    task_id = f"task-{round_number}-{buyer_number}"
    quote_response = await client.post(
        "/v1/quotes",
        json={
            "buyer_id": buyer_id,
            "service_id": persona.service_id,
            "budget": persona.budget,
            "complexity": persona.complexity,
            "urgency": persona.urgency,
            "buyer_reputation": persona.reputation,
        },
    )
    quote_response.raise_for_status()
    quote = quote_response.json()

    negotiation_response = await client.post(
        f"/v1/quotes/{quote['quote_id']}/negotiate",
        json={"buyer_offer": quote["reservation_price"]},
    )
    negotiation_response.raise_for_status()
    decision = negotiation_response.json()
    if not decision["accepted"]:
        raise AssertionError("reservation-price offer must be accepted")

    order_payload = {
        "quote_id": quote["quote_id"],
        "buyer_id": buyer_id,
        "service_id": persona.service_id,
        "amount": decision["final_price"],
        "idempotency_key": f"seller-harness:{round_number}:{buyer_number}",
        "input": {"events": _interaction_events(task_id, buyer_id, buyer_number)},
    }
    first_response, replay_response = await asyncio.gather(
        client.post("/v1/orders", json=order_payload),
        client.post("/v1/orders", json=order_payload),
    )
    first_response.raise_for_status()
    replay_response.raise_for_status()
    first = first_response.json()
    replay = replay_response.json()
    if first["trade_id"] != replay["trade_id"]:
        raise AssertionError("idempotent replay created a second order")
    stored_event = first["metadata"]["input"]["events"][0]
    if "provenance" in stored_event:
        raise AssertionError("caller-controlled provenance reached persistence")

    conflicting_payload = copy.deepcopy(order_payload)
    conflicting_payload["input"]["events"][2]["artifact_hash"] += ":changed"
    conflict_response = await client.post("/v1/orders", json=conflicting_payload)
    if conflict_response.status_code != 409:
        raise AssertionError("mutated idempotency replay was not rejected")

    delivery_response = await client.post(f"/v1/orders/{first['trade_id']}/deliver")
    delivery_response.raise_for_status()
    delivery = delivery_response.json()
    output = delivery["output"]
    if output["provenance_counts"] != {"self_reported": 4}:
        raise AssertionError("public events were promoted above self-reported")
    if output["reputation_eligible"]:
        raise AssertionError("self-reported evidence entered reputation aggregation")
    if output["credit_settlement"] != "not_evaluated":
        raise AssertionError("seller claimed an unverified credit settlement")

    return {
        "buyer_id": buyer_id,
        "persona": persona.name,
        "trade_id": first["trade_id"],
        "declared_credits": first["amount"],
        "duplicate_replay_safe": True,
        "conflict_rejected": True,
        "provenance_downgraded": True,
        "delivered": delivery["status"] == "delivered",
    }


async def run_seller_harness(
    *,
    concurrency: int = 8,
    rounds: int = 2,
    duration_seconds: float | None = None,
    seed: int = 7,
) -> dict[str, Any]:
    """Exercise concurrent buyers; duration mode turns the same oracle into a soak test."""

    if concurrency < 1 or rounds < 1:
        raise ValueError("concurrency and rounds must be positive")
    if duration_seconds is not None and duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")

    app = create_app(Settings(ledger_path=":memory:"))
    transport = httpx.ASGITransport(app=app)
    rng = random.Random(seed)
    started = perf_counter()
    outcomes: list[dict[str, Any]] = []
    failures: list[str] = []
    round_number = 0

    async with httpx.AsyncClient(transport=transport, base_url="http://seller.test") as client:
        while True:
            if duration_seconds is None and round_number >= rounds:
                break
            if (
                duration_seconds is not None
                and round_number > 0
                and perf_counter() - started >= duration_seconds
            ):
                break
            personas = [rng.choice(PERSONAS) for _ in range(concurrency)]
            batch = await asyncio.gather(
                *(
                    _exercise_buyer(
                        client,
                        persona,
                        buyer_number=buyer_number,
                        round_number=round_number,
                    )
                    for buyer_number, persona in enumerate(personas)
                ),
                return_exceptions=True,
            )
            for result in batch:
                if isinstance(result, BaseException):
                    failures.append(f"{type(result).__name__}: {result}")
                else:
                    outcomes.append(result)
            round_number += 1

    elapsed = perf_counter() - started
    interactions = len(outcomes) + len(failures)
    unique_trade_ids = {item["trade_id"] for item in outcomes}
    report = {
        "passed": not failures and len(unique_trade_ids) == len(outcomes),
        "mode": "soak" if duration_seconds is not None else "fixed_rounds",
        "seed": seed,
        "concurrency": concurrency,
        "rounds_completed": round_number,
        "interactions": interactions,
        "unique_orders": len(unique_trade_ids),
        "deliveries": sum(item["delivered"] for item in outcomes),
        "duplicate_replays_safe": sum(
            item["duplicate_replay_safe"] for item in outcomes
        ),
        "idempotency_conflicts_rejected": sum(
            item["conflict_rejected"] for item in outcomes
        ),
        "provenance_downgrades": sum(
            item["provenance_downgraded"] for item in outcomes
        ),
        "declared_credits": sum(item["declared_credits"] for item in outcomes),
        "elapsed_seconds": round(elapsed, 3),
        "interactions_per_second": round(interactions / elapsed, 2),
        "failures": failures[:20],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Concurrent seller and soak harness")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    report = asyncio.run(
        run_seller_harness(
            concurrency=args.concurrency,
            rounds=args.rounds,
            duration_seconds=args.duration_seconds,
            seed=args.seed,
        )
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
