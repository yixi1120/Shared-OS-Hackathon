from __future__ import annotations

import argparse
import asyncio
import copy
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Callable

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
    ledger_path: str = ":memory:",
    round_pause_seconds: float = 0.0,
    progress_every_seconds: float | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Exercise concurrent buyers; duration mode turns the same oracle into a soak test."""

    if concurrency < 1 or rounds < 1:
        raise ValueError("concurrency and rounds must be positive")
    if duration_seconds is not None and duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if round_pause_seconds < 0:
        raise ValueError("round_pause_seconds cannot be negative")
    if progress_every_seconds is not None and progress_every_seconds <= 0:
        raise ValueError("progress_every_seconds must be positive")

    app = create_app(Settings(ledger_path=ledger_path))
    transport = httpx.ASGITransport(app=app)
    rng = random.Random(seed)
    started = perf_counter()
    failures: list[str] = []
    round_number = 0
    successful_interactions = 0
    deliveries = 0
    duplicate_replays_safe = 0
    conflicts_rejected = 0
    provenance_downgrades = 0
    declared_credits = 0
    next_progress_at = (
        started + progress_every_seconds
        if progress_every_seconds is not None
        else None
    )

    def snapshot(*, final: bool) -> dict[str, Any]:
        elapsed = perf_counter() - started
        interactions = successful_interactions + len(failures)
        return {
            "passed": not failures and successful_interactions == interactions,
            "final": final,
            "mode": "soak" if duration_seconds is not None else "fixed_rounds",
            "seed": seed,
            "concurrency": concurrency,
            "rounds_completed": round_number,
            "interactions": interactions,
            "unique_orders": successful_interactions,
            "deliveries": deliveries,
            "duplicate_replays_safe": duplicate_replays_safe,
            "idempotency_conflicts_rejected": conflicts_rejected,
            "provenance_downgrades": provenance_downgrades,
            "declared_credits": declared_credits,
            "elapsed_seconds": round(elapsed, 3),
            "interactions_per_second": round(interactions / elapsed, 2),
            "failures": failures[:20],
        }

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
                    successful_interactions += 1
                    deliveries += int(result["delivered"])
                    duplicate_replays_safe += int(result["duplicate_replay_safe"])
                    conflicts_rejected += int(result["conflict_rejected"])
                    provenance_downgrades += int(result["provenance_downgraded"])
                    declared_credits += result["declared_credits"]
            round_number += 1
            if (
                next_progress_at is not None
                and perf_counter() >= next_progress_at
                and on_progress is not None
            ):
                on_progress(snapshot(final=False))
                next_progress_at = perf_counter() + progress_every_seconds
            if round_pause_seconds:
                await asyncio.sleep(round_pause_seconds)

    return snapshot(final=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Concurrent seller and soak harness")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--ledger-path", default=":memory:")
    parser.add_argument("--round-pause-seconds", type=float, default=0.0)
    parser.add_argument("--progress-every-seconds", type=float, default=60.0)
    args = parser.parse_args()

    def print_progress(progress: dict[str, Any]) -> None:
        print(json.dumps(progress, sort_keys=True), file=sys.stderr, flush=True)

    report = asyncio.run(
        run_seller_harness(
            concurrency=args.concurrency,
            rounds=args.rounds,
            duration_seconds=args.duration_seconds,
            seed=args.seed,
            ledger_path=args.ledger_path,
            round_pause_seconds=args.round_pause_seconds,
            progress_every_seconds=args.progress_every_seconds,
            on_progress=print_progress,
        )
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
