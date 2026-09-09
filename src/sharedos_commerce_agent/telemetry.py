from __future__ import annotations

from collections import Counter

from .models import (
    EvidenceProvenance,
    InteractionEvent,
    InteractionStage,
    InteractionTraceReport,
)


_STAGE_ORDER = {
    InteractionStage.TASK_CREATED: 0,
    InteractionStage.REQUEST_RECEIVED: 1,
    InteractionStage.QUOTE_DECLARED: 2,
    InteractionStage.TASK_STARTED: 3,
    InteractionStage.ARTIFACT_DELIVERED: 4,
    InteractionStage.BUYER_ACKNOWLEDGED: 5,
    InteractionStage.TASK_COMPLETED: 6,
    InteractionStage.TASK_FAILED: 6,
    InteractionStage.DISPUTED: 7,
}

_PROVENANCE_WEIGHT = {
    EvidenceProvenance.PLATFORM: 1.0,
    EvidenceProvenance.OBSERVED: 0.9,
    EvidenceProvenance.BILATERAL: 0.6,
    EvidenceProvenance.SELF_REPORTED: 0.15,
}

_CONFIDENCE = {
    EvidenceProvenance.PLATFORM: "platform-verified-single-interaction",
    EvidenceProvenance.OBSERVED: "service-observed-single-interaction",
    EvidenceProvenance.BILATERAL: "bilateral-single-interaction",
    EvidenceProvenance.SELF_REPORTED: "self-reported-single-interaction",
}


def evaluate_interaction_trace(
    events: list[InteractionEvent],
) -> InteractionTraceReport:
    """Evaluate observable A2A task evidence without assuming credit settlement."""

    if not events:
        raise ValueError("at least one interaction event is required")
    task_ids = {event.task_id for event in events}
    subjects = {event.subject_agent_id for event in events}
    if len(task_ids) != 1 or len(subjects) != 1:
        raise ValueError("all events must belong to one task and subject agent")

    chronological = sorted(events, key=lambda event: event.occurred_at)
    stage_positions = [_STAGE_ORDER[event.stage] for event in chronological]
    ordered = stage_positions == sorted(stage_positions)
    stages = {event.stage for event in events}
    delivered = InteractionStage.ARTIFACT_DELIVERED in stages
    completed = delivered and InteractionStage.TASK_COMPLETED in stages
    terminal = bool(
        {InteractionStage.TASK_COMPLETED, InteractionStage.TASK_FAILED} & stages
    )
    disputed = InteractionStage.DISPUTED in stages
    schema_valid_rate = sum(event.schema_valid for event in events) / len(events)

    latency_ms: int | None = None
    starts = [
        event.occurred_at
        for event in events
        if event.stage
        in {InteractionStage.REQUEST_RECEIVED, InteractionStage.TASK_STARTED}
    ]
    finishes = [
        event.occurred_at
        for event in events
        if event.stage
        in {InteractionStage.TASK_COMPLETED, InteractionStage.TASK_FAILED}
    ]
    if starts and finishes:
        latency_ms = max(0, int((max(finishes) - min(starts)).total_seconds() * 1000))

    latency_points = 0.0
    if latency_ms is not None:
        latency_points = max(0.0, 10.0 - latency_ms / 2000)
    score = (
        (40.0 if completed else 0.0)
        + (15.0 if delivered else 0.0)
        + (15.0 if ordered else 0.0)
        + 20.0 * schema_valid_rate
        + latency_points
        - (25.0 if disputed else 0.0)
    )

    weakest_provenance = min(
        (event.provenance for event in events),
        key=lambda provenance: _PROVENANCE_WEIGHT[provenance],
    )
    trusted_sources = {EvidenceProvenance.PLATFORM, EvidenceProvenance.OBSERVED}
    reputation_eligible = terminal and all(
        event.provenance in trusted_sources for event in events
    )
    provenance_counts = Counter(event.provenance.value for event in events)

    risk_flags: list[str] = []
    if not terminal:
        risk_flags.append("missing_terminal_task_state")
    if not delivered:
        risk_flags.append("artifact_not_delivered")
    if not ordered:
        risk_flags.append("invalid_stage_order")
    if schema_valid_rate < 1:
        risk_flags.append("schema_validation_failure")
    if disputed:
        risk_flags.append("interaction_disputed")
    if not reputation_eligible:
        risk_flags.append("evidence_not_reputation_eligible")

    return InteractionTraceReport(
        task_id=next(iter(task_ids)),
        subject_agent_id=next(iter(subjects)),
        completed=completed,
        delivered=delivered,
        ordered=ordered,
        schema_valid_rate=round(schema_valid_rate, 4),
        disputed=disputed,
        end_to_end_latency_ms=latency_ms,
        execution_score=round(max(0.0, min(100.0, score)), 2),
        evidence_weight=_PROVENANCE_WEIGHT[weakest_provenance],
        confidence=_CONFIDENCE[weakest_provenance],
        reputation_eligible=reputation_eligible,
        provenance_counts=dict(provenance_counts),
        evidence_ids=[event.evidence_id for event in events if event.evidence_id],
        risk_flags=risk_flags,
    )
