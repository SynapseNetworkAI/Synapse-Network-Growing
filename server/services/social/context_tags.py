"""Tagged source-context contracts for agent-generated content."""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

from server import config
from server.services.social.distribution_asset_signals import _public_safe


class ContextTagContract(BaseModel):
    ref_key: str
    project_key: str
    root_dir_name: str
    label: str
    whitelist_globs: tuple[str, ...]
    required: bool = True


class ContextTagSnippet(BaseModel):
    ref_key: str
    project_key: str
    file_path: str
    label: str
    language: str | None = None
    excerpt: str
    content_hash: str


class ContextTagCheckResult(BaseModel):
    checked: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    snippets: list[ContextTagSnippet] = Field(default_factory=list)


class InsufficientSourceContextError(ValueError):
    code = "insufficient_source_context"

    def __init__(self, ref_key: str) -> None:
        super().__init__(
            f"{self.code}: required source context tag missing for {ref_key}"
        )
        self.ref_key = ref_key


REQUIRED_CONTEXT_TAGS: tuple[ContextTagContract, ...] = (
    ContextTagContract(
        ref_key="synapse-network-sdk:quickstart",
        project_key="synapse-network-sdk",
        root_dir_name="Synapse-Network-Sdk",
        label="quickstart",
        whitelist_globs=(
            "README*.md",
            "docs/**/*.md",
            "python/README*.md",
            "python/examples/**/*.py",
            "typescript/src/**/*.ts",
            "java/**/*.java",
        ),
    ),
    ContextTagContract(
        ref_key="synapse-network-mcp-server:spring_boot_mcp",
        project_key="synapse-network-mcp-server",
        root_dir_name="Synapse-Network-MCP-Server",
        label="spring_boot_mcp",
        whitelist_globs=(
            "README*.md",
            "docs/**/*.md",
            "src/**/*.java",
            "src/**/*.kt",
            "examples/**/*.java",
            "examples/**/*.md",
        ),
    ),
    ContextTagContract(
        ref_key="synapse-network-provider:onboarding",
        project_key="synapse-network-provider",
        root_dir_name="Synapse-Network-Provider",
        label="onboarding",
        whitelist_globs=(
            "README*.md",
            "docs/**/*.md",
            "scripts/**/*.py",
            "server/**/*.py",
        ),
    ),
)


def resolve_required_context_tag(
    ref_key: str,
    *,
    workspace_root: Path | None = None,
    contracts: tuple[ContextTagContract, ...] = REQUIRED_CONTEXT_TAGS,
) -> ContextTagSnippet:
    contract = _contract_for_ref(ref_key, contracts)
    root = _project_root(contract, workspace_root=workspace_root)
    for path in _candidate_files(root, contract.whitelist_globs):
        snippet = _snippet_from_file(path, root=root, contract=contract)
        if snippet:
            return snippet
    raise InsufficientSourceContextError(ref_key)


def check_required_context_tags(
    *,
    ref_keys: list[str] | None = None,
    workspace_root: Path | None = None,
    contracts: tuple[ContextTagContract, ...] = REQUIRED_CONTEXT_TAGS,
) -> ContextTagCheckResult:
    selected = tuple(
        contract
        for contract in contracts
        if ref_keys is None or contract.ref_key in set(ref_keys)
    )
    snippets: list[ContextTagSnippet] = []
    missing: list[str] = []
    checked: list[str] = []
    for contract in selected:
        checked.append(contract.ref_key)
        try:
            snippets.append(
                resolve_required_context_tag(
                    contract.ref_key,
                    workspace_root=workspace_root,
                    contracts=contracts,
                )
            )
        except InsufficientSourceContextError:
            missing.append(contract.ref_key)
    return ContextTagCheckResult(checked=checked, missing=missing, snippets=snippets)


def _contract_for_ref(
    ref_key: str, contracts: tuple[ContextTagContract, ...]
) -> ContextTagContract:
    for contract in contracts:
        if contract.ref_key == ref_key:
            return contract
    raise InsufficientSourceContextError(ref_key)


def _project_root(
    contract: ContextTagContract, *, workspace_root: Path | None = None
) -> Path:
    root = workspace_root or Path(
        os.environ.get("OPS_WORKSPACE_ROOT", str(config.PROJECT_ROOT.parent))
    )
    return root / contract.root_dir_name


def _candidate_files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    if not root.is_dir():
        return []
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(path for path in root.glob(pattern) if _is_safe_candidate(path))
    return sorted(set(paths))


def _is_safe_candidate(path: Path) -> bool:
    blocked_parts = {".git", ".venv", "node_modules", "dist", "build", "logs"}
    return path.is_file() and not blocked_parts.intersection(path.parts)


def _snippet_from_file(
    path: Path, *, root: Path, contract: ContextTagContract
) -> ContextTagSnippet | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    start_index = _find_tag_line(lines, contract.label)
    if start_index is None:
        return None
    excerpt = _extract_tagged_excerpt(lines, start_index)
    return ContextTagSnippet(
        ref_key=contract.ref_key,
        project_key=contract.project_key,
        file_path=_relative_path(path, root),
        label=contract.label,
        language=_language_for_path(path),
        excerpt=_public_safe(excerpt),
        content_hash=_short_hash(excerpt),
    )


def _find_tag_line(lines: list[str], label: str) -> int | None:
    pattern = re.compile(rf"@synapse-context:{re.escape(label)}(?:\b|$)")
    for index, line in enumerate(lines):
        if pattern.search(line):
            return index
    return None


def _extract_tagged_excerpt(
    lines: list[str], start_index: int, *, max_lines: int = 80, max_chars: int = 4000
) -> str:
    collected: list[str] = []
    for line in lines[start_index : start_index + max_lines]:
        if collected and "@synapse-context:" in line:
            break
        collected.append(line)
        if len("\n".join(collected)) >= max_chars:
            break
    return "\n".join(collected)[:max_chars]


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _language_for_path(path: Path) -> str | None:
    suffix = path.suffix.lower()
    return {
        ".java": "java",
        ".kt": "kotlin",
        ".md": "markdown",
        ".py": "python",
        ".ts": "typescript",
    }.get(suffix)


def _short_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]
