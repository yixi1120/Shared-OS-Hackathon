from __future__ import annotations

import json
import stat

import httpx
import pytest

from sharedos_commerce_agent.config import Settings
from sharedos_commerce_agent.ledger import Ledger
from sharedos_commerce_agent.production import (
    ROOM_PROTOCOL,
    RoomMessageRouter,
    RuntimeConfigurationError,
    RuntimeIdentity,
    RuntimeIdentityStore,
    SharedNetProductionAgent,
    bootstrap_room_runtime,
    configured_arena_routes,
)
from sharedos_commerce_agent.sharednet_adapter import (
    SharedNetMessage,
    SharedNetRoomClient,
)


ROOM_ID = "rom_ProdRoom01"
MEMBER_ID = "i_ProdSeat01"
MEMBER_TOKEN = "sni_production-secret"
INVITE_TOKEN = "rit_invite-secret"
SERVICE_URL = "https://service.example.test"


def _settings(tmp_path, **changes) -> Settings:
    values = {
        "service_base_url": SERVICE_URL,
        "sharednet_room_id": ROOM_ID,
        "sharednet_invite_token": INVITE_TOKEN,
        "sharednet_state_path": str(tmp_path / "identity.json"),
        "sharednet_inbox_path": str(tmp_path / "inbox.sqlite3"),
        "sharednet_agent_name": "sharedos-commerce-agent",
    }
    values.update(changes)
    return Settings(**values)


def _response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(status, json=payload)


def test_identity_store_is_private_atomic_and_redacted(tmp_path) -> None:
    path = tmp_path / "private" / "identity.json"
    store = RuntimeIdentityStore(str(path))
    identity = RuntimeIdentity(
        room_id=ROOM_ID, member_id=MEMBER_ID, member_token=MEMBER_TOKEN
    )

    store.save(identity)

    assert store.load(ROOM_ID) == identity
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert MEMBER_TOKEN not in repr(identity)
    assert INVITE_TOKEN not in path.read_text(encoding="utf-8")


def test_identity_store_rejects_wrong_room_and_repairs_permissions(tmp_path) -> None:
    path = tmp_path / "identity.json"
    store = RuntimeIdentityStore(str(path))
    store.save(
        RuntimeIdentity(
            room_id=ROOM_ID, member_id=MEMBER_ID, member_token=MEMBER_TOKEN
        )
    )
    path.chmod(0o644)

    assert store.load(ROOM_ID) is not None
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(RuntimeConfigurationError, match="different room"):
        store.load("rom_Different123")


async def test_bootstrap_joins_once_persists_identity_and_history(tmp_path) -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        assert request.headers["authorization"] == f"Bearer {INVITE_TOKEN}"
        return _response(
            200,
            {
                "member": {"id": MEMBER_ID},
                "member_token": MEMBER_TOKEN,
                "history": {
                    "items": [
                        {
                            "id": "msg_history-1",
                            "sequence": 7,
                            "content": "round brief",
                            "sender_instance_id": "i_host",
                        }
                    ],
                    "next_cursor": 7,
                    "has_more": False,
                },
            },
        )

    settings = _settings(tmp_path)
    runtime = await bootstrap_room_runtime(
        settings, transport=httpx.MockTransport(handler)
    )
    try:
        assert runtime.identity.member_id == MEMBER_ID
        assert runtime.agent.client.joined is True
        assert runtime.agent.inbox.message_cursor(ROOM_ID) == 7
        assert stat.S_IMODE(
            (tmp_path / "inbox.sqlite3").stat().st_mode
        ) == 0o600
        assert [
            item["message_id"]
            for item in runtime.agent.inbox.pending_messages(ROOM_ID)
        ] == ["msg_history-1"]
        assert calls == [f"POST /api/v1/rooms/{ROOM_ID}/join"]
        saved = RuntimeIdentityStore(settings.sharednet_state_path).load(ROOM_ID)
        assert saved == runtime.identity
    finally:
        await runtime.close()


async def test_bootstrap_reuses_saved_identity_without_join(tmp_path) -> None:
    settings = _settings(tmp_path)
    RuntimeIdentityStore(settings.sharednet_state_path).save(
        RuntimeIdentity(
            room_id=ROOM_ID, member_id=MEMBER_ID, member_token=MEMBER_TOKEN
        )
    )

    async def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("bootstrap must not call SharedNet when identity is saved")

    runtime = await bootstrap_room_runtime(
        settings, transport=httpx.MockTransport(handler)
    )
    try:
        assert runtime.identity.member_token == MEMBER_TOKEN
        assert runtime.agent.client.joined is True
    finally:
        await runtime.close()


async def test_second_listener_for_same_identity_is_rejected(tmp_path) -> None:
    settings = _settings(tmp_path)
    RuntimeIdentityStore(settings.sharednet_state_path).save(
        RuntimeIdentity(
            room_id=ROOM_ID, member_id=MEMBER_ID, member_token=MEMBER_TOKEN
        )
    )

    async def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("restoring an identity must not call the network")

    transport = httpx.MockTransport(handler)
    first = await bootstrap_room_runtime(settings, transport=transport)
    try:
        with pytest.raises(RuntimeConfigurationError, match="already owns"):
            await bootstrap_room_runtime(settings, transport=transport)
    finally:
        await first.close()

    resumed = await bootstrap_room_runtime(settings, transport=transport)
    await resumed.close()


