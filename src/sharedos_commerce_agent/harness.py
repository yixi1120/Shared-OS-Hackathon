from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from .graph import build_arena_graph
from .models import (
    OrderStatus,
    RankingEntry,
    ServiceListing,
    ServiceResult,
    TradeReceipt,
)


MOCK_LISTINGS = [
    ServiceListing(
        service_id="audience-map",
        seller_id="seller-a",
        name="Audience Map",
        description="Maps product tags to likely autonomous buyers.",
        price=20,
        tags=["sales", "market"],
        evidence=["schema", "sample"],
        reputation=0.83,
    ),
    ServiceListing(
        service_id="risk-scan",
        seller_id="seller-b",
        name="Risk Scan",
        description="Finds execution and settlement risks.",
        price=25,
        tags=["strategy"],
        evidence=["checklist"],
        reputation=0.76,
    ),
    ServiceListing(
        service_id="demand-forecast",
        seller_id="seller-c",
        name="Demand Forecast",
        description="Estimates demand from current marketplace metadata.",
        price=35,
        tags=["market", "strategy"],
        evidence=["confidence interval", "backtest"],
        reputation=0.88,
    ),
    ServiceListing(
        service_id="pitch-review",
        seller_id="seller-d",
        name="Pitch Review",
        description="Returns objections and a revised machine-readable pitch.",
        price=15,
        tags=["sales"],
        evidence=["before-after example"],
        reputation=0.72,
    ),
]


@dataclass
class ArenaScenario:
    name: str
    listings: list[ServiceListing] = field(default_factory=lambda: MOCK_LISTINGS.copy())
    failed_invocations: set[str] = field(default_factory=set)
    failed_settlements: set[str] = field(default_factory=set)
    buy_timeouts: set[str] = field(default_factory=set)
    buy_ack_timeouts_after_success: set[str] = field(default_factory=set)
    unexpected_amounts: dict[str, int] = field(default_factory=dict)
    duplicate_receipt_id: str | None = None
    critique_post_failures: set[str] = field(default_factory=set)
    critique_ack_timeouts_after_success: set[str] = field(default_factory=set)
    ranking_submission_fails: bool = False
    ranking_ack_timeout_after_success: bool = False
    expected_valid: bool = True
    expected_violation_fragments: tuple[str, ...] = ()


@dataclass
class MockArenaClient:
    scenario: ArenaScenario = field(
        default_factory=lambda: ArenaScenario(name="happy_path")
    )
    posted_critiques: list[dict[str, str]] = field(default_factory=list)
    submitted_rankings: list[RankingEntry] = field(default_factory=list)
    purchases: list[TradeReceipt] = field(default_factory=list)
    purchases_by_key: dict[str, TradeReceipt] = field(default_factory=dict)
    posted_critique_keys: set[str] = field(default_factory=set)
    ranking_keys: set[str] = field(default_factory=set)
    acknowledgement_timeouts: set[str] = field(default_factory=set)

    async def discover_services(self) -> list[ServiceListing]:
        return self.scenario.listings.copy()

    async def invoke_service(self, listing: ServiceListing) -> ServiceResult:
        if listing.service_id in self.scenario.failed_invocations:
            return ServiceResult(
                service_id=listing.service_id,
                seller_id=listing.seller_id,
                success=False,
                latency_ms=2_000,
                output={"error": "synthetic provider failure"},
            )
        return ServiceResult(
            service_id=listing.service_id,
            seller_id=listing.seller_id,
            success=True,
            latency_ms=120 + listing.price,
            output={
                "recommendation": f"Use {listing.name} for a bounded decision.",
                "confidence": round(listing.reputation, 2),
                "limitation": "The result uses synthetic marketplace metadata.",
            },
        )

    async def post_critique(
        self, critique_text: str, product_id: str, *, idempotency_key: str
    ) -> None:
        if idempotency_key in self.posted_critique_keys:
            return
        if product_id in self.scenario.critique_post_failures:
            raise ConnectionError("synthetic critique endpoint failure")
        self.posted_critiques.append(
            {"product_id": product_id, "critique": critique_text}
        )
        self.posted_critique_keys.add(idempotency_key)
        if (
            product_id in self.scenario.critique_ack_timeouts_after_success
            and idempotency_key not in self.acknowledgement_timeouts
        ):
            self.acknowledgement_timeouts.add(idempotency_key)
            raise TimeoutError("synthetic acknowledgement loss after critique")

    async def submit_ranking(
        self, rankings: list[RankingEntry], *, idempotency_key: str
    ) -> None:
        if idempotency_key in self.ranking_keys:
            return
        if self.scenario.ranking_submission_fails:
            raise ConnectionError("synthetic ranking endpoint failure")
        self.submitted_rankings = rankings
        self.ranking_keys.add(idempotency_key)
        if (
            self.scenario.ranking_ack_timeout_after_success
            and idempotency_key not in self.acknowledgement_timeouts
        ):
            self.acknowledgement_timeouts.add(idempotency_key)
            raise TimeoutError("synthetic acknowledgement loss after ranking")

    async def buy(
        self, listing: ServiceListing, *, idempotency_key: str
    ) -> TradeReceipt:
        if idempotency_key in self.purchases_by_key:
            return self.purchases_by_key[idempotency_key]
        if listing.service_id in self.scenario.buy_timeouts:
            raise TimeoutError("synthetic purchase timeout")
        status = (
            OrderStatus.FAILED
            if listing.service_id in self.scenario.failed_settlements
            else OrderStatus.PAID
        )
        receipt_data: dict[str, Any] = {
            "buyer_id": "agent-commerce-network",
            "seller_id": listing.seller_id,
            "service_id": listing.service_id,
            "amount": self.scenario.unexpected_amounts.get(
                listing.service_id, listing.price
            ),
            "status": status,
            "metadata": {"source": "mock-arena"},
        }
        if self.scenario.duplicate_receipt_id:
            receipt_data["trade_id"] = self.scenario.duplicate_receipt_id
        receipt = TradeReceipt.model_validate(receipt_data)
        self.purchases.append(receipt)
        self.purchases_by_key[idempotency_key] = receipt
        if (
            listing.service_id in self.scenario.buy_ack_timeouts_after_success
            and idempotency_key not in self.acknowledgement_timeouts
        ):
            self.acknowledgement_timeouts.add(idempotency_key)
            raise TimeoutError("synthetic acknowledgement loss after purchase")
        return receipt


