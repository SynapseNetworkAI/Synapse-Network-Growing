#!/usr/bin/env python3
"""Small fail-closed secret scanner for changed files when no baseline exists."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from quality_gate_utils import ROOT, run_git_lines

SECRET_PATTERNS = {
    "SECRET_ASSIGNMENT": re.compile(
        r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\s]{16,}['\"]"
    ),
    "OPENAI_KEY": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "GITHUB_TOKEN": re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "PRIVATE_KEY": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
}
CHECK_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".sh",
    ".yml",
    ".yaml",
    ".json",
    ".md",
    ".env",
}
EXCLUDED_PARTS = {"node_modules", "dist", ".git", ".playwright", "__pycache__"}


def _eligible(path: Path) -> bool:
    if path.suffix not in CHECK_SUFFIXES or set(path.parts) & EXCLUDED_PARTS:
        return False
    if path.parts and path.parts[0] == "tests":
        return False
    if path.as_posix().startswith("dashboard/tests/"):
        return False
    if ".test." in path.name or ".spec." in path.name:
        return False
    return (ROOT / path).exists()


def _changed_files(base: str) -> list[Path]:
    names = set(run_git_lines(["diff", "--name-only", "--diff-filter=ACMR", base]))
    names.update(run_git_lines(["ls-files", "--others", "--exclude-standard"]))
    return [Path(name) for name in sorted(names) if _eligible(Path(name))]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    args = parser.parse_args(argv)

    failures: list[str] = []
    for path in _changed_files(args.base):
        text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{name}: {path}")

    if failures:
        print(
            "[quality:secrets] possible secret introduced; values are redacted:",
            file=sys.stderr,
        )
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1
    print("[quality:secrets] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
