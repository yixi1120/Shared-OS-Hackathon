from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator

from .models import InteractionEvent, OrderStatus, TradeReceipt


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
            except BaseException:
                connection.rollback()
                raise
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
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_buyer_id ON trades(buyer_id)"
            )
            connection.execute("CREATE TABLE IF NOT EXISTS event_identities (identity_key TEXT PRIMARY KEY, content_hash TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS event_conflicts (id INTEGER PRIMARY KEY, identity_key TEXT NOT NULL, previous_hash TEXT NOT NULL, incoming_hash TEXT NOT NULL, recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            connection.execute("CREATE TABLE IF NOT EXISTS room_inbox (room_id TEXT NOT NULL, message_id TEXT NOT NULL, payload TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(room_id, message_id))")
            connection.execute("CREATE TABLE IF NOT EXISTS room_cursors (room_id TEXT PRIMARY KEY, cursor INTEGER NOT NULL)")

    def receive_messages(self, room_id: str, messages: list[dict], cursor: int) -> None:
        """Save inbox and receive cursor in one transaction before dispatch."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for message in messages:
                message_id = message.get("message_id")
                if not message_id:
                    raise ValueError("room message requires message_id for replay protection")
                payload = json.dumps(message, sort_keys=True)
                old = connection.execute("SELECT payload FROM room_inbox WHERE room_id=? AND message_id=?", (room_id, message_id)).fetchone()
                if old is not None and old[0] != payload:
                    raise ValueError("room_message_identity_conflict")
                connection.execute("INSERT OR IGNORE INTO room_inbox(room_id, message_id, payload) VALUES (?, ?, ?)", (room_id, message_id, payload))
            connection.execute("INSERT INTO room_cursors VALUES (?, ?) ON CONFLICT(room_id) DO UPDATE SET cursor=MAX(cursor, excluded.cursor)", (room_id, cursor))

    def message_cursor(self, room_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT cursor FROM room_cursors WHERE room_id=?", (room_id,)).fetchone()
            return row[0] if row else 0

    def pending_messages(self, room_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM room_inbox WHERE room_id=? AND acknowledged=0 ORDER BY rowid", (room_id,)).fetchall()
            return sorted((json.loads(row[0]) for row in rows), key=lambda m: m["sequence"])

    def acknowledge_message(self, room_id: str, message_id: str) -> None:
        with self._connect() as connection:
            result = connection.execute("UPDATE room_inbox SET acknowledged=1 WHERE room_id=? AND message_id=?", (room_id, message_id))
            if result.rowcount != 1:
                raise KeyError("Cannot acknowledge an unknown room message")

    def validate_events(self, events: list[InteractionEvent]) -> list[InteractionEvent]:
        """Persist identities atomically; conflicting batches register no new events."""
        from .event_identity import EventConflictError, identity

        conflict = None
        unique = []
        batch = {}
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for event in events:
                key, digest = identity(event)
                row = connection.execute("SELECT content_hash FROM event_identities WHERE identity_key = ?", (key,)).fetchone()
                previous = batch.get(key, row[0] if row else None)
                if previous is not None and previous != digest:
                    connection.execute("INSERT INTO event_conflicts (identity_key, previous_hash, incoming_hash) VALUES (?, ?, ?)", (key, previous, digest))
                    conflict = (key, previous, digest)
                    break
                if key not in batch:
                    unique.append(event)
                    batch[key] = digest
            if conflict is None:
                connection.executemany("INSERT OR IGNORE INTO event_identities VALUES (?, ?)", batch.items())
        # Raise after committing the audit entry, so restarts retain the conflict.
        if conflict is not None:
            raise EventConflictError(*conflict)
        return unique

    def event_conflicts(self) -> list[dict]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM event_conflicts ORDER BY id")]

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

    def has_buyer(self, buyer_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM trades WHERE buyer_id = ? LIMIT 1", (buyer_id,)
            ).fetchone()
            return row is not None

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
