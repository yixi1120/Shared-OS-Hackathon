import hashlib
import json
import sqlite3

from fastapi.testclient import TestClient

from sharedos_commerce_agent.api import create_app
from sharedos_commerce_agent.config import Settings


def test_registration_is_immediately_usable_private_and_persistent(tmp_path):
    settings = Settings(ledger_path=str(tmp_path / "seller.db"), seller_api_token="operator-only-secret")
    client = TestClient(create_app(settings))
    one = client.post("/v1/agents/register", json={"name": "one"})
    assert one.status_code == 201 and one.headers["cache-control"] == "no-store"
    a = one.json()
    b = client.post("/v1/agents/register", json={"name": "two"}).json()
    assert a["agent_id"] != b["agent_id"] and a["api_key"] != b["api_key"]
    assert a["identity_verified"] is False
    headers = lambda agent: {"Authorization": "Bearer " + agent["api_key"]}
    orders = []
    for agent in (a, b):
        auth = headers(agent)
        assert client.get("/v1/auth/whoami", headers=auth).json()["principal_id"] == agent["buyer_id"]
        quote = client.post("/v1/quotes", headers=auth, json={"buyer_id": agent["buyer_id"], "service_id": "a2a-interaction-trace", "budget": 6}).json()
        response = client.post("/v1/orders", headers=auth, json={"buyer_id": agent["buyer_id"], "quote_id": quote["quote_id"], "service_id": "a2a-interaction-trace", "amount": quote["ask_price"], "idempotency_key": "same-key-across-agents", "input": {"events": [{"task_id": "test-registration", "subject_agent_id": "synthetic", "stage": "request_received", "occurred_at": "2026-09-13T00:00:00Z"}]}})
        assert response.status_code == 200
        orders.append(response.json()["trade_id"])
    assert orders[0] != orders[1]
    assert client.post("/v1/quotes", headers=headers(b), json={"buyer_id": a["buyer_id"], "service_id": "a2a-interaction-trace", "budget": 6}).status_code == 403
    for suffix, method in (("", "get"), ("/deliver", "post")):
        assert getattr(client, method)("/v1/orders/" + orders[0] + suffix, headers=headers(b)).status_code == 403
    assert client.post("/v1/orders/" + orders[0] + "/deliver", headers=headers(a)).status_code == 200
    client = TestClient(create_app(settings))
    assert client.get("/v1/orders/" + orders[0], headers=headers(a)).status_code == 200
    with sqlite3.connect(settings.ledger_path) as db:
        stored = db.execute("SELECT token_hash FROM api_agents WHERE agent_id=?", (a["agent_id"],)).fetchone()[0]
    assert stored == hashlib.sha256(a["api_key"].encode()).hexdigest()
    assert a["api_key"].encode() not in (tmp_path / "seller.db").read_bytes()
    assert client.delete("/v1/agents/me/key", headers=headers(a)).status_code == 204
    client = TestClient(create_app(settings))
    assert client.get("/v1/auth/whoami", headers=headers(a)).status_code == 401
    assert client.get("/v1/auth/whoami", headers=headers(b)).status_code == 200


def test_registration_rejects_claimed_identity_and_rate_limits(tmp_path):
    settings = Settings(ledger_path=str(tmp_path / "seller.db"), seller_api_token="operator-secret")
    client = TestClient(create_app(settings))
    for body in ({"name": " "}, {"name": "ok", "principal_id": "p_owner"}, {"name": "ok", "is_operator": True}):
        assert client.post("/v1/agents/register", json=body).status_code == 422
    for _ in range(100):
        assert client.post("/v1/agents/register", json={"name": "same-display-name"}).status_code == 201
    response = TestClient(create_app(settings)).post("/v1/agents/register", json={"name": "another"})
    assert response.status_code == 429 and "retry-after" in response.headers
    assert client.get("/.well-known/agent.json").json()["authentication"]["registration"] == "/v1/agents/register"
