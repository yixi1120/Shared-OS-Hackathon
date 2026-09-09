from datetime import datetime, timedelta, timezone

from sharedos_commerce_agent.models import (
    EvidenceProvenance,
    InteractionEvent,
    InteractionStage,
)
from sharedos_commerce_agent.telemetry import evaluate_interaction_trace


def _event(
    stage: InteractionStage,
    offset_seconds: int,
    *,
    provenance: EvidenceProvenance = EvidenceProvenance.OBSERVED,
    **changes,
) -> InteractionEvent:
    data = {
        "task_id": "task-one",
        "subject_agent_id": "seller-one",
        "stage": stage,
        "occurred_at": datetime(2026, 9, 10, tzinfo=timezone.utc)
        + timedelta(seconds=offset_seconds),
        "schema_valid": True,
        "provenance": provenance,
    }
    data.update(changes)
    return InteractionEvent(**data)


def _successful_trace(
    provenance: EvidenceProvenance = EvidenceProvenance.OBSERVED,
) -> list[InteractionEvent]:
    return [
        _event(
            InteractionStage.REQUEST_RECEIVED,
            0,
            provenance=provenance,
            evidence_id="request-1",
            request_hash="sha256:request",
        ),
        _event(InteractionStage.TASK_STARTED, 1, provenance=provenance),
        _event(
            InteractionStage.ARTIFACT_DELIVERED,
            3,
            provenance=provenance,
            evidence_id="artifact-1",
            artifact_hash="sha256:artifact",
        ),
        _event(InteractionStage.TASK_COMPLETED, 4, provenance=provenance),
    ]


def test_observed_trace_is_reputation_eligible() -> None:
    report = evaluate_interaction_trace(_successful_trace())

    assert report.completed is True
    assert report.delivered is True
    assert report.ordered is True
    assert report.end_to_end_latency_ms == 4000
    assert report.evidence_weight == 0.9
    assert report.reputation_eligible is True
    assert report.credit_settlement == "not_evaluated"
    assert report.risk_flags == []


def test_perfect_self_report_cannot_become_reputation_evidence() -> None:
    report = evaluate_interaction_trace(
        _successful_trace(EvidenceProvenance.SELF_REPORTED)
    )

    assert report.execution_score > 90
    assert report.evidence_weight == 0.15
    assert report.reputation_eligible is False
    assert report.confidence == "self-reported-single-interaction"
    assert "evidence_not_reputation_eligible" in report.risk_flags


def test_failed_or_malformed_trace_exposes_objective_risk_flags() -> None:
    report = evaluate_interaction_trace(
        [
            _event(InteractionStage.TASK_STARTED, 1),
            _event(
                InteractionStage.REQUEST_RECEIVED,
                2,
                schema_valid=False,
            ),
            _event(InteractionStage.TASK_FAILED, 3),
        ]
    )

    assert report.completed is False
    assert report.reputation_eligible is True
    assert set(report.risk_flags) == {
        "artifact_not_delivered",
        "invalid_stage_order",
        "schema_validation_failure",
    }
