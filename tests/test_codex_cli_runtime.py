from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from server import config
from server.services.codex_cli import CodexExecResult
from server.services.llm_adapter import CodexCLIProvider
from server.services.task_runtime import CodexCLITaskRuntime, get_task_runtime


def test_resolve_orchestration_backend_for_codex_provider():
    assert config.resolve_orchestration_backend(provider="codex", execution_mode="sync", override="") == "codex_cli"


def test_codex_cli_provider_uses_codex_exec(tmp_path):
    output_path = tmp_path / "last-message.txt"
    output_path.write_text("planned steps", encoding="utf-8")
    provider = CodexCLIProvider()

    with patch("server.services.llm_adapter.run_codex_exec", return_value=CodexExecResult(
        text="planned steps",
        stdout="",
        stderr="",
        exit_code=0,
        execution_time_ms=12,
        command=["codex", "exec"],
        output_path=output_path,
    )) as mock_run:
        text, tokens = provider.call("system", "user", "gpt-5-codex", 0.1, 30)

    assert text == "planned steps"
    assert tokens == 0
    mock_run.assert_called_once()


def test_codex_cli_task_runtime_returns_completed_result(tmp_path):
    runtime = CodexCLITaskRuntime(project_root=tmp_path)

    def _fake_run_codex_exec(*, output_path: Path | None = None, **kwargs):
        assert output_path is not None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("# Done\nUpdated project", encoding="utf-8")
        return CodexExecResult(
            text="# Done\nUpdated project",
            stdout="",
            stderr="",
            exit_code=0,
            execution_time_ms=18,
            command=["codex", "exec"],
            output_path=output_path,
        )

    with patch("server.services.task_runtime.run_codex_exec", side_effect=_fake_run_codex_exec):
        result = runtime.execute(
            persona={"role": "content_writer", "display_name": "Writer", "goal": "Write", "body": ""},
            skill_name="copywriting",
            task_description="Target project path: /Users/cliff/workspace/agent/Synapse-Network-Growing",
            output_dir=tmp_path / "roles" / "content_writer" / "outputs" / "task-1",
        )

    assert result.runtime_backend == "codex_cli"
    assert result.error is None
    assert "# Done" in result.text
    assert result.files


def test_get_task_runtime_returns_codex_cli_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ORCHESTRATION_BACKEND", "codex_cli")
    runtime = get_task_runtime(project_root=tmp_path)
    assert isinstance(runtime, CodexCLITaskRuntime)
