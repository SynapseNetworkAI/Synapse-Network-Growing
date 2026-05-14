#!/usr/bin/env python3
"""Classify PR changes into the smallest safe CI scope."""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404 - CI classifier invokes git with fixed argv only.
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]


FULL_REQUIRED_PREFIXES = (
    ".github/workflows/",
    "server/migrations/",
    "migrations/",
    "quality/",
)
FULL_REQUIRED_FILES = {
    "requirements.txt",
    "dashboard/yarn.lock",
    "dashboard/package.json",
    "docker-compose.postgres.yml",
}
BACKEND_PREFIXES = ("server/", "scripts/", "tests/")
DASHBOARD_PREFIXES = ("dashboard/",)
DOCS_PREFIXES = ("docs/", "content/", "roles/", ".agents/")
PROMPT_CONTENT_PREFIXES = ("content/", "roles/", ".agents/skills/")
SCOPE_SELF_TEST_FILES = {
    "scripts/ci/ci_scope.py",
    "tests/test_ci_scope.py",
}
FULL_REQUIRED_CI_PREFIXES = ("scripts/ci/",)
DOCS_FILES = {
    "README.md",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "CLAUDE.md",
    "GEMINI.md",
    "harness-engineering.md",
}
SECURITY_PATTERNS = (
    ".secrets.baseline",
    "security",
    "auth",
    "secret",
)
BACKEND_FULL_REQUIRED_KEYWORDS = (
    "auth",
    "finance",
    "release",
    "security",
    "settlement",
    "workflow",
)
SCOPED_BACKEND_MODE = "targeted"
FULL_BACKEND_MODE = "full"
NO_BACKEND_MODE = "none"


@dataclass(frozen=True)
class ScopeResult:
    changed_files: list[str] = field(default_factory=list)
    scope: str = "docs_only"
    docs_only: bool = False
    backend: bool = False
    dashboard: bool = False
    security: bool = False
    prompt_content: bool = False
    scope_self_test: bool = False
    full_required: bool = False
    run_guardrails: bool = True
    run_docs: bool = True
    run_backend: bool = False
    run_dashboard: bool = False
    run_security: bool = False
    run_scope_self_test: bool = False
    run_full: bool = False
    backend_mode: str = NO_BACKEND_MODE
    run_backend_targeted: bool = False
    run_backend_full: bool = False
    reason: str = ""

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, sort_keys=True)


def run_git(args: list[str]) -> str:
    # args are assembled by this script from fixed git subcommands; shell is never used.
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stderr=subprocess.DEVNULL,
    )  # nosec B603 B607


def _split_lines(text: str) -> list[str]:
    return sorted({line.strip() for line in text.splitlines() if line.strip()})


def changed_files(base: str | None) -> list[str]:
    files: set[str] = set()
    if base:
        files.update(_split_lines(run_git(["diff", "--name-only", base, "--"])))
    files.update(_split_lines(run_git(["ls-files", "--others", "--exclude-standard"])))
    return sorted(files)


