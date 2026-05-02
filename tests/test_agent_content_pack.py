import pytest

from server.services.runtime.codex_cli import CodexExecResult
from server.services.social import agent_content_pack
from server.services.social.agent_content_pack import (
    AgentContentGenerationError,
    AgentJsonParseError,
    _call_content_agent,
    _call_content_codex,
    _content_codex_fallback_models,
    generate_canonical_asset_pack,
    generate_platform_task_draft,
    parse_agent_json_output,
)
from server.services.social.context_tags import (
    ContextTagSnippet,
)
from server.services.social.distribution_asset_signals import AssetSignal


def _codex_result(
    *,
    text: str,
    exit_code: int,
    model: str,
    tmp_path,
) -> CodexExecResult:
    return CodexExecResult(
        text=text,
        stdout=text,
        stderr="",
        exit_code=exit_code,
        execution_time_ms=1,
        command=["codex", "exec", "-m", model],
        output_path=tmp_path / f"{model}.json",
    )


def test_parse_agent_json_output_accepts_plain_and_fenced_json():
    assert parse_agent_json_output('{"title":"A"}').data["title"] == "A"
    assert parse_agent_json_output('```json\n{"title":"B"}\n```').data["title"] == "B"
    assert parse_agent_json_output('```\n{"title":"C"}\n```').data["title"] == "C"
    assert parse_agent_json_output('json {"title":"D"}').data["title"] == "D"


def test_parse_agent_json_output_extracts_first_embedded_object():
    parsed = parse_agent_json_output('Here is the JSON:\n{"title":"A"}\nThanks')
    assert parsed.data == {"title": "A"}
    assert parsed.cleaned_text == '{"title":"A"}'


@pytest.mark.parametrize(
    "raw",
    [
        "title: A\nbody: B",
        "| title | body |",
        '{"title":',
        '["not-object"]',
    ],
)
def test_parse_agent_json_output_fails_closed_for_invalid_shapes(raw):
    with pytest.raises(AgentJsonParseError, match="agent_json_parse_failed"):
        parse_agent_json_output(raw)


def test_content_codex_fallback_models_use_configured_models_only(monkeypatch):
    monkeypatch.setattr(
        agent_content_pack.config, "SOCIAL_CONTENT_LLM_FALLBACK_MODEL", "gpt-5.4"
    )

    assert _content_codex_fallback_models("gpt-5-codex") == ["gpt-5.4"]
    assert _content_codex_fallback_models("gpt-5.4") == []


def test_content_codex_unsupported_model_reports_root_cause(monkeypatch, tmp_path):
    unsupported_payload = (
        '{"type":"error","error":{"message":"The gpt-5-codex model is not '
        'supported when using Codex with a ChatGPT account."}}'
    )
    monkeypatch.setattr(
        agent_content_pack.config, "SOCIAL_CONTENT_LLM_FALLBACK_MODEL", ""
    )
    monkeypatch.setattr(
        agent_content_pack,
        "run_codex_exec",
        lambda **kwargs: _codex_result(
            text=unsupported_payload,
            exit_code=1,
            model=kwargs["model"],
            tmp_path=tmp_path,
        ),
    )

    with pytest.raises(AgentContentGenerationError) as exc:
        _call_content_codex(
            "system",
            "user",
            output_schema={"type": "object"},
            artifact_prefix="test",
            model="gpt-5-codex",
            timeout=30,
        )

    message = str(exc.value)
    assert "not supported when using Codex with a ChatGPT account" in message
    assert "title_empty" not in message


def test_content_codex_falls_back_to_gpt54_and_records_attempts(monkeypatch, tmp_path):
    unsupported_payload = (
        '{"type":"error","error":{"message":"The gpt-5-codex model is not '
        'supported when using Codex with a ChatGPT account."}}'
    )
    valid_payload = (
        '{"title":"A","summary":"B","body":"C","asset_type":"shipping_proof",'
        '"source_type":"asset_planner"}'
    )
    calls: list[str] = []

    monkeypatch.setattr(
        agent_content_pack.config, "SOCIAL_CONTENT_LLM_FALLBACK_MODEL", "gpt-5.4"
    )

    def fake_run_codex_exec(**kwargs):
        model = kwargs["model"]
        calls.append(model)
        if model == "gpt-5-codex":
            return _codex_result(
                text=unsupported_payload,
                exit_code=1,
                model=model,
                tmp_path=tmp_path,
            )
        return _codex_result(
            text=valid_payload,
            exit_code=0,
            model=model,
            tmp_path=tmp_path,
        )

    monkeypatch.setattr(agent_content_pack, "run_codex_exec", fake_run_codex_exec)

    raw_text, metadata, model = _call_content_codex(
        "system",
        "user",
        output_schema={"type": "object"},
        artifact_prefix="test",
        model="gpt-5-codex",
        timeout=30,
    )

    assert parse_agent_json_output(raw_text).data["title"] == "A"
    assert calls == ["gpt-5-codex", "gpt-5.4"]
    assert model == "gpt-5.4"
    assert metadata["model"] == "gpt-5.4"
    assert metadata["attempted_models"] == ["gpt-5-codex", "gpt-5.4"]


