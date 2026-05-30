#!/usr/bin/env python3
"""Verify local Codex can discover the Bug List skill and MCP server."""

from __future__ import annotations

import subprocess  # nosec B404
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_NAME = "bug-list-agent"
MCP_NAME = "synapse-bug-list"
MCP_SCRIPT = REPO_ROOT / "scripts" / "mcp" / "bug_list_server.py"
CODEX_SKILL = Path.home() / ".codex" / "skills" / SKILL_NAME / "SKILL.md"


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 # nosec B603
        command,
        cwd=str(REPO_ROOT),
        check=True,
        text=True,
        capture_output=True,
    )


def main() -> None:
    if not CODEX_SKILL.exists():
        raise SystemExit(f"Codex skill is not readable: {CODEX_SKILL}")
    skill_text = CODEX_SKILL.read_text(encoding="utf-8")
    if "name: bug-list-agent" not in skill_text:
        raise SystemExit(f"Codex skill does not look like {SKILL_NAME}: {CODEX_SKILL}")

    get_result = _run(["codex", "mcp", "get", MCP_NAME])
    if str(MCP_SCRIPT) not in get_result.stdout:
        raise SystemExit(f"Codex MCP {MCP_NAME} does not point at {MCP_SCRIPT}")

    list_result = _run(["codex", "mcp", "list"])
    if MCP_NAME not in list_result.stdout or "enabled" not in list_result.stdout:
        raise SystemExit(f"Codex MCP {MCP_NAME} is not enabled")

    print("bug_list_codex_registration_e2e: ok")


if __name__ == "__main__":
    main()
