import httpx
from fastapi.testclient import TestClient

from sharedos_commerce_agent.api import create_app
from sharedos_commerce_agent.config import Settings


def _register(client: TestClient, name: str = "buyer-agent") -> dict:
    response = client.post("/v1/agents/register", json={"name": name})
    assert response.status_code == 201
    return response.json()


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def test_production_default_fails_closed_and_registration_is_self_service() -> None:
    client = TestClient(create_app(Settings(ledger_path=":memory:")))

    denied = client.post(
        "/v1/quotes",
        json={
            "buyer_id": "unregistered",
            "service_id": "a2a-interaction-trace",
            "budget": 6,
        },
    )
    assert denied.status_code == 401

    identity = _register(client)
    assert identity["agent_id"] == identity["buyer_id"]
    assert identity["agent_id"].startswith("agt_")
    assert identity["api_key"].startswith("sca_")
    assert identity["identity_verified"] is False

    headers = _headers(identity["api_key"])
    assert client.get("/v1/auth/whoami", headers=headers).json() == {
        "principal_id": identity["agent_id"],
        "mode": "registered-agent-token",
        "is_operator": False,
    }
    assert client.delete("/v1/agents/me/key", headers=headers).status_code == 204
    assert client.get("/v1/auth/whoami", headers=headers).status_code == 401


def test_registered_key_and_quote_survive_application_restart(tmp_path) -> None:
    database = str(tmp_path / "commerce.sqlite3")
    settings = Settings(ledger_path=database)
    first = TestClient(create_app(settings))
    identity = _register(first, "restart-buyer")
    headers = _headers(identity["api_key"])
    quote = first.post(
        "/v1/quotes",
        headers=headers,
        json={
            "buyer_id": identity["buyer_id"],
            "service_id": "a2a-interaction-trace",
            "budget": 6,
        },
    ).json()

    second = TestClient(create_app(settings))
    assert second.get("/v1/auth/whoami", headers=headers).status_code == 200
    order = second.post(
        "/v1/orders",
        headers=headers,
        json={
            "quote_id": quote["quote_id"],
            "buyer_id": identity["buyer_id"],
            "service_id": quote["service_id"],
            "amount": quote["ask_price"],
            "idempotency_key": "restart-safe-order-001",
            "input": {
                "events": [
                    {
                        "task_id": "restart-task",
                        "subject_agent_id": "seller",
                        "stage": "task_completed",
                        "occurred_at": "2026-09-13T08:00:00Z",
                    }
                ]
            },
        },
    )
    assert order.status_code == 200
    delivered = second.post(
        f"/v1/orders/{order.json()['trade_id']}/deliver", headers=headers
    )
    assert delivered.status_code == 200


def test_registration_and_agent_rate_limits_are_enforced() -> None:
    registration_client = TestClient(
        create_app(
            Settings(
                ledger_path=":memory:",
                seller_registration_limit_per_hour=1,
            )
        )
    )
    _register(registration_client, "first")
    limited = registration_client.post("/v1/agents/register", json={"name": "second"})
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "3600"

    request_client = TestClient(
        create_app(
            Settings(
                ledger_path=":memory:",
                seller_agent_requests_per_minute=1,
            )
        )
    )
    identity = _register(request_client)
    headers = _headers(identity["api_key"])
    assert request_client.get("/v1/auth/whoami", headers=headers).status_code == 200
    limited = request_client.get("/v1/auth/whoami", headers=headers)
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"


def test_health_and_agent_card_expose_deploy_identity_without_secrets() -> None:
    client = TestClient(
        create_app(Settings(ledger_path=":memory:", build_sha="abc1234"))
    )
    health = client.get("/health").json()
    assert health == {
        "status": "ok",
        "version": "0.1.0",
        "build_sha": "abc1234",
        "authentication": "enabled",
        "registration": True,
    }
    card = client.get("/.well-known/agent.json").json()
    assert card["authentication"]["registration"] == "/v1/agents/register"
    assert card["workflow"] == ["register", "quote", "order", "deliver"]
    assert card["credit_settlement"] == "not_evaluated"


def test_optional_payment_assurance_verifies_official_ledger_before_delivery() -> None:
    expected: dict[str, str | int] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/credits/transfers"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "txn_1234567890",
                        "from_principal_id": "p_0987654321",
                        "to_principal_id": "p_1234567890",
                        "amount": expected["amount"],
                        "memo": f"service order={expected['trade_id']}",
                        "room_id": "rom_1234567890",
                        "by_instance_id": "i_1234567890",
                        "addressed_to": "p_1234567890",
                        "code": None,
                        "created_at": "2026-09-13T08:00:00Z",
                    }
                ],
                "next_cursor": None,
                "has_more": False,
            },
        )

    settings = Settings(
        ledger_path=":memory:",
        require_sharednet_payment=True,
        sharednet_room_id="rom_1234567890",
        sharednet_principal_id="p_1234567890",
        sharednet_member_token="sni_test-member-token",
    )
    client = TestClient(
        create_app(settings, sharednet_transport=httpx.MockTransport(handler))
    )
    identity = _register(client)
    headers = _headers(identity["api_key"])
    quote = client.post(
        "/v1/quotes",
        headers=headers,
        json={
            "buyer_id": identity["buyer_id"],
            "service_id": "a2a-interaction-trace",
            "budget": 6,
        },
    ).json()
    order = client.post(
        "/v1/orders",
        headers=headers,
        json={
            "quote_id": quote["quote_id"],
            "buyer_id": identity["buyer_id"],
            "service_id": quote["service_id"],
            "amount": quote["ask_price"],
            "idempotency_key": "payment-assured-order-001",
            "input": {
                "events": [
                    {
                        "task_id": "paid-task",
                        "subject_agent_id": "seller",
                        "stage": "task_completed",
                        "occurred_at": "2026-09-13T08:00:00Z",
                    }
                ]
            },
        },
    ).json()
    expected.update(trade_id=order["trade_id"], amount=order["amount"])

    blocked = client.post(f"/v1/orders/{order['trade_id']}/deliver", headers=headers)
    assert blocked.status_code == 402
    verified = client.post(
        f"/v1/orders/{order['trade_id']}/settlement",
        headers=headers,
        json={"transfer_id": "txn_1234567890"},
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "paid"
    delivered = client.post(f"/v1/orders/{order['trade_id']}/deliver", headers=headers)
    assert delivered.status_code == 200
