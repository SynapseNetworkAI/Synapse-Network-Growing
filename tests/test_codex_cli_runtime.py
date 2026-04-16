from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server import config
from server.services.runtime.codex_cli import (
    CodexAsyncExecResult,
    CodexExecResult,
    _build_codex_exec_command,
    _sanitize_plugin_manifests,
    run_codex_exec,
    start_codex_exec_async,
)
from server.services.agents.llm_adapter import CodexCLIProvider
from server.services.runtime.task_runtime import (
    CodexCLITaskRuntime,
    _codex_workdirs,
    get_task_runtime,
    resolve_runtime_selection,
)
from server.services.workflows.planner_provider import call_full_plan_provider


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


def test_raw_codex_plan_provider_uses_read_only_exec_without_template_wrappers(tmp_path):
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
        content, tokens = call_full_plan_provider(
            provider_name="codex",
            provider=object(),
            prompt=raw_prompt,
            model_name="gpt-5.4",
            system_prompt="",
            raw_prompt=True,
            raw_cwd=target_project,
            raw_output_path=output_path,
            metadata_out=metadata,
        )

    assert content == "Plan for this exact requirement"
    assert tokens == 0
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


def test_raw_codex_plan_provider_passes_resume_session_per_requirement(tmp_path):
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
        content, _tokens = call_full_plan_provider(
            provider_name="codex",
            provider=object(),
            prompt="raw prompt",
            model_name="gpt-5.4",
            system_prompt="",
            raw_prompt=True,
            raw_cwd=target_project,
            raw_output_path=output_path,
            raw_resume_session_id="thread-plan-1",
            metadata_out=metadata,
        )

    assert content == "Updated plan"
    _, kwargs = mock_run.call_args
    assert kwargs["resume_thread_id"] == "thread-plan-1"
    assert metadata["planning_resumed_from_session_id"] == "thread-plan-1"


