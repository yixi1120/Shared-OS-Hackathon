from __future__ import annotations

from typing import Any

from .ledger import Ledger
from pydantic import TypeAdapter

from .models import (
    EvidenceProvenance,
    InteractionEvent,
    InteractionEventSubmission,
    OrderStatus,
    Quote,
    QuoteRequest,
    ServiceListing,
    TradeReceipt,
)
from .strategy import PricingPolicy
from .telemetry import evaluate_interaction_trace


SELLER_ID = "agent-commerce-network"


CATALOG = [
    ServiceListing(
        service_id="a2a-interaction-trace",
        seller_id=SELLER_ID,
        name="A2A Interaction Trace",
        description=(
            "Evaluates structured A2A task lifecycle evidence and reports execution quality, "
            "provenance confidence, and machine-readable risk flags without claiming payment."
        ),
        price=6,
        tags=["a2a", "task", "telemetry", "reputation", "verification"],
        evidence=["task state", "artifact delivery", "latency", "schema validity"],
        reputation=0.8,
    ),
    ServiceListing(
        service_id="a2a-interaction-risk-report",
        seller_id=SELLER_ID,
        name="A2A Interaction Risk Report",
        description=(
            "Explains objective risk flags in an A2A interaction trace and separates "
            "execution quality from evidence confidence."
        ),
        price=8,
        tags=["a2a", "task", "risk", "evidence"],
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

    def accept_order(
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
            status=OrderStatus.ACCEPTED,
            metadata={
                "input": input_payload,
                "declared_amount": amount,
                "credit_settlement": "not_evaluated",
            },
        )
        return self.ledger.record(receipt, idempotency_key=idempotency_key)

    def deliver(self, trade_id: str) -> dict[str, Any]:
        receipt = self.ledger.get(trade_id)
        if not receipt:
            raise KeyError(f"Unknown trade: {trade_id}")
        payload = receipt.metadata.get("input", {})
        submissions = TypeAdapter(list[InteractionEventSubmission]).validate_python(
            payload.get("events", [])
        )
        # A caller cannot promote its own claim to platform-verified evidence.
        events = [
            InteractionEvent(
                **submission.model_dump(),
                provenance=EvidenceProvenance.SELF_REPORTED,
            )
            for submission in submissions
        ]
        report = evaluate_interaction_trace(events)
        output = report.model_dump(mode="json")
        if receipt.service_id == "a2a-interaction-risk-report":
            output["interpretation"] = {
                "meaning": "This score describes the supplied A2A task trace only.",
                "not_meaning": (
                    "It does not verify credit settlement or establish global reputation."
                ),
            }
        self.ledger.update_status(trade_id, OrderStatus.DELIVERED)
        return {"trade_id": trade_id, "status": "delivered", "output": output}
