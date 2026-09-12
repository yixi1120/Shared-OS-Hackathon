import json

import pytest
from fastapi.testclient import TestClient

from sharedos_commerce_agent.api import create_app
from sharedos_commerce_agent.auth import AuthenticationConfigurationError
from sharedos_commerce_agent.config import Settings


BUYER_ONE_TOKEN = "buyer-one-secret-token-000001"
BUYER_TWO_TOKEN = "buyer-two-secret-token-000002"


def _client() -> TestClient:
    return TestClient(
        create_app(
            Settings(
                ledger_path=":memory:",
                seller_api_token="operator-secret",
                seller_agent_tokens_json=json.dumps(
                    {
                        "buyer-one": BUYER_ONE_TOKEN,
                        "buyer-two": BUYER_TWO_TOKEN,
                    }
                ),
            )
        )
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _quote_payload(buyer_id: str) -> dict:
    return {
        "buyer_id": buyer_id,
        "service_id": "a2a-interaction-trace",
        "budget": 6,
    }


def test_scoped_agent_token_resolves_identity_and_binds_buyer_id() -> None:
    client = _client()

    whoami = client.get("/v1/auth/whoami", headers=_headers(BUYER_ONE_TOKEN))
    own_quote = client.post(
        "/v1/quotes",
        json=_quote_payload("buyer-one"),
        headers=_headers(BUYER_ONE_TOKEN),
    )
    impersonation = client.post(
        "/v1/quotes",
        json=_quote_payload("buyer-two"),
        headers=_headers(BUYER_ONE_TOKEN),
    )

    assert whoami.json() == {
        "principal_id": "buyer-one",
        "mode": "scoped-agent-token",
        "is_operator": False,
    }
    assert own_quote.status_code == 200
    assert impersonation.status_code == 403
    assert "does not match buyer_id" in impersonation.text


def test_scoped_agent_cannot_negotiate_another_buyers_quote() -> None:
    client = _client()
    quote = client.post(
        "/v1/quotes",
        json=_quote_payload("buyer-one"),
        headers=_headers(BUYER_ONE_TOKEN),
    ).json()

    response = client.post(
        f"/v1/quotes/{quote['quote_id']}/negotiate",
        json={"buyer_offer": 5},
        headers=_headers(BUYER_TWO_TOKEN),
    )

    assert response.status_code == 403


def test_scoped_agent_owns_order_delivery_and_lookup() -> None:
    client = _client()
    quote = client.post(
        "/v1/quotes",
        json=_quote_payload("buyer-one"),
        headers=_headers(BUYER_ONE_TOKEN),
    ).json()
    order = client.post(
        "/v1/orders",
        headers=_headers(BUYER_ONE_TOKEN),
        json={
            "quote_id": quote["quote_id"],
            "buyer_id": "buyer-one",
            "service_id": "a2a-interaction-trace",
            "amount": quote["ask_price"],
            "idempotency_key": "buyer-one-auth-order-001",
            "input": {
                "events": [
                    {
                        "task_id": "task-auth-1",
                        "subject_agent_id": "seller-one",
                        "stage": "task_completed",
                        "occurred_at": "2026-09-12T12:00:00Z",
                    }
                ]
            },
        },
    ).json()

    denied_delivery = client.post(
        f"/v1/orders/{order['trade_id']}/deliver",
        headers=_headers(BUYER_TWO_TOKEN),
    )
    denied_lookup = client.get(
        f"/v1/orders/{order['trade_id']}",
        headers=_headers(BUYER_TWO_TOKEN),
    )
    own_delivery = client.post(
        f"/v1/orders/{order['trade_id']}/deliver",
        headers=_headers(BUYER_ONE_TOKEN),
    )

    assert denied_delivery.status_code == 403
    assert denied_lookup.status_code == 403
    assert own_delivery.status_code == 200
    assert own_delivery.json()["status"] == "delivered"


def test_operator_token_retains_explicit_break_glass_access() -> None:
    client = _client()

    whoami = client.get(
        "/v1/auth/whoami", headers=_headers("operator-secret")
    )
    quote = client.post(
        "/v1/quotes",
        json=_quote_payload("buyer-one"),
        headers=_headers("operator-secret"),
    )

    assert whoami.json()["is_operator"] is True
    assert quote.status_code == 200


def test_agent_token_configuration_fails_closed() -> None:
    with pytest.raises(AuthenticationConfigurationError, match="valid JSON"):
        create_app(Settings(seller_agent_tokens_json="not-json"))
    with pytest.raises(AuthenticationConfigurationError, match="at least 24"):
        create_app(
            Settings(seller_agent_tokens_json=json.dumps({"buyer-one": "short"}))
        )
    with pytest.raises(AuthenticationConfigurationError, match="unique"):
        create_app(
            Settings(
                seller_agent_tokens_json=json.dumps(
                    {
                        "buyer-one": BUYER_ONE_TOKEN,
                        "buyer-two": BUYER_ONE_TOKEN,
                    }
                )
            )
        )


def test_settings_repr_hides_all_configured_secrets() -> None:
    settings = Settings(
        model_api_key="model-secret",
        arena_api_token="arena-secret",
        sharednet_invite_token="rit_secret",
        sharednet_member_token="sni_secret",
        seller_api_token="seller-secret",
        seller_agent_tokens_json='{"buyer":"buyer-secret-token-123456"}',
    )

    rendered = repr(settings)
    for secret in (
        "model-secret",
        "arena-secret",
        "rit_secret",
        "sni_secret",
        "seller-secret",
        "buyer-secret-token-123456",
    ):
        assert secret not in rendered
