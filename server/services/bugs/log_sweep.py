"""Recurring bug log sweep helpers."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server.database import OptimizationSignalRow
from server.schemas import BugIntakeRequest
from server.services.bugs.intake import intake_bug

_MAX_LOG_LINES = 200
_MAX_LOG_CANDIDATES = 20
_MAX_TRACEBACK_CAPTURE_LINES = 10
_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(?P<level>[A-Z]+)\] (?P<logger>[^:]+): (?P<message>.*)$"
)
_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)
_HEX_ID_RE = re.compile(r"\b[a-f0-9]{12,}\b", re.IGNORECASE)
_DIGIT_RUN_RE = re.compile(r"\b\d{3,}\b")
_REQUEST_ID_RE = re.compile(r"\b(request_id|task_id|bug_id|signal_id|requirement_id|workflow_run_id)=\S+")
_AUTOBUG_TAG_RE = re.compile(r"\bAUTOBUG-[A-Z-]+-\d{8}-\d+\b")


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


def _looks_like_log_line(line: str) -> bool:
    return bool(_LOG_LINE_RE.match(line.strip()))


def _normalize_log_message(message: str) -> str:
    normalized = str(message or "").strip()
    normalized = _REQUEST_ID_RE.sub(r"\1=<id>", normalized)
    normalized = _AUTOBUG_TAG_RE.sub(lambda match: re.sub(r"\d", "#", match.group(0)), normalized)
    normalized = _UUID_RE.sub("<uuid>", normalized)
    normalized = _HEX_ID_RE.sub("<hex>", normalized)
    normalized = _DIGIT_RUN_RE.sub("#", normalized)
    return " ".join(normalized.split())


def _extract_stack_trace(lines: list[str], start_index: int) -> tuple[str, int]:
    captured: list[str] = []
    index = start_index
    while index < len(lines):
        line = lines[index]
        if _looks_like_log_line(line):
            break
        stripped = line.rstrip()
        if not stripped:
            if captured:
                break
            index += 1
            continue
        captured.append(stripped)
        index += 1
        if len(captured) >= _MAX_TRACEBACK_CAPTURE_LINES:
            break
    return "\n".join(captured), index


def _error_title_for_message(stack_trace: str) -> str:
    if stack_trace:
        lines = [line.strip() for line in stack_trace.splitlines() if line.strip()]
        if lines:
            tail = lines[-1]
            if ":" in tail:
                return tail.split(":", 1)[0].strip() or "Runtime traceback detected"
            if "Error" in tail or "Exception" in tail:
                return tail
        return "Runtime traceback detected"
    return "Runtime log error"


def _runtime_log_candidates() -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for path in _iter_log_paths():
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-_MAX_LOG_LINES:]
        except Exception:
            continue
        index = 0
        while index < len(lines):
            line = lines[index]
            match = _LOG_LINE_RE.match(line)
            if not match or match.group("level") != "ERROR":
                index += 1
                continue
            message = str(match.group("message") or "").strip()
            logger_name = str(match.group("logger") or "").strip()
            stack_trace, next_index = _extract_stack_trace(lines, index + 1)
            joined = "\n".join(filter(None, [line, stack_trace]))
            project_key = _guess_project_key_from_text(joined)
            normalized_message = _normalize_log_message(message)
            normalized_stack = _normalize_log_message(stack_trace)
            title = _error_title_for_message(stack_trace)
            candidates.append(
                {
                    "source_key": "runtime_log_error",
                    "project_key": project_key,
                    "title": title,
                    "summary": normalized_message[:400] or line[-400:],
                    "severity": "high",
                    "fingerprint": f"{title}|{normalized_message}|{normalized_stack[:240]}",
                    "source_ref": f"log:{path.name}",
                    "environment": config.ENV,
                    "log_excerpt": line[-500:],
                    "stack_trace": stack_trace or None,
                    "metadata": {
                        "log_file": path.name,
                        "logger_name": logger_name,
                        "normalized_message": normalized_message,
                    },
                }
            )
            if len(candidates) >= _MAX_LOG_CANDIDATES:
                return candidates
            index = next_index
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
