#!/usr/bin/env python3
"""Lightweight changed-source coverage proxy for Growing.

This repo intentionally avoids optional coverage dependencies in the base
environment. The hard v1 gate is therefore: source changes must travel with a
matching test change unless the operator explicitly scopes a docs-only update.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_lines(args: list[str]) -> list[str]:
    result = subprocess.run(["git", "-C", str(REPO_ROOT), *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files() -> set[str]:
    merge_base = _git_lines(["merge-base", "HEAD", "origin/main"])
    diff_base = merge_base[0] if merge_base else "HEAD"
    return set(_git_lines(["diff", "--name-only", diff_base, "--"]) + _git_lines(["ls-files", "--others", "--exclude-standard"]))


def main() -> int:
    changed = changed_files()
    server_source = [path for path in changed if path.startswith("server/") and path.endswith(".py")]
    dashboard_source = [path for path in changed if path.startswith("dashboard/src/") and path.endswith((".ts", ".tsx")) and not path.endswith(".test.tsx")]
    server_tests = [path for path in changed if path.startswith("tests/") and path.endswith(".py")]
    dashboard_tests = [path for path in changed if path.startswith("dashboard/src/") and path.endswith((".test.ts", ".test.tsx"))]
    errors: list[str] = []
    if server_source and not server_tests:
        errors.append("server source changed but no Python test file changed under tests/.")
    if dashboard_source and not dashboard_tests:
        errors.append("dashboard source changed but no dashboard test file changed.")
    if errors:
        print("FATAL DIFF-COVERAGE-001: changed source lacks matching test evidence.", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        print("Agent fix: add or update focused tests, then rerun the guardrail bundle.", file=sys.stderr)
        return 1
    print("[diff-coverage] changed-source test evidence gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
