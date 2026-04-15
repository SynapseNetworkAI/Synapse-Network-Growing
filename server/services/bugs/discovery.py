"""Unified discovery recommendation helpers for bug and error self-healing."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import BugRecordRow, ErrorFingerprintRow
from server.services.projects.project_center import create_project, ensure_projects_materialized, resolve_project

_DISCOVERY_CONFIDENCE_HIGH = 0.82
_DISCOVERY_CONFIDENCE_LOW = 0.45
_HIGH_RISK_SOURCES = {"workflow_incident", "delivery_blocker_bug"}
_HIGH_RISK_ERROR_KINDS = {"workflow_incident"}
_AUTO_SEVERITIES = {"high", "critical"}


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _score_total(payload: dict[str, Any]) -> float:
    try:
        return float(payload.get("total") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _clamp_confidence(value: float) -> float:
    return round(max(0.0, min(value, 0.99)), 2)


def _display_name_from_key(project_key: str) -> str:
    return " ".join(part.capitalize() for part in str(project_key or "").replace("_", "-").split("-") if part.strip())


def resolve_or_create_signal_project(
    db: Session,
    *,
    project_key: str | None,
    project_root_path: str | None,
    display_name: str | None = None,
):
    ensure_projects_materialized(db)
    row = resolve_project(db, project_key=project_key, target_project_path=project_root_path)
    if row is not None:
        return row
    cleaned_key = str(project_key or "").strip().lower()
    cleaned_root = str(project_root_path or "").strip()
    if not cleaned_key or not cleaned_root:
        return None
    return create_project(
        db,
        project_key=cleaned_key,
        display_name=str(display_name or _display_name_from_key(cleaned_key) or cleaned_key),
        root_path=cleaned_root,
    )


def build_bug_discovery_recommendation(row: BugRecordRow) -> dict[str, object]:
    scorecard = _json_loads(getattr(row, "scorecard_json", None), {})
    blocker_flags = [str(item).strip() for item in list(scorecard.get("blocker_flags") or []) if str(item).strip()]
    severity = str(getattr(row, "severity", "normal") or "normal").strip().lower() or "normal"
    source_key = str(getattr(row, "source_key", "") or "").strip().lower()
    occurrence_count = int(getattr(row, "occurrence_count", 0) or 0)
    total = _score_total(scorecard)
    auto_eligible = bool(scorecard.get("auto_intake_eligible", False))
    priority = str(scorecard.get("priority") or severity or "normal").strip().lower() or "normal"

    if severity in {"low"} and occurrence_count <= 1 and total < 25.0:
        action = "ignore_as_noise"
        reason = "low-severity low-confidence bug candidate stayed below the auto-intake floor"
        confidence = _DISCOVERY_CONFIDENCE_LOW
    elif auto_eligible or severity in _AUTO_SEVERITIES or total >= 65.0 or blocker_flags:
        action = "auto_materialize"
        reason = "bug candidate is high-severity or high-value enough to enter the requirement self-healing loop"
        confidence = _clamp_confidence(max(0.78, total / 100.0))
    else:
        action = "queue_for_operator"
        reason = "bug candidate is worth backlog review but is not strong enough for autonomous materialization yet"
        confidence = _clamp_confidence(max(0.55, total / 100.0))

    auto_start_allowed = action == "auto_materialize" and source_key not in _HIGH_RISK_SOURCES and severity != "critical"
    return {
        "discovery_action": action,
        "confidence": confidence,
        "reason": reason,
        "target_project_key": str(getattr(row, "project_key", "") or "").strip() or None,
        "suggested_title": f"Bug Fix: {str(getattr(row, 'title', '') or '').strip()}",
        "suggested_priority": "high" if priority == "critical" else priority,
        "auto_start_allowed": auto_start_allowed,
        "severity": severity,
        "source_kind": str(getattr(row, "source_kind", "") or "").strip() or None,
        "source_key": source_key or None,
        "occurrence_count": occurrence_count,
    }


def build_error_discovery_recommendation(row: ErrorFingerprintRow) -> dict[str, object]:
    severity = str(getattr(row, "severity", "normal") or "normal").strip().lower() or "normal"
    source_kind = str(getattr(row, "source_kind", "") or "").strip().lower()
    occurrence_count = int(getattr(row, "occurrence_count", 0) or 0)
    has_stack = bool(str(getattr(row, "stack_signature", "") or "").strip())
    has_project = bool(str(getattr(row, "project_key", "") or getattr(row, "project_root_path", "") or "").strip())

    if severity == "low" and occurrence_count <= 1 and not has_stack:
        action = "ignore_as_noise"
        reason = "single low-severity error fingerprint lacks enough evidence for autonomous self-healing"
        confidence = 0.41
    elif severity in _AUTO_SEVERITIES or occurrence_count >= 2 or source_kind in {"runtime_log_error", "workflow_incident"}:
        action = "auto_materialize"
        reason = "error fingerprint is stable enough to become a self-healing requirement"
        confidence = 0.9 if severity in _AUTO_SEVERITIES else 0.84
    elif has_project:
        action = "queue_for_operator"
        reason = "error fingerprint has a target project but still needs operator confirmation before materialization"
        confidence = 0.63
    else:
        action = "ignore_as_noise"
        reason = "error fingerprint could not be routed confidently enough to a project"
        confidence = 0.38

    auto_start_allowed = action == "auto_materialize" and source_kind not in _HIGH_RISK_ERROR_KINDS and severity != "critical"
    return {
        "discovery_action": action,
        "confidence": _clamp_confidence(confidence),
        "reason": reason,
        "target_project_key": str(getattr(row, "project_key", "") or "").strip() or None,
        "suggested_title": f"Error Recovery: {str(getattr(row, 'summary', '') or '').strip()[:96]}",
        "suggested_priority": "high" if severity in _AUTO_SEVERITIES else "normal",
        "auto_start_allowed": auto_start_allowed,
        "severity": severity,
        "source_kind": source_kind or None,
        "occurrence_count": occurrence_count,
    }


def update_bug_discovery_state(
    row: BugRecordRow,
    *,
    recommendation: dict[str, object],
    status: str,
) -> None:
    row.discovery_status = str(status or "pending")
    row.discovery_recommendation_json = _json_dumps(recommendation)
    row.last_discovery_at = _utcnow()


def update_error_discovery_state(
    row: ErrorFingerprintRow,
    *,
    recommendation: dict[str, object],
    status: str,
) -> None:
    row.discovery_status = str(status or "pending")
    row.discovery_recommendation_json = _json_dumps(recommendation)
    row.last_discovery_at = _utcnow()
