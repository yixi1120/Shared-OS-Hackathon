"""Agent-facing explanations and contracts; no pricing or scoring decisions."""
from __future__ import annotations

from dataclasses import asdict
from importlib.resources import files
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import TransactionEvent, TransactionTraceReport


class SubmittedEvent(TransactionEvent):
    """Preserve source claims without confusing them with verified evidence."""

    model_config = ConfigDict(extra="forbid")
    provenance: Literal["platform", "bilateral", "self_reported"] = "self_reported"

    @field_validator("occurred_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class TransactionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[SubmittedEvent] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def one_transaction(self):
        if len({(e.transaction_id, e.subject_agent_id) for e in self.events}) != 1:
            raise ValueError("all events must belong to one transaction and subject")
        evidence = [e.evidence_id for e in self.events if e.evidence_id]
        if len(evidence) != len(set(evidence)):
            raise ValueError("duplicate evidence_id within request")
        return self


def templates() -> dict[str, Any]:
    return json.loads(files(__package__).joinpath("sales_assets/templates.json").read_text(encoding="utf-8"))


def introduction() -> str:
    return templates()["intro_under_20_seconds"]


def answer(topic: str, goal: str | None = None) -> dict[str, Any]:
    content = templates()
    if goal in content["pitches"]:
        text = content["pitches"][goal]
    else:
        text = content["faq"].get(topic, content["faq"]["why_node"])["answer"]
    return {"text": text, "side_effects": False, "scope": "sales_explanation"}


def catalog_for_agents(seller) -> list[dict[str, Any]]:
    result = []
    for item in seller.catalog():
        entry = item.model_dump(mode="json")
        schema = TransactionTraceReport.model_json_schema()
        if item.service_id == "transaction-risk-report":
            schema["properties"]["interpretation"] = {
                "type": "object",
                "properties": {"meaning": {"type": "string"}, "not_meaning": {"type": "string"}},
                "required": ["meaning", "not_meaning"],
            }
            schema["required"].append("interpretation")
        entry.update({
            "description": (
                "Inspect one supplied transaction's completion, stage order, price, "
                "paid-to-delivered latency, schema assertions and disputes. Returns "
                "the runtime's deterministic report and evidence references. "
                "Source claims are retained but are not authenticated by this local runtime."
                + (" Adds a fixed interpretation explaining scope; no extra risk model." if item.service_id == "transaction-risk-report" else "")
            ),
            "input_schema": TransactionInput.model_json_schema(),
            "report_schema": schema,
            "delivery_envelope": {"trade_id": "string", "status": "delivered", "output": "report_schema", "evidence_provenance": "list of source claims; verified is always false in local runtime"},
            "purchase_flow": [
                {"method": "POST", "path": "/v1/quotes", "required": ["buyer_id", "service_id", "budget"]},
                {"method": "POST", "path": "/v1/quotes/{quote_id}/negotiate", "optional": True, "required": ["buyer_offer"]},
                {"method": "POST", "path": "/v1/orders", "required": ["quote_id", "buyer_id", "service_id", "amount", "idempotency_key", "input"], "note": "Use the actual quoted/agreed amount; input follows input_schema."},
                {"method": "POST", "path": "/v1/orders/{trade_id}/deliver"},
            ],
            "pricing": {
                "catalog_price_is_binding": False,
                "binding_price_source": "/v1/quotes ask_price or accepted negotiated price",
                "runtime_policy": asdict(seller.pricing),
                "note": "The current shared runtime base price differs from the 6/8 catalog reference prices. Do not pay the reference price without obtaining a quote. Team pricing reconciliation is pending.",
                "bundles_enabled": False,
            },
            "data_not_accepted": ["raw prompts", "full deliverables", "credentials", "extra payload fields"],
            "limitations": [
                "Local runtime demonstration; no live SharedNet address or Cloud audit has been configured.",
                "A single transaction is not global reputation.",
                "Provenance is a source claim, not signature verification; existing scoring does not weight provenance.",
                "300 seconds is the Arena requirement, not a measured production SLA.",
                "The local ledger status paid does not prove an Arena credit transfer.",
                "Listing reputation values are repository placeholders, not verified reputation measurements.",
            ],
        })
        result.append(entry)
    return result
