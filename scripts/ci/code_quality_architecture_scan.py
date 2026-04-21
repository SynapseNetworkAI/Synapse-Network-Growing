#!/usr/bin/env python3
"""Growing-specific architecture and complexity guardrails.

The checks are intentionally deterministic and dependency-free so workflow
atoms can run them as hard evidence gates without relying on optional tools.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PY_NEW_FILE_MAX_EFFECTIVE_LINES = 90
PY_NEW_FILE_MAX_NESTING = 4
PY_NEW_FILE_MAX_ARGS = 7
TS_NEW_FILE_MAX_FUNCTION_LINES = 80


@dataclass(frozen=True)
class Finding:
    code: str
    path: Path
    line: int
    message: str
    fix: str

    def render(self) -> str:
        rel = self.path.relative_to(REPO_ROOT)
        return f"{self.code} {rel}:{self.line}: {self.message}\n  Agent fix: {self.fix}"


def _git_lines(args: list[str]) -> list[str]:
    result = subprocess.run(["git", "-C", str(REPO_ROOT), *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files() -> list[Path]:
    base_ref = "origin/main"
    merge_base = _git_lines(["merge-base", "HEAD", base_ref])
    diff_base = merge_base[0] if merge_base else "HEAD"
    tracked = _git_lines(["diff", "--name-only", diff_base, "--"])
    untracked = _git_lines(["ls-files", "--others", "--exclude-standard"])
    return sorted({Path(item) for item in [*tracked, *untracked] if item})


def new_files() -> set[Path]:
    return {Path(item) for item in _git_lines(["diff", "--name-only", "--diff-filter=A", "HEAD", "--"])}


def effective_lines(lines: list[str], start: int, end: int) -> int:
    body = lines[start - 1 : end]
    return sum(1 for line in body if line.strip() and not line.lstrip().startswith("#"))


def arg_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    args = node.args
    return (
        len(args.posonlyargs)
        + len(args.args)
        + len(args.kwonlyargs)
        + (1 if args.vararg else 0)
        + (1 if args.kwarg else 0)
    )


def max_nesting(node: ast.AST) -> int:
    nesting_nodes = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)

    def walk(current: ast.AST, depth: int) -> int:
        next_depth = depth + 1 if isinstance(current, nesting_nodes) else depth
        child_depths = [walk(child, next_depth) for child in ast.iter_child_nodes(current)]
        return max([next_depth, *child_depths])

    return walk(node, 0)


def scan_python_file(path: Path, *, is_new: bool) -> list[Finding]:
    absolute = REPO_ROOT / path
    if not absolute.exists():
        return []
    text = absolute.read_text(encoding="utf-8")
    findings: list[Finding] = []
    if path.as_posix().startswith("server/services/") and "server.routers" in text:
        findings.append(
            Finding(
                "ARCH-PY-BOUNDARY-001",
                absolute,
                1,
                "server/services must not import or depend on server.routers.",
                "move router-facing behavior behind a service function or schema boundary.",
            )
        )
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [
            Finding(
                "ARCH-PY-SYNTAX-001",
                absolute,
                exc.lineno or 1,
                "Python file cannot be parsed by the architecture scanner.",
                "fix the syntax error before relying on workflow evidence.",
            )
        ]
    if not is_new:
        return findings
    lines = text.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = getattr(node, "end_lineno", node.lineno)
        effective = effective_lines(lines, node.lineno, end)
        if effective > PY_NEW_FILE_MAX_EFFECTIVE_LINES:
            findings.append(
                Finding(
                    "ARCH-PY-COMPLEXITY-001",
                    absolute,
                    node.lineno,
                    f"new function {node.name!r} has {effective} effective lines > {PY_NEW_FILE_MAX_EFFECTIVE_LINES}.",
                    "split the function into smaller deterministic helpers before shipping.",
                )
            )
        nesting = max_nesting(node)
        if nesting > PY_NEW_FILE_MAX_NESTING:
            findings.append(
                Finding(
                    "ARCH-PY-NESTING-001",
                    absolute,
                    node.lineno,
                    f"new function {node.name!r} has nesting depth {nesting} > {PY_NEW_FILE_MAX_NESTING}.",
                    "flatten branching or extract state handlers.",
                )
            )
        args = arg_count(node)
        if args > PY_NEW_FILE_MAX_ARGS:
            findings.append(
                Finding(
                    "ARCH-PY-ARGS-001",
                    absolute,
                    node.lineno,
                    f"new function {node.name!r} has {args} arguments > {PY_NEW_FILE_MAX_ARGS}.",
                    "group related data into a typed object or reduce responsibilities.",
                )
            )
    return findings


def scan_ts_file(path: Path, *, is_new: bool) -> list[Finding]:
    absolute = REPO_ROOT / path
    if not absolute.exists():
        return []
    text = absolute.read_text(encoding="utf-8")
    findings: list[Finding] = []
    if path.as_posix().startswith("dashboard/src/components/") and "../api" in text:
        findings.append(
            Finding(
                "ARCH-FE-BOUNDARY-001",
                absolute,
                1,
                "dashboard components must not import API clients directly.",
                "move data fetching to page or hook boundaries and pass data through props.",
            )
        )
    if not is_new:
        return findings
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("function ") or "=> {" in stripped:
            # Lightweight new-file tripwire: prevent obvious single-file monster components.
            remaining = text.splitlines()[line_no - 1 :]
            if len(remaining) > TS_NEW_FILE_MAX_FUNCTION_LINES:
                findings.append(
                    Finding(
                        "ARCH-FE-COMPLEXITY-001",
                        absolute,
                        line_no,
                        f"new TS/TSX function appears to span more than {TS_NEW_FILE_MAX_FUNCTION_LINES} lines.",
                        "split page logic into small pure helpers or child components.",
                    )
                )
                break
    return findings


def main() -> int:
    changed = changed_files()
    added = new_files()
    findings: list[Finding] = []
    for path in changed:
        suffix = path.suffix.lower()
        if suffix == ".py" and (path.as_posix().startswith("server/") or path.as_posix().startswith("scripts/")):
            findings.extend(scan_python_file(path, is_new=path in added))
        if suffix in {".ts", ".tsx"} and path.as_posix().startswith("dashboard/src/"):
            findings.extend(scan_ts_file(path, is_new=path in added))
    if findings:
        print("FATAL ARCH-GUARDRAILS: architecture quality gates failed.", file=sys.stderr)
        for finding in findings:
            print(finding.render(), file=sys.stderr)
        return 1
    print("[architecture-quality] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
