from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RoundName(str, Enum):
    CRITIQUE = "critique"
    MARKET = "market"
    COMPLETE = "complete"


class ArenaRunMode(str, Enum):
    """Which competition phase this graph invocation is allowed to execute."""

    CRITIQUE = "critique"
    MARKET = "market"
    FULL_DRY_RUN = "full"


class OrderStatus(str, Enum):
    QUOTED = "quoted"
    ACCEPTED = "accepted"
    PAID = "paid"
    DELIVERED = "delivered"
    FAILED = "failed"


class TransactionStage(str, Enum):
    REQUESTED = "requested"
    QUOTED = "quoted"
    ACCEPTED = "accepted"
    PAID = "paid"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    DISPUTED = "disputed"


class ServiceListing(BaseModel):
    service_id: str
    seller_id: str
    name: str
    description: str
    price: int = Field(ge=1, le=100)
    tags: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    reachable: bool = True
    reputation: float = Field(default=0.5, ge=0, le=1)


class ServiceResult(BaseModel):
    service_id: str
    seller_id: str
    success: bool
    output: dict[str, Any]
    latency_ms: int = Field(ge=0)
    receipt_id: str = Field(default_factory=lambda: str(uuid4()))


class QuoteRequest(BaseModel):
    buyer_id: str
    service_id: str
    budget: int = Field(ge=0, le=100)
    complexity: float = Field(default=1.0, ge=0.5, le=3.0)
    urgency: float = Field(default=1.0, ge=0.5, le=2.0)
    buyer_reputation: float = Field(default=0.5, ge=0, le=1)
    requirements: dict[str, Any] = Field(default_factory=dict)


class Quote(BaseModel):
    quote_id: str = Field(default_factory=lambda: str(uuid4()))
    buyer_id: str
    service_id: str
    ask_price: int = Field(ge=1, le=100)
    reservation_price: int = Field(ge=1, le=100)
    pitch: str
    expires_at: datetime

    @model_validator(mode="after")
    def floor_does_not_exceed_ask(self) -> "Quote":
        if self.reservation_price > self.ask_price:
            raise ValueError("reservation_price cannot exceed ask_price")
        return self


class NegotiationDecision(BaseModel):
    accepted: bool
    final_price: int | None = Field(default=None, ge=1, le=100)
    counter_price: int | None = Field(default=None, ge=1, le=100)
    message: str


class Critique(BaseModel):
    product_id: str
    seller_id: str
    tested_service_id: str
    evidence: str
    disagreement: str
    suggestion: str

    @model_validator(mode="after")
    def disagreement_is_specific(self) -> "Critique":
        if len(self.evidence.strip()) < 12 or len(self.disagreement.strip()) < 20:
            raise ValueError("critique must contain concrete evidence and disagreement")
        return self


class RankingEntry(BaseModel):
    product_id: str
    score: float = Field(ge=0, le=100)
    rationale: str


class PurchaseIntent(BaseModel):
    product_id: str
    service_id: str
    seller_id: str
    price: int = Field(ge=1, le=100)
    expected_value: float = Field(ge=0)


class TradeReceipt(BaseModel):
    trade_id: str = Field(default_factory=lambda: str(uuid4()))
    buyer_id: str
    seller_id: str
    service_id: str
    amount: int = Field(ge=1, le=100)
    status: OrderStatus = OrderStatus.PAID
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransactionEvent(BaseModel):
    """One consented, machine-observable event from a routed transaction."""

    transaction_id: str
    subject_agent_id: str
    stage: TransactionStage
    occurred_at: datetime
    amount: int | None = Field(default=None, ge=1, le=100)
    latency_ms: int | None = Field(default=None, ge=0)
    schema_valid: bool = True
    evidence_id: str | None = None


class TransactionTraceReport(BaseModel):
    transaction_id: str
    subject_agent_id: str
    completed: bool
    ordered: bool
    schema_valid_rate: float = Field(ge=0, le=1)
    price_consistent: bool
    disputed: bool
    end_to_end_latency_ms: int | None = Field(default=None, ge=0)
    reliability_score: float = Field(ge=0, le=100)
    confidence: str
    evidence_ids: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class ArenaProgress(BaseModel):
    agent_id: str
    round: RoundName = RoundName.CRITIQUE
    tried_products: set[str] = Field(default_factory=set)
    critiques: list[Critique] = Field(default_factory=list)
    ranking_submitted: bool = False
    spent_credits: int = 0
    purchased_products: set[str] = Field(default_factory=set)
    receipts: list[TradeReceipt] = Field(default_factory=list)

    @property
    def critique_compliant(self) -> bool:
        critiqued = {item.product_id for item in self.critiques}
        return (
            len(self.tried_products) >= 3
            and self.tried_products.issubset(critiqued)
            and self.ranking_submitted
        )

    @property
    def market_compliant(self) -> bool:
        return self.spent_credits >= 80 and len(self.purchased_products) >= 3


class ArenaReport(BaseModel):
    progress: ArenaProgress
    rankings: list[RankingEntry]
    violations: list[str]

    @property
    def valid(self) -> bool:
        return not self.violations