def _matches_prefix(path: str, prefixes: Iterable[str]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def _is_full_required(path: str) -> bool:
    if path in FULL_REQUIRED_FILES:
        return True
    if path in SCOPE_SELF_TEST_FILES:
        return False
    if _matches_prefix(path, FULL_REQUIRED_CI_PREFIXES):
        return True
    if _matches_prefix(path, FULL_REQUIRED_PREFIXES):
        return True
    lower = path.lower()
    if "schema" in lower or "migration" in lower:
        return True
    return _is_backend_full_required(path)


def _is_backend_full_required(path: str) -> bool:
    """Return true for backend changes that need full backend regression."""
    if path in SCOPE_SELF_TEST_FILES:
        return False
    if not _matches_prefix(path, BACKEND_PREFIXES):
        return False
    lower = path.lower()
    return any(keyword in lower for keyword in BACKEND_FULL_REQUIRED_KEYWORDS)


def _is_docs(path: str) -> bool:
    return path in DOCS_FILES or _matches_prefix(path, DOCS_PREFIXES)


def _is_prompt_content(path: str) -> bool:
    return _matches_prefix(path, PROMPT_CONTENT_PREFIXES)


def _is_scope_self_test(path: str) -> bool:
    return path in SCOPE_SELF_TEST_FILES


def _is_backend(path: str) -> bool:
    if _is_scope_self_test(path):
        return False
    return _matches_prefix(path, BACKEND_PREFIXES)


def _is_dashboard(path: str) -> bool:
    return _matches_prefix(path, DASHBOARD_PREFIXES)


def _is_security(path: str) -> bool:
    lower = path.lower()
    return any(pattern in lower for pattern in SECURITY_PATTERNS)


def _forced_full(paths: list[str], reason: str) -> ScopeResult:
    return ScopeResult(
        changed_files=paths,
        scope="full",
        full_required=True,
        run_backend=True,
        run_dashboard=True,
        run_security=True,
        run_full=True,
        backend_mode=FULL_BACKEND_MODE,
        run_backend_full=True,
        reason=reason,
    )


def _empty_scope() -> ScopeResult:
    return ScopeResult(
        changed_files=[],
        scope="docs_only",
        docs_only=True,
        reason="no_changed_files",
    )


def _all_paths_known(paths: list[str]) -> bool:
    return all(
        _is_docs(path)
        or _is_prompt_content(path)
        or _is_scope_self_test(path)
        or _is_backend(path)
        or _is_dashboard(path)
        or _is_security(path)
        or _is_full_required(path)
        for path in paths
    )


def _scope_name(
    *,
    backend: bool,
    dashboard: bool,
    prompt_content: bool,
    scope_self_test: bool,
    security: bool,
) -> str:
    if scope_self_test and not (backend or dashboard or security):
        return "scope_self_test"
    if backend and dashboard:
        return "backend_dashboard"
    if backend:
        return "backend"
    if dashboard:
        return "dashboard"
    if security:
        return "security"
    if prompt_content:
        return "prompt_content"
    return "docs_only"


def _path_flags(paths: list[str]) -> dict[str, bool]:
    return {
        "backend": any(_is_backend(path) for path in paths),
        "dashboard": any(_is_dashboard(path) for path in paths),
        "docs": any(_is_docs(path) for path in paths),
        "full_required": any(_is_full_required(path) for path in paths),
        "known": _all_paths_known(paths),
        "prompt_content": any(_is_prompt_content(path) for path in paths),
        "scope_self_test": any(_is_scope_self_test(path) for path in paths),
        "security": any(_is_security(path) for path in paths),
    }


def _full_required_scope(paths: list[str], flags: dict[str, bool]) -> ScopeResult:
    return ScopeResult(
        changed_files=paths,
        scope="full",
        backend=flags["backend"],
        dashboard=flags["dashboard"],
        prompt_content=flags["prompt_content"],
        scope_self_test=flags["scope_self_test"],
        security=flags["security"],
        full_required=True,
        run_backend=True,
        run_dashboard=True,
        run_security=True,
        run_full=True,
        backend_mode=FULL_BACKEND_MODE,
        run_backend_full=True,
        reason="full_required_path",
    )


def _has_code_scope(flags: dict[str, bool]) -> bool:
    return (
        flags["backend"]
        or flags["dashboard"]
        or flags["security"]
        or flags["scope_self_test"]
    )


def _docs_only(flags: dict[str, bool]) -> bool:
    return (flags["docs"] and not _has_code_scope(flags)) or not _has_code_scope(flags)


def _scoped_result(paths: list[str], flags: dict[str, bool]) -> ScopeResult:
    docs_only = _docs_only(flags)
    backend_mode = SCOPED_BACKEND_MODE if flags["backend"] else NO_BACKEND_MODE
    return ScopeResult(
        changed_files=paths,
        scope=_scope_name(
            backend=flags["backend"],
            dashboard=flags["dashboard"],
            prompt_content=flags["prompt_content"],
            scope_self_test=flags["scope_self_test"],
            security=flags["security"],
        ),
        docs_only=docs_only,
        backend=flags["backend"],
        dashboard=flags["dashboard"],
        prompt_content=flags["prompt_content"],
        scope_self_test=flags["scope_self_test"],
        security=flags["security"],
        run_docs=flags["docs"] or flags["prompt_content"] or docs_only,
        run_backend=flags["backend"],
        run_dashboard=flags["dashboard"],
        run_security=flags["security"],
        run_scope_self_test=flags["scope_self_test"],
        backend_mode=backend_mode,
        run_backend_targeted=flags["backend"],
        run_backend_full=False,
        reason="classified",
    )


def classify_paths(paths: list[str], *, force_full: bool = False) -> ScopeResult:
    if force_full:
        return _forced_full(paths, "forced_full")
    if not paths:
        return _empty_scope()

    flags = _path_flags(paths)
    if flags["full_required"] or not flags["known"]:
        return _full_required_scope(paths, flags)
    return _scoped_result(paths, flags)


def _write_github_outputs(result: ScopeResult) -> None:
    output_env = os.environ.get("GITHUB_OUTPUT")
    if not output_env:
        return
    output_path = Path(output_env)
    with output_path.open("a", encoding="utf-8") as fh:
        for key, value in result.__dict__.items():
            if key == "changed_files":
                value = json.dumps(value)
            elif isinstance(value, bool):
                value = str(value).lower()
            fh.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=None)
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--force-full", action="store_true")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args(argv)

    paths = changed_files(args.base) if not args.force_full else []
    result = classify_paths(paths, force_full=args.force_full)
    text = result.to_json()
    print(text)
    if args.json_path:
        Path(args.json_path).write_text(text + "\n", encoding="utf-8")
    if args.github_output:
        _write_github_outputs(result)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
