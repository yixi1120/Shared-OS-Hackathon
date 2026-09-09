from sharedos_commerce_agent.ledger import Ledger
from sharedos_commerce_agent.models import OrderStatus, TradeReceipt
import pytest


def test_ledger_is_idempotent() -> None:
    ledger = Ledger(":memory:")
    first = ledger.record(
        TradeReceipt(
            buyer_id="buyer-a",
            seller_id="seller-a",
            service_id="service-a",
            amount=10,
        ),
        idempotency_key="same-request",
    )
    second = ledger.record(
        TradeReceipt(
            buyer_id="buyer-a",
            seller_id="seller-a",
            service_id="service-a",
            amount=10,
        ),
        idempotency_key="same-request",
    )

    assert first.trade_id == second.trade_id
    assert len(ledger.list()) == 1
    updated = ledger.update_status(first.trade_id, OrderStatus.DELIVERED)
    assert updated.status is OrderStatus.DELIVERED


def test_idempotency_key_cannot_be_reused_for_a_different_order() -> None:
    ledger = Ledger(":memory:")
    ledger.record(
        TradeReceipt(
            buyer_id="buyer-a",
            seller_id="seller-a",
            service_id="service-a",
            amount=10,
        ),
        idempotency_key="same-request",
    )

    with pytest.raises(ValueError, match="different order"):
        ledger.record(
            TradeReceipt(
                buyer_id="buyer-b",
                seller_id="seller-a",
                service_id="service-a",
                amount=10,
            ),
            idempotency_key="same-request",
        )
