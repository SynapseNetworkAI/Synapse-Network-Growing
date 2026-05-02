from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_social_content_llm_defaults_to_supported_codex_model():
    config_text = (PROJECT_ROOT / "server" / "config.py").read_text(encoding="utf-8")

    assert (
        'SOCIAL_CONTENT_LLM_MODEL = os.environ.get("SOCIAL_CONTENT_LLM_MODEL", "gpt-5.4")'
        in config_text
    )
    assert (
        'SOCIAL_CONTENT_LLM_FALLBACK_MODEL = os.environ.get("SOCIAL_CONTENT_LLM_FALLBACK_MODEL", "gpt-5.4")'
        in config_text
    )


def test_env_example_recommends_supported_social_content_model():
    env_text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "SOCIAL_CONTENT_LLM_PROVIDER=codex" in env_text
    assert "SOCIAL_CONTENT_LLM_MODEL=gpt-5.4" in env_text
    assert "SOCIAL_CONTENT_LLM_FALLBACK_MODEL=gpt-5.4" in env_text
    assert "SOCIAL_CONTENT_LLM_MODEL=gpt-5-codex" not in env_text
    assert "SOCIAL_CONTENT_LLM_FALLBACK_MODEL=gpt-5.5" not in env_text
