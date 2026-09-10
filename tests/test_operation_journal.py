from __future__ import annotations

import pytest

from sharedos_commerce_agent.models import OrderStatus, TradeReceipt
from sharedos_commerce_agent.operation_journal import (
    OperationStatus,
    SqliteOperationJournal,
)


def test_sqlite_journal_persists_intent_and_receipt_across_instances(tmp_path) -> None:
    path = tmp_path / "operations.sqlite3"
    first = SqliteOperationJournal(path)
    operation, created = first.prepare(
        idempotency_key="run:purchase:service:0",
        buyer_id="buyer",
        seller_id="seller",
        service_id="service",
        amount=20,
    )
    assert created is True
    assert operation.status is OperationStatus.PREPARED

    first.transition(operation.idempotency_key, OperationStatus.SUBMITTED)
    receipt = TradeReceipt(
        trade_id="trade-001",
        buyer_id="buyer",
        seller_id="seller",
        service_id="service",
        amount=20,
        status=OrderStatus.PAID,
    )
    first.transition(
        operation.idempotency_key,
        OperationStatus.SETTLED,
        receipt=receipt,
    )

    reopened = SqliteOperationJournal(path)
    recovered, created = reopened.prepare(
        idempotency_key="run:purchase:service:0",
        buyer_id="buyer",
        seller_id="seller",
        service_id="service",
        amount=20,
    )
    assert created is False
    assert recovered.status is OperationStatus.SETTLED
    assert recovered.receipt == receipt


def test_journal_rejects_idempotency_key_reuse_with_different_intent(tmp_path) -> None:
    journal = SqliteOperationJournal(tmp_path / "operations.sqlite3")
    journal.prepare(
        idempotency_key="same-key",
        buyer_id="buyer",
        seller_id="seller-a",
        service_id="service",
        amount=20,
    )

    with pytest.raises(ValueError, match="different purchase intent"):
        journal.prepare(
            idempotency_key="same-key",
            buyer_id="buyer",
            seller_id="seller-b",
            service_id="service",
            amount=20,
        )


def test_settled_operation_cannot_be_downgraded_to_unknown(tmp_path) -> None:
    journal = SqliteOperationJournal(tmp_path / "operations.sqlite3")
    operation, _ = journal.prepare(
        idempotency_key="settled-key",
        buyer_id="buyer",
        seller_id="seller",
        service_id="service",
        amount=20,
    )
    receipt = TradeReceipt(
        buyer_id="buyer",
        seller_id="seller",
        service_id="service",
        amount=20,
        status=OrderStatus.PAID,
    )
    journal.transition(
        operation.idempotency_key,
        OperationStatus.SETTLED,
        receipt=receipt,
    )

    recovered = journal.transition(
        operation.idempotency_key,
        OperationStatus.UNKNOWN,
        reason="late timeout",
    )
    assert recovered.status is OperationStatus.SETTLED
    assert recovered.receipt == receipt
