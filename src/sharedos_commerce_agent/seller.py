from __future__ import annotations

import json
from importlib.resources import files
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
from .risk_rules import interpret_risks
from .strategy import DEFAULT_PRICING_POLICY, PricingPolicy
from .telemetry import evaluate_interaction_trace


SELLER_ID = "agent-commerce-network"


def _load_catalog() -> list[ServiceListing]:
    resource = files("sharedos_commerce_agent.resources").joinpath(
        "product_catalog_v1.json"
    )
    payload = json.loads(resource.read_text(encoding="utf-8"))
    return [
        ServiceListing(
            **item,
            seller_id=SELLER_ID,
            price=DEFAULT_PRICING_POLICY.base_price,
            pricing_policy_version=DEFAULT_PRICING_POLICY.version,
            floor_price=DEFAULT_PRICING_POLICY.floor_price,
        )
        for item in payload["services"]
    ]


CATALOG = _load_catalog()


def interaction_contract() -> dict[str, Any]:
    resource = files("sharedos_commerce_agent.resources").joinpath(
        "interaction_contract_v1.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


class SellerService:
    def __init__(self, ledger: Ledger, pricing: PricingPolicy | None = None) -> None:
        self.ledger = ledger
        self.pricing = pricing or DEFAULT_PRICING_POLICY

    def catalog(self) -> list[ServiceListing]:
        return [
            item.model_copy(
                update={
                    "price": self.pricing.base_price,
                    "pricing_policy_version": self.pricing.version,
                    "floor_price": self.pricing.floor_price,
                }
            )
            for item in CATALOG
        ]

    def quote(self, request: QuoteRequest) -> Quote:
        first_purchase = not self.ledger.has_buyer(request.buyer_id)
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
                "flags": interpret_risks(report.risk_flags),
                "not_meaning": (
                    "It does not verify credit settlement or establish global reputation."
                ),
            }
        self.ledger.update_status(trade_id, OrderStatus.DELIVERED)
        return {"trade_id": trade_id, "status": "delivered", "output": output}
