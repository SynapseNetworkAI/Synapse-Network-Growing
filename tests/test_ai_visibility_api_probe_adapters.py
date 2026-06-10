import urllib.error

from scripts.growth import ai_visibility_api_probe_adapters as adapters
from scripts.growth import run_ai_visibility_api_probe as api_probe
from server.services.growth import ai_visibility_release_snapshot as release_snapshot


def test_api_probe_gemini_alias_key_and_text_extraction(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GENIMI_API_KEY", "test-gemini-alias-key")
    assert api_probe.missing_key_blockers(["gemini"]) == []

    captured = {}

    def fake_post_json(url, payload, headers):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return (
            {
                "responseId": "gemini-response-1",
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        "Synapse Network is an AI agent payment "
                                        "layer. Source: https://www.synapse-network.ai/"
                                    )
                                }
                            ]
                        }
                    }
                ],
            },
            "",
        )

    monkeypatch.setattr(adapters, "post_json", fake_post_json)
    answer = adapters.call_gemini("AI agent payment API")

    assert "models/gemini-2.5-flash:generateContent" in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == "test-gemini-alias-key"
    assert captured["payload"]["contents"][0]["parts"][0]["text"]
    assert answer["platform"] == "gemini"
    assert answer["synapse_mentioned"] is True
    assert answer["request_id"] == "gemini-response-1"


def test_answer_payload_rejects_synapse_org_source_host_collision():
    payload = adapters.answer_payload(
        platform="chatgpt",
        model="gpt-test",
        text=(
            "SynapseNetwork's MCP server supports dataset searches and entity "
            "metadata inspection."
        ),
        urls=[
            "https://python-docs.synapse.org/mcp/",
            "https://mcp.synapse.org/",
        ],
        request_id="req-1",
    )

    assert payload["synapse_mentioned"] is False
    assert payload["synapse_cited"] is False
    assert "python-docs.synapse.org" in payload["competitor_mentions"]
    assert "mcp.synapse.org" in payload["competitor_mentions"]


def test_api_probe_default_models_use_current_provider_ids():
    assert adapters.DEFAULT_MODELS["claude"] == "claude-sonnet-4-6"
    assert adapters.DEFAULT_MODELS["gemini"] == "gemini-2.5-flash"


def test_post_json_redacts_secret_values_on_http_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai-value")

    class FakeError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                "https://api.openai.com/v1/responses",
                401,
                "Unauthorized",
                hdrs=None,
                fp=None,
            )

        def read(self):
            return b'{"error":"bad key secret-openai-value"}'

    def fake_urlopen(*_args, **_kwargs):
        raise FakeError()

    monkeypatch.setattr(adapters.urllib.request, "urlopen", fake_urlopen)

    try:
        adapters.post_json(
            adapters.OPENAI_RESPONSES_URL,
            {"model": "test"},
            {"Authorization": "Bearer secret-openai-value"},
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("HTTPError should raise RuntimeError")

    assert "secret-openai-value" not in message
    assert "[REDACTED]" in message


def test_adapter_extractors_cover_provider_shapes_and_nested_urls(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GENIMI_API_KEY", raising=False)

    assert adapters.api_key_for_platform("gemini") == ""
    assert (
        adapters.extract_openai_text(
            {"output": [{"content": [{"text": "OpenAI answer"}, {"type": "image"}]}]}
        )
        == "OpenAI answer"
    )
    assert (
        adapters.extract_anthropic_text(
            {"content": [{"text": "Claude answer"}, {"type": "tool_use"}]}
        )
        == "Claude answer"
    )
    assert adapters.extract_urls(
        {
            "url": "https://www.synapse-network.ai/",
            "summary": "MCPay is documented at https://docs.mcpay.tech/.",
            "items": [
                {"uri": "https://docs.synapse-network.ai/mcp/paid-api-calls"},
                {"url": "mailto:not-web"},
            ],
        }
    ) == [
        "https://docs.mcpay.tech/",
        "https://docs.synapse-network.ai/mcp/paid-api-calls",
        "https://www.synapse-network.ai/",
    ]
    assert adapters.source_hosts(
        ["https://www.synapse-network.ai/", "https://docs.mcpay.tech/path"]
    ) == ["docs.mcpay.tech", "synapse-network.ai"]
    assert "x402" in adapters.competitor_mentions("Compare Synapse and x402", [])
    assert "mcpay" in adapters.competitor_mentions(
        "MCPay and Latch appear in paid MCP results.",
        ["https://docs.mcpay.tech/"],
    )


def test_release_snapshot_next_action_without_blockers():
    assert release_snapshot._next_actions([]) == [
        "Run external answer-engine probes and compare citation results."
    ]
