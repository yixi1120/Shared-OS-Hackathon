from __future__ import annotations

from .models import TransactionEvent, TransactionStage, TransactionTraceReport


_STAGE_ORDER = {
    TransactionStage.REQUESTED: 0,
    TransactionStage.QUOTED: 1,
    TransactionStage.ACCEPTED: 2,
    TransactionStage.PAID: 3,
    TransactionStage.DELIVERED: 4,
    TransactionStage.ACKNOWLEDGED: 5,
    TransactionStage.DISPUTED: 6,
}


def evaluate_transaction_trace(
    events: list[TransactionEvent],
) -> TransactionTraceReport:
    """Score only observable transaction facts; no LLM or subjective review is used."""

    if not events:
        raise ValueError("at least one transaction event is required")
    transaction_ids = {event.transaction_id for event in events}
    subjects = {event.subject_agent_id for event in events}
    if len(transaction_ids) != 1 or len(subjects) != 1:
        raise ValueError("all events must belong to one transaction and subject agent")

    chronological = sorted(events, key=lambda event: event.occurred_at)
    stage_positions = [_STAGE_ORDER[event.stage] for event in chronological]
    ordered = stage_positions == sorted(stage_positions)
    stages = {event.stage for event in events}
    completed = TransactionStage.PAID in stages and TransactionStage.DELIVERED in stages
    disputed = TransactionStage.DISPUTED in stages
    schema_valid_rate = sum(event.schema_valid for event in events) / len(events)

    quoted_amounts = [event.amount for event in events if event.stage is TransactionStage.QUOTED]
    paid_amounts = [event.amount for event in events if event.stage is TransactionStage.PAID]
    price_consistent = bool(quoted_amounts and paid_amounts) and quoted_amounts[-1] == paid_amounts[-1]

    latency_ms: int | None = None
    if completed:
        paid_at = min(event.occurred_at for event in events if event.stage is TransactionStage.PAID)
        delivered_at = max(
            event.occurred_at for event in events if event.stage is TransactionStage.DELIVERED
        )
        latency_ms = max(0, int((delivered_at - paid_at).total_seconds() * 1000))

    # Transparent deterministic weights. One trace is evidence, not a global reputation.
    latency_points = 0.0
    if latency_ms is not None:
        latency_points = max(0.0, 20.0 - latency_ms / 1000)
    score = (
        (40.0 if completed else 0.0)
        + (15.0 if ordered else 0.0)
        + 20.0 * schema_valid_rate
        + (10.0 if price_consistent else 0.0)
        + latency_points
        - (25.0 if disputed else 0.0)
    )

    risk_flags: list[str] = []
    if not completed:
        risk_flags.append("transaction_not_delivered_after_payment")
    if not ordered:
        risk_flags.append("invalid_stage_order")
    if schema_valid_rate < 1:
        risk_flags.append("schema_validation_failure")
    if not price_consistent:
        risk_flags.append("quoted_and_paid_amount_differ")
    if disputed:
        risk_flags.append("transaction_disputed")

    return TransactionTraceReport(
        transaction_id=next(iter(transaction_ids)),
        subject_agent_id=next(iter(subjects)),
        completed=completed,
        ordered=ordered,
        schema_valid_rate=round(schema_valid_rate, 4),
        price_consistent=price_consistent,
        disputed=disputed,
        end_to_end_latency_ms=latency_ms,
        reliability_score=round(max(0.0, min(100.0, score)), 2),
        confidence="single-transaction",
        evidence_ids=[event.evidence_id for event in events if event.evidence_id],
        risk_flags=risk_flags,
    )
