from scripts.growth import run_ai_visibility_api_probe as api_probe
from scripts.growth.record_ai_visibility_probe import validate_records


def test_api_probe_uses_current_claude_default_model():
    assert api_probe.DEFAULT_MODELS["claude"] == "claude-sonnet-4-6"


def test_run_api_probes_records_provider_failures_without_stopping(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-anthropic-key")

    def fake_call_platform(platform: str, query: str):
        if platform == "claude":
            raise RuntimeError(
                "POST https://api.anthropic.com/v1/messages failed with "
                "404 using secret-anthropic-key"
            )
        return {
            "summary": f"{platform} mentions Synapse Network.",
            "synapse_mentioned": True,
            "synapse_cited": False,
            "cited_urls": [],
            "source_urls": [],
            "competitor_mentions": [],
            "missing_facts": [],
            "next_action": "Compare against previous run group.",
            "result_rank": 1,
            "model": f"{platform}-model",
            "request_id": f"{platform}-request",
        }

    monkeypatch.setattr(api_probe, "call_platform", fake_call_platform)

    records = api_probe.run_api_probes(
        feed_key="agent_payment_category_pages",
        run_group="2026-06-18-api-probe",
        platforms=["chatgpt", "claude"],
        queries=["AI agent payment API"],
    )

    assert len(records) == 2
    assert validate_records(records) == []
    claude = next(record for record in records if record.platform == "claude")
    assert claude.synapse_mentioned is False
    assert claude.synapse_cited is False
    assert claude.result_rank == 0
    assert "claude API probe failed" in claude.answer_summary
    assert "secret-anthropic-key" not in claude.answer_summary
    assert "Fix provider/API probe failure" in claude.next_action


def test_provider_failure_redacts_account_identifiers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("XAI_API_KEY", "secret-xai-key")

    def fake_call_platform(platform: str, query: str):  # noqa: ARG001
        raise RuntimeError(
            "POST https://api.x.ai/v1/responses failed with 403: "
            "team e1874538-b2a3-4c03-a773-ccd3373313db used secret-xai-key "
            "for project_proj123456"
        )

    monkeypatch.setattr(api_probe, "call_platform", fake_call_platform)

    records = api_probe.run_api_probes(
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-18-api-probe",
        platforms=["grok"],
        queries=["MCP server for paid API calls"],
    )

    assert validate_records(records) == []
    grok = records[0]
    assert "secret-xai-key" not in grok.answer_summary
    assert "e1874538-b2a3-4c03-a773-ccd3373313db" not in grok.answer_summary
    assert "project_proj123456" not in grok.answer_summary
    assert "team [REDACTED]" in grok.answer_summary


def test_provider_failure_records_platform_model_override(monkeypatch):
    monkeypatch.setenv("GENIMI_API_KEY", "secret-gemini-key")
    monkeypatch.setenv("GEMINI_AI_VISIBILITY_MODEL", "gemini-2.0-flash-lite")

    def fake_call_platform(platform: str, query: str):  # noqa: ARG001
        raise RuntimeError(
            "POST https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.0-flash-lite:generateContent failed with 429"
        )

    monkeypatch.setattr(api_probe, "call_platform", fake_call_platform)

    records = api_probe.run_api_probes(
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-18-api-probe",
        platforms=["gemini"],
        queries=["Synapse Network MCP server for paid API calls"],
    )

    assert validate_records(records) == []
    gemini = records[0]
    assert gemini.metadata["api_model"] == "gemini-2.0-flash-lite"
    assert "secret-gemini-key" not in gemini.answer_summary
