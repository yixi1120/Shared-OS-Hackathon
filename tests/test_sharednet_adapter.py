from __future__ import annotations

import json

import httpx
import pytest

from sharedos_commerce_agent.sharednet_adapter import (
    SharedNetNotJoinedError,
    SharedNetProtocolError,
    SharedNetRoomClient,
)


ROOM_ID = "rom_AbC123xYz9"
INVITE_TOKEN = "rit_invite-secret"
MEMBER_TOKEN = "sni_member-secret"


def json_response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload,
        headers={"content-type": "application/json"},
    )


async def test_join_uses_invite_once_and_tracks_history_cursor() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/api/v1/rooms/{ROOM_ID}/join"
        assert request.headers["authorization"] == f"Bearer {INVITE_TOKEN}"
        assert json.loads(request.content) == {
            "name": "commerce-agent",
            "runtime": {"kind": "codex"},
        }
        return json_response(
            200,
            {
                "member": {"id": "i_Member1234"},
                "member_token": MEMBER_TOKEN,
                "history": {
                    "items": [
                        {
                            "id": "msg_One123456",
                            "sequence": 3,
                            "content": "Arena room opened",
                            "sender_instance_id": "i_Host123456",
                        },
                        {
                            "id": "msg_Two123456",
                            "sequence": 5,
                            "content": "Round brief",
                            "sender": {
                                "instance_id": "i_Host123456",
                                "agent_id": "a_Host123456",
                            },
                        },
                    ],
                    "next_cursor": "5",
                    "has_more": False,
                },
            },
        )

    client = SharedNetRoomClient(
        room_id=ROOM_ID,
        invite_token=INVITE_TOKEN,
        agent_name="commerce-agent",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await client.join()
        assert result.member_id == "i_Member1234"
        assert [item.sequence for item in result.history.items] == [3, 5]
        assert result.history.items[1].sender_agent_id == "a_Host123456"
        assert client.joined is True
        assert client.last_sequence == 5
        assert MEMBER_TOKEN not in repr(result)
    finally:
        await client.close()


async def test_say_uses_member_token_without_advancing_receive_cursor() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers["authorization"] == f"Bearer {MEMBER_TOKEN}"
        assert json.loads(request.content) == {"content": "Hello room"}
        return json_response(
            201,
            {
                "message": {
                    "id": "msg_Mine123456",
                    "sequence": 9,
                    "content": "Hello room",
                }
            },
        )

    client = SharedNetRoomClient(
        room_id=ROOM_ID,
        member_token=MEMBER_TOKEN,
        last_sequence=7,
        transport=httpx.MockTransport(handler),
    )
    try:
        message = await client.say("Hello room")
        assert message.sequence == 9
        assert client.last_sequence == 7
    finally:
        await client.close()


async def test_wait_defaults_to_receive_cursor_and_advances_it() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.params["after"] == "7"
        assert request.url.params["timeout"] == "25"
        return json_response(
            200,
            {
                "items": [
                    {"sequence": 8, "content": "new message"},
                    {"sequence": 10, "content": "another message"},
                ],
                "next_cursor": 10,
                "has_more": False,
            },
        )

    client = SharedNetRoomClient(
        room_id=ROOM_ID,
        member_token=MEMBER_TOKEN,
        last_sequence=7,
        transport=httpx.MockTransport(handler),
    )
    try:
        page = await client.wait()
        assert [item.content for item in page.items] == [
            "new message",
            "another message",
        ]
        assert client.last_sequence == 10
    finally:
        await client.close()


async def test_read_filters_history_without_consuming_wait_cursor() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "deployment"
        assert request.url.params["sender_agent_id"] == "default"
        assert request.url.params["order"] == "desc"
        assert request.url.params["limit"] == "10"
        assert request.url.params["before"] == "82"
        return json_response(
            200,
            {
                "items": [{"sequence": 80, "content": "deployment ready"}],
                "next_cursor": 80,
                "has_more": True,
            },
        )

    client = SharedNetRoomClient(
        room_id=ROOM_ID,
        member_token=MEMBER_TOKEN,
        last_sequence=90,
        transport=httpx.MockTransport(handler),
    )
    try:
        page = await client.read(
            grep="deployment", from_agent="default", limit=10, before=82
        )
        assert page.items[0].sequence == 80
        assert page.has_more is True
        assert client.last_sequence == 90
    finally:
        await client.close()


async def test_room_operations_require_a_member_token() -> None:
    client = SharedNetRoomClient(room_id=ROOM_ID, invite_token=INVITE_TOKEN)
    try:
        with pytest.raises(SharedNetNotJoinedError):
            await client.say("not joined")
        with pytest.raises(SharedNetNotJoinedError):
            await client.wait(timeout_seconds=0)
        with pytest.raises(SharedNetNotJoinedError):
            await client.read()
    finally:
        await client.close()


async def test_invalid_join_payload_does_not_install_a_credential() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return json_response(200, {"member": {"id": "i_Member1234"}})

    client = SharedNetRoomClient(
        room_id=ROOM_ID,
        invite_token=INVITE_TOKEN,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(SharedNetProtocolError, match="member_token"):
            await client.join()
        assert client.joined is False
    finally:
        await client.close()


async def test_read_rejects_ambiguous_cursor_combinations() -> None:
    client = SharedNetRoomClient(room_id=ROOM_ID, member_token=MEMBER_TOKEN)
    try:
        with pytest.raises(ValueError, match="after and before"):
            await client.read(after=2, before=4)
        with pytest.raises(ValueError, match="descending"):
            await client.read(after=2)
    finally:
        await client.close()