SCENARIOS = [
    ArenaScenario(name="happy_path"),
    ArenaScenario(
        name="one_provider_fails_during_evaluation",
        failed_invocations={"demand-forecast"},
        expected_valid=True,
    ),
    ArenaScenario(
        name="critique_cannot_be_posted",
        critique_post_failures={"seller-c"},
        expected_valid=False,
        expected_violation_fragments=("Could not post critique",),
    ),
    ArenaScenario(
        name="critique_succeeds_but_ack_is_lost",
        critique_ack_timeouts_after_success={"seller-c"},
        expected_valid=True,
    ),
    ArenaScenario(
        name="ranking_submission_fails",
        ranking_submission_fails=True,
        expected_valid=False,
        expected_violation_fragments=("Could not submit ranking",),
    ),
    ArenaScenario(
        name="ranking_succeeds_but_ack_is_lost",
        ranking_ack_timeout_after_success=True,
        expected_valid=True,
    ),
    ArenaScenario(
        name="purchase_does_not_settle",
        failed_settlements={"demand-forecast"},
        expected_valid=False,
        expected_violation_fragments=("did not settle",),
    ),
    ArenaScenario(
        name="not_enough_distinct_sellers",
        listings=MOCK_LISTINGS[:2],
        expected_valid=False,
        expected_violation_fragments=("needs 3 reachable products",),
    ),
    ArenaScenario(
        name="settlement_price_changes",
        unexpected_amounts={"demand-forecast": 34},
        expected_valid=False,
        expected_violation_fragments=("unexpected price",),
    ),
    ArenaScenario(
        name="purchase_api_times_out",
        buy_timeouts={"demand-forecast"},
        expected_valid=False,
        expected_violation_fragments=("TimeoutError",),
    ),
    ArenaScenario(
        name="purchase_succeeds_but_ack_is_lost",
        buy_ack_timeouts_after_success={"demand-forecast"},
        expected_valid=True,
    ),
    ArenaScenario(
        name="duplicate_receipts",
        duplicate_receipt_id="synthetic-duplicate-receipt",
        expected_valid=False,
        expected_violation_fragments=("Duplicate receipt detected",),
    ),
]


async def run_harness(scenario: ArenaScenario | None = None) -> dict[str, Any]:
    active_scenario = scenario or SCENARIOS[0]
    client = MockArenaClient(scenario=active_scenario)
    graph = build_arena_graph(client)
    state = await graph.ainvoke({"agent_id": "agent-commerce-network"})
    report = state["report"]
    return {
        "scenario": active_scenario.name,
        "valid": state["compliant"],
        "phase": state["phase"],
        "report": report.model_dump(mode="json"),
        "side_effects": {
            "critiques_posted": len(client.posted_critiques),
            "ranking_entries": len(client.submitted_rankings),
            "purchases": len(client.purchases),
        },
    }


async def run_suite() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        result = await run_harness(scenario)
        violations = result["report"]["violations"]
        expected_fragments_found = all(
            any(fragment in violation for violation in violations)
            for fragment in scenario.expected_violation_fragments
        )
        result["expectation_met"] = (
            result["valid"] is scenario.expected_valid and expected_fragments_found
        )
        results.append(result)
    return {
        "suite_passed": all(item["expectation_met"] for item in results),
        "scenarios": results,
    }


def main() -> None:
    result = asyncio.run(run_suite())
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["suite_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
