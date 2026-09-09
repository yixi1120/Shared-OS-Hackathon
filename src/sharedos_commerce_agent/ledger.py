from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator

from .models import OrderStatus, TradeReceipt


class Ledger:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = RLock()
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._memory_connection = (
            sqlite3.connect(":memory:", check_same_thread=False)
            if path == ":memory:"
            else None
        )
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._memory_connection or sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            try:
                yield connection
                connection.commit()
            finally:
                if self._memory_connection is None:
                    connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    buyer_id TEXT NOT NULL,
                    seller_id TEXT NOT NULL,
                    service_id TEXT NOT NULL,
                    amount INTEGER NOT NULL CHECK(amount > 0),
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )

    def record(self, receipt: TradeReceipt, *, idempotency_key: str) -> TradeReceipt:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM trades WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                stored = self._from_row(existing)
                comparable_fields = (
                    "buyer_id",
                    "seller_id",
                    "service_id",
                    "amount",
                    "metadata",
                )
                if any(
                    getattr(stored, field) != getattr(receipt, field)
                    for field in comparable_fields
                ):
                    raise ValueError(
                        "idempotency key was already used for a different order"
                    )
                return stored
            connection.execute(
                """
                INSERT INTO trades (
                    trade_id, idempotency_key, buyer_id, seller_id, service_id,
                    amount, status, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.trade_id,
                    idempotency_key,
                    receipt.buyer_id,
                    receipt.seller_id,
                    receipt.service_id,
                    receipt.amount,
                    receipt.status.value,
                    receipt.created_at.isoformat(),
                    json.dumps(receipt.metadata, sort_keys=True),
                ),
            )
            return receipt

    def update_status(self, trade_id: str, status: OrderStatus) -> TradeReceipt:
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE trades SET status = ? WHERE trade_id = ?",
                (status.value, trade_id),
            ).rowcount
            if not changed:
                raise KeyError(f"Unknown trade: {trade_id}")
            row = connection.execute(
                "SELECT * FROM trades WHERE trade_id = ?", (trade_id,)
            ).fetchone()
            assert row is not None
            return self._from_row(row)

    def get(self, trade_id: str) -> TradeReceipt | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM trades WHERE trade_id = ?", (trade_id,)
            ).fetchone()
            return self._from_row(row) if row else None

    def list(self) -> list[TradeReceipt]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM trades ORDER BY created_at").fetchall()
            return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TradeReceipt:
        return TradeReceipt(
            trade_id=row["trade_id"],
            buyer_id=row["buyer_id"],
            seller_id=row["seller_id"],
            service_id=row["service_id"],
            amount=row["amount"],
            status=OrderStatus(row["status"]),
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"]),
        )
