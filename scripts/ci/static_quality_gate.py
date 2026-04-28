#!/usr/bin/env python3
"""Static ratchet gates for changed files.

The repository has legacy files above the target size limits. This gate keeps
that debt from growing while applying hard limits to new and previously-small
files.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from quality_gate_utils import ROOT, run_git

DEFAULT_BASELINE = ROOT / "quality" / "quality_baseline.json"
PRODUCTION_LIMIT = 500
TEST_LIMIT = 900
FUNCTION_LIMIT = 120
CHECK_SUFFIXES = {".py", ".ts", ".tsx"}
CHECK_ROOTS = ("server/", "scripts/", "dashboard/src/", "tests/", "dashboard/tests/")
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".playwright",
    "__pycache__",
    "node_modules",
    "dist",
    "coverage",
}


@dataclass(frozen=True)
class QualityFailure:
    code: str
    path: str
    message: str


def _is_under_check_root(path: Path) -> bool:
    normalized = path.as_posix()
    return any(normalized.startswith(root) for root in CHECK_ROOTS)


def _is_excluded(path: Path) -> bool:
    return bool(set(path.parts) & EXCLUDED_PARTS)


def is_test_file(path: Path) -> bool:
    normalized = path.as_posix()
    return (
        normalized.startswith("tests/")
        or normalized.startswith("dashboard/tests/")
        or ".test." in path.name
        or ".spec." in path.name
    )


def target_limit(path: Path) -> int:
    return TEST_LIMIT if is_test_file(path) else PRODUCTION_LIMIT


def line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def load_baseline(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(key): int(value) for key, value in payload.get("legacy_files", {}).items()
    }


def changed_paths(base: str) -> list[Path]:
    roots = [root.rstrip("/") for root in CHECK_ROOTS]
    diff_output = run_git(
        ["diff", "--name-only", "--diff-filter=ACMR", base, "--", *roots]
    )
    untracked_output = run_git(
        ["ls-files", "--others", "--exclude-standard", "--", *roots]
    )
    names = {
        line.strip()
        for line in [*diff_output.splitlines(), *untracked_output.splitlines()]
        if line.strip()
    }
    return _filter_check_paths(names)


def _filter_check_paths(names: set[str]) -> list[Path]:
    result: list[Path] = []
    for name in sorted(names):
        path = Path(name)
        abs_path = ROOT / path
        if path.suffix not in CHECK_SUFFIXES:
            continue
        if (
            not _is_under_check_root(path)
            or _is_excluded(path)
            or not abs_path.exists()
        ):
            continue
        result.append(path)
    return result


def _python_function_failures(path: Path) -> list[QualityFailure]:
    abs_path = ROOT / path
    try:
        tree = ast.parse(abs_path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [
            QualityFailure(
                "PYTHON_PARSE_ERROR", path.as_posix(), f"{exc.msg} at line {exc.lineno}"
            )
        ]

    failures: list[QualityFailure] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.end_lineno is None:
            continue
        length = node.end_lineno - node.lineno + 1
        if length > FUNCTION_LIMIT:
            failures.append(
                QualityFailure(
                    "FUNCTION_TOO_LONG",
                    path.as_posix(),
                    f"{node.name} is {length} lines; max is {FUNCTION_LIMIT}. Extract helpers before adding large functions.",
                )
            )
    return failures


def evaluate_path(path: Path, baseline: dict[str, int]) -> list[QualityFailure]:
    current = line_count(ROOT / path)
    normalized = path.as_posix()
    limit = target_limit(path)
    baseline_lines = baseline.get(normalized)
    failures: list[QualityFailure] = []

    if baseline_lines is not None:
        if current > baseline_lines:
            failures.append(
                QualityFailure(
                    "LEGACY_FILE_GREW",
                    normalized,
                    f"{current} lines exceeds legacy baseline {baseline_lines}. Split code or reduce this file before adding more.",
                )
            )
    elif current > limit:
        code = "TEST_FILE_TOO_LONG" if is_test_file(path) else "FILE_TOO_LONG"
        failures.append(
            QualityFailure(
                code,
                normalized,
                f"{current} lines exceeds limit {limit}. New or previously-small files must be split.",
            )
        )

    # Enforce function length only for files not already grandfathered.
    if path.suffix == ".py" and baseline_lines is None and not is_test_file(path):
        failures.extend(_python_function_failures(path))

    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        required=True,
        help="Git merge-base or branch used to find changed files",
    )
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--print-changed", action="store_true")
    args = parser.parse_args(argv)

    baseline_path = Path(args.baseline)
    if not baseline_path.is_absolute():
        baseline_path = ROOT / baseline_path
    baseline = load_baseline(baseline_path)
    paths = changed_paths(args.base)

    if args.print_changed:
        for path in paths:
            print(path.as_posix())
        return 0

    failures: list[QualityFailure] = []
    for path in paths:
        failures.extend(evaluate_path(path, baseline))

    if failures:
        print("[quality:static] static quality gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"{failure.code}: {failure.path}: {failure.message}", file=sys.stderr)
        return 1

    print(f"[quality:static] ok ({len(paths)} changed source file(s) checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
