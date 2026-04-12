"""Helpers for invoking Codex CLI as a local orchestration backend."""
from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from server import config

logger = logging.getLogger("ops-dashboard.codex_cli")

_GENERIC_MODEL_ALIASES = {"", "openai", "claude", "copilot", "codex", "responses", "gpt"}


@dataclass
class CodexExecResult:
    text: str
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int
    command: list[str]
    output_path: Path | None


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
) -> CodexExecResult:
    command = [config.CODEX_CLI_BIN, "exec", "-", "-C", str(cwd), "--color", "never"]
    resolved_model = resolve_codex_cli_model(model)
    if resolved_model:
        command.extend(["-m", resolved_model])
    if config.CODEX_CLI_FULL_AUTO:
        command.append("--full-auto")
    else:
        command.extend(["--sandbox", config.CODEX_CLI_SANDBOX])
    if config.CODEX_CLI_SKIP_GIT_REPO_CHECK:
        command.append("--skip-git-repo-check")
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

    effective_timeout = int(timeout or config.CODEX_CLI_TIMEOUT or config.LLM_TIMEOUT or 300)
    t0 = time.monotonic()
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        cwd=str(cwd),
        timeout=effective_timeout,
        check=False,
    )
    elapsed = int((time.monotonic() - t0) * 1000)

    text = ""
    if output_path is not None and output_path.exists():
        text = output_path.read_text(encoding="utf-8", errors="replace")
    elif completed.stdout:
        text = completed.stdout

    result = CodexExecResult(
        text=text,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        exit_code=int(completed.returncode),
        execution_time_ms=elapsed,
        command=command,
        output_path=output_path,
    )
    logger.info(
        "event=codex_cli_exec exit_code=%s cwd=%s model=%s elapsed_ms=%s",
        result.exit_code,
        str(cwd),
        resolved_model or "(default)",
        result.execution_time_ms,
    )
    return result
