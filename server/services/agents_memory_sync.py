"""Non-blocking sync of requirement and workflow data to Agents-Memory."""
from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("ops-dashboard.agents-memory-sync")

AGENTS_MEMORY_URL = os.environ.get("AGENTS_MEMORY_URL", "http://localhost:10100")
AGENTS_MEMORY_SYNC_ENABLED = os.environ.get("AGENTS_MEMORY_SYNC_ENABLED", "true").lower() == "true"
_TIMEOUT = 5  # seconds


def _push(content: str, source_type: str, project: str) -> None:
    """Fire-and-forget: POST to Agents-Memory /api/ingest in a daemon thread."""
    if not AGENTS_MEMORY_SYNC_ENABLED:
        return

    def _do() -> None:
        try:
            import urllib.request  # stdlib-only, no extra deps
            import json as _json

            payload = _json.dumps(
                {"content": content, "source_type": source_type, "project": project}
            ).encode()
            req = urllib.request.Request(
                f"{AGENTS_MEMORY_URL}/api/ingest",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                body = _json.loads(resp.read())
                logger.info(
                    "agents-memory ingest ok: %s / %s (project=%s)",
                    source_type, body.get("id", "?"), project,
                )
        except Exception as exc:
            logger.debug("agents-memory ingest failed (non-critical): %s", exc)

    threading.Thread(target=_do, daemon=True).start()


def _project_name(target_project_path: str | None) -> str:
    if not target_project_path:
        return "synapse-network-growing"
    name = Path(target_project_path).name
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return normalized or "synapse-network-growing"


# ── Public push functions ────────────────────────────────────────────────────


def push_requirement_completed(
    requirement: Any,
    steps_summary: list[dict[str, Any]],
    output_summary: str,
    changed_files: list[str],
) -> None:
    """Push a completed requirement summary to Agents-Memory."""
    project = _project_name(getattr(requirement, "target_project_path", None))
    steps_table = "\n".join(
        f"| {s.get('title', '')} | {s.get('role', '')} | {s.get('status', '')} | {s.get('execution_time_ms') or '-'}ms |"
        for s in steps_summary
    )
    files_list = "\n".join(f"- {f}" for f in changed_files) if changed_files else "（无）"
    req_id = getattr(requirement, "id", "")

    content = f"""---
id: REQ-{req_id}
title: "{requirement.title}"
project: {project}
source_type: requirement_completion
status: completed
priority: {requirement.priority}
completed_at: {requirement.completed_at}
created_at: {requirement.created_at}
---

## 需求描述

{requirement.description_markdown}

## 执行步骤

| 步骤 | 角色 | 状态 | 执行耗时 |
|------|------|------|---------|
{steps_table}

## 产出摘要

{(output_summary or '（无输出）')[:2000]}

## 文件改动

{files_list}
"""
    _push(content, "requirement_completion", project)
