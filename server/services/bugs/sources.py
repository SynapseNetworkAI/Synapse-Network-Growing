"""Bug source registry definitions and source-level summary helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import ArtifactRow, OptimizationSignalRow, TaskRow


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


_BUILTIN_BUG_SOURCE_REGISTRY: list[dict[str, Any]] = [
    {
        "source_key": "external_log_center_error",
        "display_name": "External Log Center Error",
        "source_kind": "centralized_logs",
        "ingest_mode": "push_api",
        "project_resolution_rule": "prefer_event_project_metadata_then_service_mapping",
        "severity_mapping": {
            "critical": "production_wide_outage_or_cross_project_blocker",
            "high": "repeated_error_burst_or_core_flow_breakage",
            "normal": "single_service_error_candidate",
        },
        "dedupe_scope": "project_key + fingerprint + source_ref",
        "auto_requirement_policy": {
            "allowed": True,
            "default_priority": "high",
            "requires_scoring": True,
        },
        "sample_evidence_types": ["log_center_event", "stack_trace", "alert_metadata"],
        "notes": "External logging platforms or alerting systems can push normalized errors here.",
    },
    {
        "source_key": "manual_bug_report",
        "display_name": "Manual Bug Report",
        "source_kind": "manual_input",
        "ingest_mode": "push_api",
        "project_resolution_rule": "explicit_project_key_or_root_path",
        "severity_mapping": {
            "critical": "production_blocker_or_funds_risk",
            "high": "core_flow_breakage_or_high_recurrence",
            "normal": "localized_or_non_blocking_failure",
        },
        "dedupe_scope": "project_key + fingerprint + source_kind",
        "auto_requirement_policy": {
            "allowed": True,
            "default_priority": "high",
            "requires_scoring": True,
        },
        "sample_evidence_types": ["operator_payload", "stack_trace", "log_excerpt"],
        "notes": "Operator or external system submits a bug directly into the COO system.",
    },
    {
        "source_key": "runtime_log_error",
        "display_name": "Runtime Log Error",
        "source_kind": "runtime_logs",
        "ingest_mode": "log_sweep",
        "project_resolution_rule": "derive_from_log_metadata_or_path_hint",
        "severity_mapping": {
            "critical": "repeated_runtime_guard_or_system_blocker",
            "high": "persistent_runtime_failure",
            "normal": "single_error_candidate",
        },
        "dedupe_scope": "project_key + normalized_error_stem + component",
        "auto_requirement_policy": {
            "allowed": True,
            "default_priority": "high",
            "requires_scoring": True,
        },
        "sample_evidence_types": ["service_log", "runtime_error", "monitor_event"],
        "notes": "Recurring workflow bug_log_sweep will eventually normalize service and runtime errors here.",
    },
    {
        "source_key": "workflow_incident",
        "display_name": "Workflow Incident",
        "source_kind": "artifact_derived",
        "ingest_mode": "artifact_derived",
        "project_resolution_rule": "derive_from_requirement_target_or_project_catalog",
        "severity_mapping": {
            "critical": "incident_recovery_required",
            "high": "operator_review_required",
            "normal": "needs_revision",
        },
        "dedupe_scope": "project_key + incident_code + recovery_status",
        "auto_requirement_policy": {
            "allowed": True,
            "default_priority": "high",
            "requires_scoring": True,
        },
        "sample_evidence_types": ["incident_record", "workflow_artifact", "recovery_narrative"],
        "notes": "Workflow incidents already exist in the runtime evidence model and should feed bug intake.",
    },
    {
        "source_key": "task_failure",
        "display_name": "Task Failure",
        "source_kind": "task_runtime",
        "ingest_mode": "artifact_derived",
        "project_resolution_rule": "derive_from_task_project_or_requirement_target",
        "severity_mapping": {
            "critical": "systemic_runtime_failure_or_high_budget_blocker",
            "high": "repeated_failed_task",
            "normal": "isolated_failed_task",
        },
        "dedupe_scope": "project_id + runtime_backend + normalized_error_stem",
        "auto_requirement_policy": {
            "allowed": False,
            "default_priority": "normal",
            "requires_scoring": True,
        },
        "sample_evidence_types": ["task_log", "runtime_error", "task_output"],
        "notes": "Single task failures are signals first; repeated or blocking failures become backlog candidates.",
    },
    {
        "source_key": "delivery_blocker_bug",
        "display_name": "Delivery Blocker Bug",
        "source_kind": "delivery_state",
        "ingest_mode": "artifact_derived",
        "project_resolution_rule": "derive_from_requirement_target_or_delivery_project",
        "severity_mapping": {
            "critical": "publish_blocked_for_core_project",
            "high": "delivery_gate_blocked",
            "normal": "non_urgent_release_gap",
        },
        "dedupe_scope": "project_key + publish_blocker + release_mode",
        "auto_requirement_policy": {
            "allowed": True,
            "default_priority": "high",
            "requires_scoring": True,
        },
        "sample_evidence_types": ["delivery_state", "publish_blocker", "required_check"],
        "notes": "Release blockers should become bug backlog candidates, not only delivery metadata.",
    },
]


def get_bug_source_definition(source_key: str) -> dict[str, Any]:
    """Return the normalized bug source definition for a source key."""

    normalized = str(source_key or "").strip().lower()
    for definition in _BUILTIN_BUG_SOURCE_REGISTRY:
        if str(definition.get("source_key") or "").strip().lower() == normalized:
            return dict(definition)
    raise ValueError(f"Unknown bug source: {source_key}")


def _count_manual_bug_reports(db: Session) -> int:
    return db.query(ArtifactRow).filter(ArtifactRow.artifact_type == "bug_report").count()


def _count_external_log_center_errors(db: Session) -> int:
    from server.database import BugRecordRow

    return db.query(BugRecordRow).filter(BugRecordRow.source_key == "external_log_center_error", BugRecordRow.status == "open").count()


def _count_runtime_log_errors(db: Session) -> int:
    return db.query(TaskRow).filter(TaskRow.status.in_(("failed", "rejected"))).count()


def _count_workflow_incidents(db: Session) -> int:
    return db.query(OptimizationSignalRow).filter(
        OptimizationSignalRow.signal_type == "workflow_incident",
        OptimizationSignalRow.status == "open",
    ).count()


def _count_task_failures(db: Session) -> int:
    return db.query(TaskRow).filter(TaskRow.status.in_(("failed", "rejected"))).count()


def _count_delivery_blockers(db: Session) -> int:
    total = 0
    for row in db.query(ArtifactRow).filter(ArtifactRow.artifact_type == "delivery_state").all():
        payload = _json_loads(getattr(row, "machine_readable_payload", None), {})
        blockers = payload.get("publish_blockers") or []
        if isinstance(blockers, list) and blockers:
            total += 1
    return total


def list_bug_source_registry(db: Session) -> dict[str, Any]:
    """Return the bug source registry enriched with current observed counts."""

    now = datetime.now(timezone.utc)
    observed_count_by_source = {
        "external_log_center_error": _count_external_log_center_errors(db),
        "manual_bug_report": _count_manual_bug_reports(db),
        "runtime_log_error": _count_runtime_log_errors(db),
        "workflow_incident": _count_workflow_incidents(db),
        "task_failure": _count_task_failures(db),
        "delivery_blocker_bug": _count_delivery_blockers(db),
    }
    sources = []
    for definition in _BUILTIN_BUG_SOURCE_REGISTRY:
        source_key = str(definition["source_key"])
        sources.append(
            {
                **definition,
                "observed_open_count": int(observed_count_by_source.get(source_key, 0)),
            }
        )
    return {
        "generated_at": now,
        "total_sources": len(sources),
        "total_open_candidates": sum(int(item["observed_open_count"]) for item in sources),
        "sources": sources,
    }
