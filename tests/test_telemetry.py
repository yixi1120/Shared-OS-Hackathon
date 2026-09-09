from datetime import datetime, timedelta, timezone

from sharedos_commerce_agent.models import TransactionEvent, TransactionStage
from sharedos_commerce_agent.telemetry import evaluate_transaction_trace


def _event(stage: TransactionStage, offset_seconds: int, **changes) -> TransactionEvent:
    data = {
        "transaction_id": "tx-one",
        "subject_agent_id": "seller-one",
        "stage": stage,
        "occurred_at": datetime(2026, 9, 10, tzinfo=timezone.utc)
        + timedelta(seconds=offset_seconds),
        "schema_valid": True,
    }
    data.update(changes)
    return TransactionEvent(**data)


def test_trace_score_uses_observable_transaction_facts() -> None:
    report = evaluate_transaction_trace(
        [
            _event(TransactionStage.QUOTED, 0, amount=10, evidence_id="q1"),
            _event(TransactionStage.PAID, 1, amount=10, evidence_id="p1"),
            _event(TransactionStage.DELIVERED, 3, evidence_id="d1"),
        ]
    )

    assert report.completed is True
    assert report.ordered is True
    assert report.price_consistent is True
    assert report.end_to_end_latency_ms == 2000
    assert report.confidence == "single-transaction"
    assert report.risk_flags == []


def test_trace_flags_non_delivery_price_change_and_schema_failure() -> None:
    report = evaluate_transaction_trace(
        [
            _event(TransactionStage.QUOTED, 0, amount=10),
            _event(TransactionStage.PAID, 1, amount=12, schema_valid=False),
        ]
    )

    assert report.completed is False
    assert report.price_consistent is False
    assert set(report.risk_flags) == {
        "transaction_not_delivered_after_payment",
        "schema_validation_failure",
        "quoted_and_paid_amount_differ",
    }
