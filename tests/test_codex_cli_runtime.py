from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from server import config
from server.services.runtime.codex_cli import (
    CodexAsyncExecResult,
    CodexExecResult,
    _build_codex_exec_command,
    _parse_codex_exec_stdout,
    _sanitize_plugin_manifests,
    run_codex_exec,
    start_codex_exec_async,
)
from server.services.agents.llm_adapter import CodexCLIProvider
from server.services.workflows.planner_provider import PlannerRequest, generate_planner_text


def test_resolve_orchestration_backend_for_codex_provider():
    assert config.resolve_orchestration_backend(provider="codex", execution_mode="sync", override="") == "codex_cli"


def test_codex_cli_provider_uses_codex_exec(tmp_path):
    output_path = tmp_path / "last-message.txt"
    output_path.write_text("planned steps", encoding="utf-8")
    provider = CodexCLIProvider()

    with patch("server.services.agents.llm_adapter.run_codex_exec", return_value=CodexExecResult(
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


def test_codex_cli_provider_prefers_target_project_path_for_planner_context(tmp_path):
    output_path = tmp_path / "last-message.txt"
    output_path.write_text("markdown plan", encoding="utf-8")
    provider = CodexCLIProvider()
    target_project = tmp_path / "Synapse-Network"
    target_project.mkdir()

    with patch(
        "server.services.agents.llm_adapter.run_codex_exec",
        return_value=CodexExecResult(
            text="markdown plan",
            stdout="",
            stderr="",
            exit_code=0,
            execution_time_ms=12,
            command=["codex", "exec"],
            output_path=output_path,
        ),
    ) as mock_run:
        text, tokens = provider.call(
            "system prompt",
            f"Requirement context\n\nTarget project path: {target_project}",
            "gpt-5-codex",
            0.1,
            30,
        )

    assert text == "markdown plan"
    assert tokens == 0
    _, kwargs = mock_run.call_args
    assert kwargs["cwd"] == target_project.resolve()
    assert target_project.resolve() in kwargs["add_dirs"]
    assert config.PROJECT_ROOT.resolve() in kwargs["add_dirs"]


def test_raw_codex_plan_adapter_uses_read_only_exec_without_template_wrappers(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PLANNER_BACKEND", "codex_cli")
    monkeypatch.setattr(config, "PLANNER_MODEL", "gpt-5.4")
    target_project = tmp_path / "Synapse-Network"
    target_project.mkdir()
    output_path = tmp_path / "runtime" / "plans" / "req-3-plan.md"
    raw_prompt = "提交代码\n\n提交项目代码\n\nTarget project:\n" + str(target_project)
    metadata: dict[str, object] = {}

    with patch(
        "server.services.workflows.planner_provider.run_codex_exec",
        return_value=CodexExecResult(
            text="Plan for this exact requirement",
            stdout="",
            stderr="",
            exit_code=0,
            execution_time_ms=12,
            command=[
                "codex",
                "exec",
                "-",
                "-C",
                str(target_project),
                "--sandbox",
                "read-only",
                "--output-last-message",
                str(output_path),
            ],
            output_path=output_path,
            thread_id="thread-plan-1",
            json_event_count=3,
        ),
    ) as mock_run:
        response = generate_planner_text(PlannerRequest(
            prompt=raw_prompt,
            system_prompt="",
            raw_prompt=True,
            cwd=target_project,
            output_path=output_path,
            metadata=metadata,
        ))

    assert response.text == "Plan for this exact requirement"
    assert response.tokens == 0
    _, kwargs = mock_run.call_args
    assert kwargs["prompt"] == raw_prompt
    assert "# Goal" not in kwargs["prompt"]
    assert "# Constraints" not in kwargs["prompt"]
    assert "# Done When" not in kwargs["prompt"]
    assert kwargs["cwd"] == target_project.resolve()
    assert kwargs["sandbox_mode"] == "read-only"
    assert kwargs["output_path"] == output_path
    assert metadata["planning_session_id"] == "thread-plan-1"
    assert metadata["planning_command"] == [
        "codex",
        "exec",
        "-",
        "-C",
        str(target_project),
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(output_path),
    ]


def test_raw_codex_plan_adapter_passes_resume_session_per_requirement(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PLANNER_BACKEND", "codex_cli")
    monkeypatch.setattr(config, "PLANNER_MODEL", "gpt-5.4")
    target_project = tmp_path / "Synapse-Network"
    target_project.mkdir()
    output_path = tmp_path / "runtime" / "plans" / "req-3-plan.md"
    metadata: dict[str, object] = {}

    with patch(
        "server.services.workflows.planner_provider.run_codex_exec",
        return_value=CodexExecResult(
            text="Updated plan",
            stdout="",
            stderr="",
            exit_code=0,
            execution_time_ms=12,
            command=["codex", "exec", "resume", "--output-last-message", str(output_path), "thread-plan-1", "-"],
            output_path=output_path,
            thread_id="thread-plan-1",
        ),
    ) as mock_run:
        response = generate_planner_text(PlannerRequest(
            prompt="raw prompt",
            system_prompt="",
            raw_prompt=True,
            cwd=target_project,
            output_path=output_path,
            resume_session_id="thread-plan-1",
            metadata=metadata,
        ))

    assert response.text == "Updated plan"
    _, kwargs = mock_run.call_args
    assert kwargs["resume_thread_id"] == "thread-plan-1"
    assert metadata["planning_resumed_from_session_id"] == "thread-plan-1"


def test_codex_resume_command_omits_exec_only_flags(tmp_path):
    command = _build_codex_exec_command(
        cwd=tmp_path,
        model="gpt-5-codex-mini",
        add_dirs=[tmp_path / "extra"],
        output_path=tmp_path / "output.md",
        resume_thread_id="thread-123",
        sandbox_mode="read-only",
    )

    assert command[:3] == ["codex", "exec", "resume"]
    assert "--sandbox" not in command
    assert "-C" not in command
    assert "--add-dir" not in command
    assert "--json" in command
    assert "--output-last-message" in command
    assert command[-2:] == ["thread-123", "-"]


def test_codex_cli_explicit_codex_models_are_passed_to_avoid_cli_default_drift(tmp_path):
    command = _build_codex_exec_command(
        cwd=tmp_path,
        model="gpt-5-codex",
        add_dirs=[],
        output_path=tmp_path / "output.md",
        resume_thread_id=None,
        sandbox_mode=None,
    )

    assert "-m" in command
    assert command[command.index("-m") + 1] == "gpt-5-codex"


def test_codex_cli_json_parser_preserves_error_events():
    stdout = "\n".join(
        [
            '{"type":"thread.started","thread_id":"thread-err"}',
            '{"type":"error","message":"model requires newer Codex"}',
            '{"type":"turn.failed","error":{"message":"turn failed because model requires newer Codex"}}',
        ]
    )

    passthrough, text, thread_id, event_count, usage, turn_count = _parse_codex_exec_stdout(stdout)

    assert text == ""
    assert thread_id == "thread-err"
    assert event_count == 3
    assert turn_count == 0
    assert usage is None
    assert "model requires newer Codex" in passthrough
    assert "turn failed because model requires newer Codex" in passthrough


def test_codex_cli_json_parser_preserves_string_turn_failed_error():
    stdout = '{"type":"turn.failed","error":"plain string failure"}'

    passthrough, text, thread_id, event_count, usage, turn_count = _parse_codex_exec_stdout(stdout)

    assert text == ""
    assert thread_id is None
    assert event_count == 1
    assert turn_count == 0
    assert usage is None
    assert "plain string failure" in passthrough


def test_codex_cli_async_runtime_clears_stale_output_before_launch(tmp_path):
    output_dir = tmp_path / "roles" / "dev_rel" / "outputs" / "task-2"
    output_dir.mkdir(parents=True)
    stale_output = output_dir / "output.md"
    stale_state = output_dir / "codex.state.json"
    stale_output.write_text("old unrelated output", encoding="utf-8")
    stale_state.write_text("{\"status\":\"completed\"}", encoding="utf-8")

    class FakeProcess:
        pid = 4242
        stdin = None

    fake_process = FakeProcess()

    with patch("server.services.runtime.codex_cli.subprocess.Popen", return_value=fake_process), patch(
        "server.services.runtime.codex_cli._watch_codex_process"
    ):
        result = start_codex_exec_async(
            prompt="Implement the requested change",
            cwd=tmp_path,
            output_dir=output_dir,
            model="gpt-5-codex",
        )

    assert result.output_path == stale_output
    assert not stale_output.exists()
    state_payload = json.loads(stale_state.read_text(encoding="utf-8"))
    assert state_payload["status"] == "running"


def test_codex_cli_timeout_returns_structured_error(tmp_path):
    output_path = tmp_path / "out.md"
    timeout_error = subprocess.TimeoutExpired(
        cmd=["codex", "exec"],
        timeout=45,
        output="partial stdout",
        stderr="partial stderr",
    )

    with patch("server.services.runtime.codex_cli.subprocess.run", side_effect=timeout_error):
        result = run_codex_exec(
            prompt="do work",
            cwd=tmp_path,
            output_path=output_path,
            model="gpt-5-codex",
            timeout=45,
        )

    assert result.exit_code == 124
    assert "timed out after 45s" in result.stderr
    assert "partial stdout" in result.stdout


def test_codex_cli_timeout_accepts_bytes_streams(tmp_path):
    timeout_error = subprocess.TimeoutExpired(
        cmd=["codex", "exec"],
        timeout=45,
        output=b'{"type":"thread.started","thread_id":"thread-123"}\npartial stdout',
        stderr=b"partial stderr",
    )

    with patch("server.services.runtime.codex_cli.subprocess.run", side_effect=timeout_error):
        result = run_codex_exec(
            prompt="do work",
            cwd=tmp_path,
            output_path=None,
            model="gpt-5-codex",
            timeout=45,
        )

    assert result.exit_code == 124
    assert result.thread_id == "thread-123"
    assert "partial stdout" in result.stdout


def test_codex_cli_parses_jsonl_thread_and_final_message(tmp_path):
    with patch("server.services.runtime.codex_cli.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex", "exec"],
            returncode=0,
            stdout="\n".join(
                [
                    '{"type":"thread.started","thread_id":"thread-123"}',
                    '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"done"}}',
                ]
            ),
            stderr="",
        )
        result = run_codex_exec(
            prompt="do work",
            cwd=tmp_path,
            output_path=None,
            model="gpt-5-codex",
            timeout=45,
        )

    assert result.exit_code == 0
    assert result.thread_id == "thread-123"
    assert result.text == "done"
    assert result.json_event_count == 2


def _write_plugin_manifest(path: Path, *, prompt: str) -> None:
    payload = {
        "name": "sample",
        "interface": {
            "defaultPrompt": prompt,
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_sanitize_plugin_manifests_trims_long_prompts(tmp_path):
    plugin_root = tmp_path / "plugins-root"
    manifest_dir = plugin_root / "sample" / ".codex-plugin"
    manifest_dir.mkdir(parents=True)
    manifest_path = manifest_dir / "plugin.json"
    _write_plugin_manifest(manifest_path, prompt="x" * 200)
    sha_path = tmp_path / "plugins.sha"
    sha_path.write_text("abc", encoding="utf-8")

    _sanitize_plugin_manifests(plugin_root=plugin_root, max_prompt_len=64, sha_path=sha_path)

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(data["interface"]["defaultPrompt"]) == 64


def test_sanitize_plugin_manifests_rechecks_when_sha_changes(tmp_path):
    plugin_root = tmp_path / "plugins-root"
    manifest_dir = plugin_root / "sample" / ".codex-plugin"
    manifest_dir.mkdir(parents=True)
    manifest_path = manifest_dir / "plugin.json"
    _write_plugin_manifest(manifest_path, prompt="a" * 150)
    sha_path = tmp_path / "plugins.sha"
    sha_path.write_text("first", encoding="utf-8")

    _sanitize_plugin_manifests(plugin_root=plugin_root, max_prompt_len=32, sha_path=sha_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(data["interface"]["defaultPrompt"]) == 32

    _write_plugin_manifest(manifest_path, prompt="b" * 80)
    _sanitize_plugin_manifests(plugin_root=plugin_root, max_prompt_len=16, sha_path=sha_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(data["interface"]["defaultPrompt"]) == 80

    sha_path.write_text("second", encoding="utf-8")
    _sanitize_plugin_manifests(plugin_root=plugin_root, max_prompt_len=16, sha_path=sha_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(data["interface"]["defaultPrompt"]) == 16
