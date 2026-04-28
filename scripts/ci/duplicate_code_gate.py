#!/usr/bin/env python3
"""Simple duplicate-block gate for changed source files.

This is intentionally small and dependency-free. It catches the costly case:
large copied code blocks added to changed files. Historical duplication is not
re-scored here; it is a ratchet, not a one-shot rewrite mandate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from quality_gate_utils import ROOT, run_git


CHECK_SUFFIXES = {".py", ".ts", ".tsx"}
CHECK_ROOTS = ("server/", "scripts/", "dashboard/src/")
EXCLUDED_PARTS = {"node_modules", "dist", "__pycache__", ".pytest_cache", ".ruff_cache"}
WINDOW = 8
BASELINE = ROOT / "quality" / "quality_baseline.json"


def _eligible(path: Path) -> bool:
    normalized = path.as_posix()
    return (
        path.suffix in CHECK_SUFFIXES
        and any(normalized.startswith(root) for root in CHECK_ROOTS)
        and not (set(path.parts) & EXCLUDED_PARTS)
        and ".test." not in path.name
        and ".spec." not in path.name
        and (ROOT / path).exists()
    )


def _changed_files(base: str) -> list[Path]:
    names: set[str] = set()
    for line in run_git(
        [
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            base,
            "--",
            *[root.rstrip("/") for root in CHECK_ROOTS],
        ]
    ).splitlines():
        if line.strip():
            names.add(line.strip())
    for line in run_git(
        [
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            *[root.rstrip("/") for root in CHECK_ROOTS],
        ]
    ).splitlines():
        if line.strip():
            names.add(line.strip())
    return [Path(name) for name in sorted(names) if _eligible(Path(name))]


def _legacy_files() -> set[str]:
    if not BASELINE.exists():
        return set()
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    return set(str(path) for path in payload.get("legacy_files", {}))


def _normalize_line(line: str) -> str:
    stripped = line.strip()
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped


def _windows(path: Path) -> list[tuple[int, tuple[str, ...]]]:
    raw_lines = (ROOT / path).read_text(encoding="utf-8", errors="replace").splitlines()
    lines: list[tuple[int, str]] = []
    for index, line in enumerate(raw_lines, start=1):
        normalized = _normalize_line(line)
        if not normalized or normalized in {"{", "}", ")", "};"}:
            continue
        if normalized.startswith(("#", "//", "import ", "from ", "export type ")):
            continue
        lines.append((index, normalized))
    result: list[tuple[int, tuple[str, ...]]] = []
    for offset in range(0, max(0, len(lines) - WINDOW + 1)):
        chunk = tuple(line for _, line in lines[offset : offset + WINDOW])
        if len(set(chunk)) <= 2:
            continue
        result.append((lines[offset][0], chunk))
    return result


def duplicate_failures(changed: list[Path]) -> list[str]:
    seen: dict[tuple[str, ...], list[tuple[Path, int]]] = defaultdict(list)
    for path in changed:
        for line, chunk in _windows(path):
            seen[chunk].append((path, line))
    failures: list[str] = []
    for locations in seen.values():
        unique_files = {path for path, _ in locations}
        if len(locations) > 1 and (len(unique_files) > 1 or len(locations) > 2):
            first = locations[0]
            second = locations[1]
            failures.append(
                f"DUPLICATE_BLOCK: {first[0]}:{first[1]} duplicates {second[0]}:{second[1]} "
                f"({WINDOW} normalized lines). Extract shared code."
            )
    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    args = parser.parse_args(argv)

    legacy = _legacy_files()
    changed = [
        path for path in _changed_files(args.base) if path.as_posix() not in legacy
    ]
    if not changed:
        print("[quality:duplicates] ok (no changed production source files)")
        return 0

    failures = duplicate_failures(changed)

    if failures:
        print("[quality:duplicates] failed:", file=sys.stderr)
        for failure in failures[:20]:
            print(f" - {failure}", file=sys.stderr)
        if len(failures) > 20:
            print(
                f" - ... {len(failures) - 20} more duplicate block(s)", file=sys.stderr
            )
        return 1

    print(
        f"[quality:duplicates] ok ({len(changed)} changed production source file(s) scanned)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
