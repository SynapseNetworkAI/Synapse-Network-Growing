from __future__ import annotations

"""Load project context files for agent execution."""
import logging
from pathlib import Path

from server.config import PROJECT_ROOT

logger = logging.getLogger("ops-dashboard.context_loader")

MAX_FILE_SIZE = 100_000   # 100 KB per file
MAX_CONTEXT_SIZE = 500_000  # 500 KB total


def _safe_resolve(project_root: Path, rel_path: str) -> Path | None:
    """Resolve a relative path and ensure it stays inside project_root."""
    full = (project_root / rel_path).resolve()
    try:
        full.relative_to(project_root.resolve())
    except ValueError:
        logger.warning("Path traversal blocked: %s", rel_path)
        return None
    return full


def load_context(project_root: Path | None = None, extra_files: list[str] | None = None) -> str:
    """Load product-marketing-context.md + optional extra context files.

    Returns concatenated Markdown string, respecting size limits.
    """
    root = (project_root or PROJECT_ROOT).resolve()
    parts: list[str] = []
    total = 0

    # Always load product marketing context
    ctx_path = root / ".agents" / "product-marketing-context.md"
    if ctx_path.exists():
        content = ctx_path.read_text(encoding="utf-8")[:MAX_FILE_SIZE]
        parts.append(f"# Product Marketing Context\n{content}")
        total += len(parts[-1])

    # Extra files (user-specified references)
    for rel_path in (extra_files or []):
        if total >= MAX_CONTEXT_SIZE:
            logger.warning("Context size limit reached, skipping remaining files")
            break
        full = _safe_resolve(root, rel_path)
        if not full or not full.exists() or not full.is_file():
            continue
        content = full.read_text(encoding="utf-8")[:MAX_FILE_SIZE]
        chunk = f"# Reference: {rel_path}\n{content}"
        parts.append(chunk)
        total += len(chunk)

    return "\n\n---\n\n".join(parts)
