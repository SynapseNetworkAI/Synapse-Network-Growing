from __future__ import annotations

from unittest.mock import patch

from server import config
from server.services.runtime.codex_cli import CodexExecResult
from server.services.runtime.codex_sdk import CodexSDKPlanResult
from server.services.workflows.planner_provider import (
    CodexCliPlannerAdapter,
    CodexSdkPlannerAdapter,
    LLMPlannerAdapter,
    PlannerRequest,
    generate_planner_text,
    resolve_planner_backend,
    resolve_planner_model,
)


def test_resolve_planner_backend_prefers_explicit_config(monkeypatch):
    monkeypatch.setattr(config, "PLANNER_BACKEND", "codex_sdk")
    monkeypatch.setattr(config, "ORCHESTRATION_BACKEND", "copilot_sdk")
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")

    assert resolve_planner_backend() == "codex_sdk"


def test_resolve_planner_backend_falls_back_to_orchestration_backend(monkeypatch):
    monkeypatch.setattr(config, "PLANNER_BACKEND", "")
    monkeypatch.setattr(config, "ORCHESTRATION_BACKEND", "copilot_sdk")
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")

    assert resolve_planner_backend() == "copilot"


def test_resolve_planner_model_allows_explicit_override(monkeypatch):
    monkeypatch.setattr(config, "PLANNER_MODEL", "planner-special")
    monkeypatch.setattr(config, "CODEX_SDK_MODEL", "gpt-5.4")

    assert resolve_planner_model("codex_sdk") == "planner-special"


def test_llm_planner_adapter_does_not_write_codex_session_metadata(monkeypatch):
    class FakeProvider:
        def call(self, system_prompt, prompt, model, temperature, timeout):
            return "LLM plan", 13

    metadata: dict[str, object] = {}
    monkeypatch.setattr(config, "PLANNER_BACKEND", "claude")
    monkeypatch.setattr(config, "PLANNER_MODEL", "claude-test")
    monkeypatch.setattr(config, "PLANNER_TIMEOUT", 123)
    monkeypatch.setattr("server.services.workflows.planner_provider.get_provider", lambda name: FakeProvider())

    response = generate_planner_text(PlannerRequest(prompt="Need plan", system_prompt="Plan", metadata=metadata))

    assert response.text == "LLM plan"
    assert response.tokens == 13
    assert response.backend == "claude"
    assert metadata["planning_backend"] == "claude"
    assert metadata["planning_model"] == "claude-test"
    assert "planning_session_id" not in metadata
    assert isinstance(LLMPlannerAdapter("claude"), LLMPlannerAdapter)


def test_codex_cli_planner_adapter_records_session_metadata(monkeypatch, tmp_path):
    output_path = tmp_path / "runtime" / "plans" / "plan.md"
    metadata: dict[str, object] = {}
    monkeypatch.setattr(config, "PLANNER_BACKEND", "codex_cli")
    monkeypatch.setattr(config, "PLANNER_MODEL", "gpt-5.4")
    monkeypatch.setattr(config, "PLANNER_TIMEOUT", 456)

    with patch(
        "server.services.workflows.planner_provider.run_codex_exec",
        return_value=CodexExecResult(
            text="Codex CLI plan",
            stdout="",
            stderr="",
            exit_code=0,
            execution_time_ms=12,
            command=["codex", "exec"],
            output_path=output_path,
            thread_id="thread-cli-plan",
        ),
    ) as mock_run:
        response = generate_planner_text(PlannerRequest(
            prompt="Raw plan",
            raw_prompt=True,
            cwd=tmp_path,
            output_path=output_path,
            resume_session_id="thread-old",
            metadata=metadata,
        ))

    assert isinstance(CodexCliPlannerAdapter(), CodexCliPlannerAdapter)
    assert response.text == "Codex CLI plan"
    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == 456
    assert kwargs["resume_thread_id"] == "thread-old"
    assert kwargs["sandbox_mode"] == "read-only"
    assert metadata["planning_backend"] == "codex_cli"
    assert metadata["planning_session_id"] == "thread-cli-plan"
    assert metadata["planning_resumed_from_session_id"] == "thread-old"


def test_codex_sdk_planner_adapter_records_session_metadata(monkeypatch, tmp_path):
    output_path = tmp_path / "runtime" / "plans" / "plan.md"
    metadata: dict[str, object] = {}
    monkeypatch.setattr(config, "PLANNER_BACKEND", "codex_sdk")
    monkeypatch.setattr(config, "PLANNER_MODEL", "gpt-5.4")
    monkeypatch.setattr(config, "PLANNER_TIMEOUT", 789)

    with patch(
        "server.services.workflows.planner_provider.run_codex_sdk_plan",
        return_value=CodexSDKPlanResult(
            text="Codex SDK plan",
            thread_id="thread-sdk-plan",
            turn_id="turn-sdk-plan",
            usage={"total_tokens": 9},
            status="completed",
            execution_time_ms=12,
            output_path=output_path,
            metadata={},
        ),
    ) as mock_run:
        response = generate_planner_text(PlannerRequest(
            prompt="Need plan",
            system_prompt="Plan well",
            cwd=tmp_path,
            output_path=output_path,
            resume_session_id="thread-old",
            metadata=metadata,
        ))

    assert isinstance(CodexSdkPlannerAdapter(), CodexSdkPlannerAdapter)
    assert response.text == "Codex SDK plan"
    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == 789
    assert kwargs["resume_thread_id"] == "thread-old"
    assert "# System Instructions" in kwargs["prompt"]
    assert metadata["planning_backend"] == "codex_sdk"
    assert metadata["planning_session_id"] == "thread-sdk-plan"
    assert metadata["planning_turn_id"] == "turn-sdk-plan"
