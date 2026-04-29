import json
from pathlib import Path

import pytest

from server.database import SocialReplyItemRow, SocialRepostCandidateRow
from server.services.runtime.codex_cli import CodexExecResult
from server.services.social import reply_agent, reply_records


def _candidate(**overrides):
    data = {
        "id": 7,
        "source_url": "https://x.com/OpenAI/status/12345",
        "author_handle": "OpenAI",
        "source_text": "GPT-5.5 improves coding and research workflows for agent builders.",
        "suggested_quote": "Agent workflows also need governed API access and settlement.",
    }
    data.update(overrides)
    return SocialRepostCandidateRow(**data)


def _codex_result(text: str, *, exit_code: int = 0, stderr: str = "", stdout: str = ""):
    return CodexExecResult(
        text=text,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        execution_time_ms=12,
        command=["codex"],
        output_path=Path("/tmp/reply.json"),
        thread_id="thread-1",
        json_event_count=2,
    )


def test_reply_json_parsing_and_validation_helpers(tmp_path):
    assert reply_agent._bounded_excerpt("abc", max_chars=5) == "abc"
    assert reply_agent._bounded_excerpt("abcdef", max_chars=5).endswith("[Truncated]")
    assert reply_agent._read_context_file(tmp_path / "missing.md", max_chars=10) == ""
    with pytest.raises(ValueError, match="required context file missing"):
        reply_agent._read_context_file(
            tmp_path / "missing.md", max_chars=10, required=True
        )
    context = tmp_path / "context.md"
    context.write_text("x" * 20, encoding="utf-8")
    assert reply_agent._read_context_file(context, max_chars=5).endswith("[Truncated]")
    assert reply_agent._normalize_for_check(" A\n B ") == "a b"


def test_reply_json_parser_accepts_fences_and_embedded_objects():
    parsed = reply_agent._parse_generated_reply(
        '```json\n{"reply":"Useful angle","risk_level":"weird","generation_reason":"specific"}\n```'
    )
    assert parsed.suggested_reply == "Useful angle"
    assert parsed.risk_level == "normal"
    embedded = reply_agent._parse_generated_reply(
        'noise {"suggested_reply":"Agent builders need rails.","risk_level":"elevated","rationale":"ties to source"} tail'
    )
    assert embedded.risk_level == "elevated"
    with pytest.raises(ValueError, match="did not return JSON"):
        reply_agent._parse_generated_reply("not json")
    with pytest.raises(ValueError, match="must include"):
        reply_agent._parse_generated_reply('{"suggested_reply":"missing rationale"}')
    with pytest.raises(ValueError, match="must be an object"):
        reply_agent._parse_generated_reply('["not-object"]')


def test_reply_prompt_builder_reads_context(monkeypatch, tmp_path):
    (tmp_path / ".agents" / "skills" / "social-content").mkdir(parents=True)
    (tmp_path / ".agents" / "product-marketing-context.md").write_text(
        "Product context", encoding="utf-8"
    )
    (tmp_path / ".agents" / "skills" / "social-content" / "SKILL.md").write_text(
        "Social rules", encoding="utf-8"
    )
    monkeypatch.setattr(reply_agent.config, "PROJECT_ROOT", tmp_path)
    system_prompt, user_prompt, sources = reply_agent._build_reply_generation_prompt(
        _candidate()
    )
    assert "X reply agent" in system_prompt
    assert "Product context" in user_prompt
    assert "Social rules" in user_prompt
    assert sources == ("product-marketing-context", "social-content")
    assert "OpenAI" in user_prompt


def test_reply_codex_paths_success_failure_and_fallback(monkeypatch):
    payload = json.dumps(
        {
            "suggested_reply": "Specific reply",
            "risk_level": "normal",
            "rationale": "good fit",
        }
    )
    assert (
        reply_agent._codex_nonzero_can_use_reply_json(
            _codex_result(payload, exit_code=1)
        )
        is True
    )
    assert (
        reply_agent._codex_nonzero_can_use_reply_json(_codex_result("", exit_code=1))
        is False
    )
    assert reply_agent._is_codex_model_compatibility_result(
        _codex_result("", exit_code=1, stderr="requires a newer version of codex")
    )
    monkeypatch.setattr(
        reply_agent.config, "SOCIAL_CONTENT_LLM_FALLBACK_MODEL", "gpt-5.4,gpt-5.3"
    )
    assert reply_agent._social_codex_fallback_models("gpt-5.5") == [
        "gpt-5.4",
        "gpt-5.3",
    ]

    calls = []

    def fake_run(system_prompt, user_prompt, *, model, timeout):
        calls.append(model)
        if model == "gpt-5.5":
            return _codex_result(
                "", exit_code=1, stderr="requires a newer version of codex"
            )
        return _codex_result(payload)

    monkeypatch.setattr(reply_agent, "_run_reply_codex_once", fake_run)
    text, metadata, model = reply_agent._call_reply_codex(
        "system", "user", model="gpt-5.5", timeout=30
    )
    assert json.loads(text)["suggested_reply"] == "Specific reply"
    assert metadata["fallback_used"] is True
    assert calls == ["gpt-5.5", "gpt-5.4"]
    assert model == "gpt-5.4"
    assert "codex_cli_failed" in reply_agent._codex_failure_detail(
        _codex_result("", exit_code=2), model="bad"
    )


