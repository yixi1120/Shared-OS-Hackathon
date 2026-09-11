from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Protocol

from .models import TradeReceipt, TradeReconciliation


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperationStatus(str, Enum):
    PREPARED = "prepared"
    SUBMITTED = "submitted"
    UNKNOWN = "unknown"
    SETTLED = "settled"
    BILATERALLY_CONFIRMED = "bilaterally_confirmed"
    FAILED = "failed"
    DISPUTED = "disputed"


@dataclass(frozen=True, slots=True)
class OutboundOperation:
    idempotency_key: str
    operation_type: str
    buyer_id: str
    seller_id: str
    service_id: str
    amount: int
    status: OperationStatus
    receipt: TradeReceipt | None = None
    evidence: TradeReconciliation | None = None
    reason: str | None = None
    created_at: str = ""
    updated_at: str = ""


class OperationJournal(Protocol):
    def prepare(
        self,
        *,
        idempotency_key: str,
        buyer_id: str,
        seller_id: str,
        service_id: str,
        amount: int,
    ) -> tuple[OutboundOperation, bool]: ...

    def get(self, idempotency_key: str) -> OutboundOperation | None: ...

    def transition(
        self,
        idempotency_key: str,
        status: OperationStatus,
        *,
        receipt: TradeReceipt | None = None,
        evidence: TradeReconciliation | None = None,
        reason: str | None = None,
    ) -> OutboundOperation: ...


def _validate_same_intent(
    operation: OutboundOperation,
    *,
    buyer_id: str,
    seller_id: str,
    service_id: str,
    amount: int,
) -> None:
    expected = (buyer_id, seller_id, service_id, amount)
    actual = (
        operation.buyer_id,
        operation.seller_id,
        operation.service_id,
        operation.amount,
    )
    if actual != expected:
        raise ValueError("idempotency key was reused for a different purchase intent")


class InMemoryOperationJournal:
    def __init__(self) -> None:
        self._operations: dict[str, OutboundOperation] = {}
        self._lock = Lock()

    def prepare(
        self,
        *,
        idempotency_key: str,
        buyer_id: str,
        seller_id: str,
        service_id: str,
        amount: int,
    ) -> tuple[OutboundOperation, bool]:
        with self._lock:
            existing = self._operations.get(idempotency_key)
            if existing is not None:
                _validate_same_intent(
                    existing,
                    buyer_id=buyer_id,
                    seller_id=seller_id,
                    service_id=service_id,
                    amount=amount,
                )
                return existing, False
            now = utc_timestamp()
            operation = OutboundOperation(
                idempotency_key=idempotency_key,
                operation_type="purchase",
                buyer_id=buyer_id,
                seller_id=seller_id,
                service_id=service_id,
                amount=amount,
                status=OperationStatus.PREPARED,
                created_at=now,
                updated_at=now,
            )
            self._operations[idempotency_key] = operation
            return operation, True

    def get(self, idempotency_key: str) -> OutboundOperation | None:
        with self._lock:
            return self._operations.get(idempotency_key)

    def transition(
        self,
        idempotency_key: str,
        status: OperationStatus,
        *,
        receipt: TradeReceipt | None = None,
        evidence: TradeReconciliation | None = None,
        reason: str | None = None,
    ) -> OutboundOperation:
        with self._lock:
            current = self._operations.get(idempotency_key)
            if current is None:
                raise KeyError(f"unknown outbound operation: {idempotency_key}")
            if current.status is OperationStatus.SETTLED and status is not OperationStatus.SETTLED:
                return current
            updated = replace(
                current,
                status=status,
                receipt=receipt if receipt is not None else current.receipt,
                evidence=evidence if evidence is not None else current.evidence,
                reason=reason,
                updated_at=utc_timestamp(),
            )
            self._operations[idempotency_key] = updated
            return updated


class SqliteOperationJournal:
    """Durable write-ahead journal for outbound side effects."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS outbound_operations (
                    idempotency_key TEXT PRIMARY KEY,
                    operation_type TEXT NOT NULL,
                    buyer_id TEXT NOT NULL,
                    seller_id TEXT NOT NULL,
                    service_id TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    receipt_json TEXT,
                    evidence_json TEXT,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def prepare(
        self,
        *,
        idempotency_key: str,
        buyer_id: str,
        seller_id: str,
        service_id: str,
        amount: int,
    ) -> tuple[OutboundOperation, bool]:
        now = utc_timestamp()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO outbound_operations (
                    idempotency_key, operation_type, buyer_id, seller_id,
                    service_id, amount, status, created_at, updated_at
                ) VALUES (?, 'purchase', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    idempotency_key,
                    buyer_id,
                    seller_id,
                    service_id,
                    amount,
                    OperationStatus.PREPARED.value,
                    now,
                    now,
                ),
            )
            created = cursor.rowcount == 1
            row = connection.execute(
                "SELECT * FROM outbound_operations WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            raise RuntimeError("operation journal insert was not visible")
        operation = self._from_row(row)
        _validate_same_intent(
            operation,
            buyer_id=buyer_id,
            seller_id=seller_id,
            service_id=service_id,
            amount=amount,
        )
        return operation, created

    def get(self, idempotency_key: str) -> OutboundOperation | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM outbound_operations WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def transition(
        self,
        idempotency_key: str,
        status: OperationStatus,
        *,
        receipt: TradeReceipt | None = None,
        evidence: TradeReconciliation | None = None,
        reason: str | None = None,
    ) -> OutboundOperation:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM outbound_operations WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown outbound operation: {idempotency_key}")
            current = self._from_row(row)
            if current.status is OperationStatus.SETTLED and status is not OperationStatus.SETTLED:
                return current
            receipt_json = (
                receipt.model_dump_json() if receipt is not None else row["receipt_json"]
            )
            evidence_json = (
                evidence.model_dump_json()
                if evidence is not None
                else row["evidence_json"]
            )
            connection.execute(
                """
                UPDATE outbound_operations
                SET status = ?, receipt_json = ?, evidence_json = ?, reason = ?,
                    updated_at = ?
                WHERE idempotency_key = ?
                """,
                (
                    status.value,
                    receipt_json,
                    evidence_json,
                    reason,
                    utc_timestamp(),
                    idempotency_key,
                ),
            )
            updated_row = connection.execute(
                "SELECT * FROM outbound_operations WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if updated_row is None:
            raise RuntimeError("operation journal update was not visible")
        return self._from_row(updated_row)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> OutboundOperation:
        receipt_payload = row["receipt_json"]
        evidence_payload = row["evidence_json"]
        return OutboundOperation(
            idempotency_key=row["idempotency_key"],
            operation_type=row["operation_type"],
            buyer_id=row["buyer_id"],
            seller_id=row["seller_id"],
            service_id=row["service_id"],
            amount=row["amount"],
            status=OperationStatus(row["status"]),
            receipt=(
                TradeReceipt.model_validate(json.loads(receipt_payload))
                if receipt_payload
                else None
            ),
            evidence=(
                TradeReconciliation.model_validate(json.loads(evidence_payload))
                if evidence_payload
                else None
            ),
            reason=row["reason"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
