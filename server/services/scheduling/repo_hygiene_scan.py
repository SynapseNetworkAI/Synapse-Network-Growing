"""Read-only scanner for weekly repository hygiene review."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from server import config


ROOT_MARKDOWN_ALLOWLIST = {"AGENTS.md", "ARCHITECTURE.md", "README.md", "llms.txt"}
TODO_COMMENT_PATTERNS = (
    re.compile(r"#\s*(TODO|FIXME)\b"),
    re.compile(r"//\s*(TODO|FIXME)\b"),
    re.compile(r"/\*\s*(TODO|FIXME)\b"),
    re.compile(r"\*\s*(TODO|FIXME)\b"),
)


def _repo_rel(path: Path) -> str:
    try:
        return path.relative_to(config.PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _finding(
    *,
    finding_id: str,
    category: str,
    title: str,
    description: str,
    path: str | None = None,
    severity: str = "low",
    risk_level: str = "normal",
    auto_fixable: bool = False,
    recommended_action: str,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "category": category,
        "severity": severity,
        "risk_level": risk_level,
        "title": title,
        "description": description,
        "path": path,
        "auto_fixable": bool(auto_fixable),
        "recommended_action": recommended_action,
    }


def _has_frontmatter(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    if not text.startswith("---\n"):
        return False
    return "\n---\n" in text[4:]


def _root_markdown_findings(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.md")):
        if path.name in ROOT_MARKDOWN_ALLOWLIST:
            continue
        findings.append(
            _finding(
                finding_id=f"root-markdown:{path.name}",
                category="repo_structure",
                title=f"Root markdown file should be archived or moved: {path.name}",
                description="Harness docs rules keep active design docs under docs/design-docs and historical plans under docs/archive.",
                path=_repo_rel(path),
                auto_fixable=False,
                recommended_action="Review whether this file belongs under docs/design-docs or docs/archive before moving it.",
            )
        )
    return findings


def _frontmatter_findings(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for base in [root / "docs" / "design-docs", root / "docs" / "plans"]:
        if not base.exists():
            continue
        for path in sorted(base.glob("*.md")):
            if _has_frontmatter(path):
                continue
            findings.append(
                _finding(
                    finding_id=f"missing-frontmatter:{_repo_rel(path)}",
                    category="docs_metadata",
                    title=f"Missing docs frontmatter: {_repo_rel(path)}",
                    description="Current design and planning docs should carry machine-checkable YAML metadata.",
                    path=_repo_rel(path),
                    auto_fixable=True,
                    recommended_action="Add standard docs lifecycle frontmatter with id/title/status/date/author/target_repo.",
                )
            )
    return findings


def _pr_template_findings(root: Path) -> list[dict[str, Any]]:
    path = root / ".github" / "pull_request_template.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    if "literal `\\n` escape sequences" in text:
        return []
    return [
        _finding(
            finding_id="pr-template:literal-newline-hygiene",
            category="ci_review_hygiene",
            title="PR template missing literal newline hygiene checkbox",
            description="Recent PR comments were malformed by pasted literal \\n sequences; the template should guard this.",
            path=_repo_rel(path),
            auto_fixable=True,
            recommended_action="Add a PR checklist item requiring real Markdown line breaks instead of literal \\n escapes.",
        )
    ]


def _has_todo_comment(text: str) -> bool:
    return any(pattern.search(text) for pattern in TODO_COMMENT_PATTERNS)


def _todo_findings(root: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for base in [root / "server", root / "scripts", root / "dashboard" / "src"]:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in {".py", ".ts", ".tsx"} or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not _has_todo_comment(text):
                continue
            findings.append(
                _finding(
                    finding_id=f"todo:{_repo_rel(path)}",
                    category="code_health",
                    title=f"TODO/FIXME needs review: {_repo_rel(path)}",
                    description="Stale TODO/FIXME comments should become tracked requirements or be removed when obsolete.",
                    path=_repo_rel(path),
                    severity="medium",
                    risk_level="normal",
                    auto_fixable=False,
                    recommended_action="Review the TODO/FIXME and either materialize a requirement or remove obsolete commentary.",
                )
            )
            if len(findings) >= limit:
                return findings
    return findings


def scan_repo_hygiene_payload(*, root: Path | None = None) -> dict[str, Any]:
    repo_root = root or config.PROJECT_ROOT
    repo_findings = [
        *_root_markdown_findings(repo_root),
        *_frontmatter_findings(repo_root),
        *_pr_template_findings(repo_root),
        *_todo_findings(repo_root),
    ]
    return {
        "workflow_key": "weekly_repo_hygiene_review",
        "repo_root": str(repo_root),
        "repo_findings": repo_findings,
        "ops_findings": [],
        "finding_count": len(repo_findings),
        "auto_fixable_count": sum(
            1 for item in repo_findings if item.get("auto_fixable")
        ),
    }
