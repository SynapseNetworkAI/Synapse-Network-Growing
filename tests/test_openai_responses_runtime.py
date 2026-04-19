from __future__ import annotations

from unittest.mock import patch

from server import config
from server.services.agents.llm_adapter import OpenAIProvider


def test_resolve_orchestration_backend_for_openai_session():
    assert config.resolve_orchestration_backend(provider="openai", execution_mode="session", override="") == "openai_responses"


def test_resolve_orchestration_backend_prefers_explicit_override():
    assert config.resolve_orchestration_backend(
        provider="openai",
        execution_mode="session",
        override="copilot_sdk",
    ) == "copilot_sdk"


def test_openai_provider_normalizes_provider_name_model_alias_for_chat_calls(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    provider = OpenAIProvider()

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 7},
            }

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["model"] = json["model"]
        return FakeResponse()

    with patch("httpx.post", side_effect=fake_post):
        text, tokens = provider.call("sys", "user", "openai", 0.1, 30)

    assert text == "ok"
    assert tokens == 7
    assert captured["model"] == "gpt-4o"


def test_openai_provider_normalizes_provider_name_model_alias_for_responses(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    provider = OpenAIProvider()

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id": "resp_123", "status": "in_progress"}

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["model"] = json["model"]
        return FakeResponse()

    with patch("httpx.post", side_effect=fake_post):
        payload = provider.create_response(
            instructions="plan",
            user_input="task",
            model="openai",
            temperature=0.1,
            timeout=30,
            background=False,
        )

    assert payload["id"] == "resp_123"
    assert captured["model"] == "gpt-4o"