def test_generate_x_reply_for_candidate_codex_and_provider_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(
        reply_agent,
        "_build_reply_generation_prompt",
        lambda candidate: ("system", "user", ("ctx",)),
    )
    monkeypatch.setattr(reply_agent.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex")
    monkeypatch.setattr(reply_agent.config, "SOCIAL_CONTENT_LLM_MODEL", "gpt-test")
    monkeypatch.setattr(reply_agent.config, "SOCIAL_CONTENT_LLM_TIMEOUT", 31)
    monkeypatch.setattr(
        reply_agent,
        "_call_reply_codex",
        lambda *args, **kwargs: (
            '{"suggested_reply":"Agent builders need governed API access too.","risk_level":"normal","rationale":"specific to tools"}',
            {"provider": "codex"},
            "gpt-test",
        ),
    )
    generated = reply_agent.generate_x_reply_for_candidate(_candidate())
    assert generated.generation_metadata["context_sources"] == ["ctx"]

    class FakeProvider:
        def call(self, system_prompt, user_prompt, model, temperature, timeout):
            return (
                '{"suggested_reply":"Provider path reply about settlement rails.","risk_level":"normal","rationale":"specific"}',
                12,
            )

    monkeypatch.setattr(reply_agent.config, "SOCIAL_CONTENT_LLM_PROVIDER", "fake")
    monkeypatch.setattr(reply_agent, "get_provider", lambda name: FakeProvider())
    assert reply_agent.generate_x_reply_for_candidate(_candidate()).model == "gpt-test"


def test_reply_validation_blocks_unsafe_or_low_value_output():
    candidate = _candidate(source_text="A" * 140)
    valid = reply_agent.GeneratedXReply(
        "Agent builders need governed access for API-heavy work.", "normal", "specific"
    )
    reply_agent._validate_generated_reply(candidate, valid)
    blocked_cases = [
        reply_agent.GeneratedXReply("Great point!", "normal", "generic"),
        reply_agent.GeneratedXReply(
            "Use token: abcdefghijklmnopqrstuvwxyz", "normal", "leak"
        ),
        reply_agent.GeneratedXReply(
            "Guaranteed profit from AI agents", "normal", "bad"
        ),
        reply_agent.GeneratedXReply("A" * 130, "normal", "copy"),
    ]
    for generated in blocked_cases:
        with pytest.raises(ValueError, match="agent_reply_generation_failed"):
            reply_agent._validate_generated_reply(candidate, generated)


def test_reply_record_helpers_apply_success_failure_and_blocked():
    candidate = _candidate(id=42, source_url="https://x.com/OpenAI/status/987")
    row = SocialReplyItemRow()
    generated = reply_agent.GeneratedXReply(
        "Specific reply",
        "normal",
        "specific rationale",
        generation_metadata={"provider": "test"},
    )
    reply_records.apply_generated_reply_to_row(
        row,
        candidate,
        actor="tester",
        generated=generated,
        failure_summary=None,
        policy={"status": "passed"},
    )
    assert row.status == "needs_review"
    assert row.source_post_id == "987"
    metadata = json.loads(row.metadata_json)
    assert metadata["generated_by"] == "social_reply_agent_v1"
    assert metadata["template_fallback"] is False
    assert reply_records.extract_x_post_id("https://x.com/i/web/statuses/234") == "234"
    assert reply_records.extract_x_post_id("https://x.com/share?tweet_id=345") == "345"
    assert reply_records.extract_x_post_id(None) == ""

    reply_records.apply_generated_reply_to_row(
        row,
        candidate,
        actor="tester",
        generated=generated,
        failure_summary=None,
        policy={"status": "blocked", "blocked_reasons": ["unsafe"]},
    )
    assert row.status == "failed"
    assert row.failure_summary == "Blocked: unsafe"
    reply_records.apply_generated_reply_to_row(
        row, candidate, actor="tester", generated=None, failure_summary="boom"
    )
    assert row.status == "failed"
    assert row.suggested_reply == ""
    assert json.loads(row.metadata_json)["generation_failed"] is True
    assert reply_records.reply_agent_failure_summary(
        ValueError("plain failure")
    ).startswith("agent_reply_generation_failed:")
