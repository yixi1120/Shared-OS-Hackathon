from __future__ import annotations

import operator
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .arena import ArenaClient
from .models import (
    ArenaProgress,
    ArenaReport,
    ArenaRunMode,
    OrderStatus,
    PurchaseIntent,
    RankingEntry,
    RoundName,
    ServiceListing,
    ServiceResult,
)
from .strategy import ComplianceError, CritiqueStrategy, MarketStrategy


class ArenaGraphState(TypedDict, total=False):
    """Raw, inspectable facts shared between Arena workflow nodes."""

    agent_id: str
    run_id: str
    run_mode: ArenaRunMode
    phase: str
    listings: list[ServiceListing]
    evaluation_targets: list[ServiceListing]
    results: dict[str, ServiceResult]
    progress: ArenaProgress
    rankings: list[RankingEntry]
    purchase_plan: list[PurchaseIntent]
    violations: Annotated[list[str], operator.add]
    report: ArenaReport
    compliant: bool


def build_arena_graph(
    client: ArenaClient,
    *,
    critique_strategy: CritiqueStrategy | None = None,
    market_strategy: MarketStrategy | None = None,
    checkpointer=None,
):
    """Compile the Arena workflow with business-relevant, testable nodes."""

    critique_policy = critique_strategy or CritiqueStrategy()
    market_policy = market_strategy or MarketStrategy()

    async def retry_idempotent(operation: Callable[[], Awaitable[object]]) -> object:
        """Retry once; the caller must reuse the same idempotency key."""

        try:
            return await operation()
        except (TimeoutError, ConnectionError):
            return await operation()

    async def prepare(state: ArenaGraphState) -> ArenaGraphState:
        agent_id = state.get("agent_id")
        if not agent_id:
            raise ValueError("agent_id is required")
        run_mode = ArenaRunMode(state.get("run_mode", ArenaRunMode.FULL_DRY_RUN))
        run_id = state.get("run_id") or f"{agent_id}:{run_mode.value}"
        progress = state.get("progress") or ArenaProgress(agent_id=agent_id)
        if progress.agent_id != agent_id:
            raise ValueError("progress belongs to a different agent_id")
        return {
            "phase": "discover",
            "run_mode": run_mode,
            "run_id": run_id,
            "progress": progress.model_copy(deep=True),
            "rankings": [],
            "violations": [],
        }

    async def discover(state: ArenaGraphState) -> ArenaGraphState:
        listings = [
            item
            for item in await client.discover_services()
            if item.seller_id != state["agent_id"] and item.reachable
        ]
        targets: list[ServiceListing] = []
        if state["run_mode"] is not ArenaRunMode.MARKET:
            try:
                targets = critique_policy.select_targets(listings)
            except ComplianceError as exc:
                return {
                    "phase": "audit",
                    "listings": listings,
                    "evaluation_targets": [],
                    "violations": [str(exc)],
                }
        return {
            "phase": "evaluate_services",
            "listings": listings,
            "evaluation_targets": targets,
        }

    def after_discovery(
        state: ArenaGraphState,
    ) -> Literal["evaluate_services", "plan_market", "audit"]:
        if state["run_mode"] is ArenaRunMode.MARKET:
            return "plan_market"
        return "evaluate_services" if state.get("evaluation_targets") else "audit"

    async def evaluate_services(state: ArenaGraphState) -> ArenaGraphState:
        """Run products and retain objective observations before writing any opinion."""

        progress = state["progress"].model_copy(deep=True)
        results: dict[str, ServiceResult] = {}

        for listing in state["evaluation_targets"]:
            try:
                result = await client.invoke_service(listing)
            except Exception as exc:  # Network/provider failures become evidence.
                result = ServiceResult(
                    service_id=listing.service_id,
                    seller_id=listing.seller_id,
                    success=False,
                    latency_ms=0,
                    output={"error_type": type(exc).__name__},
                )
            results[listing.service_id] = result
            progress.tried_products.add(listing.seller_id)

        return {
            "phase": "publish_required_feedback",
            "progress": progress,
            "results": results,
        }

    async def publish_required_feedback(state: ArenaGraphState) -> ArenaGraphState:
        """Translate recorded evidence into the disagreement required by Round 1."""

        progress = state["progress"].model_copy(deep=True)
        violations: list[str] = []
        for index, listing in enumerate(state["evaluation_targets"]):
            result = state["results"][listing.service_id]
            item = critique_policy.create(listing, result)
            progress.critiques.append(item)
            idempotency_key = (
                f"{state['run_id']}:feedback:{listing.seller_id}:{index}"
            )
            try:
                await retry_idempotent(
                    lambda: client.post_critique(
                        " ".join([item.evidence, item.disagreement, item.suggestion]),
                        listing.seller_id,
                        idempotency_key=idempotency_key,
                    )
                )
            except Exception as exc:
                violations.append(
                    f"Could not post critique for {listing.seller_id}: {type(exc).__name__}"
                )

        return {
            "phase": "ranking",
            "progress": progress,
            "violations": violations,
        }

    async def rank(state: ArenaGraphState) -> ArenaGraphState:
        progress = state["progress"].model_copy(deep=True)
        rankings = critique_policy.rank(
            state["evaluation_targets"], state["results"]
        )
        violations: list[str] = []
        idempotency_key = f"{state['run_id']}:ranking:final"
        try:
            await retry_idempotent(
                lambda: client.submit_ranking(
                    rankings, idempotency_key=idempotency_key
                )
            )
            progress.ranking_submitted = bool(rankings)
        except Exception as exc:
            violations.append(f"Could not submit ranking: {type(exc).__name__}")
        progress.round = RoundName.MARKET
        return {
            "phase": "market_plan",
            "progress": progress,
            "rankings": rankings,
            "violations": violations,
        }

    async def plan_market(state: ArenaGraphState) -> ArenaGraphState:
        try:
            plan = market_policy.plan_purchases(
                state["listings"], own_agent_id=state["agent_id"]
            )
        except ComplianceError as exc:
            return {
                "phase": "audit",
                "purchase_plan": [],
                "violations": [str(exc)],
            }
        return {"phase": "purchase", "purchase_plan": plan}

    def after_market_plan(state: ArenaGraphState) -> Literal["purchase", "audit"]:
        return "purchase" if state.get("purchase_plan") else "audit"

    def after_ranking(state: ArenaGraphState) -> Literal["plan_market", "audit"]:
        if state["run_mode"] is ArenaRunMode.CRITIQUE:
            return "audit"
        return "plan_market"

    async def purchase(state: ArenaGraphState) -> ArenaGraphState:
        progress = state["progress"].model_copy(deep=True)
        listings = {item.service_id: item for item in state["listings"]}
        violations: list[str] = []
        seen_trade_ids = {receipt.trade_id for receipt in progress.receipts}

        for index, intent in enumerate(state["purchase_plan"]):
            idempotency_key = f"{state['run_id']}:purchase:{intent.service_id}:{index}"
            try:
                receipt = await retry_idempotent(
                    lambda: client.buy(
                        listings[intent.service_id],
                        idempotency_key=idempotency_key,
                    )
                )
            except Exception as exc:
                violations.append(
                    f"Purchase of {intent.service_id} failed: {type(exc).__name__}"
                )
                continue
            if receipt.status not in {OrderStatus.PAID, OrderStatus.DELIVERED}:
                violations.append(f"Purchase {receipt.trade_id} did not settle")
                continue
            if receipt.amount != intent.price:
                violations.append(
                    f"Purchase {receipt.trade_id} settled at unexpected price {receipt.amount}"
                )
                continue
            if receipt.trade_id in seen_trade_ids:
                violations.append(f"Duplicate receipt detected: {receipt.trade_id}")
                continue
            seen_trade_ids.add(receipt.trade_id)
            progress.receipts.append(receipt)
            progress.spent_credits += receipt.amount
            progress.purchased_products.add(receipt.seller_id)

        return {
            "phase": "audit",
            "progress": progress,
            "violations": violations,
        }

    async def audit(state: ArenaGraphState) -> ArenaGraphState:
        progress = state["progress"].model_copy(deep=True)
        added: list[str] = []
        checks_critique = state["run_mode"] in {
            ArenaRunMode.CRITIQUE,
            ArenaRunMode.FULL_DRY_RUN,
        }
        checks_market = state["run_mode"] in {
            ArenaRunMode.MARKET,
            ArenaRunMode.FULL_DRY_RUN,
        }
        if checks_critique and not progress.critique_compliant:
            added.append(
                "Critique round requires 3 tried products, a specific disagreement "
                "for each, and a ranking."
            )
        if checks_market and not progress.market_compliant:
            added.append(
                "Market round requires spending at least 80 credits across at least 3 products."
            )
        all_violations = list(dict.fromkeys(state.get("violations", []) + added))
        if not all_violations and checks_market:
            progress.round = RoundName.COMPLETE
        report = ArenaReport(
            progress=progress,
            rankings=state.get("rankings", []),
            violations=all_violations,
        )
        return {
            "phase": "complete",
            "progress": progress,
            "violations": added,
            "report": report,
            "compliant": report.valid,
        }

    graph = StateGraph(ArenaGraphState)
    graph.add_node("prepare", prepare)
    graph.add_node("discover", discover)
    graph.add_node("evaluate_services", evaluate_services)
    graph.add_node("publish_required_feedback", publish_required_feedback)
    graph.add_node("rank", rank)
    graph.add_node("plan_market", plan_market)
    graph.add_node("purchase", purchase)
    graph.add_node("audit", audit)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "discover")
    graph.add_conditional_edges("discover", after_discovery)
    graph.add_edge("evaluate_services", "publish_required_feedback")
    graph.add_edge("publish_required_feedback", "rank")
    graph.add_conditional_edges("rank", after_ranking)
    graph.add_conditional_edges("plan_market", after_market_plan)
    graph.add_edge("purchase", "audit")
    graph.add_edge("audit", END)
    return graph.compile(checkpointer=checkpointer)
