"""Recurring bug log sweep helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server.database import OptimizationSignalRow, TaskRow
from server.schemas import BugIntakeRequest
from server.services.bug_intake import intake_bug

_MAX_LOG_LINES = 200
_MAX_LOG_CANDIDATES = 20


def _guess_project_key_from_text(text: str) -> str | None:
    lowered = str(text or "").lower()
    if "synapse-network-growing" in lowered:
        return "synapse-network-growing"
    if "synapse-network-provider" in lowered:
        return "synapse-network-provider"
    if "synapse-network-sdk" in lowered:
        return "synapse-network-sdk"
    if "synapse-network" in lowered:
        return "synapse-network"
    if "agents-memory" in lowered:
        return "agents-memory"
    return None


def _iter_log_paths() -> list[Path]:
    log_dir = Path(config.LOG_DIR)
    if not log_dir.exists():
        return []
    current = log_dir / config.LOG_FILE
    rotated = sorted(log_dir.glob(f"{config.LOG_FILE}*"))
    paths: list[Path] = []
    if current.exists():
        paths.append(current)
    for path in rotated:
        if path not in paths and path.is_file():
            paths.append(path)
    return paths[:3]


def _runtime_log_candidates() -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for path in _iter_log_paths():
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-_MAX_LOG_LINES:]
        except Exception:
            continue
        for line in lines:
            if "[ERROR]" not in line:
                continue
            project_key = _guess_project_key_from_text(line)
            title = "Runtime log error"
            if "Traceback" in line:
                title = "Runtime traceback detected"
            candidates.append(
                {
                    "source_key": "runtime_log_error",
                    "project_key": project_key,
                    "title": title,
                    "summary": line[-400:],
                    "severity": "high",
                    "fingerprint": line[-220:],
                    "source_ref": f"log:{path.name}",
                    "environment": config.ENV,
                    "log_excerpt": line[-500:],
                    "metadata": {"log_file": path.name},
                }
            )
            if len(candidates) >= _MAX_LOG_CANDIDATES:
                return candidates
    return candidates


def _task_failure_candidates(db: Session) -> list[dict[str, object]]:
    rows = (
        db.query(TaskRow)
        .filter(TaskRow.status.in_(("failed", "rejected")))
        .order_by(TaskRow.id.desc())
        .limit(20)
        .all()
    )
    candidates: list[dict[str, object]] = []
    for row in rows:
        error_text = str(row.last_error_message or row.description or "task failure")
        candidates.append(
            {
                "source_key": "task_failure",
                "project_key": str(row.project_id or "").strip().lower() or None,
                "title": f"Task failure #{int(row.id)}",
                "summary": error_text[:400],
                "severity": "high" if int(row.attempt_no or 1) > 1 else "normal",
                "fingerprint": f"{row.runtime_backend}:{error_text[:180]}",
                "source_ref": f"task:{int(row.id)}",
                "environment": config.ENV,
                "log_excerpt": error_text[:500],
                "metadata": {
                    "task_id": int(row.id),
                    "runtime_backend": str(row.runtime_backend or ""),
                    "attempt_no": int(row.attempt_no or 1),
                    "status": str(row.status or ""),
                },
            }
        )
    return candidates


def _workflow_incident_candidates(db: Session) -> list[dict[str, object]]:
    rows = (
        db.query(OptimizationSignalRow)
        .filter(
            OptimizationSignalRow.signal_type == "workflow_incident",
            OptimizationSignalRow.status == "open",
        )
        .order_by(OptimizationSignalRow.id.desc())
        .limit(20)
        .all()
    )
    candidates: list[dict[str, object]] = []
    for row in rows:
        candidates.append(
            {
                "source_key": "workflow_incident",
                "project_key": str(row.project_key or "").strip().lower() or None,
                "title": str(row.title or "Workflow incident"),
                "summary": str(row.summary or "")[:400],
                "severity": str(row.severity or "high"),
                "fingerprint": f"incident:{row.project_key}:{row.title}",
                "source_ref": f"optimization-signal:{int(row.id)}",
                "environment": config.ENV,
                "metadata": {
                    "signal_id": int(row.id),
                    "confidence": float(row.confidence or 0.0),
                    "occurrence_count": int(row.occurrence_count or 0),
                },
            }
        )
    return candidates


def run_bug_log_sweep(db: Session) -> dict[str, object]:
    created_ids: list[int] = []
    updated_ids: list[int] = []
    deduped_ids: list[int] = []
    intake_results: list[dict[str, object]] = []

    source_batches = {
        "runtime_log_error": _runtime_log_candidates(),
        "task_failure": _task_failure_candidates(db),
        "workflow_incident": _workflow_incident_candidates(db),
    }

    for source_key, items in source_batches.items():
        for payload in items:
            result = intake_bug(db, BugIntakeRequest(**payload))
            bug = dict(result.get("bug") or {})
            bug_id = int(bug.get("id") or 0)
            intake_results.append(
                {
                    "source_key": source_key,
                    "result": str(result.get("result") or ""),
                    "bug_id": bug_id,
                    "bug_key": str(bug.get("bug_key") or ""),
                    "priority": str((bug.get("scorecard") or {}).get("priority") or ""),
                }
            )
            if result["result"] == "created":
                created_ids.append(bug_id)
            elif result["result"] == "updated":
                updated_ids.append(bug_id)
            else:
                deduped_ids.append(bug_id)

    return {
        "created_bug_ids": sorted(set(created_ids)),
        "updated_bug_ids": sorted(set(updated_ids)),
        "deduped_bug_ids": sorted(set(deduped_ids)),
        "intake_results": intake_results,
        "source_counts": {key: len(items) for key, items in source_batches.items()},
        "total_candidates": sum(len(items) for items in source_batches.values()),
    }
