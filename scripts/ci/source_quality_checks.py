#!/usr/bin/env python3
"""Source API shape checks.

Public service functions should return typed result objects instead of raw
maps. Raw maps are still allowed for private serializers, request/patch bodies,
metadata fields, blackboards, and external payloads.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from quality_gate_utils import ROOT, run_git

PYTHON_SUFFIXES = {".py"}
TS_SUFFIXES = {".ts", ".tsx"}
SOURCE_SUFFIXES = PYTHON_SUFFIXES | TS_SUFFIXES
CORE_PATHS = (
    "server/services/planning",
    "server/services/social",
    "server/services/releases",
    "server/routers/planning.py",
    "server/routers/releases.py",
)
CHANGED_ROOTS = ("server/", "scripts/", "dashboard/src/")
BASELINE_PATH = ROOT / "scripts" / "ci" / "source_quality_baseline.json"
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
RAW_RETURN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z_][\w]*\.)?(?:dict|Dict|Mapping|MutableMapping)\s*(?:\[|$)"
)
ALLOWED_NAME_PREFIXES = (
    "_",
    "parse_",
    "normalize_",
    "serialize_",
    "build_",
    "request_",
    "response_",
    "model_",
    "as_",
)
ALLOWED_NAME_SUFFIXES = (
    "_body",
    "_payload",
    "_patch",
    "_schema",
    "_schemas",
    "_manifest",
    "_headers",
    "_metadata",
    "_blackboard",
)
PROMISE_RECORD_RE = re.compile(
    r"""
    (?P<prefix>
      (?:export\s+)?(?:async\s+)?function\s+(?P<fn>[A-Za-z_$][\w$]*)\s*\([^)]*\)
      |
      (?P<const>(?:export\s+)?(?:const|let|var)\s+(?P<const_name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\))
      |
      (?P<method>(?P<method_name>[A-Za-z_$][\w$]*)\s*\([^)]*\))
    )
    \s*:\s*(?:Promise\s*<\s*)?Record\s*<\s*string\s*,\s*unknown\s*>
    """,
    re.VERBOSE | re.MULTILINE,
)


@dataclass(frozen=True)
class SourceQualityFailure:
    code: str
    path: str
    line: int
    name: str
    message: str

    @property
    def baseline_key(self) -> str:
        return f"{self.code}:{self.path}:{self.line}:{self.name}"


def _is_excluded(path: Path) -> bool:
    return bool(set(path.parts) & EXCLUDED_PARTS)


def _is_source_path(path: Path) -> bool:
    return path.suffix in SOURCE_SUFFIXES and not _is_excluded(path)


def _core_paths() -> list[Path]:
    paths: list[Path] = []
    for name in CORE_PATHS:
        path = ROOT / name
        rel = Path(name)
        if path.is_file() and _is_source_path(rel):
            paths.append(rel)
        elif path.is_dir():
            paths.extend(
                candidate.relative_to(ROOT)
                for candidate in path.rglob("*")
                if candidate.is_file() and _is_source_path(candidate.relative_to(ROOT))
            )
    return paths


def _changed_paths(base: str) -> list[Path]:
    roots = [root.rstrip("/") for root in CHANGED_ROOTS]
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
    paths: list[Path] = []
    for name in sorted(names):
        path = Path(name)
        if _is_source_path(path) and (ROOT / path).exists():
            paths.append(path)
    return paths


def paths_to_check(base: str | None) -> list[Path]:
    paths = set(_core_paths())
    if base:
        paths.update(_changed_paths(base))
    return sorted(paths, key=lambda item: item.as_posix())


def _annotation_contains_raw_map(node: ast.AST | None) -> bool:
    if node is None:
        return False
    return bool(RAW_RETURN_RE.search(ast.unparse(node)))


def _is_allowed_raw_return_name(name: str) -> bool:
    return name.startswith(ALLOWED_NAME_PREFIXES) or name.endswith(
        ALLOWED_NAME_SUFFIXES
    )


def evaluate_python_path(path: Path) -> list[SourceQualityFailure]:
    abs_path = ROOT / path
    try:
        tree = ast.parse(abs_path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [
            SourceQualityFailure(
                "PYTHON_PARSE_ERROR",
                path.as_posix(),
                int(exc.lineno or 0),
                path.name,
                f"{exc.msg} at line {exc.lineno}",
            )
        ]

    failures: list[SourceQualityFailure] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _is_allowed_raw_return_name(node.name):
            continue
        if not _annotation_contains_raw_map(node.returns):
            continue
        failures.append(
            SourceQualityFailure(
                "RAW_DICT_RETURN",
                path.as_posix(),
                node.lineno,
                node.name,
                f"{node.name} returns a raw map. Return a Pydantic result object and convert with model_dump() at the API boundary.",
            )
        )
    return failures


def _line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def evaluate_ts_path(path: Path) -> list[SourceQualityFailure]:
    text = (ROOT / path).read_text(encoding="utf-8")
    failures: list[SourceQualityFailure] = []
    for match in PROMISE_RECORD_RE.finditer(text):
        name = (
            match.groupdict().get("fn")
            or match.groupdict().get("const_name")
            or match.groupdict().get("method_name")
            or "<anonymous>"
        )
        if _is_allowed_raw_return_name(name):
            continue
        failures.append(
            SourceQualityFailure(
                "RAW_RECORD_PROMISE_RETURN",
                path.as_posix(),
                _line_number_for_offset(text, match.start()),
                name,
                f"{name} returns Promise<Record<string, unknown>>. Return a typed object/interface instead.",
            )
        )
    return failures


def evaluate_path(path: Path) -> list[SourceQualityFailure]:
    if path.suffix in PYTHON_SUFFIXES:
        return evaluate_python_path(path)
    if path.suffix in TS_SUFFIXES:
        return evaluate_ts_path(path)
    return []


def _load_baseline() -> set[str]:
    baseline_path = BASELINE_PATH
    if not baseline_path.exists():
        return set()
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    return {str(item) for item in payload.get("allow", [])}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        default=None,
        help="Git merge-base or branch used to include changed source files.",
    )
    args = parser.parse_args(argv)

    baseline = _load_baseline()
    failures: list[SourceQualityFailure] = []
    paths = paths_to_check(args.base)
    for path in paths:
        failures.extend(
            failure
            for failure in evaluate_path(path)
            if failure.baseline_key not in baseline
        )

    if failures:
        print("[quality:source] object-return quality gate failed:", file=sys.stderr)
        for failure in failures:
            print(
                f"{failure.code}: {failure.path}:{failure.line}: {failure.name}: {failure.message}",
                file=sys.stderr,
            )
        return 1

    print(f"[quality:source] ok ({len(paths)} source file(s) checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
