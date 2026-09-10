from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    model_base_url: str = "https://openrouter.ai/api/v1"
    model_api_key: str | None = None
    model_name: str = "z-ai/glm-5.3-flash"
    model_fallback_name: str = "deepseek/deepseek-v4-flash-0731"
    model_max_output_tokens: int = 800
    model_request_timeout_seconds: float = 45.0
    arena_base_url: str | None = None
    arena_api_token: str | None = None
    agent_node_id: str | None = None
    sharednet_base_url: str = "https://www.sharednet.ai"
    sharednet_room_id: str | None = None
    sharednet_invite_token: str | None = None
    sharednet_member_token: str | None = None
    sharednet_last_sequence: int = 0
    sharednet_agent_name: str = "sharedos-commerce-agent"
    sharednet_runtime_kind: str = "codex"
    seller_api_token: str | None = None
    ledger_path: str = "./commerce.sqlite3"
    checkpoint_path: str = "./checkpoints.sqlite3"

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            model_base_url=os.getenv("MODEL_BASE_URL", defaults.model_base_url),
            model_api_key=os.getenv("MODEL_API_KEY") or None,
            model_name=os.getenv("MODEL_NAME", defaults.model_name),
            model_fallback_name=os.getenv(
                "MODEL_FALLBACK_NAME", defaults.model_fallback_name
            ),
            model_max_output_tokens=int(
                os.getenv("MODEL_MAX_OUTPUT_TOKENS", str(defaults.model_max_output_tokens))
            ),
            model_request_timeout_seconds=float(
                os.getenv(
                    "MODEL_REQUEST_TIMEOUT_SECONDS",
                    str(defaults.model_request_timeout_seconds),
                )
            ),
            arena_base_url=os.getenv("ARENA_BASE_URL") or None,
            arena_api_token=os.getenv("ARENA_API_TOKEN") or None,
            agent_node_id=os.getenv("AGENT_NODE_ID") or None,
            sharednet_base_url=os.getenv(
                "SHAREDNET_BASE_URL", defaults.sharednet_base_url
            ),
            sharednet_room_id=os.getenv("SHAREDNET_ROOM_ID") or None,
            sharednet_invite_token=os.getenv("SHAREDNET_INVITE_TOKEN") or None,
            sharednet_member_token=os.getenv("SHAREDNET_MEMBER_TOKEN") or None,
            sharednet_last_sequence=int(
                os.getenv(
                    "SHAREDNET_LAST_SEQUENCE",
                    str(defaults.sharednet_last_sequence),
                )
            ),
            sharednet_agent_name=os.getenv(
                "SHAREDNET_AGENT_NAME", defaults.sharednet_agent_name
            ),
            sharednet_runtime_kind=os.getenv(
                "SHAREDNET_RUNTIME_KIND", defaults.sharednet_runtime_kind
            ),
            seller_api_token=os.getenv("SELLER_API_TOKEN") or None,
            ledger_path=os.getenv("LEDGER_PATH", defaults.ledger_path),
            checkpoint_path=os.getenv(
                "CHECKPOINT_PATH", defaults.checkpoint_path
            ),
        )
