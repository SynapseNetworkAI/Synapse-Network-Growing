#!/usr/bin/env python3
"""Dependency-light dashboard lint for high-signal frontend mistakes."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from quality_gate_utils import ROOT, run_git_lines

DEFAULT_ROOT = ROOT / "dashboard" / "src"
CHECK_SUFFIXES = {".ts", ".tsx"}
RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "NO_CONSOLE_LOG",
        re.compile(r"\bconsole\.log\s*\("),
        "Use structured UI feedback or console.warn/error for diagnostics.",
    ),
    (
        "NO_BROWSER_CONFIRM",
        re.compile(r"\b(?:alert|confirm|prompt)\s*\("),
        "Use the Ops modal/confirmation components instead of browser-native dialogs.",
    ),
    (
        "NO_FLOATING_FETCH",
        re.compile(r"^\s*fetch\s*\(", re.MULTILINE),
        "Route network calls through dashboard/src/api.ts so errors are bounded.",
    ),
)


def iter_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        abs_path = path if path.is_absolute() else ROOT / path
        if abs_path.is_dir():
            files.extend(p for p in abs_path.rglob("*") if p.suffix in CHECK_SUFFIXES)
        elif abs_path.suffix in CHECK_SUFFIXES and abs_path.exists():
            files.append(abs_path)
    return sorted(set(files))


def changed_dashboard_files(base: str) -> list[Path]:
    names = set(
        run_git_lines(
            ["diff", "--name-only", "--diff-filter=ACMR", base, "--", "dashboard/src"]
        )
    )
    names.update(
        run_git_lines(
            ["ls-files", "--others", "--exclude-standard", "--", "dashboard/src"]
        )
    )
    return [
        ROOT / name
        for name in sorted(names)
        if Path(name).suffix in CHECK_SUFFIXES and (ROOT / name).exists()
    ]


def scan_file(file_path: Path) -> list[str]:
    rel = file_path.relative_to(ROOT)
    if ".test." in file_path.name or ".spec." in file_path.name:
        return []
    text = file_path.read_text(encoding="utf-8", errors="replace")
    failures: list[str] = []
    for code, pattern, message in RULES:
        if code == "NO_FLOATING_FETCH" and rel.as_posix() == "dashboard/src/api.ts":
            continue
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            failures.append(f"{code}: {rel}:{line}: {message}")
    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=[str(DEFAULT_ROOT)])
    parser.add_argument(
        "--base",
        help="When provided, lint only dashboard source files changed since this git base",
    )
    args = parser.parse_args(argv)

    failures: list[str] = []
    files = (
        changed_dashboard_files(args.base)
        if args.base
        else iter_files([Path(p) for p in args.paths])
    )
    for file_path in files:
        failures.extend(scan_file(file_path))

    if failures:
        print("[dashboard-lint] failed:", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1

    print(f"[dashboard-lint] ok ({len(files)} file(s) checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
