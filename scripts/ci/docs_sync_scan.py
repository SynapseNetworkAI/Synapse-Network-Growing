#!/usr/bin/env python3
"""Fail closed when architecture-sensitive changes miss canonical docs."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_DOC_PREFIXES = ("ARCHITECTURE.md", "docs/design-docs/")
SENSITIVE_PREFIXES = (
    "server/services/workflows/",
    "server/services/planning/",
    "server/services/scheduling/",
    "server/services/requirements/acceptance.py",
    "server/routers/recurring_workflows.py",
    "scripts/ci/",
)


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
    sensitive = [path for path in changed if path.startswith(SENSITIVE_PREFIXES)]
    docs = [path for path in changed if path == "ARCHITECTURE.md" or path.startswith("docs/design-docs/")]
    if sensitive and not docs:
        print("FATAL DOC-SYNC-001: architecture-sensitive code changed without canonical design doc updates.", file=sys.stderr)
        print("Changed sensitive files:", file=sys.stderr)
        for path in sorted(sensitive):
            print(f"- {path}", file=sys.stderr)
        print("Agent fix: update ARCHITECTURE.md or docs/design-docs/* with the operator-facing contract.", file=sys.stderr)
        return 1
    print("[docs-sync] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