def test_router_responds_only_to_machine_requests_or_product_mentions() -> None:
    router = RoomMessageRouter(
        agent_name="sharedos-commerce-agent",
        service_base_url=SERVICE_URL,
        payment_target=MEMBER_ID,
    )
    ignored = SharedNetMessage(
        sequence=1, message_id="msg_ignore", content="unrelated room chatter"
    )
    discovery = SharedNetMessage(
        sequence=2,
        message_id="msg_discover",
        content=json.dumps({"type": "service_discovery", "to": "*"}),
    )
    question = SharedNetMessage(
        sequence=3,
        message_id="msg_question",
        content=json.dumps(
            {
                "type": "product_query",
                "to": "sharedos-commerce-agent",
                "question": "What is the price?",
            }
        ),
    )

    assert router.reply(ignored) is None
    offer = json.loads(router.reply(discovery) or "{}")
    assert offer["protocol"] == ROOM_PROTOCOL
    assert offer["type"] == "service_offer"
    assert offer["reply_to"] == "msg_discover"
    assert {item["price"] for item in offer["services"]} == {6}
    assert offer["payment"]["target"] == MEMBER_ID
    assert offer["payment"]["settlement"] == "sharednet-ledger"
    assert f"pay {MEMBER_ID}" in offer["payment"]["instruction"]
    answer = json.loads(router.reply(question) or "{}")
    assert answer["type"] == "product_answer"
    assert answer["intent"] == "price"
    assert answer["credit_settlement"] == "not_evaluated"


def test_router_rejects_an_invalid_payment_target() -> None:
    with pytest.raises(RuntimeConfigurationError, match="payment_target"):
        RoomMessageRouter(
            agent_name="sharedos-commerce-agent",
            service_base_url=SERVICE_URL,
            payment_target="not-a-sharednet-address",
        )


async def test_process_once_replies_then_acknowledges(tmp_path) -> None:
    inbox = Ledger(str(tmp_path / "inbox.sqlite3"))
    inbox.receive_messages(
        ROOM_ID,
        [
            {
                "sequence": 4,
                "content": json.dumps(
                    {"type": "product_query", "question": "price"}
                ),
                "message_id": "msg_question-4",
                "sender_instance_id": "i_buyer",
            }
        ],
        4,
    )
    sent: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert request.url.params["q"] == '"reply_to":"msg_question-4"'
            assert request.url.params["sender_instance_id"] == MEMBER_ID
            return _response(
                200, {"items": [], "next_cursor": 4, "has_more": False}
            )
        sent.append(json.loads(request.content))
        return _response(
            201,
            {
                "message": {
                    "id": "msg_reply-4",
                    "sequence": 5,
                    "content": sent[-1]["content"],
                }
            },
        )

    client = SharedNetRoomClient(
        room_id=ROOM_ID,
        member_token=MEMBER_TOKEN,
        transport=httpx.MockTransport(handler),
    )
    agent = SharedNetProductionAgent(
        client=client,
        inbox=inbox,
        router=RoomMessageRouter(
            agent_name="sharedos-commerce-agent", service_base_url=SERVICE_URL
        ),
        room_id=ROOM_ID,
        member_id=MEMBER_ID,
    )
    try:
        assert await agent.process_once(timeout_seconds=0) == 1
        assert len(sent) == 1
        reply = json.loads(sent[0]["content"])
        assert reply["reply_to"] == "msg_question-4"
        assert inbox.pending_messages(ROOM_ID) == []
    finally:
        await client.close()


async def test_recovery_reconciles_remote_reply_before_ack(tmp_path) -> None:
    inbox = Ledger(str(tmp_path / "inbox.sqlite3"))
    inbox.receive_messages(
        ROOM_ID,
        [
            {
                "sequence": 8,
                "content": json.dumps({"type": "service_discovery"}),
                "message_id": "msg_request-8",
                "sender_instance_id": "i_buyer",
            }
        ],
        8,
    )
    posts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        if request.method == "POST":
            posts += 1
            raise AssertionError("a remotely visible reply must not be sent twice")
        marker = '"reply_to":"msg_request-8"'
        return _response(
            200,
            {
                "items": [
                    {
                        "id": "msg_existing-reply",
                        "sequence": 9,
                        "content": "{" + marker + ",\"type\":\"service_offer\"}",
                        "sender_instance_id": MEMBER_ID,
                    }
                ],
                "next_cursor": 9,
                "has_more": False,
            },
        )

    client = SharedNetRoomClient(
        room_id=ROOM_ID,
        member_token=MEMBER_TOKEN,
        transport=httpx.MockTransport(handler),
    )
    agent = SharedNetProductionAgent(
        client=client,
        inbox=inbox,
        router=RoomMessageRouter(
            agent_name="sharedos-commerce-agent", service_base_url=SERVICE_URL
        ),
        room_id=ROOM_ID,
        member_id=MEMBER_ID,
    )
    try:
        assert await agent.process_once(timeout_seconds=0) == 1
        assert posts == 0
        assert inbox.pending_messages(ROOM_ID) == []
    finally:
        await client.close()


def test_arena_routes_fail_closed_until_organizer_contract_is_complete() -> None:
    with pytest.raises(RuntimeConfigurationError, match="ARENA_DISCOVER_ROUTE"):
        configured_arena_routes(Settings())

    routes = configured_arena_routes(
        Settings(
            arena_discover_route="/discover",
            arena_invoke_route="/invoke/{service_id}",
            arena_critique_route="/critique",
            arena_ranking_route="/ranking",
            arena_buy_route="/buy/{service_id}",
        )
    )
    assert routes.buy == "/buy/{service_id}"
