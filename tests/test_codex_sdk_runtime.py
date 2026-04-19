from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from server import config
from server.services.runtime.codex_sdk import CodexSDKPlanResult, run_codex_sdk_plan
from server.services.workflows.planner_provider import (
    PlannerRequest,
    generate_planner_text,
    resolve_planner_backend,
    resolve_planner_model,
)


class _FakeThread:
    id = "thread-sdk-1"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def run(self, prompt: str):
        self.prompts.append(prompt)
        return SimpleNamespace(
            final_response='{"steps":[]}',
            items=[],
            usage={"total_tokens": 11},
            id="turn-sdk-1",
            status="completed",
        )


class _FakeCodex:
    def __init__(self) -> None:
        self.started_kwargs: dict | None = None
        self.resumed: tuple[str, dict] | None = None
        self.thread = _FakeThread()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def thread_start(self, **kwargs):
        self.started_kwargs = kwargs
        return self.thread

    def thread_resume(self, thread_id: str, **kwargs):
        self.resumed = (thread_id, kwargs)
        return self.thread


def test_resolve_orchestration_backend_accepts_codex_sdk_override():
    assert config.resolve_orchestration_backend(provider="codex", execution_mode="session", override="codex_sdk") == "codex_sdk"


def test_codex_sdk_plan_writes_output_and_metadata(tmp_path):
    codex = _FakeCodex()
    output_path = tmp_path / "plan.md"

    result = run_codex_sdk_plan(
        prompt="Plan this",
        cwd=tmp_path,
        output_path=output_path,
        model="gpt-5.4",
        timeout=300,
        sandbox_mode="read-only",
        codex_factory=lambda: codex,
    )

    assert result.text == '{"steps":[]}'
    assert result.thread_id == "thread-sdk-1"
    assert result.turn_id == "turn-sdk-1"
    assert result.usage == {"total_tokens": 11}
    assert output_path.read_text(encoding="utf-8") == '{"steps":[]}'
    metadata = (tmp_path / "metadata.json").read_text(encoding="utf-8")
    assert '"backend": "codex_sdk"' in metadata
    assert '"thread_id": "thread-sdk-1"' in metadata
    assert codex.started_kwargs == {"cwd": str(tmp_path), "sandbox": "read-only", "model": "gpt-5.4"}


def test_codex_sdk_plan_resumes_thread(tmp_path):
    codex = _FakeCodex()

    result = run_codex_sdk_plan(
        prompt="Continue",
        cwd=tmp_path,
        model="gpt-5.4",
        resume_thread_id="thread-existing",
        codex_factory=lambda: codex,
    )

    assert result.thread_id == "thread-sdk-1"
    assert codex.resumed == ("thread-existing", {"cwd": str(tmp_path), "sandbox": "read-only", "model": "gpt-5.4"})


def test_generate_planner_text_uses_codex_sdk_adapter(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PLANNER_BACKEND", "codex_sdk")
    monkeypatch.setattr(config, "PLANNER_MODEL", "gpt-5.4")
    monkeypatch.setattr(config, "PLANNER_TIMEOUT", 300)
    metadata: dict[str, object] = {}
    output_path = tmp_path / "runtime" / "plans" / "plan.md"

    with patch(
        "server.services.workflows.planner_provider.run_codex_sdk_plan",
        return_value=CodexSDKPlanResult(
            text='{"steps":[]}',
            thread_id="thread-sdk-plan",
            turn_id="turn-sdk-plan",
            usage={"total_tokens": 7},
            status="completed",
            execution_time_ms=12,
            output_path=output_path,
            metadata={},
        ),
    ) as mock_run:
        response = generate_planner_text(PlannerRequest(
            prompt="Need a plan",
            system_prompt="Return JSON only",
            cwd=tmp_path,
            output_path=output_path,
            metadata=metadata,
        ))

    assert response.text == '{"steps":[]}'
    assert response.tokens == 0
    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == 300
    assert kwargs["sandbox_mode"] == "read-only"
    assert "# System Instructions" in kwargs["prompt"]
    assert metadata["planning_backend"] == "codex_sdk"
    assert metadata["planning_session_id"] == "thread-sdk-plan"
    assert metadata["planning_turn_id"] == "turn-sdk-plan"


def test_resolve_planner_backend_and_model_support_codex_sdk(monkeypatch):
    monkeypatch.setattr(config, "PLANNER_BACKEND", "")
    monkeypatch.setattr(config, "PLANNER_MODEL", "")
    monkeypatch.setattr(config, "ORCHESTRATION_BACKEND", "codex_sdk")
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "LLM_MODEL", "codex")
    monkeypatch.setattr(config, "CODEX_SDK_MODEL", "gpt-5.4")

    assert resolve_planner_backend() == "codex_sdk"
    assert resolve_planner_model("codex_sdk") == "gpt-5.4"
