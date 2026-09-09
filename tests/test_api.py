from fastapi.testclient import TestClient

from sharedos_commerce_agent.api import create_app
from sharedos_commerce_agent.config import Settings


def test_quote_negotiate_order_and_delivery() -> None:
    client = TestClient(create_app(Settings(ledger_path=":memory:")))
    quote_response = client.post(
        "/v1/quotes",
        json={
            "buyer_id": "buyer-one",
            "service_id": "a2a-interaction-trace",
            "budget": 30,
        },
    )
    assert quote_response.status_code == 200
    quote = quote_response.json()

    negotiation = client.post(
        f"/v1/quotes/{quote['quote_id']}/negotiate",
        json={"buyer_offer": quote["reservation_price"]},
    )
    assert negotiation.status_code == 200
    agreed_price = negotiation.json()["final_price"]

    order_payload = {
        "quote_id": quote["quote_id"],
        "buyer_id": "buyer-one",
        "service_id": "a2a-interaction-trace",
        "amount": agreed_price,
        "idempotency_key": "buyer-one-request-001",
        "input": {
            "events": [
                {
                    "task_id": "task-001",
                    "subject_agent_id": "seller-one",
                    "stage": "request_received",
                    "occurred_at": "2026-09-10T01:00:00Z",
                    # Caller claims a trusted source, but the public boundary must
                    # downgrade every caller-supplied event to self-reported.
                    "provenance": "platform",
                    "evidence_id": "request-001",
                    "request_hash": "sha256:request",
                },
                {
                    "task_id": "task-001",
                    "subject_agent_id": "seller-one",
                    "stage": "task_started",
                    "occurred_at": "2026-09-10T01:00:01Z",
                    "evidence_id": "start-001",
                },
                {
                    "task_id": "task-001",
                    "subject_agent_id": "seller-one",
                    "stage": "artifact_delivered",
                    "occurred_at": "2026-09-10T01:00:03Z",
                    "schema_valid": True,
                    "evidence_id": "delivery-001",
                    "artifact_hash": "sha256:artifact",
                },
                {
                    "task_id": "task-001",
                    "subject_agent_id": "seller-one",
                    "stage": "task_completed",
                    "occurred_at": "2026-09-10T01:00:04Z",
                    "evidence_id": "complete-001",
                },
            ]
        },
    }
    first_order = client.post("/v1/orders", json=order_payload)
    repeated_order = client.post("/v1/orders", json=order_payload)
    assert first_order.status_code == 200
    assert first_order.json()["status"] == "accepted"
    assert first_order.json()["metadata"]["credit_settlement"] == "not_evaluated"
    assert "provenance" not in first_order.json()["metadata"]["input"]["events"][0]
    assert repeated_order.json()["trade_id"] == first_order.json()["trade_id"]

    trade_id = first_order.json()["trade_id"]
    delivery = client.post(f"/v1/orders/{trade_id}/deliver")
    assert delivery.status_code == 200
    assert delivery.json()["status"] == "delivered"
    assert delivery.json()["output"]["completed"] is True
    assert delivery.json()["output"]["credit_settlement"] == "not_evaluated"
    assert delivery.json()["output"]["reputation_eligible"] is False
    assert delivery.json()["output"]["confidence"].startswith("self-reported")

    stored = client.get(f"/v1/orders/{trade_id}")
    assert stored.json()["status"] == "delivered"


def test_configured_bearer_token_protects_non_discovery_endpoints() -> None:
    client = TestClient(
        create_app(Settings(ledger_path=":memory:", seller_api_token="secret-token"))
    )

    assert client.get("/v1/catalog").status_code == 200
    payload = {
        "buyer_id": "buyer-one",
        "service_id": "a2a-interaction-trace",
        "budget": 30,
    }
    missing = client.post("/v1/quotes", json=payload)
    wrong = client.post(
        "/v1/quotes",
        json=payload,
        headers={"Authorization": "Bearer wrong-token"},
    )
    correct = client.post(
        "/v1/quotes",
        json=payload,
        headers={"Authorization": "Bearer secret-token"},
    )

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert wrong.status_code == 401
    assert correct.status_code == 200


def test_order_input_rejects_mixed_tasks_before_it_is_persisted() -> None:
    client = TestClient(create_app(Settings(ledger_path=":memory:")))
    quote = client.post(
        "/v1/quotes",
        json={
            "buyer_id": "buyer-one",
            "service_id": "a2a-interaction-trace",
            "budget": 30,
        },
    ).json()

    response = client.post(
        "/v1/orders",
        json={
            "quote_id": quote["quote_id"],
            "buyer_id": "buyer-one",
            "service_id": "a2a-interaction-trace",
            "amount": quote["ask_price"],
            "idempotency_key": "mixed-task-request",
            "input": {
                "events": [
                    {
                        "task_id": "task-one",
                        "subject_agent_id": "seller-one",
                        "stage": "request_received",
                        "occurred_at": "2026-09-10T01:00:00Z",
                    },
                    {
                        "task_id": "task-two",
                        "subject_agent_id": "seller-one",
                        "stage": "task_completed",
                        "occurred_at": "2026-09-10T01:00:01Z",
                    },
                ]
            },
        },
    )

    assert response.status_code == 422