@pytest.mark.parametrize(
    ("provider_name", "failure"),
    [
        ("openai", "LLM API error 429: insufficient_quota"),
        ("claude", "LLM API error 401: invalid x-api-key"),
        (
            "copilot",
            "Personal Access Tokens are not supported for LLM_PROVIDER=copilot",
        ),
    ],
)
def test_content_agent_provider_failures_remain_fail_closed(
    monkeypatch, provider_name, failure
):
    class FailingProvider:
        def call(self, *_args, **_kwargs):
            raise RuntimeError(failure)

    monkeypatch.setattr(
        agent_content_pack.config, "SOCIAL_CONTENT_LLM_PROVIDER", provider_name
    )
    monkeypatch.setattr(agent_content_pack.config, "SOCIAL_CONTENT_LLM_MODEL", "gpt-4o")
    monkeypatch.setattr(
        agent_content_pack, "get_provider", lambda _name: FailingProvider()
    )

    with pytest.raises(RuntimeError, match=failure.split(":", 1)[0]):
        _call_content_agent(
            "system",
            "user",
            output_schema={"type": "object"},
            artifact_prefix="provider-failure",
        )


def test_generate_canonical_asset_pack_uses_resolved_context_and_metadata(
    monkeypatch,
):
    signal = AssetSignal(
        signal_type="developer_education",
        source_ref="product_opportunity:1",
        title="SDK quickstart",
        summary="Teach developers how to integrate Synapse.",
        score=0.9,
    )
    snippet = ContextTagSnippet(
        ref_key="synapse-network-sdk:quickstart",
        project_key="synapse-network-sdk",
        file_path="README.md",
        label="quickstart",
        language="markdown",
        excerpt="Quickstart code",
        content_hash="abc",
    )

    monkeypatch.setattr(
        agent_content_pack,
        "_call_content_agent",
        lambda *_args, **_kwargs: (
            (
                '{"title":"SDK quickstart","summary":"Public summary",'
                '"body":"Public body","asset_type":"developer_education",'
                '"source_type":"asset_planner","goal_key":"sdk_developer_quickstart",'
                '"key_facts":["fact"],'
                '"code_blocks":[{"language":"java","title":"Demo","code":"class Demo {}"}],'
                '"recommended_channels":["x","devto"],'
                '"source_signal_refs":["product_opportunity:1"],'
                '"generation_reason":"Useful developer education"}'
            ),
            {"provider": "codex", "attempted_models": ["gpt-5.4"]},
            "gpt-5.4",
        ),
    )
    monkeypatch.setattr(
        agent_content_pack, "_resolve_context_refs", lambda _refs: [snippet]
    )

    pack = generate_canonical_asset_pack(
        asset_type="developer_education",
        local_date="2026-05-02",
        signals=[signal],
    )

    assert pack.title == "SDK quickstart"
    assert pack.goal_key == "sdk_developer_quickstart"
    assert pack.context_refs == ["synapse-network-sdk:quickstart"]
    assert pack.context_sources == ["synapse-network-sdk:quickstart"]
    assert pack.generation_metadata["model"] == "gpt-5.4"
    assert pack.code_blocks[0].language == "java"


def test_generate_platform_task_draft_adds_canonical_warning(monkeypatch):
    monkeypatch.setattr(
        agent_content_pack,
        "_call_content_agent",
        lambda *_args, **_kwargs: (
            (
                '{"platform_title":"DEV title","platform_body":"DEV body",'
                '"operator_checklist":"Set canonical URL before publishing.",'
                '"risk_level":"normal","rationale":"fits DEV"}'
            ),
            {"provider": "codex"},
            "gpt-5.4",
        ),
    )

    draft = generate_platform_task_draft(
        asset_title="Asset",
        asset_summary="Summary",
        asset_body="Body",
        asset_metadata={"key_facts": ["fact"]},
        canonical_url=None,
        platform="devto",
        channel_key="dev.to",
        display_name="DEV",
    )

    assert draft.title == "DEV title"
    assert draft.metadata["warning"] == "canonical_url_missing"
    assert draft.metadata["generated_by"] == "agent_content_pack_v1"


def test_required_context_resolution_wraps_missing_tag():
    with pytest.raises(
        AgentContentGenerationError, match="insufficient_source_context"
    ):
        agent_content_pack._resolve_context_refs(["missing:tag"])


def test_payload_helpers_fail_closed_for_missing_required_text():
    with pytest.raises(AgentContentGenerationError, match="title_empty"):
        agent_content_pack._canonical_pack_from_payload(
            {
                "summary": "S",
                "body": "B",
                "asset_type": "shipping_proof",
            }
        )
    draft = agent_content_pack._platform_draft_from_payload(
        {
            "platform_title": "Title",
            "platform_body": "Body",
            "operator_checklist": "Checklist",
        }
    )
    assert draft.risk_level == "normal"
    assert agent_content_pack._string_list("not-list") == []


def test_context_ref_selection_deduplicates_by_asset_need():
    signals = [
        AssetSignal(
            signal_type="developer_education",
            source_ref="sdk",
            title="SDK MCP Spring Boot provider onboarding",
            summary="Quickstart for provider onboarding",
            score=1.0,
        )
    ]

    refs = agent_content_pack._required_context_refs_for_asset(
        "developer_education", signals
    )

    assert refs == [
        "synapse-network-sdk:quickstart",
        "synapse-network-mcp-server:spring_boot_mcp",
        "synapse-network-provider:onboarding",
    ]
