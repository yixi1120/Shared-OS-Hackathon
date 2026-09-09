from fastapi.testclient import TestClient

from sharedos_commerce_agent.api import create_app
from sharedos_commerce_agent.config import Settings


def test_quote_negotiate_order_and_delivery() -> None:
    client = TestClient(create_app(Settings(ledger_path=":memory:")))
    quote_response = client.post(
        "/v1/quotes",
        json={
            "buyer_id": "buyer-one",
            "service_id": "verified-transaction-trace",
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
        "service_id": "verified-transaction-trace",
        "amount": agreed_price,
        "idempotency_key": "buyer-one-request-001",
        "input": {
            "events": [
                {
                    "transaction_id": "tx-001",
                    "subject_agent_id": "seller-one",
                    "stage": "quoted",
                    "occurred_at": "2026-09-10T01:00:00Z",
                    "amount": 10,
                    "evidence_id": "quote-001",
                },
                {
                    "transaction_id": "tx-001",
                    "subject_agent_id": "seller-one",
                    "stage": "paid",
                    "occurred_at": "2026-09-10T01:00:01Z",
                    "amount": 10,
                    "evidence_id": "payment-001",
                },
                {
                    "transaction_id": "tx-001",
                    "subject_agent_id": "seller-one",
                    "stage": "delivered",
                    "occurred_at": "2026-09-10T01:00:03Z",
                    "schema_valid": True,
                    "evidence_id": "delivery-001",
                },
            ]
        },
    }
    first_order = client.post("/v1/orders", json=order_payload)
    repeated_order = client.post("/v1/orders", json=order_payload)
    assert first_order.status_code == 200
    assert repeated_order.json()["trade_id"] == first_order.json()["trade_id"]

    trade_id = first_order.json()["trade_id"]
    delivery = client.post(f"/v1/orders/{trade_id}/deliver")
    assert delivery.status_code == 200
    assert delivery.json()["status"] == "delivered"
    assert delivery.json()["output"]["completed"] is True
    assert delivery.json()["output"]["price_consistent"] is True

    stored = client.get(f"/v1/orders/{trade_id}")
    assert stored.json()["status"] == "delivered"
