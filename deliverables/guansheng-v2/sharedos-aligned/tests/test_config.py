from sharedos_commerce_agent.config import Settings


def test_settings_defaults_are_concrete_values(monkeypatch) -> None:
    for name in (
        "MODEL_BASE_URL",
        "MODEL_NAME",
        "MODEL_FALLBACK_NAME",
        "MODEL_MAX_OUTPUT_TOKENS",
        "MODEL_REQUEST_TIMEOUT_SECONDS",
        "SHAREDNET_BASE_URL",
        "SHAREDNET_ROOM_ID",
        "SHAREDNET_INVITE_TOKEN",
        "SHAREDNET_MEMBER_TOKEN",
        "SHAREDNET_LAST_SEQUENCE",
        "SHAREDNET_AGENT_NAME",
        "SHAREDNET_RUNTIME_KIND",
        "OPERATION_JOURNAL_PATH",
        "LEDGER_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()
    assert settings.model_name == "z-ai/glm-5.3-flash"
    assert settings.model_max_output_tokens == 800
    assert settings.sharednet_base_url == "https://www.sharednet.ai"
    assert settings.sharednet_last_sequence == 0
    assert settings.sharednet_runtime_kind == "codex"
    assert settings.operation_journal_path == "./outbound-operations.sqlite3"
