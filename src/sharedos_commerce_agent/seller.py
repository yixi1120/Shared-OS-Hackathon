from __future__ import annotations

from typing import Any

from .ledger import Ledger
from pydantic import TypeAdapter

from .models import (
    OrderStatus,
    Quote,
    QuoteRequest,
    ServiceListing,
    TradeReceipt,
    TransactionEvent,
)
from .strategy import PricingPolicy
from .telemetry import evaluate_transaction_trace


SELLER_ID = "agent-commerce-network"


CATALOG = [
    ServiceListing(
        service_id="verified-transaction-trace",
        seller_id=SELLER_ID,
        name="Verified Transaction Trace",
        description=(
            "Validates a routed agent-to-agent transaction from structured lifecycle events "
            "and returns deterministic reliability evidence and risk flags."
        ),
        price=6,
        tags=["transaction", "telemetry", "reputation", "verification"],
        evidence=["stage order", "price consistency", "latency", "schema validity"],
        reputation=0.8,
    ),
    ServiceListing(
        service_id="transaction-risk-report",
        seller_id=SELLER_ID,
        name="Transaction Risk Report",
        description=(
            "Explains the objective risk flags in a verified transaction trace without "
            "using subjective ratings in the reliability score."
        ),
        price=8,
        tags=["transaction", "risk", "evidence"],
        evidence=["machine-readable flags", "score breakdown", "sample-size disclosure"],
        reputation=0.78,
    ),
]


class SellerService:
    def __init__(self, ledger: Ledger, pricing: PricingPolicy | None = None) -> None:
        self.ledger = ledger
        self.pricing = pricing or PricingPolicy()

    def catalog(self) -> list[ServiceListing]:
        return CATALOG

    def quote(self, request: QuoteRequest) -> Quote:
        first_purchase = not any(
            receipt.buyer_id == request.buyer_id for receipt in self.ledger.list()
        )
        return self.pricing.quote(request, first_purchase=first_purchase)

    def settle(
        self,
        *,
        buyer_id: str,
        service_id: str,
        amount: int,
        idempotency_key: str,
        input_payload: dict[str, Any],
    ) -> TradeReceipt:
        if service_id not in {item.service_id for item in CATALOG}:
            raise KeyError(f"Unknown service: {service_id}")
        receipt = TradeReceipt(
            buyer_id=buyer_id,
            seller_id=SELLER_ID,
            service_id=service_id,
            amount=amount,
            status=OrderStatus.PAID,
            metadata={"input": input_payload},
        )
        return self.ledger.record(receipt, idempotency_key=idempotency_key)

    def deliver(self, trade_id: str) -> dict[str, Any]:
        receipt = self.ledger.get(trade_id)
        if not receipt:
            raise KeyError(f"Unknown trade: {trade_id}")
        payload = receipt.metadata.get("input", {})
        events = TypeAdapter(list[TransactionEvent]).validate_python(payload.get("events", []))
        report = evaluate_transaction_trace(events)
        output = report.model_dump(mode="json")
        if receipt.service_id == "transaction-risk-report":
            output["interpretation"] = {
                "meaning": "This score describes the supplied transaction trace only.",
                "not_meaning": "It is not a subjective review or a global reputation score.",
            }
        self.ledger.update_status(trade_id, OrderStatus.DELIVERED)
        return {"trade_id": trade_id, "status": "delivered", "output": output}
