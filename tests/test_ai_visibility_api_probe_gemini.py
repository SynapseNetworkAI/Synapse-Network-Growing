from scripts.growth import run_ai_visibility_api_probe as api_probe


def test_api_probe_supports_gemini_and_genimi_alias(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GENIMI_API_KEY", "test-genimi-key")

    assert api_probe.parse_api_platforms("chatgpt,gemini") == ["chatgpt", "gemini"]
    assert api_probe.platform_api_key("gemini") == "test-genimi-key"
    assert api_probe.missing_key_blockers(["gemini"]) == []


def test_api_probe_reports_both_gemini_key_names_when_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GENIMI_API_KEY", raising=False)

    assert api_probe.missing_key_blockers(["gemini"]) == [
        {"platform": "gemini", "missing_env": "GEMINI_API_KEY or GENIMI_API_KEY"}
    ]


def test_call_gemini_uses_grounded_search_payload(monkeypatch):
    monkeypatch.setenv("GENIMI_API_KEY", "test-genimi-key")

    captured = {}

    def fake_post_json(url: str, payload: dict, headers: dict):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return (
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        "Synapse Remote MCP exposes "
                                        "discover_services, invoke_and_pay, "
                                        "and get_receipt for Agent Credentials."
                                    )
                                }
                            ]
                        },
                        "groundingMetadata": {
                            "groundingChunks": [
                                {
                                    "web": {
                                        "uri": "https://www.synapse-network.ai/",
                                        "title": "Synapse Network",
                                    }
                                }
                            ]
                        },
                    }
                ]
            },
            "gemini-request",
        )

    monkeypatch.setattr(api_probe.probe_adapters, "post_json", fake_post_json)

    payload = api_probe.call_gemini("MCP server for paid API calls")

    assert "gemini-2.5-flash:generateContent" in captured["url"]
    assert captured["headers"] == {"x-goog-api-key": "test-genimi-key"}
    assert captured["payload"]["tools"] == [{"google_search": {}}]
    assert payload["synapse_mentioned"] is True
    assert payload["synapse_cited"] is True
    assert payload["cited_urls"] == ["https://www.synapse-network.ai/"]


def test_api_probe_normalizes_markdown_citation_url_suffixes():
    urls = api_probe.probe_adapters.extract_urls(
        {
            "answer": (
                "Endpoint: https://mcp.synapse-network.ai/mcp.**[[1]] "
                "or `https://mcp.synapse-network.ai/mcp`."
            )
        }
    )

    assert urls == ["https://mcp.synapse-network.ai/mcp"]


def test_api_probe_collision_domains_use_boundaries():
    official = api_probe.answer_payload(
        platform="grok",
        model="grok-test",
        text="SynapseNetwork.ai documents the Remote MCP endpoint.",
        urls=["https://github.com/synapsenetworkai/synapse-network-mcp-server"],
        request_id="req-1",
    )
    collision = api_probe.answer_payload(
        platform="grok",
        model="grok-test",
        text="The unrelated Synapse Protocol site is https://synapse.network/.",
        urls=["https://synapse.network/"],
        request_id="req-2",
    )

    assert official["synapse_cited"] is True
    assert "synapse.network" not in official["competitor_mentions"]
    assert "synapse.network" in collision["competitor_mentions"]


def test_redact_secrets_includes_genimi_alias(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai")
    monkeypatch.setenv("GENIMI_API_KEY", "secret-genimi")

    redacted = api_probe.redact_secrets("bad secret-openai and secret-genimi")

    assert "secret-openai" not in redacted
    assert "secret-genimi" not in redacted
    assert redacted.count("[REDACTED]") == 2
