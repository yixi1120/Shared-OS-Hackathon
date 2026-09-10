from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class LedgerDirection(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class InteractionStage(str, Enum):
    TASK_CREATED = "task_created"
    REQUEST_RECEIVED = "request_received"
    QUOTE_DECLARED = "quote_declared"
    TASK_STARTED = "task_started"
    ARTIFACT_DELIVERED = "artifact_delivered"
    BUYER_ACKNOWLEDGED = "buyer_acknowledged"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    DISPUTED = "disputed"


class EvidenceProvenance(str, Enum):
    PLATFORM = "platform"
    OBSERVED = "observed"
    BILATERAL = "bilateral"
    SELF_REPORTED = "self_reported"


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
    status: OrderStatus = OrderStatus.ACCEPTED
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AccountLedgerEntry(BaseModel):
    """One independently observable side of a transfer."""

    entry_id: str
    transfer_id: str
    idempotency_key: str
    account_id: str
    counterparty_id: str
    direction: LedgerDirection
    amount: int = Field(ge=1, le=100)
    status: str = "settled"
    balance_after: int | None = Field(default=None, ge=0)
    ledger_version: str | None = None


class TradeReconciliation(BaseModel):
    """Independent evidence returned after an ambiguous purchase outcome."""

    platform_receipt: TradeReceipt | None = None
    buyer_entry: AccountLedgerEntry | None = None
    seller_entry: AccountLedgerEntry | None = None


class InteractionEventSubmission(BaseModel):
    """Untrusted event payload accepted from an external caller."""

    # Unknown fields are discarded before persistence. In particular, an external
    # caller cannot inject the trusted-only `provenance` field.
    model_config = ConfigDict(extra="ignore")

    task_id: str = Field(min_length=1, max_length=256)
    subject_agent_id: str = Field(min_length=1, max_length=256)
    stage: InteractionStage
    occurred_at: datetime
    schema_valid: bool = True
    evidence_id: str | None = Field(default=None, max_length=256)
    request_hash: str | None = Field(default=None, max_length=256)
    artifact_hash: str | None = Field(default=None, max_length=256)


class InteractionTraceInput(BaseModel):
    """Bounded, content-minimized input accepted by both trace services."""

    model_config = ConfigDict(extra="ignore")
    events: list[InteractionEventSubmission] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def one_task_and_subject_per_report(self) -> "InteractionTraceInput":
        if len({event.task_id for event in self.events}) != 1:
            raise ValueError("all events must belong to one task_id")
        if len({event.subject_agent_id for event in self.events}) != 1:
            raise ValueError("all events must describe one subject_agent_id")
        return self


class InteractionEvent(InteractionEventSubmission):
    """Event enriched with provenance assigned by a trusted ingestion boundary."""

    provenance: EvidenceProvenance


class InteractionTraceReport(BaseModel):
    task_id: str
    subject_agent_id: str
    completed: bool
    delivered: bool
    ordered: bool
    schema_valid_rate: float = Field(ge=0, le=1)
    disputed: bool
    end_to_end_latency_ms: int | None = Field(default=None, ge=0)
    execution_score: float = Field(ge=0, le=100)
    evidence_weight: float = Field(ge=0, le=1)
    confidence: str
    reputation_eligible: bool
    credit_settlement: str = "not_evaluated"
    provenance_counts: dict[str, int] = Field(default_factory=dict)
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
