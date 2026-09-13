from __future__ import annotations

import asyncio
import operator
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .arena import ArenaClient
from .models import (
    ArenaProgress,
    ArenaReport,
    ArenaRunMode,
    LedgerDirection,
    OrderStatus,
    PurchaseIntent,
    RankingEntry,
    RoundName,
    ServiceListing,
    ServiceResult,
    TradeReceipt,
    TradeReconciliation,
)
from .operation_journal import (
    InMemoryOperationJournal,
    OperationJournal,
    OperationStatus,
)
from .reasoning import EvidenceBoundedCritiqueComposer, StructuredReasoningModel
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
    purchase_index: int
    pending_purchase_key: str
    pending_service_id: str
    violations: Annotated[list[str], operator.add]
    report: ArenaReport
    compliant: bool
    model_attempts: int
    model_successes: int
    model_fallbacks: int
    model_fallback_reasons: Annotated[list[str], operator.add]


def build_arena_graph(
    client: ArenaClient,
    *,
    critique_strategy: CritiqueStrategy | None = None,
    market_strategy: MarketStrategy | None = None,
    checkpointer=None,
    operation_journal: OperationJournal | None = None,
    max_concurrent_evaluations: int = 3,
    reasoning_model: StructuredReasoningModel | None = None,
):
    """Compile the Arena workflow with business-relevant, testable nodes."""

    if max_concurrent_evaluations < 1:
        raise ValueError("max_concurrent_evaluations must be positive")

    critique_policy = critique_strategy or CritiqueStrategy()
    market_policy = market_strategy or MarketStrategy()
    outbound_journal = operation_journal or InMemoryOperationJournal()
    critique_composer = EvidenceBoundedCritiqueComposer(
        policy=critique_policy,
        model=reasoning_model,
    )

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
            "model_attempts": 0,
            "model_successes": 0,
            "model_fallbacks": 0,
            "model_fallback_reasons": [],
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
        semaphore = asyncio.Semaphore(max_concurrent_evaluations)

        async def invoke_one(listing: ServiceListing) -> tuple[str, ServiceResult]:
            try:
                async with semaphore:
                    result = await client.invoke_service(listing)
            except Exception as exc:  # Network/provider failures become evidence.
                result = ServiceResult(
                    service_id=listing.service_id,
                    seller_id=listing.seller_id,
                    success=False,
                    latency_ms=0,
                    output={"error_type": type(exc).__name__},
                )
            return listing.service_id, result

        pairs = await asyncio.gather(
            *(invoke_one(listing) for listing in state["evaluation_targets"])
        )
        results = dict(pairs)
        for listing in state["evaluation_targets"]:
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
        model_attempts = state.get("model_attempts", 0)
        model_successes = state.get("model_successes", 0)
        model_fallbacks = state.get("model_fallbacks", 0)
        model_fallback_reasons: list[str] = []
        for index, listing in enumerate(state["evaluation_targets"]):
            result = state["results"][listing.service_id]
            composition = await critique_composer.create(listing, result)
            item = composition.critique
            model_attempts += int(composition.model_attempted)
            model_successes += int(composition.model_succeeded)
            if composition.model_attempted and not composition.model_succeeded:
                model_fallbacks += 1
                model_fallback_reasons.append(
                    composition.fallback_reason or "unknown-model-error"
                )
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
            "model_attempts": model_attempts,
            "model_successes": model_successes,
            "model_fallbacks": model_fallbacks,
            "model_fallback_reasons": model_fallback_reasons,
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
        return {
            "phase": "prepare_purchase",
            "purchase_plan": plan,
            "purchase_index": 0,
        }

    def after_market_plan(
        state: ArenaGraphState,
    ) -> Literal["prepare_purchase", "audit"]:
        return "prepare_purchase" if state.get("purchase_plan") else "audit"

    def after_ranking(state: ArenaGraphState) -> Literal["plan_market", "audit"]:
        if state["run_mode"] is ArenaRunMode.CRITIQUE:
            return "audit"
        return "plan_market"

    def receipt_violation(
        receipt: TradeReceipt,
        intent: PurchaseIntent,
    ) -> str | None:
        if receipt.status not in {OrderStatus.PAID, OrderStatus.DELIVERED}:
            return f"Purchase {receipt.trade_id} did not settle"
        if receipt.amount != intent.price:
            return (
                f"Purchase {receipt.trade_id} settled at unexpected price "
                f"{receipt.amount}"
            )
        if receipt.seller_id != intent.seller_id:
            return f"Purchase {receipt.trade_id} settled with an unexpected seller"
        if receipt.service_id != intent.service_id:
            return f"Purchase {receipt.trade_id} settled for an unexpected service"
        return None

    def bilateral_entries_match(
        evidence: TradeReconciliation,
        intent: PurchaseIntent,
        idempotency_key: str,
        buyer_id: str,
    ) -> bool:
        buyer = evidence.buyer_entry
        seller = evidence.seller_entry
        if buyer is None or seller is None:
            return False
        return (
            buyer.transfer_id == seller.transfer_id
            and buyer.idempotency_key == idempotency_key
            and seller.idempotency_key == idempotency_key
            and buyer.direction is LedgerDirection.DEBIT
            and seller.direction is LedgerDirection.CREDIT
            and buyer.account_id == buyer_id
            and buyer.counterparty_id == intent.seller_id
            and seller.account_id == intent.seller_id
            and seller.counterparty_id == buyer_id
            and buyer.amount == intent.price
            and seller.amount == intent.price
            and buyer.status == "settled"
            and seller.status == "settled"
        )

    async def prepare_purchase(state: ArenaGraphState) -> ArenaGraphState:
        index = state.get("purchase_index", 0)
        if index >= len(state["purchase_plan"]):
            return {"phase": "audit"}
        intent = state["purchase_plan"][index]
        idempotency_key = (
            f"{state['run_id']}:purchase:{intent.service_id}:{index}"
        )
        operation, created = outbound_journal.prepare(
            idempotency_key=idempotency_key,
            buyer_id=state["agent_id"],
            seller_id=intent.seller_id,
            service_id=intent.service_id,
            amount=intent.price,
        )
        if created:
            phase = "execute_purchase"
        elif operation.status is OperationStatus.PREPARED:
            # A PREPARED record discovered during replay may have been submitted just
            # before the process died, so recovery must reconcile before another send.
            phase = "reconcile_purchase"
        elif operation.status in {
            OperationStatus.SUBMITTED,
            OperationStatus.UNKNOWN,
        }:
            phase = "reconcile_purchase"
        else:
            phase = "record_purchase"
        return {
            "phase": phase,
            "pending_purchase_key": idempotency_key,
            "pending_service_id": intent.service_id,
        }

    def after_purchase_preparation(
        state: ArenaGraphState,
    ) -> Literal["execute_purchase", "reconcile_purchase", "record_purchase", "audit"]:
        return state["phase"]  # type: ignore[return-value]

    async def execute_purchase(state: ArenaGraphState) -> ArenaGraphState:
        index = state["purchase_index"]
        intent = state["purchase_plan"][index]
        listings = {item.service_id: item for item in state["listings"]}
        key = state["pending_purchase_key"]
        operation = outbound_journal.get(key)
        if operation is None:
            raise RuntimeError("prepared outbound operation disappeared")
        if operation.status is not OperationStatus.PREPARED:
            return {"phase": "reconcile_purchase"}

        # This durable transition is committed before the external side effect. If the
        # process dies after payment but before the graph checkpoint, recovery sees
        # SUBMITTED and reconciles instead of blindly paying again.
        outbound_journal.transition(key, OperationStatus.SUBMITTED)
        try:
            receipt = await client.buy(
                listings[intent.service_id], idempotency_key=key
            )
        except (TimeoutError, ConnectionError) as exc:
            outbound_journal.transition(
                key,
                OperationStatus.UNKNOWN,
                reason=f"ambiguous transport failure: {type(exc).__name__}",
            )
            return {"phase": "reconcile_purchase"}
        except Exception as exc:
            outbound_journal.transition(
                key,
                OperationStatus.FAILED,
                reason=type(exc).__name__,
            )
            return {"phase": "record_purchase"}

        violation = receipt_violation(receipt, intent)
        if violation is not None:
            outbound_journal.transition(
                key,
                OperationStatus.DISPUTED,
                receipt=receipt,
                reason=violation,
            )
        else:
            outbound_journal.transition(
                key,
                OperationStatus.SETTLED,
                receipt=receipt,
            )
        return {"phase": "record_purchase"}

    def after_purchase_execution(
        state: ArenaGraphState,
    ) -> Literal["reconcile_purchase", "record_purchase"]:
        return state["phase"]  # type: ignore[return-value]

    async def reconcile_purchase(state: ArenaGraphState) -> ArenaGraphState:
        index = state["purchase_index"]
        intent = state["purchase_plan"][index]
        listings = {item.service_id: item for item in state["listings"]}
        key = state["pending_purchase_key"]
        try:
            evidence = await client.reconcile_trade(
                listings[intent.service_id], idempotency_key=key
            )
        except Exception as exc:
            outbound_journal.transition(
                key,
                OperationStatus.UNKNOWN,
                reason=f"reconciliation unavailable: {type(exc).__name__}",
            )
            return {"phase": "record_purchase"}

        if evidence.platform_receipt is not None:
            violation = receipt_violation(evidence.platform_receipt, intent)
            if violation is None:
                outbound_journal.transition(
                    key,
                    OperationStatus.SETTLED,
                    receipt=evidence.platform_receipt,
                    evidence=evidence,
                )
            else:
                outbound_journal.transition(
                    key,
                    OperationStatus.DISPUTED,
                    receipt=evidence.platform_receipt,
                    evidence=evidence,
                    reason=violation,
                )
        elif evidence.buyer_entry is not None and evidence.seller_entry is not None:
            if bilateral_entries_match(
                evidence, intent, key, state["agent_id"]
            ):
                outbound_journal.transition(
                    key,
                    OperationStatus.BILATERALLY_CONFIRMED,
                    evidence=evidence,
                    reason="matching buyer debit and seller credit entries",
                )
            else:
                outbound_journal.transition(
                    key,
                    OperationStatus.DISPUTED,
                    evidence=evidence,
                    reason="buyer and seller ledger entries disagree",
                )
        else:
            outbound_journal.transition(
                key,
                OperationStatus.UNKNOWN,
                evidence=evidence,
                reason="no authoritative receipt or matching bilateral entries",
            )
        return {"phase": "record_purchase"}

    async def record_purchase(state: ArenaGraphState) -> ArenaGraphState:
        progress = state["progress"].model_copy(deep=True)
        index = state["purchase_index"]
        intent = state["purchase_plan"][index]
        key = state["pending_purchase_key"]
        operation = outbound_journal.get(key)
        if operation is None:
            raise RuntimeError("outbound operation disappeared before recording")

        violations: list[str] = []
        if operation.status is OperationStatus.SETTLED and operation.receipt is not None:
            receipt = operation.receipt
            seen_trade_ids = {item.trade_id for item in progress.receipts}
            if receipt.trade_id in seen_trade_ids:
                violations.append(f"Duplicate receipt detected: {receipt.trade_id}")
            else:
                progress.receipts.append(receipt)
                progress.spent_credits += receipt.amount
                progress.purchased_products.add(receipt.seller_id)
        elif operation.status is OperationStatus.BILATERALLY_CONFIRMED:
            violations.append(
                f"Purchase of {intent.service_id} was bilaterally confirmed but "
                "lacks an official Arena settlement receipt"
            )
        elif operation.status is OperationStatus.DISPUTED:
            violations.append(
                f"Purchase of {intent.service_id} reconciliation disputed: "
                f"{operation.reason or 'evidence mismatch'}"
            )
        elif operation.status is OperationStatus.FAILED:
            violations.append(
                f"Purchase of {intent.service_id} failed: "
                f"{operation.reason or 'unknown error'}"
            )
        else:
            violations.append(
                f"Purchase of {intent.service_id} settlement remains unknown; "
                "automatic repayment is blocked"
            )

        next_index = index + 1
        phase = (
            "prepare_purchase"
            if next_index < len(state["purchase_plan"])
            else "audit"
        )
        return {
            "phase": phase,
            "progress": progress,
            "purchase_index": next_index,
            "pending_purchase_key": "",
            "pending_service_id": "",
            "violations": violations,
        }

    def after_purchase_recording(
        state: ArenaGraphState,
    ) -> Literal["prepare_purchase", "audit"]:
        return state["phase"]  # type: ignore[return-value]

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
            model_attempts=state.get("model_attempts", 0),
            model_successes=state.get("model_successes", 0),
            model_fallbacks=state.get("model_fallbacks", 0),
            model_fallback_reasons=state.get("model_fallback_reasons", []),
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
    graph.add_node("prepare_purchase", prepare_purchase)
    graph.add_node("execute_purchase", execute_purchase)
    graph.add_node("reconcile_purchase", reconcile_purchase)
    graph.add_node("record_purchase", record_purchase)
    graph.add_node("audit", audit)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "discover")
    graph.add_conditional_edges("discover", after_discovery)
    graph.add_edge("evaluate_services", "publish_required_feedback")
    graph.add_edge("publish_required_feedback", "rank")
    graph.add_conditional_edges("rank", after_ranking)
    graph.add_conditional_edges("plan_market", after_market_plan)
    graph.add_conditional_edges("prepare_purchase", after_purchase_preparation)
    graph.add_conditional_edges("execute_purchase", after_purchase_execution)
    graph.add_edge("reconcile_purchase", "record_purchase")
    graph.add_conditional_edges("record_purchase", after_purchase_recording)
    graph.add_edge("audit", END)
    return graph.compile(checkpointer=checkpointer)
