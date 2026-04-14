"""File-change baseline, snapshot, and payload helpers for workflow orchestration."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

from server.config import PROJECT_ROOT
from server.database import TaskRow
from server.services.runtime.copilot_sdk_state import task_output_dir


def _task_output_dir_for_snapshot(task: TaskRow) -> Path | None:
    """Resolve the task output directory used for file-change snapshots."""

    output_path = str(task.output_path or "").strip()
    if output_path:
        return Path(output_path).resolve().parent
    task_id = int(getattr(cast(Any, task), "id", 0) or 0)
    agent_id = str(getattr(cast(Any, task), "agent_id", "unknown") or "unknown")
    if task_id <= 0:
        return None
    return task_output_dir(PROJECT_ROOT, agent_id, task_id)


def _parse_git_diff_files(diff_text: str, *, target_path: str) -> list[dict[str, Any]]:
    """Parse unified git diff text into structured changed-file records."""

    files: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current:
                files.append(current)
            current = {
                "filename": "",
                "additions": 0,
                "deletions": 0,
                "patch": "",
                "target_project_path": target_path,
            }
            continue
        if current is None:
            continue
        if line.startswith("+++ b/"):
            current["filename"] = line[6:].rstrip("\n")
        elif line.startswith("+") and not line.startswith("+++"):
            current["additions"] += 1
            current["patch"] += line
        elif line.startswith("-") and not line.startswith("---"):
            current["deletions"] += 1
            current["patch"] += line
        else:
            current["patch"] += line
    if current:
        files.append(current)
    return [item for item in files if item["filename"]]


def _git_dirty_files(target_dir: Path) -> list[str]:
    """Return dirty files relative to the git root for a target directory."""

    result = subprocess.run(
        ["git", "diff", "HEAD", "--name-only"],
        cwd=str(target_dir),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    dirty_files: list[str] = []
    for raw_line in result.stdout.splitlines():
        path = raw_line.strip()
        if not path:
            continue
        dirty_files.append(path)
    return sorted(set(dirty_files))


def _file_content_sha256(path: Path) -> str | None:
    """Return the SHA256 digest for a file path if it exists."""

    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dirty_file_hashes(target_dir: Path, dirty_files: list[str]) -> dict[str, str | None]:
    """Capture current hashes for the pre-existing dirty files in a repo."""

    hashes: dict[str, str | None] = {}
    for relative_path in dirty_files:
        candidate = (target_dir / relative_path).resolve()
        hashes[relative_path] = _file_content_sha256(candidate)
    return hashes


def _load_task_file_changes(task: TaskRow) -> dict[str, Any]:
    """Load the cached file-change payload for a task if present."""

    output_path = str(task.output_path or "").strip()
    if not output_path:
        return {}
    cache_file = Path(output_path).parent / "file-changes.json"
    if not cache_file.exists():
        return {}
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_task_file_change_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy and current file-change payloads to a single shape."""

    normalized = dict(payload or {})
    if not normalized:
        normalized["legacy_snapshot"] = False
        return normalized
    baseline_captured_at = str(normalized.get("baseline_captured_at") or "").strip()
    if baseline_captured_at:
        normalized["legacy_snapshot"] = False
        return normalized
    normalized["legacy_snapshot"] = True
    normalized["changed_files"] = []
    normalized["project_snapshots"] = []
    normalized["changed_target_project_paths"] = []
    normalized["change_warning"] = (
        "This task was captured before task-scoped diff baselines were introduced. "
        "Re-run the step to collect a clean task-only file change snapshot."
    )
    return normalized


def _task_changed_files_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract normalized changed-file rows from a snapshot payload."""

    changed_files_raw = payload.get("changed_files") or []
    return [
        {
            "filename": str(item.get("filename") or "").strip(),
            "additions": int(item.get("additions") or 0),
            "deletions": int(item.get("deletions") or 0),
            "patch": str(item.get("patch") or ""),
            "target_project_path": str(item.get("target_project_path") or "").strip() or None,
        }
        for item in changed_files_raw
        if isinstance(item, dict) and str(item.get("filename") or "").strip()
    ]


def _task_changed_output_files(changed_files: list[dict[str, Any]]) -> list[str]:
    """Return the unique changed filenames from normalized change rows."""

    seen: set[str] = set()
    output_files: list[str] = []
    for item in changed_files:
        filename = str(item.get("filename") or "").strip()
        if not filename or filename in seen:
            continue
        seen.add(filename)
        output_files.append(filename)
    return output_files


def _task_has_tracked_repo_changes(task: TaskRow) -> bool:
    """Return whether a task snapshot contains tracked repository file changes."""

    payload = _normalize_task_file_change_payload(_load_task_file_changes(task))
    changed_files = _task_changed_files_from_payload(payload)
    return bool(changed_files)


__all__ = [
    "_dirty_file_hashes",
    "_file_content_sha256",
    "_git_dirty_files",
    "_load_task_file_changes",
    "_normalize_task_file_change_payload",
    "_parse_git_diff_files",
    "_task_changed_files_from_payload",
    "_task_changed_output_files",
    "_task_has_tracked_repo_changes",
    "_task_output_dir_for_snapshot",
]
