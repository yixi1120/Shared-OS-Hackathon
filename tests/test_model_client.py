import json

import httpx
import pytest

from sharedos_commerce_agent.config import Settings
from sharedos_commerce_agent.model_client import ModelError, OpenAICompatibleModel

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


async def test_primary_failure_uses_configured_fallback() -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["model"])
        if body["model"] == "primary":
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"answer":"ok"}'}}]},
        )

    model = OpenAICompatibleModel(
        Settings(
            model_api_key="test-key",
            model_name="primary",
            model_fallback_name="fallback",
            model_request_timeout_seconds=1,
        ),
        transport=httpx.MockTransport(handler),
    )
    result = await model.complete_json(
        system="system", prompt="prompt", json_schema=SCHEMA
    )
    assert result == {"answer": "ok"}
    assert calls == ["primary", "fallback"]


async def test_connectivity_failure_reports_each_candidate_without_secret() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("network unavailable", request=request)

    model = OpenAICompatibleModel(
        Settings(
            model_api_key="must-never-appear",
            model_name="primary",
            model_fallback_name="fallback",
            model_request_timeout_seconds=1,
        ),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelError) as captured:
        await model.complete_json(system="system", prompt="prompt", json_schema=SCHEMA)
    rendered = str(captured.value)
    assert "primary:ConnectTimeout" in rendered
    assert "fallback:ConnectTimeout" in rendered
    assert "must-never-appear" not in rendered
