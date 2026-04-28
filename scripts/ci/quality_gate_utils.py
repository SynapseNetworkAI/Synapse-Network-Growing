"""Shared helpers for lightweight CI quality gates."""

from __future__ import annotations

import subprocess  # nosec B404 - quality gates execute fixed local git commands only.
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_git(args: list[str]) -> str:
    # Fixed git executable; arguments are repo-local quality selectors.
    completed = subprocess.run(  # nosec
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout


def run_git_lines(args: list[str]) -> list[str]:
    return [line.strip() for line in run_git(args).splitlines() if line.strip()]
