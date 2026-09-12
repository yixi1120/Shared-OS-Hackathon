from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

import httpx

from .ledger import Ledger
from .models import (
    RankingEntry,
    ServiceListing,
    ServiceResult,
    TradeReceipt,
    TradeReconciliation,
)


class SharedNetProtocolError(RuntimeError):
    """Raised when SharedNet returns a payload that violates its room protocol."""


class SharedNetNotJoinedError(RuntimeError):
    """Raised when a room operation is attempted without a member credential."""


@dataclass(frozen=True, slots=True)
class SharedNetMessage:
    sequence: int
    content: str
    message_id: str | None = None
    sender_instance_id: str | None = None
    sender_agent_id: str | None = None
    created_at: str | None = None


@dataclass(frozen=True, slots=True)
class SharedNetMessagePage:
    items: tuple[SharedNetMessage, ...]
    next_cursor: int | None
    has_more: bool


@dataclass(frozen=True, slots=True)
class SharedNetJoinResult:
    room_id: str
    member_id: str
    member_token: str = field(repr=False)
    history: SharedNetMessagePage = field(
        default_factory=lambda: SharedNetMessagePage((), None, False)
    )


@dataclass(frozen=True, slots=True)
class SharedNetCreditBalance:
    principal_id: str
    balance: int
    granted: int
    sent: int
    received: int


@dataclass(frozen=True, slots=True)
class SharedNetTransfer:
    transfer_id: str
    from_principal_id: str | None
    to_principal_id: str
    amount: int
    memo: str | None
    room_id: str | None
    by_instance_id: str | None
    addressed_to: str
    code: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class SharedNetLedgerPage:
    items: tuple[SharedNetTransfer, ...]
    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True, slots=True)
class SharedNetPaymentResult:
    transfer: SharedNetTransfer
    room_receipt: SharedNetMessage | None
    warning: str | None = None


