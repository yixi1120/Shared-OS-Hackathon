from __future__ import annotations

import json
from asyncio import get_running_loop
from typing import Any

import httpx
from jsonschema import SchemaError, ValidationError, validate

from .config import Settings


class ModelError(RuntimeError):
    pass


class OpenAICompatibleModel:
    """Small client for OpenRouter or any OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not settings.model_api_key:
            raise ModelError("MODEL_API_KEY is required for live model calls")
        self.settings = settings
        self.transport = transport

    async def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        json_schema: dict[str, Any],
        model: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.model_api_key}"}
        async with httpx.AsyncClient(
            base_url=self.settings.model_base_url,
            headers=headers,
            transport=self.transport,
        ) as client:
            requested_model = model or self.settings.model_name
            candidates = [requested_model]
            if model is None and self.settings.model_fallback_name != requested_model:
                candidates.append(self.settings.model_fallback_name)

            deadline = (
                get_running_loop().time() + self.settings.model_request_timeout_seconds
            )
            failures: list[str] = []
            last_error: Exception | None = None
            for index, candidate in enumerate(candidates):
                remaining = deadline - get_running_loop().time()
                if remaining <= 0:
                    failures.append(f"{candidate}:TotalTimeout")
                    break
                attempt_timeout = max(0.5, remaining / max(1, len(candidates) - index))
                body = {
                    "model": candidate,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                f"{system}\nReturn only a JSON object matching this schema: "
                                f"{json.dumps(json_schema, sort_keys=True)}"
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": self.settings.model_max_output_tokens,
                    "response_format": {"type": "json_object"},
                }
                try:
                    response = await client.post(
                        "/chat/completions",
                        json=body,
                        timeout=attempt_timeout,
                    )
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    validate(instance=parsed, schema=json_schema)
                    return parsed
                except (
                    httpx.HTTPError,
                    KeyError,
                    IndexError,
                    json.JSONDecodeError,
                    SchemaError,
                    ValidationError,
                ) as exc:
                    last_error = exc
                    suffix = (
                        f":{exc.response.status_code}"
                        if isinstance(exc, httpx.HTTPStatusError)
                        else ""
                    )
                    failures.append(f"{candidate}:{type(exc).__name__}{suffix}")

            summary = ", ".join(failures) or "UnknownError"
            raise ModelError(f"All model candidates failed: {summary}") from last_error
