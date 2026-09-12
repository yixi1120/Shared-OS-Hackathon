import httpx

from sharedos_commerce_agent.client_cli import InteractionServiceClient


def test_agent_client_reads_free_endpoints_and_delivers_paid_report():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/catalog":
            return httpx.Response(200, json=[{"service_id": "a2a-interaction-trace"}])
        if request.url.path == "/v1/contracts/interaction-v1":
            return httpx.Response(200, json={"input": {"type": "object"}})
        if request.url.path == "/v1/quotes":
            return httpx.Response(200, json={"quote_id": "quote-1", "ask_price": 6})
        if request.url.path == "/v1/orders":
            return httpx.Response(200, json={"trade_id": "trade-1", "status": "accepted"})
        if request.url.path == "/v1/orders/trade-1/deliver":
            return httpx.Response(200, json={"trade_id": "trade-1", "status": "delivered"})
        return httpx.Response(404)

    with InteractionServiceClient(
        "https://service.example",
        token="test-token",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.health() == {"status": "ok"}
        assert client.catalog()[0]["service_id"] == "a2a-interaction-trace"
        assert client.contract()["input"]["type"] == "object"
        result = client.analyze(
            service_id="a2a-interaction-trace",
            buyer_id="buyer-1",
            budget=6,
            input_payload={"events": [{"task_id": "task-1"}]},
            idempotency_key="same-logical-order",
        )

    assert result["delivery"]["status"] == "delivered"
    assert result["credit_settlement"] == "not_evaluated"
    assert all(request.headers.get("Authorization") == "Bearer test-token" for request in requests)
