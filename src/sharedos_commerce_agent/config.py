from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True, slots=True)
class Settings:
    model_base_url: str = "https://openrouter.ai/api/v1"
    model_api_key: str | None = field(default=None, repr=False)
    model_name: str = "z-ai/glm-5.3-flash"
    model_fallback_name: str = "deepseek/deepseek-v4-flash-0731"
    model_max_output_tokens: int = 800
    model_request_timeout_seconds: float = 45.0
    arena_base_url: str | None = None
    arena_api_token: str | None = field(default=None, repr=False)
    arena_discover_route: str | None = None
    arena_invoke_route: str | None = None
    arena_critique_route: str | None = None
    arena_ranking_route: str | None = None
    arena_buy_route: str | None = None
    arena_reconcile_route: str | None = None
    agent_node_id: str | None = None
    service_base_url: str | None = None
    sharednet_base_url: str = "https://www.sharednet.ai"
    sharednet_room_id: str | None = None
    sharednet_invite_token: str | None = field(default=None, repr=False)
    sharednet_member_token: str | None = field(default=None, repr=False)
    sharednet_member_id: str | None = None
    sharednet_last_sequence: int = 0
    sharednet_agent_name: str = "sharedos-commerce-agent"
    sharednet_runtime_kind: str = "codex"
    sharednet_state_path: str = "./.sharednet/runtime-identity.json"
    sharednet_inbox_path: str = "./.sharednet/inbox.sqlite3"
    sharednet_cli_credential_path: str | None = field(default=None, repr=False)
    sharednet_allow_anonymous_join: bool = False
    seller_api_token: str | None = field(default=None, repr=False)
    seller_agent_tokens_json: str | None = field(default=None, repr=False)
    ledger_path: str = "./commerce.sqlite3"
    checkpoint_path: str = "./checkpoints.sqlite3"
    operation_journal_path: str = "./outbound-operations.sqlite3"

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
            arena_discover_route=os.getenv("ARENA_DISCOVER_ROUTE") or None,
            arena_invoke_route=os.getenv("ARENA_INVOKE_ROUTE") or None,
            arena_critique_route=os.getenv("ARENA_CRITIQUE_ROUTE") or None,
            arena_ranking_route=os.getenv("ARENA_RANKING_ROUTE") or None,
            arena_buy_route=os.getenv("ARENA_BUY_ROUTE") or None,
            arena_reconcile_route=os.getenv("ARENA_RECONCILE_ROUTE") or None,
            agent_node_id=os.getenv("AGENT_NODE_ID") or None,
            service_base_url=os.getenv("SERVICE_BASE_URL") or None,
            sharednet_base_url=os.getenv(
                "SHAREDNET_BASE_URL", defaults.sharednet_base_url
            ),
            sharednet_room_id=os.getenv("SHAREDNET_ROOM_ID") or None,
            sharednet_invite_token=os.getenv("SHAREDNET_INVITE_TOKEN") or None,
            sharednet_member_token=os.getenv("SHAREDNET_MEMBER_TOKEN") or None,
            sharednet_member_id=os.getenv("SHAREDNET_MEMBER_ID") or None,
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
            sharednet_state_path=os.getenv(
                "SHAREDNET_STATE_PATH", defaults.sharednet_state_path
            ),
            sharednet_inbox_path=os.getenv(
                "SHAREDNET_INBOX_PATH", defaults.sharednet_inbox_path
            ),
            sharednet_cli_credential_path=(
                os.getenv("SHAREDNET_CLI_CREDENTIAL_PATH") or None
            ),
            sharednet_allow_anonymous_join=_env_flag(
                "SHAREDNET_ALLOW_ANONYMOUS_JOIN",
                defaults.sharednet_allow_anonymous_join,
            ),
            seller_api_token=os.getenv("SELLER_API_TOKEN") or None,
            seller_agent_tokens_json=os.getenv("SELLER_AGENT_TOKENS_JSON") or None,
            ledger_path=os.getenv("LEDGER_PATH", defaults.ledger_path),
            checkpoint_path=os.getenv(
                "CHECKPOINT_PATH", defaults.checkpoint_path
            ),
            operation_journal_path=os.getenv(
                "OPERATION_JOURNAL_PATH", defaults.operation_journal_path
            ),
        )