def _optional_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _parse_cursor(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise SharedNetProtocolError("SharedNet cursor cannot be a boolean")
    try:
        cursor = int(value)
    except (TypeError, ValueError) as exc:
        raise SharedNetProtocolError("SharedNet cursor must be an integer") from exc
    if cursor < 0:
        raise SharedNetProtocolError("SharedNet cursor cannot be negative")
    return cursor


def _non_negative_integer(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SharedNetProtocolError(f"SharedNet {key} must be a non-negative integer")
    return value


def _parse_credit_balance(payload: Any) -> SharedNetCreditBalance:
    if not isinstance(payload, dict):
        raise SharedNetProtocolError("SharedNet credit balance must be a JSON object")
    principal_id = _optional_string(payload, "principal_id")
    if principal_id is None or not re.fullmatch(r"p_[0-9A-Za-z]{10}", principal_id):
        raise SharedNetProtocolError("SharedNet balance is missing its principal_id")
    return SharedNetCreditBalance(
        principal_id=principal_id,
        balance=_non_negative_integer(payload, "balance"),
        granted=_non_negative_integer(payload, "granted"),
        sent=_non_negative_integer(payload, "sent"),
        received=_non_negative_integer(payload, "received"),
    )


def _parse_transfer(payload: Any) -> SharedNetTransfer:
    if not isinstance(payload, dict):
        raise SharedNetProtocolError("SharedNet transfer must be a JSON object")
    transfer_id = _optional_string(payload, "id", "transfer_id")
    to_principal_id = _optional_string(payload, "to_principal_id")
    addressed_to = _optional_string(payload, "addressed_to")
    created_at = _optional_string(payload, "created_at")
    if transfer_id is None or not re.fullmatch(r"txn_[0-9A-Za-z]{10}", transfer_id):
        raise SharedNetProtocolError("SharedNet transfer is missing a valid txn_ id")
    if to_principal_id is None or not re.fullmatch(
        r"p_[0-9A-Za-z]{10}", to_principal_id
    ):
        raise SharedNetProtocolError("SharedNet transfer is missing to_principal_id")
    if addressed_to is None or not re.fullmatch(
        r"(?:p|a|i)_[0-9A-Za-z]{10}", addressed_to
    ):
        raise SharedNetProtocolError("SharedNet transfer is missing addressed_to")
    if created_at is None:
        raise SharedNetProtocolError("SharedNet transfer is missing created_at")
    amount = _non_negative_integer(payload, "amount")
    if amount < 1:
        raise SharedNetProtocolError("SharedNet transfer amount must be at least 1")

    from_principal_id = _optional_string(payload, "from_principal_id")
    if from_principal_id is not None and not re.fullmatch(
        r"p_[0-9A-Za-z]{10}", from_principal_id
    ):
        raise SharedNetProtocolError("SharedNet transfer has invalid from_principal_id")
    room_id = _optional_string(payload, "room_id")
    if room_id is not None and not re.fullmatch(r"rom_[0-9A-Za-z]{10}", room_id):
        raise SharedNetProtocolError("SharedNet transfer has invalid room_id")
    by_instance_id = _optional_string(payload, "by_instance_id")
    if by_instance_id is not None and not re.fullmatch(
        r"i_[0-9A-Za-z]{10}", by_instance_id
    ):
        raise SharedNetProtocolError("SharedNet transfer has invalid by_instance_id")

    return SharedNetTransfer(
        transfer_id=transfer_id,
        from_principal_id=from_principal_id,
        to_principal_id=to_principal_id,
        amount=amount,
        memo=_optional_string(payload, "memo"),
        room_id=room_id,
        by_instance_id=by_instance_id,
        addressed_to=addressed_to,
        code=_optional_string(payload, "code"),
        created_at=created_at,
    )


def _parse_ledger_page(payload: Any) -> SharedNetLedgerPage:
    if not isinstance(payload, dict):
        raise SharedNetProtocolError("SharedNet ledger must be a JSON object")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise SharedNetProtocolError("SharedNet ledger items must be a list")
    next_cursor = payload.get("next_cursor")
    if next_cursor is not None and (
        not isinstance(next_cursor, str)
        or not re.fullmatch(r"txn_[0-9A-Za-z]{10}", next_cursor)
    ):
        raise SharedNetProtocolError("SharedNet ledger next_cursor is invalid")
    return SharedNetLedgerPage(
        items=tuple(_parse_transfer(item) for item in raw_items),
        next_cursor=next_cursor,
        has_more=bool(payload.get("has_more", False)),
    )


def _parse_message(payload: Any) -> SharedNetMessage:
    if not isinstance(payload, dict):
        raise SharedNetProtocolError("SharedNet message must be a JSON object")

    sequence = _parse_cursor(payload.get("sequence"))
    if sequence is None:
        raise SharedNetProtocolError("SharedNet message is missing sequence")
    content = payload.get("content")
    if not isinstance(content, str):
        raise SharedNetProtocolError("SharedNet message is missing string content")

    sender = payload.get("sender")
    sender_payload = sender if isinstance(sender, dict) else {}
    return SharedNetMessage(
        sequence=sequence,
        content=content,
        message_id=_optional_string(payload, "id", "message_id"),
        sender_instance_id=(
            _optional_string(payload, "sender_instance_id")
            or _optional_string(sender_payload, "instance_id", "id")
        ),
        sender_agent_id=(
            _optional_string(payload, "sender_agent_id")
            or _optional_string(sender_payload, "agent_id")
        ),
        created_at=_optional_string(payload, "created_at", "sent_at"),
    )


def _parse_message_page(payload: Any) -> SharedNetMessagePage:
    if not isinstance(payload, dict):
        raise SharedNetProtocolError("SharedNet message page must be a JSON object")
    raw_items = payload.get("items", [])
    if not isinstance(raw_items, list):
        raise SharedNetProtocolError("SharedNet message page items must be a list")
    return SharedNetMessagePage(
        items=tuple(_parse_message(item) for item in raw_items),
        next_cursor=_parse_cursor(payload.get("next_cursor")),
        has_more=bool(payload.get("has_more", False)),
    )


class SharedNetRoomClient:
    """Client for SharedNet room transport and official credit settlement.

    Product discovery and service invocation remain room/application protocols. Credit
    transfer and ledger endpoints are official SharedNet operations and are implemented
    here without treating a room message or local order as proof of settlement.

    The room invite token is used only for ``join``. After joining, all room operations
    use the returned member token. Neither credential is included in object reprs.
    """

    def __init__(
        self,
        *,
        room_id: str,
        invite_token: str | None = None,
        member_token: str | None = None,
        last_sequence: int = 0,
        agent_name: str = "sharedos-commerce-agent",
        runtime_kind: str = "codex",
        base_url: str = "https://www.sharednet.ai",
        timeout_seconds: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not room_id.startswith("rom_"):
            raise ValueError("room_id must be a SharedNet rom_ identifier")
        if invite_token is not None and not invite_token.startswith("rit_"):
            raise ValueError("invite_token must be a SharedNet rit_ credential")
        if member_token is not None and not member_token.startswith("sni_"):
            raise ValueError("member_token must be a SharedNet sni_ credential")
        if last_sequence < 0:
            raise ValueError("last_sequence cannot be negative")
        if not agent_name.strip():
            raise ValueError("agent_name cannot be empty")
        if not runtime_kind.strip() or runtime_kind.lower() != runtime_kind:
            raise ValueError("runtime_kind must be a non-empty lower-case handle")

        self.room_id = room_id
        self._invite_token = invite_token
        self._member_token = member_token
        self._last_sequence = last_sequence
        self.agent_name = agent_name
        self.runtime_kind = runtime_kind
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            transport=transport,
        )

    @property
    def joined(self) -> bool:
        return self._member_token is not None

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    async def __aenter__(self) -> "SharedNetRoomClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self.client.aclose()

    async def join(self) -> SharedNetJoinResult:
        if self._member_token is not None:
            raise SharedNetProtocolError("SharedNet client is already joined")
        if self._invite_token is None:
            raise SharedNetProtocolError("join requires an organizer-issued rit_ token")

        response = await self.client.post(
            f"/api/v1/rooms/{self.room_id}/join",
            headers=self._authorization(self._invite_token),
            json={
                "name": self.agent_name,
                "runtime": {"kind": self.runtime_kind},
            },
        )
        response.raise_for_status()
        payload = self._json_object(response)

        member_token = _optional_string(payload, "member_token", "instance_token")
        if member_token is None or not member_token.startswith("sni_"):
            raise SharedNetProtocolError(
                "SharedNet join response is missing its sni_ member_token"
            )

        member = payload.get("member")
        instance = payload.get("instance")
        member_payload = member if isinstance(member, dict) else {}
        instance_payload = instance if isinstance(instance, dict) else {}
        member_id = (
            _optional_string(payload, "member_id", "instance_id")
            or _optional_string(member_payload, "id", "member_id", "instance_id")
            or _optional_string(instance_payload, "id", "instance_id")
        )
        if member_id is None:
            raise SharedNetProtocolError(
                "SharedNet join response is missing its member identifier"
            )

        history = _parse_message_page(payload.get("history", {}))
        self._member_token = member_token
        self._invite_token = None
        self._advance_cursor(history)
        return SharedNetJoinResult(
            room_id=self.room_id,
            member_id=member_id,
            member_token=member_token,
            history=history,
        )

    async def say(
        self, content: str, *, idempotency_key: str | None = None
    ) -> SharedNetMessage:
        if not content.strip():
            raise ValueError("message content cannot be empty")
        response = await self.client.post(
            f"/api/v1/rooms/{self.room_id}/messages",
            headers=self._member_headers(idempotency_key=idempotency_key),
            json={"content": content},
        )
        response.raise_for_status()
        payload = self._json_object(response)
        raw_message = payload.get("message", payload)
        # Sending must not advance the receive cursor: another member may have spoken
        # between our last read and this post.
        return _parse_message(raw_message)

    async def wait(
        self,
        *,
        after: int | None = None,
        timeout_seconds: int = 25,
    ) -> SharedNetMessagePage:
        if not 0 <= timeout_seconds <= 25:
            raise ValueError("SharedNet wait timeout must be between 0 and 25 seconds")
        cursor = self._last_sequence if after is None else after
        if cursor < 0:
            raise ValueError("after cannot be negative")

        response = await self.client.get(
            f"/api/v1/rooms/{self.room_id}/wait",
            headers=self._member_headers(),
            params={"after": cursor, "timeout": timeout_seconds},
        )
        response.raise_for_status()
        page = _parse_message_page(self._json_object(response))
        self._advance_cursor(page)
        return page

    async def receive_pending(
        self, inbox: Ledger, *, timeout_seconds: int = 25,
    ) -> tuple[SharedNetMessage, ...]:
        """Durable consumer path. Acknowledge only after idempotent handling.

        Raw read/wait remain inspection APIs; use a file-backed inbox for restart
        recovery. Pending messages are retried until explicitly acknowledged.
        """
        pending = inbox.pending_messages(self.room_id)
        if pending:
            return tuple(SharedNetMessage(**m) for m in pending)
        page = await self.wait(after=inbox.message_cursor(self.room_id), timeout_seconds=timeout_seconds)
        cursor = max([inbox.message_cursor(self.room_id), page.next_cursor or 0] + [m.sequence for m in page.items])
        try:
            inbox.receive_messages(self.room_id, [asdict(m) for m in page.items], cursor)
        except ValueError as exc:
            raise SharedNetProtocolError(str(exc)) from exc
        return tuple(SharedNetMessage(**m) for m in inbox.pending_messages(self.room_id))

    async def read(
        self,
        *,
        grep: str | None = None,
        from_instance: str | None = None,
        from_agent: str | None = None,
        order: Literal["asc", "desc"] = "desc",
        limit: int = 20,
        after: int | None = None,
        before: int | None = None,
    ) -> SharedNetMessagePage:
        if not 1 <= limit <= 100:
            raise ValueError("SharedNet read limit must be between 1 and 100")
        if after is not None and before is not None:
            raise ValueError("after and before cannot be combined")
        if order == "desc" and after is not None:
            raise ValueError("after cannot be combined with descending order")
        if after is not None and after < 0:
            raise ValueError("after cannot be negative")
        if before is not None and before < 0:
            raise ValueError("before cannot be negative")

        params: dict[str, str | int] = {"order": order, "limit": limit}
        if grep is not None:
            if not grep:
                raise ValueError("grep cannot be empty")
            params["q"] = grep
        if from_instance is not None:
            params["sender_instance_id"] = from_instance
        if from_agent is not None:
            params["sender_agent_id"] = from_agent
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before

        response = await self.client.get(
            f"/api/v1/rooms/{self.room_id}/messages",
            headers=self._member_headers(),
            params=params,
        )
        response.raise_for_status()
        # Historical lookup does not consume or advance the wait cursor.
        return _parse_message_page(self._json_object(response))

    async def credit_balance(self) -> SharedNetCreditBalance:
        response = await self.client.get(
            "/api/v1/credits", headers=self._member_headers()
        )
        response.raise_for_status()
        payload = self._json_object(response)
        raw_balance = payload.get("credits", payload)
        return _parse_credit_balance(raw_balance)

    async def credit_ledger(
        self, *, last: int = 20, before: str | None = None
    ) -> SharedNetLedgerPage:
        if not 1 <= last <= 100:
            raise ValueError("SharedNet ledger last must be between 1 and 100")
        if before is not None and not re.fullmatch(r"txn_[0-9A-Za-z]{10}", before):
            raise ValueError("SharedNet ledger before must be a txn_ identifier")
        params = {"limit": last}
        if before is not None:
            params["before"] = before
        response = await self.client.get(
            "/api/v1/credits/transfers",
            headers=self._member_headers(),
            params=params,
        )
        response.raise_for_status()
        return _parse_ledger_page(self._json_object(response))

    async def find_transfer(
        self, transfer_id: str, *, max_pages: int = 10
    ) -> SharedNetTransfer | None:
        if not re.fullmatch(r"txn_[0-9A-Za-z]{10}", transfer_id):
            raise ValueError("transfer_id must be a SharedNet txn_ identifier")
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        before: str | None = None
        for _ in range(max_pages):
            page = await self.credit_ledger(last=100, before=before)
            found = next(
                (item for item in page.items if item.transfer_id == transfer_id), None
            )
            if found is not None:
                return found
            if not page.has_more or page.next_cursor is None:
                return None
            before = page.next_cursor
        return None

    async def verify_received_transfer(
        self,
        transfer_id: str,
        *,
        recipient_principal_id: str,
        amount: int,
        room_id: str | None = None,
        memo_contains: str | None = None,
    ) -> SharedNetTransfer | None:
        transfer = await self.find_transfer(transfer_id)
        if transfer is None:
            return None
        mismatches: list[str] = []
        if transfer.to_principal_id != recipient_principal_id:
            mismatches.append("recipient")
        if transfer.amount != amount:
            mismatches.append("amount")
        if room_id is not None and transfer.room_id != room_id:
            mismatches.append("room")
        if memo_contains is not None and memo_contains not in (transfer.memo or ""):
            mismatches.append("memo")
        if mismatches:
            raise SharedNetProtocolError(
                "SharedNet transfer does not match expected " + ", ".join(mismatches)
            )
        return transfer

    async def pay(
        self,
        target: str,
        amount: int,
        *,
        memo: str | None,
        idempotency_key: str,
        announce_in_room: bool = True,
    ) -> SharedNetPaymentResult:
        if not re.fullmatch(r"(?:p|a|i)_[0-9A-Za-z]{10}", target):
            raise ValueError("payment target must be a p_, a_, or i_ identifier")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
            raise ValueError("payment amount must be a positive whole number")
        if not idempotency_key.strip():
            raise ValueError("payment idempotency_key cannot be empty")

        payment_key = self._stable_key("credit-transfer", idempotency_key)
        body: dict[str, Any] = {"to": target, "amount": amount}
        if memo is not None:
            body["memo"] = memo
        if announce_in_room:
            body["room_id"] = self.room_id
        response = await self.client.post(
            "/api/v1/credits/transfers",
            headers=self._member_headers(idempotency_key=payment_key),
            json=body,
        )
        response.raise_for_status()
        payload = self._json_object(response)
        transfer = _parse_transfer(payload.get("transfer", payload))
        if transfer.addressed_to != target or transfer.amount != amount:
            raise SharedNetProtocolError(
                "SharedNet payment response does not match target and amount"
            )
        if announce_in_room and transfer.room_id != self.room_id:
            raise SharedNetProtocolError(
                "SharedNet payment response is not bound to the current room"
            )

        receipt: SharedNetMessage | None = None
        warning: str | None = None
        if announce_in_room:
            content = (
                f"Paid {amount} credit{'s' if amount != 1 else ''} to {target}"
                f"{f' — {memo}' if memo else ''} ({transfer.transfer_id})"
            )
            try:
                receipt = await self.say(
                    content,
                    idempotency_key=self._stable_key(
                        "credit-room-receipt", idempotency_key
                    ),
                )
            except (httpx.HTTPError, SharedNetProtocolError):
                warning = (
                    "Payment settled, but the room receipt was not confirmed; "
                    "do not repeat the payment"
                )
        return SharedNetPaymentResult(
            transfer=transfer, room_receipt=receipt, warning=warning
        )

    @staticmethod
    def _authorization(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _member_headers(
        self, *, idempotency_key: str | None = None
    ) -> dict[str, str]:
        if self._member_token is None:
            raise SharedNetNotJoinedError(
                "join the SharedNet room or restore its member token first"
            )
        headers = self._authorization(self._member_token)
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _stable_key(self, operation: str, idempotency_key: str) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                f"sharednet:{self.room_id}:{operation}:{idempotency_key}",
            )
        )

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise SharedNetProtocolError("SharedNet response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise SharedNetProtocolError("SharedNet response must be a JSON object")
        return payload

    def _advance_cursor(self, page: SharedNetMessagePage) -> None:
        candidates = [self._last_sequence]
        candidates.extend(item.sequence for item in page.items)
        if page.next_cursor is not None:
            candidates.append(page.next_cursor)
        self._last_sequence = max(candidates)


@dataclass(frozen=True, slots=True)
class SharedNetRoutes:
    """Organizer-supplied paths; intentionally has no guessed defaults."""

    discover: str
    invoke: str
    critique: str
    ranking: str
    buy: str
    reconcile: str | None = None


class HttpArenaClient:
    """REST adapter for the ArenaClient boundary.

    Route templates may contain ``{service_id}``. If the organizer's payload schema
    differs, only this adapter needs to change; the strategy and compliance graph do not.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_token: str,
        routes: SharedNetRoutes,
        timeout_seconds: float = 30,
    ) -> None:
        self.routes = routes
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=timeout_seconds,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def discover_services(self) -> list[ServiceListing]:
        response = await self.client.get(self.routes.discover)
        response.raise_for_status()
        payload = response.json()
        records = payload.get("services", payload) if isinstance(payload, dict) else payload
        return [ServiceListing.model_validate(record) for record in records]

    async def invoke_service(self, listing: ServiceListing) -> ServiceResult:
        path = self.routes.invoke.format(service_id=listing.service_id)
        response = await self.client.post(
            path, json={"service_id": listing.service_id, "mode": "evaluate"}
        )
        response.raise_for_status()
        return ServiceResult.model_validate(response.json())

    async def post_critique(
        self, critique_text: str, product_id: str, *, idempotency_key: str
    ) -> None:
        response = await self.client.post(
            self.routes.critique,
            json={
                "product_id": product_id,
                "critique": critique_text,
                "idempotency_key": idempotency_key,
            },
        )
        response.raise_for_status()

    async def submit_ranking(
        self, rankings: list[RankingEntry], *, idempotency_key: str
    ) -> None:
        response = await self.client.post(
            self.routes.ranking,
            json={
                "rankings": [item.model_dump(mode="json") for item in rankings],
                "idempotency_key": idempotency_key,
            },
        )
        response.raise_for_status()

    async def buy(
        self, listing: ServiceListing, *, idempotency_key: str
    ) -> TradeReceipt:
        path = self.routes.buy.format(service_id=listing.service_id)
        response = await self.client.post(
            path,
            json={
                "service_id": listing.service_id,
                "seller_id": listing.seller_id,
                "amount": listing.price,
                "idempotency_key": idempotency_key,
            },
        )
        response.raise_for_status()
        return TradeReceipt.model_validate(response.json())

    async def reconcile_trade(
        self, listing: ServiceListing, *, idempotency_key: str
    ) -> TradeReconciliation:
        if self.routes.reconcile is None:
            return TradeReconciliation()
        path = self.routes.reconcile.format(service_id=listing.service_id)
        response = await self.client.get(
            path,
            params={
                "service_id": listing.service_id,
                "idempotency_key": idempotency_key,
            },
        )
        response.raise_for_status()
        return TradeReconciliation.model_validate(response.json())
