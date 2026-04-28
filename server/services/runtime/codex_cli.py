"""Helpers for invoking Codex CLI as a local orchestration backend."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from server import config

logger = logging.getLogger("ops-dashboard.codex_cli")

_GENERIC_MODEL_ALIASES = {
    "",
    "openai",
    "claude",
    "copilot",
    "codex",
    "responses",
    "gpt",
}
_STDERR_NOISE_MARKERS = (
    "model personality requested but model_messages is missing",
    "plugins::manifest: ignoring interface.defaultprompt: prompt must be at most 128 characters",
    "shell_snapshot: failed to delete shell snapshot",
    "failed to terminate mcp process group",
)

_DEFAULT_PLUGIN_ROOT = Path.home() / ".codex" / ".tmp" / "plugins" / "plugins"
_PLUGIN_SHA_PATH = _DEFAULT_PLUGIN_ROOT.parent.parent / "plugins.sha"
_PLUGIN_SANITIZE_STATE: dict[str, str | None] = {}


@dataclass
class CodexExecResult:
    text: str
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int
    command: list[str]
    output_path: Path | None
    thread_id: str | None = None
    json_event_count: int = 0
    usage: dict[str, int] | None = None
    turn_count: int = 0


@dataclass
class CodexAsyncExecResult:
    command: list[str]
    output_path: Path
    stdout_path: Path
    stderr_path: Path
    state_path: Path
    metadata_path: Path
    prompt_path: Path
    pid: int
    thread_id: str | None = None


def codex_runtime_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "output": output_dir / "output.md",
        "stdout": output_dir / "codex.stdout.jsonl",
        "stderr": output_dir / "codex.stderr.log",
        "state": output_dir / "codex.state.json",
        "metadata": output_dir / "metadata.json",
        "prompt": output_dir / "prompt.md",
    }


def _reset_async_runtime_paths(paths: dict[str, Path], *, append_logs: bool) -> None:
    stale_files = ["output", "state", "metadata", "prompt"]
    if not append_logs:
        stale_files.extend(["stdout", "stderr"])
    for key in stale_files:
        path = paths[key]
        try:
            if path.exists():
                path.unlink()
        except FileNotFoundError:
            continue


def resolve_codex_cli_model(model: str | None = None) -> str:
    raw = str(model if model is not None else (config.CODEX_CLI_MODEL or config.LLM_MODEL or "")).strip()
    if raw.lower() in _GENERIC_MODEL_ALIASES:
        return ""
    return raw


def run_codex_exec(
    *,
    prompt: str,
    cwd: Path,
    output_path: Path | None = None,
    model: str | None = None,
    timeout: int | None = None,
    add_dirs: list[Path] | None = None,
    output_schema: dict | None = None,
    sandbox_mode: str | None = None,
    resume_thread_id: str | None = None,
) -> CodexExecResult:
    _sanitize_plugin_manifests()
    if resume_thread_id:
        command = [config.CODEX_CLI_BIN, "exec", "resume"]
    else:
        command = [config.CODEX_CLI_BIN, "exec", "-", "-C", str(cwd), "--color", "never"]
    resolved_model = resolve_codex_cli_model(model)
    if resolved_model:
        command.extend(["-m", resolved_model])
    if not resume_thread_id:
        _append_codex_execution_mode(command, sandbox_mode=sandbox_mode)
    if config.CODEX_CLI_SKIP_GIT_REPO_CHECK:
        command.append("--skip-git-repo-check")
    if config.CODEX_CLI_JSON_EVENTS:
        command.append("--json")
    if not resume_thread_id:
        for extra_dir in add_dirs or []:
            command.extend(["--add-dir", str(extra_dir)])

    schema_path: Path | None = None
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command.extend(["--output-last-message", str(output_path)])
        schema_path = output_path.parent / "codex-output-schema.json" if output_schema else None
    elif output_schema:
        schema_path = cwd / ".codex-output-schema.json"

    if schema_path is not None:
        schema_path.write_text(json.dumps(output_schema, indent=2), encoding="utf-8")
        command.extend(["--output-schema", str(schema_path)])
    if resume_thread_id:
        command.extend([resume_thread_id, "-"])

    selected_timeout = timeout if timeout is not None else config.CODEX_CLI_TIMEOUT
    if selected_timeout is None:
        selected_timeout = config.LLM_TIMEOUT or 300
    effective_timeout = int(selected_timeout)
    subprocess_timeout = effective_timeout if effective_timeout > 0 else None
    t0 = time.monotonic()
    thread_id: str | None = None
    json_event_count = 0
    try:
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            cwd=str(cwd),
            timeout=subprocess_timeout,
            check=False,
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        exit_code = int(completed.returncode)
    except subprocess.TimeoutExpired as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        stdout = _coerce_codex_text(exc.stdout)
        stderr = _coerce_codex_text(exc.stderr).strip()
        timeout_message = f"Codex CLI execution timed out after {effective_timeout}s"
        stderr = f"{stderr}\n{timeout_message}".strip()
        exit_code = 124
        logger.warning(
            "event=codex_cli_exec_timeout cwd=%s model=%s timeout_s=%s elapsed_ms=%s",
            str(cwd),
            resolved_model or "(default)",
            effective_timeout if effective_timeout > 0 else "none",
            elapsed,
        )

    parsed_stdout, derived_text, parsed_thread_id, parsed_event_count, usage, turn_count = _parse_codex_exec_stdout(stdout)
    stdout = parsed_stdout
    thread_id = parsed_thread_id
    json_event_count = parsed_event_count
    text = ""
    if output_path is not None and output_path.exists():
        text = output_path.read_text(encoding="utf-8", errors="replace")
    elif derived_text:
        text = derived_text
    elif stdout:
        text = stdout

    result = CodexExecResult(
        text=text,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        execution_time_ms=elapsed,
        command=command,
        output_path=output_path,
        thread_id=thread_id,
        json_event_count=json_event_count,
        usage=usage,
        turn_count=turn_count,
    )
    logger.info(
        "event=codex_cli_exec exit_code=%s cwd=%s model=%s elapsed_ms=%s thread_id=%s json_events=%s",
        result.exit_code,
        str(cwd),
        resolved_model or "(default)",
        result.execution_time_ms,
        result.thread_id or "",
        result.json_event_count,
    )
    return result


def start_codex_exec_async(
    *,
    prompt: str,
    cwd: Path,
    output_dir: Path,
    model: str | None = None,
    add_dirs: list[Path] | None = None,
    resume_thread_id: str | None = None,
    append_logs: bool = False,
    sandbox_mode: str | None = None,
) -> CodexAsyncExecResult:
    _sanitize_plugin_manifests()
    paths = codex_runtime_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _reset_async_runtime_paths(paths, append_logs=append_logs)
    command = _build_codex_exec_command(
        cwd=cwd,
        model=model,
        add_dirs=add_dirs,
        output_path=paths["output"],
        resume_thread_id=resume_thread_id,
        sandbox_mode=sandbox_mode,
    )
    stdout_mode = "a" if append_logs else "w"
    stderr_mode = "a" if append_logs else "w"
    stdout_handle = paths["stdout"].open(stdout_mode, encoding="utf-8")
    stderr_handle = paths["stderr"].open(stderr_mode, encoding="utf-8")
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        cwd=str(cwd),
    )
    if process.stdin is not None:
        process.stdin.write(prompt)
        process.stdin.close()
    stdout_handle.close()
    stderr_handle.close()
    paths["prompt"].write_text(prompt, encoding="utf-8")
    _write_codex_state(
        paths["state"],
        {
            "status": "running",
            "pid": int(process.pid),
            "started_at": _utcnow().isoformat(),
            "cwd": str(cwd),
            "model": resolve_codex_cli_model(model) or "",
            "sandbox_mode": str(sandbox_mode or ""),
            "thread_id": resume_thread_id or "",
            "resume_thread_id": resume_thread_id or "",
            "command": command,
            "output_path": str(paths["output"]),
            "stdout_path": str(paths["stdout"]),
            "stderr_path": str(paths["stderr"]),
            "prompt_path": str(paths["prompt"]),
        },
    )
    _watch_codex_process(process, paths["state"])
    logger.info(
        "event=codex_cli_exec_spawn pid=%s cwd=%s model=%s resume_thread_id=%s",
        process.pid,
        str(cwd),
        resolve_codex_cli_model(model) or "(default)",
        resume_thread_id or "",
    )
    return CodexAsyncExecResult(
        command=command,
        output_path=paths["output"],
        stdout_path=paths["stdout"],
        stderr_path=paths["stderr"],
        state_path=paths["state"],
        metadata_path=paths["metadata"],
        prompt_path=paths["prompt"],
        pid=int(process.pid),
        thread_id=resume_thread_id,
    )


def _coerce_codex_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _parse_codex_exec_stdout(stdout: str | bytes) -> tuple[str, str, str | None, int, dict[str, int] | None, int]:
    stdout = _coerce_codex_text(stdout)
    if not stdout:
        return "", "", None, 0, None, 0

    passthrough_lines: list[str] = []
    final_text = ""
    thread_id: str | None = None
    event_count = 0
    turn_count = 0
    latest_usage: dict[str, int] | None = None

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith("{"):
            passthrough_lines.append(raw_line)
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            passthrough_lines.append(raw_line)
            continue
        if not isinstance(payload, dict) or "type" not in payload:
            passthrough_lines.append(raw_line)
            continue
        event_count += 1
        event_type = str(payload.get("type") or "").strip()
        if event_type == "thread.started":
            value = str(payload.get("thread_id") or "").strip()
            if value:
                thread_id = value
        elif event_type == "turn.completed":
            turn_count += 1
            usage_payload = payload.get("usage")
            if isinstance(usage_payload, dict):
                latest_usage = {
                    "input_tokens": int(usage_payload.get("input_tokens") or 0),
                    "cached_input_tokens": int(usage_payload.get("cached_input_tokens") or 0),
                    "output_tokens": int(usage_payload.get("output_tokens") or 0),
                }
        elif event_type == "item.completed":
            item = payload.get("item")
            if isinstance(item, dict) and str(item.get("type") or "") == "agent_message":
                value = str(item.get("text") or "").strip()
                if value:
                    final_text = value
        elif event_type == "error":
            value = str(payload.get("message") or payload.get("error") or "").strip()
            if value:
                passthrough_lines.append(value)
        elif event_type == "turn.failed":
            error_payload = payload.get("error")
            if isinstance(error_payload, dict):
                value = str(error_payload.get("message") or error_payload.get("error") or "").strip()
            else:
                value = str(error_payload or "").strip()
            if value:
                passthrough_lines.append(value)

    return "\n".join(passthrough_lines).strip(), final_text, thread_id, event_count, latest_usage, turn_count


def filter_codex_stderr(stderr: str, *, max_lines: int = 10) -> str:
    lines = [line.rstrip() for line in str(stderr or "").splitlines() if line.strip()]
    if not lines:
        return ""
    kept: list[str] = []
    for line in lines:
        lowered = line.lower()
        if any(marker in lowered for marker in _STDERR_NOISE_MARKERS):
            continue
        kept.append(line)
    selected = kept if kept else []
    if not selected:
        return ""
    if len(selected) <= max_lines:
        return "\n".join(selected)
    head = selected[:max_lines]
    omitted = len(selected) - max_lines
    return "\n".join(head + [f"... [{omitted} more stderr lines omitted]"])


def _sanitize_plugin_manifests(
    plugin_root: Path | None = None,
    *,
    max_prompt_len: int = 128,
    sha_path: Path | None = None,
) -> None:
    """Ensure Codex plugin manifests respect default prompt guardrails."""

    root = (plugin_root or _DEFAULT_PLUGIN_ROOT).resolve()
    sha_file = sha_path or _PLUGIN_SHA_PATH
    sha_value: str | None = None
    if sha_file.exists():
        try:
            sha_value = sha_file.read_text(encoding="utf-8").strip() or None
        except OSError:
            sha_value = None

    cache_key = str(root)
    if _PLUGIN_SANITIZE_STATE.get(cache_key) == sha_value:
        return

    if not root.exists():
        _PLUGIN_SANITIZE_STATE.pop(cache_key, None)
        return

    for manifest_path in _iter_plugin_manifests(root):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        interface = payload.get("interface")
        if not isinstance(interface, dict):
            continue
        default_prompt = interface.get("defaultPrompt")
        if not isinstance(default_prompt, str):
            continue
        trimmed = default_prompt.strip()
        if len(trimmed) <= max_prompt_len:
            continue
        shortened = trimmed[:max_prompt_len].rstrip()
        if not shortened:
            continue
        interface["defaultPrompt"] = shortened
        try:
            manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except OSError:
            continue
        logger.info(
            "Trimmed plugin default prompt to %s chars for %s",
            len(shortened),
            manifest_path,
        )

    _PLUGIN_SANITIZE_STATE[cache_key] = sha_value


def _iter_plugin_manifests(plugin_root: Path) -> Iterator[Path]:
    for plugin_dir in plugin_root.iterdir():
        if not plugin_dir.is_dir():
            continue
        manifest_path = plugin_dir / ".codex-plugin" / "plugin.json"
        if manifest_path.exists():
            yield manifest_path


def load_codex_state(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_codex_state(path: Path, payload: dict[str, object]) -> None:
    _write_codex_state(path, payload)


def pid_is_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


def terminate_pid(pid: int | None) -> None:
    if not pid or pid <= 0:
        return
    try:
        os.kill(int(pid), 15)
    except OSError:
        return


def _build_codex_exec_command(
    *,
    cwd: Path,
    model: str | None,
    add_dirs: list[Path] | None,
    output_path: Path,
    resume_thread_id: str | None = None,
    sandbox_mode: str | None = None,
) -> list[str]:
    resolved_model = resolve_codex_cli_model(model)
    if resume_thread_id:
        command = [config.CODEX_CLI_BIN, "exec", "resume"]
        if resolved_model:
            command.extend(["-m", resolved_model])
        if config.CODEX_CLI_FULL_AUTO and str(sandbox_mode or "").strip().lower() not in {"", "read-only"}:
            command.append("--full-auto")
        if config.CODEX_CLI_SKIP_GIT_REPO_CHECK:
            command.append("--skip-git-repo-check")
        if config.CODEX_CLI_JSON_EVENTS:
            command.append("--json")
        command.extend(["--output-last-message", str(output_path), resume_thread_id, "-"])
        return command
    else:
        command = [config.CODEX_CLI_BIN, "exec", "-", "-C", str(cwd)]
    if resolved_model:
        command.extend(["-m", resolved_model])
    _append_codex_execution_mode(command, sandbox_mode=sandbox_mode)
    if config.CODEX_CLI_SKIP_GIT_REPO_CHECK:
        command.append("--skip-git-repo-check")
    if config.CODEX_CLI_JSON_EVENTS:
        command.append("--json")
    if not resume_thread_id:
        for extra_dir in add_dirs or []:
            command.extend(["--add-dir", str(extra_dir)])
    command.extend(["--output-last-message", str(output_path)])
    return command


def _append_codex_execution_mode(command: list[str], *, sandbox_mode: str | None = None) -> None:
    selected_mode = str(sandbox_mode or "").strip().lower()
    if selected_mode == "read-only":
        command.extend(["--sandbox", "read-only"])
        return
    if selected_mode:
        command.extend(["--sandbox", selected_mode])
        return
    if config.CODEX_CLI_FULL_AUTO:
        command.append("--full-auto")
    else:
        command.extend(["--sandbox", config.CODEX_CLI_SANDBOX])


def _watch_codex_process(process: subprocess.Popen[str], state_path: Path) -> None:
    def _runner() -> None:
        try:
            exit_code = process.wait()
        except Exception as exc:
            payload = load_codex_state(state_path) or {}
            payload["status"] = "failed"
            payload["error"] = str(exc)
            payload["completed_at"] = _utcnow().isoformat()
            _write_codex_state(state_path, payload)
            return
        payload = load_codex_state(state_path) or {}
        payload["exit_code"] = int(exit_code)
        payload["completed_at"] = _utcnow().isoformat()
        payload["status"] = "completed" if int(exit_code) == 0 else "failed"
        _write_codex_state(state_path, payload)

    thread = threading.Thread(target=_runner, name=f"codex-watch-{process.pid}", daemon=True)
    thread.start()


def _write_codex_state(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
