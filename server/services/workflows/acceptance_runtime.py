"""Execution helpers for governed acceptance commands."""

from __future__ import annotations

import os
import re
import shlex
import sys


def acceptance_python_executable() -> str:
    """Return the Python runtime used for planner-generated pytest evidence."""

    explicit = str(os.environ.get("PYTHON_BIN") or "").strip()
    if explicit and os.path.exists(explicit):
        return explicit
    workspace_venv = "/Users/cliff/workspace/agent/.venv/bin/python"
    if os.path.exists(workspace_venv):
        return workspace_venv
    return sys.executable


def _split_acceptance_command(command: str) -> list[str] | None:
    try:
        return shlex.split(str(command or ""))
    except ValueError:
        return None


def _command_start_index(tokens: list[str]) -> int | None:
    index = 0
    while index < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[index]):
        index += 1
    return index if index < len(tokens) else None


def _quote_command(tokens: list[str]) -> str:
    return " ".join(shlex.quote(token) for token in tokens)


def acceptance_execution_command(command: str) -> str:
    """Rewrite safe portable pytest commands to the governed Python runtime."""

    tokens = _split_acceptance_command(command)
    if not tokens:
        return command
    index = _command_start_index(tokens)
    if index is None:
        return command

    executable = tokens[index].rsplit("/", 1)[-1]
    python = acceptance_python_executable()
    if executable in {"python", "python3"} and tokens[index + 1 : index + 3] == [
        "-m",
        "pytest",
    ]:
        tokens[index] = python
        return _quote_command(tokens)
    if executable == "pytest":
        tokens[index : index + 1] = [python, "-m", "pytest"]
        return _quote_command(tokens)
    return command
