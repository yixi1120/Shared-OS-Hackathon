from sharedos_commerce_agent.config import Settings


def test_settings_defaults_are_concrete_values(monkeypatch) -> None:
    for name in (
        "MODEL_BASE_URL",
        "MODEL_NAME",
        "MODEL_FALLBACK_NAME",
        "MODEL_MAX_OUTPUT_TOKENS",
        "MODEL_REQUEST_TIMEOUT_SECONDS",
        "LEDGER_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()
    assert settings.model_name == "z-ai/glm-5.3-flash"
    assert settings.model_max_output_tokens == 800