def test_codex_cli_task_runtime_returns_completed_result(tmp_path):
    runtime = CodexCLITaskRuntime(project_root=tmp_path)

    def _fake_start_codex_exec_async(*, output_dir: Path, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        return CodexAsyncExecResult(
            command=["codex", "exec", "--json"],
            output_path=output_dir / "output.md",
            stdout_path=output_dir / "codex.stdout.jsonl",
            stderr_path=output_dir / "codex.stderr.log",
            state_path=output_dir / "codex.state.json",
            metadata_path=output_dir / "metadata.json",
            prompt_path=output_dir / "prompt.md",
            pid=12345,
            thread_id="thread-async-1",
        )

    with patch("server.services.runtime.task_runtime.start_codex_exec_async", side_effect=_fake_start_codex_exec_async):
        result = runtime.execute(
            persona={"role": "content_writer", "display_name": "Writer", "goal": "Write", "body": ""},
            skill_name="copywriting",
            task_description="Target project path: /Users/cliff/workspace/agent/Synapse-Network-Growing",
            output_dir=tmp_path / "roles" / "content_writer" / "outputs" / "task-1",
        )

    assert result.runtime_backend == "codex_cli"
    assert result.error is None
    assert result.deferred is True
    assert result.runtime_session_id == "thread-async-1"
    assert result.files


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


def test_codex_cli_generic_codex_models_omit_model_flag(tmp_path):
    command = _build_codex_exec_command(
        cwd=tmp_path,
        model="gpt-5-codex",
        add_dirs=[],
        output_path=tmp_path / "output.md",
        resume_thread_id=None,
        sandbox_mode=None,
    )

    assert "-m" not in command


def test_codex_cli_workdirs_accept_target_project_marker(tmp_path):
    product_repo = tmp_path / "product"
    product_repo.mkdir()
    output_dir = tmp_path / "roles" / "dev_rel" / "outputs" / "task-2"

    cwd, add_dirs = _codex_workdirs(
        "## Step\nTarget project: "
        + str(product_repo)
        + "\nMore context here",
        tmp_path,
        output_dir,
    )

    assert cwd == product_repo.resolve()
    assert tmp_path.resolve() in add_dirs


def test_codex_cli_workdirs_accept_target_project_marker_with_context_prefix(tmp_path):
    product_repo = tmp_path / "product"
    product_repo.mkdir()
    output_dir = tmp_path / "roles" / "dev_rel" / "outputs" / "task-7"

    cwd, add_dirs = _codex_workdirs(
        "- Project Context: Target project path: "
        + str(product_repo)
        + "\n- Capability Contract: git_write=yes",
        tmp_path,
        output_dir,
    )

    assert cwd == product_repo.resolve()
    assert tmp_path.resolve() in add_dirs


def test_codex_cli_runtime_prefers_session_hint_project_root(tmp_path):
    runtime = CodexCLITaskRuntime(project_root=tmp_path)
    target_repo = tmp_path / "clean-clone"
    target_repo.mkdir()

    def _fake_start_codex_exec_async(*, cwd: Path, output_dir: Path, **kwargs):
        assert cwd == target_repo.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        return CodexAsyncExecResult(
            command=["codex", "exec", "--json"],
            output_path=output_dir / "output.md",
            stdout_path=output_dir / "codex.stdout.jsonl",
            stderr_path=output_dir / "codex.stderr.log",
            state_path=output_dir / "codex.state.json",
            metadata_path=output_dir / "metadata.json",
            prompt_path=output_dir / "prompt.md",
            pid=12345,
            thread_id="thread-async-2",
        )

    with patch("server.services.runtime.task_runtime.start_codex_exec_async", side_effect=_fake_start_codex_exec_async):
        result = runtime.execute(
            persona={"role": "dev_rel", "display_name": "DevRel", "goal": "Research", "body": ""},
            skill_name="content-strategy",
            task_description="## Step\nResearch context only",
            output_dir=tmp_path / "roles" / "dev_rel" / "outputs" / "task-9",
            session_hint={"project_root": str(target_repo)},
        )

    assert result.runtime_session_id == "thread-async-2"


def test_codex_cli_runtime_uses_read_only_sandbox_for_research(tmp_path):
    runtime = CodexCLITaskRuntime(project_root=tmp_path)

    def _fake_start_codex_exec_async(*, sandbox_mode: str | None, output_dir: Path, **kwargs):
        assert sandbox_mode == "read-only"
        output_dir.mkdir(parents=True, exist_ok=True)
        return CodexAsyncExecResult(
            command=["codex", "exec", "--sandbox", "read-only"],
            output_path=output_dir / "output.md",
            stdout_path=output_dir / "codex.stdout.jsonl",
            stderr_path=output_dir / "codex.stderr.log",
            state_path=output_dir / "codex.state.json",
            metadata_path=output_dir / "metadata.json",
            prompt_path=output_dir / "prompt.md",
            pid=12346,
            thread_id="thread-read-only-1",
        )

    with patch("server.services.runtime.task_runtime.start_codex_exec_async", side_effect=_fake_start_codex_exec_async):
        result = runtime.execute(
            persona={"role": "dev_rel", "display_name": "DevRel", "goal": "Research", "body": ""},
            skill_name="content-strategy",
            task_description="## Step\nInvestigate only",
            output_dir=tmp_path / "roles" / "dev_rel" / "outputs" / "task-10",
            session_hint={"step_type": "research", "project_root": str(tmp_path)},
        )

    assert result.runtime_session_id == "thread-read-only-1"


def test_codex_cli_runtime_uses_default_writable_mode_for_implementation(tmp_path):
    runtime = CodexCLITaskRuntime(project_root=tmp_path)

    def _fake_start_codex_exec_async(*, sandbox_mode: str | None, output_dir: Path, **kwargs):
        assert sandbox_mode is None
        output_dir.mkdir(parents=True, exist_ok=True)
        return CodexAsyncExecResult(
            command=["codex", "exec", "--full-auto"],
            output_path=output_dir / "output.md",
            stdout_path=output_dir / "codex.stdout.jsonl",
            stderr_path=output_dir / "codex.stderr.log",
            state_path=output_dir / "codex.state.json",
            metadata_path=output_dir / "metadata.json",
            prompt_path=output_dir / "prompt.md",
            pid=12347,
            thread_id="thread-writable-1",
        )

    with patch("server.services.runtime.task_runtime.start_codex_exec_async", side_effect=_fake_start_codex_exec_async):
        result = runtime.execute(
            persona={"role": "dev_rel", "display_name": "DevRel", "goal": "Implement", "body": ""},
            skill_name="content-strategy",
            task_description="## Step\nImplement fix",
            output_dir=tmp_path / "roles" / "dev_rel" / "outputs" / "task-11",
            session_hint={"step_type": "implementation", "project_root": str(tmp_path)},
        )

    assert result.runtime_session_id == "thread-writable-1"


def test_codex_cli_async_runtime_clears_stale_output_before_launch(tmp_path):
    output_dir = tmp_path / "roles" / "dev_rel" / "outputs" / "task-2"
    output_dir.mkdir(parents=True)
    stale_output = output_dir / "output.md"
    stale_state = output_dir / "codex.state.json"
    stale_output.write_text("old unrelated output", encoding="utf-8")
    stale_state.write_text("{\"status\":\"completed\"}", encoding="utf-8")

    fake_process = SimpleNamespace(pid=4242, stdin=None)

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


def test_get_task_runtime_returns_codex_cli_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ORCHESTRATION_BACKEND", "codex_cli")
    runtime = get_task_runtime(project_root=tmp_path)
    assert isinstance(runtime, CodexCLITaskRuntime)


def test_resolve_runtime_selection_uses_codex_mini_for_mini_tier(monkeypatch):
    monkeypatch.setattr(config, "ORCHESTRATION_BACKEND", "codex_cli")
    monkeypatch.setattr(config, "CODEX_CLI_MODEL", "gpt-5-codex")
    monkeypatch.setattr(config, "RUNTIME_TIER_MINI_BACKEND", "")
    monkeypatch.setattr(config, "RUNTIME_TIER_MINI_PROVIDER", "")
    monkeypatch.setattr(config, "RUNTIME_TIER_MINI_MODEL", "")

    selection = resolve_runtime_selection(
        {
            "complexity_tier": "mini",
            "budget_cap": {"max_runtime_seconds": 600},
            "allow_escalation": True,
            "escalation_rule": {"next_tier": "standard"},
        },
        step_type="research",
    )

    assert selection.backend == "codex_cli"
    assert selection.provider == "codex"
    assert selection.model == "gpt-5-codex-mini"
    assert selection.timeout_seconds == 600


def test_resolve_runtime_selection_respects_tier_override(monkeypatch):
    monkeypatch.setattr(config, "ORCHESTRATION_BACKEND", "codex_cli")
    monkeypatch.setattr(config, "RUNTIME_TIER_MINI_BACKEND", "openai_responses")
    monkeypatch.setattr(config, "RUNTIME_TIER_MINI_PROVIDER", "openai")
    monkeypatch.setattr(config, "RUNTIME_TIER_MINI_MODEL", "gpt-5-mini")

    selection = resolve_runtime_selection({"complexity_tier": "mini"}, step_type="research")

    assert selection.backend == "openai_responses"
    assert selection.provider == "openai"
    assert selection.model == "gpt-5-mini"


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


def test_codex_cli_task_runtime_uses_compact_prompt_packet(tmp_path):
    runtime = CodexCLITaskRuntime(project_root=tmp_path)
    captured: dict[str, str] = {}

    def _fake_start_codex_exec_async(*, prompt: str, output_dir: Path, **kwargs):
        captured["prompt"] = prompt
        output_dir.mkdir(parents=True, exist_ok=True)
        return CodexAsyncExecResult(
            command=["codex", "exec", "--json"],
            output_path=output_dir / "output.md",
            stdout_path=output_dir / "codex.stdout.jsonl",
            stderr_path=output_dir / "codex.stderr.log",
            state_path=output_dir / "codex.state.json",
            metadata_path=output_dir / "metadata.json",
            prompt_path=output_dir / "prompt.md",
            pid=222,
            thread_id="thread-compact",
        )

    with patch("server.services.runtime.task_runtime.start_codex_exec_async", side_effect=_fake_start_codex_exec_async):
        result = runtime.execute(
            persona={
                "role": "developer",
                "display_name": "Developer",
                "goal": "Fix the gateway",
                "body": "Long persona guidance that should be compacted for codex runtime.",
            },
            skill_name="__direct_execution__",
            task_description="\n".join(
                [
                    "## Step",
                    "[workflow_step:implementation] Fix gateway readiness",
                    "Requirement #3: Repair readiness endpoint",
                    "",
                    "## Project Context",
                    "Target project path: /Users/cliff/workspace/agent/Synapse-Network",
                    "IMPORTANT: Write actual source code files in the target project, not just documentation.",
                    "",
                    "## Capability Contract",
                    "- git_write: allowed",
                    "",
                    "## Suggested File Scope",
                    "- services/gateway/src/app.py",
                    "- services/gateway/tests/unit/test_gateway_readiness_endpoint_unit.py",
                    "",
                    "## Done When",
                    "Endpoint works and tests pass.",
                    "",
                    "## Validation Contract",
                    "Run focused gateway readiness checks.",
                ]
            ),
            output_dir=tmp_path / "roles" / "developer" / "outputs" / "task-compact",
        )

    prompt = captured["prompt"]
    assert "# Goal" in prompt
    assert "# Context" in prompt
    assert result.deferred is True
    assert result.runtime_session_id == "thread-compact"
    assert "# Constraints" in prompt
    assert "# Done When" in prompt
    assert "services/gateway/src/app.py" in prompt
    assert "do not search outside the target repository for parent AGENTS.md or llms.txt files" in prompt
    assert "If the target repository mentions `llms.txt` or similar bootstrap files and they are absent locally" in prompt
    assert "Do not publish, push, open PRs, install git hooks, change `.git/config`" in prompt
    assert "## Skill Instructions" not in prompt
    assert result.runtime_session_id == "thread-compact"


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
