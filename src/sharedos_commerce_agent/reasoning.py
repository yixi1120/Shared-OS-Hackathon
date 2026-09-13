from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from .model_client import ModelError
from .models import Critique, ServiceListing, ServiceResult
from .strategy import CritiqueStrategy


class StructuredReasoningModel(Protocol):
    """Narrow model boundary used by the Arena reasoning layer."""

    async def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        json_schema: dict[str, Any],
        model: str | None = None,
    ) -> dict[str, Any]: ...


class CritiqueLanguage(BaseModel):
    disagreement: str = Field(min_length=20, max_length=800)
    suggestion: str = Field(min_length=12, max_length=800)


class ProductAnswerLanguage(BaseModel):
    answer: str = Field(min_length=20, max_length=1200)


@dataclass(frozen=True, slots=True)
class CritiqueComposition:
    critique: Critique
    model_attempted: bool
    model_succeeded: bool
    fallback_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RoomReplyComposition:
    reply: str
    model_attempted: bool
    model_succeeded: bool
    fallback_reason: str | None = None


class EvidenceBoundedCritiqueComposer:
    """Use an LLM for judgement/language while locking objective evidence in code."""

    def __init__(
        self,
        *,
        policy: CritiqueStrategy,
        model: StructuredReasoningModel | None,
    ) -> None:
        self.policy = policy
        self.model = model

    async def create(
        self, listing: ServiceListing, result: ServiceResult
    ) -> CritiqueComposition:
        baseline = self.policy.create(listing, result)
        if self.model is None:
            return CritiqueComposition(
                critique=baseline,
                model_attempted=False,
                model_succeeded=False,
            )

        prompt = json.dumps(
            {
                "listing": {
                    "name": listing.name,
                    "description": listing.description,
                    "price": listing.price,
                    "evidence_claims": listing.evidence,
                    "limitations": listing.limitations,
                },
                "observed_result": {
                    "success": result.success,
                    "latency_ms": result.latency_ms,
                    "output": result.output,
                    "locked_evidence": baseline.evidence,
                },
                "deterministic_fallback": {
                    "disagreement": baseline.disagreement,
                    "suggestion": baseline.suggestion,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        schema = CritiqueLanguage.model_json_schema()
        try:
            generated = await self.model.complete_json(
                system=(
                    "You are the reasoning layer of an autonomous commerce agent. "
                    "Write a concise, specific critique grounded only in the supplied "
                    "listing and observed result. Do not invent tests, payments, "
                    "platform verification, or reputation evidence."
                ),
                prompt=prompt,
                json_schema=schema,
            )
            language = CritiqueLanguage.model_validate(generated)
            critique = Critique(
                product_id=baseline.product_id,
                seller_id=baseline.seller_id,
                tested_service_id=baseline.tested_service_id,
                evidence=baseline.evidence,
                disagreement=language.disagreement,
                suggestion=language.suggestion,
            )
            return CritiqueComposition(
                critique=critique,
                model_attempted=True,
                model_succeeded=True,
            )
        except (ModelError, ValidationError, ValueError, TypeError) as exc:
            return CritiqueComposition(
                critique=baseline,
                model_attempted=True,
                model_succeeded=False,
                fallback_reason=type(exc).__name__,
            )


async def enhance_room_product_answer(
    *,
    model: StructuredReasoningModel | None,
    original_message: str,
    deterministic_reply: str,
) -> RoomReplyComposition:
    """Improve addressed product answers without allowing the model to alter routing."""

    if model is None:
        return RoomReplyComposition(deterministic_reply, False, False)
    try:
        envelope = json.loads(deterministic_reply)
    except json.JSONDecodeError:
        return RoomReplyComposition(deterministic_reply, False, False)
    if not isinstance(envelope, dict) or envelope.get("type") != "product_answer":
        return RoomReplyComposition(deterministic_reply, False, False)

    locked = {
        key: envelope[key]
        for key in (
            "intent",
            "answer",
            "service_base_url",
            "catalog_url",
            "contract_url",
            "credit_settlement",
        )
        if key in envelope
    }
    try:
        generated = await model.complete_json(
            system=(
                "You answer an addressed product question as an autonomous seller "
                "agent. Use only the supplied locked product facts. Be concise and "
                "actionable. Never claim credit settlement, platform verification, "
                "or capabilities not present in those facts."
            ),
            prompt=json.dumps(
                {
                    "question": original_message,
                    "locked_product_facts": locked,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            json_schema=ProductAnswerLanguage.model_json_schema(),
        )
        language = ProductAnswerLanguage.model_validate(generated)
        envelope["answer"] = language.answer
        envelope["reasoning"] = {
            "mode": "llm",
            "grounding": "locked_product_facts",
        }
        return RoomReplyComposition(
            json.dumps(envelope, ensure_ascii=False, separators=(",", ":")),
            True,
            True,
        )
    except (ModelError, ValidationError, ValueError, TypeError) as exc:
        envelope["reasoning"] = {
            "mode": "deterministic_fallback",
            "reason": type(exc).__name__,
        }
        return RoomReplyComposition(
            json.dumps(envelope, ensure_ascii=False, separators=(",", ":")),
            True,
            False,
            type(exc).__name__,
        )
