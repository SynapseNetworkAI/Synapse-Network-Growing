"""Optimization signal ingestion and signal-to-requirement helpers."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import (
    ApprovalRequestRow,
    ApprovalRow,
    ArtifactRow,
    OptimizationSignalRow,
    RequirementRow,
    TaskRow,
)
from server.schemas import RequirementCreate
from server.services.signals.incidents import list_open_incidents
from server.services.signals.optimization_templates import build_template_instance, template_key_for_signal
from server.services.projects.intelligence import build_project_catalog
from server.services.requirements.sources import normalize_requirement_intake_metadata
from server.services.workflows.orchestrator import create_requirement

logger = logging.getLogger("ops-dashboard.optimization_signals")


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _normalize_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value.lower()).strip("-")
    return normalized or "signal"


def _parse_utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _severity_rank(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(str(value), 0)


def _project_map(db: Session) -> dict[str, dict[str, Any]]:
    catalog = build_project_catalog(db)
    result: dict[str, dict[str, Any]] = {}
    for root, data in catalog.items():
        result[root] = data
    return result


def build_signal_project_map(db: Session) -> dict[str, dict[str, Any]]:
    """Return project metadata used by optimization-signal API surfaces."""

    return _project_map(db)


def _split_target_paths(value: str | None) -> list[str]:
    if not value:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for raw in value.splitlines():
        candidate = raw.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


def _requirement_project_contexts(requirement: RequirementRow, project_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for root in _split_target_paths(requirement.target_project_path):
        project = dict(project_map.get(root) or {})
        if not project:
            project = {
                "project_key": None,
                "display_name": root.rsplit("/", 1)[-1],
                "root_path": root,
            }
        contexts.append(project)
    if not contexts:
        contexts.append(
            {
                "project_key": None,
                "display_name": "Org Ops",
                "root_path": None,
            }
        )
    return contexts


def _task_project_context(task: TaskRow, project_map: dict[str, dict[str, Any]], requirement_by_id: dict[int, RequirementRow]) -> dict[str, Any]:
    if task.project_id and task.project_id in project_map:
        return dict(project_map[task.project_id])
    for step in task.workflow_steps:
        requirement = requirement_by_id.get(int(step.requirement_id))
        if requirement is None:
            continue
        contexts = _requirement_project_contexts(requirement, project_map)
        if contexts:
            return contexts[0]
    return {
        "project_key": None,
        "display_name": "TaskBoard",
        "root_path": None,
    }


def _signal_title(prefix: str, display_name: str, suffix: str) -> str:
    return f"{prefix}: {display_name} {suffix}".strip()


_SIGNAL_IMPACT_BASE = {
    "delivery_blocker": 26.0,
    "bug_report": 24.0,
    "manual_override": 18.0,
}
_SIGNAL_RISK_BASE = {
    "delivery_blocker": 10.0,
    "bug_report": 8.0,
    "manual_override": 5.0,
    "workflow_incident": 12.0,
}
_SIGNAL_COST = {
    "delivery_blocker": 6.0,
    "bug_report": 9.0,
    "manual_override": 12.0,
    "workflow_incident": 8.0,
}
_SEVERITY_RISK = {"high": 20.0, "medium": 12.0, "low": 6.0}
_MAX_STORED_EVIDENCE_ITEMS = 8


def _signal_score_metadata(total: float, *, automation_ready: bool, status: str, confidence: float) -> dict[str, Any]:
    auto_intake_eligible = (
        status == "open"
        and automation_ready
        and confidence >= 0.72
        and total >= 60.0
    )
    if auto_intake_eligible:
        intake_recommendation = "auto_create"
    elif not automation_ready:
        intake_recommendation = "needs_setup"
    elif total >= 45.0:
        intake_recommendation = "review"
    else:
        intake_recommendation = "observe"

    if total >= 72.0:
        recommended_priority = "high"
    elif total >= 45.0:
        recommended_priority = "normal"
    else:
        recommended_priority = "low"

    return {
        "auto_intake_eligible": auto_intake_eligible,
        "intake_recommendation": intake_recommendation,
        "recommended_priority": recommended_priority,
    }


def _evidence_dedupe_key(evidence: dict[str, Any]) -> str:
    if "blocker" in evidence:
        payload = {
            "kind": "delivery_blocker",
            "blocker": str(evidence.get("blocker") or "").strip(),
            "publish_status": str(evidence.get("publish_status") or "").strip(),
        }
    elif "incident_code" in evidence:
        payload = {
            "kind": "workflow_incident",
            "incident_family": str(evidence.get("incident_family") or "").strip(),
            "incident_code": str(evidence.get("incident_code") or "").strip(),
            "recovery_status": str(evidence.get("recovery_status") or "").strip(),
            "summary": str(evidence.get("summary") or "").strip(),
        }
    elif "failed_checks" in evidence or "step_type" in evidence:
        payload = {
            "kind": "bug_report",
            "step_type": str(evidence.get("step_type") or "").strip(),
            "failed_checks": sorted(str(item).strip() for item in evidence.get("failed_checks") or [] if str(item).strip()),
            "content_summary": str(evidence.get("content_summary") or "").strip(),
        }
    elif "approval_request_id" in evidence:
        payload = {
            "kind": "approval_request",
            "approval_type": str(evidence.get("approval_type") or "").strip(),
            "status": str(evidence.get("status") or "").strip(),
            "reviewer": str(evidence.get("reviewer") or "").strip(),
            "comment": str(evidence.get("comment") or "").strip(),
        }
    elif "approval_id" in evidence:
        payload = {
            "kind": "approval",
            "task_description": str(evidence.get("task_description") or "").strip(),
            "status": str(evidence.get("status") or "").strip(),
            "reviewer": str(evidence.get("reviewer") or "").strip(),
            "comment": str(evidence.get("comment") or "").strip(),
        }
    else:
        payload = {
            key: value
            for key, value in evidence.items()
            if key not in {
                "artifact_id",
                "requirement_id",
                "approval_request_id",
                "approval_id",
                "task_id",
                "incident_key",
                "source_artifact_id",
                "created_at",
                "decided_at",
                "occurred_at",
            }
        }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _record_signal_evidence(signal: dict[str, Any], evidence: dict[str, Any], occurred_at: Any) -> None:
    signal["occurrence_count"] = int(signal.get("occurrence_count") or 0) + 1
    seen = signal.setdefault("_seen_evidence_keys", set())
    evidence_key = _evidence_dedupe_key(evidence)
    evidence_items = signal.setdefault("evidence", [])
    if evidence_key not in seen and len(evidence_items) < _MAX_STORED_EVIDENCE_ITEMS:
        evidence_items.append(evidence)
        seen.add(evidence_key)

    current_latest = _parse_utc_datetime(signal.get("latest_evidence_at")) or datetime.fromtimestamp(0, timezone.utc)
    incoming_latest = _parse_utc_datetime(occurred_at) or datetime.fromtimestamp(0, timezone.utc)
    signal["latest_evidence_at"] = max(current_latest, incoming_latest)


def build_optimization_signal_score_breakdown(
    row: OptimizationSignalRow,
    *,
    project_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    project = dict((project_map or {}).get(str(row.routing_target_path or row.project_root_path or "")) or {})
    automation_ready = bool(project.get("automation_ready")) if project else row.routing_target_path is None
    readiness_score = int(project.get("readiness_score") or 0)
    bug_count = int(project.get("bug_report_count") or 0)
    blocked_publish_count = int(project.get("blocked_publish_count") or 0)
    manual_override_count = int(project.get("manual_override_count") or 0)
    automation_coverage = float(project.get("automation_coverage") or 0.0)

    occurrence_count = int(row.occurrence_count or 0)
    impact = min(
        _SIGNAL_IMPACT_BASE.get(str(row.signal_type), 16.0)
        + min(occurrence_count * 4.0, 18.0)
        + min(bug_count * 2.0 + blocked_publish_count * 3.0 + manual_override_count * 2.0, 12.0),
        48.0,
    )
    risk = min(
        _SEVERITY_RISK.get(str(row.severity), 10.0)
        + _SIGNAL_RISK_BASE.get(str(row.signal_type), 4.0)
        + (6.0 if readiness_score < 60 else 0.0),
        32.0,
    )
    confidence_component = round(min(float(row.confidence or 0.0) * 18.0, 18.0), 2)

    latest = row.latest_evidence_at or row.updated_at or row.created_at or datetime.now(timezone.utc)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    age_days = max((datetime.now(timezone.utc) - latest).total_seconds() / 86400, 0.0)
    urgency = round(
        max(4.0, 18.0 - min(age_days * 2.2, 12.0))
        + min(occurrence_count * 1.2, 6.0)
        + (4.0 if str(row.signal_type) == "delivery_blocker" else 0.0),
        2,
    )
    implementation_cost = round(
        _SIGNAL_COST.get(str(row.signal_type), 10.0)
        + (5.0 if not automation_ready else 0.0)
        + max(0.0, 0.65 - automation_coverage) * 6.0,
        2,
    )
    implementation_cost_adjustment = round(-implementation_cost, 2)
    total = round(impact + risk + confidence_component + urgency + implementation_cost_adjustment, 2)

    metadata = _signal_score_metadata(
        total,
        automation_ready=automation_ready,
        status=str(row.status),
        confidence=float(row.confidence or 0.0),
    )
    return {
        "total": total,
        "impact": round(impact, 2),
        "risk": round(risk, 2),
        "confidence_component": confidence_component,
        "urgency": urgency,
        "implementation_cost": implementation_cost,
        "implementation_cost_adjustment": implementation_cost_adjustment,
        "automation_ready": automation_ready,
        "readiness_score": readiness_score,
        "bug_pressure": bug_count,
        "delivery_pressure": blocked_publish_count,
        "manual_override_pressure": manual_override_count,
        **metadata,
    }


def _summarize_bug_signals(db: Session, project_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str | None, str, str], dict[str, Any]] = {}
    requirements = {int(row.id): row for row in db.query(RequirementRow).all()}
    bug_artifacts = db.query(ArtifactRow).filter(ArtifactRow.artifact_type == "bug_report").order_by(ArtifactRow.id.asc()).all()
    for artifact in bug_artifacts:
        requirement = requirements.get(int(artifact.requirement_id))
        if requirement is None or str(requirement.status) == "deleted":
            continue
        payload = _json_loads(artifact.machine_readable_payload, {})
        failed_checks = [str(item.get("check_key") or "") for item in payload.get("failed_checks") or [] if str(item.get("check_key") or "").strip()]
        fingerprint = ",".join(sorted(failed_checks)) or str(payload.get("step_type") or "bug_report")
        for project in _requirement_project_contexts(requirement, project_map):
            key = (project.get("project_key"), str(project.get("root_path") or ""), fingerprint)
            evidence = {
                "requirement_id": int(requirement.id),
                "artifact_id": int(artifact.id),
                "step_type": str(payload.get("step_type") or ""),
                "failed_checks": failed_checks,
                "content_summary": str(artifact.content_summary or ""),
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            }
            signal = groups.get(key)
            if signal is None:
                display_name = str(project.get("display_name") or project.get("root_path") or "Org Ops")
                signal = {
                    "dedupe_key": f"bug-report::{project.get('project_key') or 'org'}::{_normalize_key(fingerprint)}",
                    "signal_type": "bug_report",
                    "source_kind": "artifact",
                    "status": "open",
                    "title": _signal_title("Defect signal", display_name, fingerprint or "validation failures"),
                    "summary": f"Repeated bug reports detected in {display_name} for `{fingerprint}`.",
                    "severity": "medium",
                    "confidence": 0.86,
                    "project_key": project.get("project_key"),
                    "project_root_path": project.get("root_path"),
                    "routing_target_path": project.get("root_path"),
                    "evidence": [],
                    "occurrence_count": 0,
                    "latest_evidence_at": artifact.created_at,
                }
                groups[key] = signal
            _record_signal_evidence(signal, evidence, artifact.created_at)
            if int(signal.get("occurrence_count") or 0) >= 3:
                signal["severity"] = "high"
                signal["confidence"] = 0.93
    return list(groups.values())


def _summarize_delivery_blockers(db: Session, project_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str | None, str, str], dict[str, Any]] = {}
    requirements = {int(row.id): row for row in db.query(RequirementRow).all()}
    delivery_rows = db.query(ArtifactRow).filter(ArtifactRow.artifact_type == "delivery_state").order_by(ArtifactRow.id.asc()).all()
    latest_per_requirement: dict[int, ArtifactRow] = {}
    for row in delivery_rows:
        latest_per_requirement[int(row.requirement_id)] = row
    for artifact in latest_per_requirement.values():
        requirement = requirements.get(int(artifact.requirement_id))
        if requirement is None or str(requirement.status) == "deleted":
            continue
        payload = _json_loads(artifact.machine_readable_payload, {})
        blockers = [str(item).strip() for item in payload.get("publish_blockers") or [] if str(item).strip()]
        if not blockers:
            continue
        for blocker in blockers:
            for project in _requirement_project_contexts(requirement, project_map):
                key = (project.get("project_key"), str(project.get("root_path") or ""), blocker)
                signal = groups.get(key)
                evidence = {
                    "requirement_id": int(requirement.id),
                    "artifact_id": int(artifact.id),
                    "publish_status": str(payload.get("publish_status") or ""),
                    "blocker": blocker,
                    "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
                }
                if signal is None:
                    display_name = str(project.get("display_name") or project.get("root_path") or "Org Ops")
                    signal = {
                        "dedupe_key": f"delivery-blocker::{project.get('project_key') or 'org'}::{_normalize_key(blocker)}",
                        "signal_type": "delivery_blocker",
                        "source_kind": "artifact",
                        "status": "open",
                        "title": _signal_title("Delivery blocker", display_name, blocker),
                        "summary": f"Delivery gate keeps blocking {display_name}: {blocker}.",
                        "severity": "high" if "disabled" in blocker.lower() else "medium",
                        "confidence": 0.9,
                        "project_key": project.get("project_key"),
                        "project_root_path": project.get("root_path"),
                        "routing_target_path": project.get("root_path"),
                        "evidence": [],
                        "occurrence_count": 0,
                        "latest_evidence_at": artifact.created_at,
                    }
                    groups[key] = signal
                _record_signal_evidence(signal, evidence, artifact.created_at)
    return list(groups.values())


def _summarize_manual_overrides(db: Session, project_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    requirements = {int(row.id): row for row in db.query(RequirementRow).all()}
    grouped: dict[tuple[str | None, str], dict[str, Any]] = {}

    for approval in db.query(ApprovalRequestRow).order_by(ApprovalRequestRow.id.asc()).all():
        requirement = requirements.get(int(approval.requirement_id or 0))
        if requirement is None or str(requirement.status) == "deleted":
            continue
        for project in _requirement_project_contexts(requirement, project_map):
            key = (project.get("project_key"), str(project.get("root_path") or ""))
            signal = grouped.get(key)
            display_name = str(project.get("display_name") or project.get("root_path") or "Org Ops")
            if signal is None:
                signal = {
                    "dedupe_key": f"manual-override::{project.get('project_key') or 'org'}",
                    "signal_type": "manual_override",
                    "source_kind": "approval_request",
                    "status": "open",
                    "title": f"Manual override load: {display_name}",
                    "summary": f"Workflow approvals are repeatedly pulling human operators into {display_name}.",
                    "severity": "medium",
                    "confidence": 0.72,
                    "project_key": project.get("project_key"),
                    "project_root_path": project.get("root_path"),
                    "routing_target_path": project.get("root_path"),
                    "evidence": [],
                    "occurrence_count": 0,
                    "latest_evidence_at": approval.decided_at or approval.created_at,
                }
                grouped[key] = signal
            _record_signal_evidence(
                signal,
                {
                    "approval_request_id": int(approval.id),
                    "requirement_id": int(requirement.id),
                    "approval_type": str(approval.approval_type),
                    "status": str(approval.status),
                    "reviewer": approval.reviewer,
                    "comment": approval.comment,
                    "created_at": approval.created_at.isoformat() if approval.created_at else None,
                    "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
                },
                approval.decided_at or approval.created_at,
            )

    task_by_id = {int(row.id): row for row in db.query(TaskRow).all()}
    for approval in db.query(ApprovalRow).order_by(ApprovalRow.id.asc()).all():
        task = task_by_id.get(int(approval.task_id))
        if task is None:
            continue
        project = _task_project_context(task, project_map, requirements)
        key = (project.get("project_key"), str(project.get("root_path") or ""))
        signal = grouped.get(key)
        display_name = str(project.get("display_name") or project.get("root_path") or "TaskBoard")
        if signal is None:
            signal = {
                "dedupe_key": f"manual-override::{project.get('project_key') or 'taskboard'}",
                "signal_type": "manual_override",
                "source_kind": "approval",
                "status": "open",
                "title": f"Manual override load: {display_name}",
                "summary": f"Task approvals are repeatedly requiring manual operator decisions in {display_name}.",
                "severity": "medium",
                "confidence": 0.68,
                "project_key": project.get("project_key"),
                "project_root_path": project.get("root_path"),
                "routing_target_path": project.get("root_path"),
                "evidence": [],
                "occurrence_count": 0,
                "latest_evidence_at": approval.decided_at or approval.created_at,
            }
            grouped[key] = signal
        _record_signal_evidence(
            signal,
            {
                "approval_id": int(approval.id),
                "task_id": int(task.id),
                "task_description": str(task.description),
                "status": str(approval.status),
                "reviewer": approval.reviewer,
                "comment": approval.comment,
                "created_at": approval.created_at.isoformat() if approval.created_at else None,
                "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
            },
            approval.decided_at or approval.created_at,
        )
        if int(signal.get("occurrence_count") or 0) >= 3:
            signal["severity"] = "high"
            signal["confidence"] = 0.82

    return list(grouped.values())


def _incident_project_context(incident: dict[str, Any], project_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    root_path = str(incident.get("project_root_path") or "")
    if root_path and root_path in project_map:
        return dict(project_map[root_path])
    display_name = str(incident.get("project_display_name") or root_path.rsplit("/", 1)[-1] or "Org Ops")
    return {
        "project_key": None,
        "display_name": display_name,
        "root_path": root_path or None,
    }


def _summarize_workflow_incidents(db: Session, project_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str | None, str, str], dict[str, Any]] = {}
    for incident in list_open_incidents(db):
        project = _incident_project_context(incident, project_map)
        incident_code = str(incident.get("incident_code") or "workflow_incident")
        recovery_status = str(incident.get("recovery_status") or "observe")
        key = (project.get("project_key"), str(project.get("root_path") or ""), incident_code)
        signal = groups.get(key)
        evidence = {
            "incident_key": str(incident.get("incident_key") or ""),
            "requirement_id": int(incident.get("requirement_id") or 0),
            "source_artifact_id": int(incident.get("source_artifact_id") or 0),
            "incident_family": str(incident.get("incident_family") or ""),
            "incident_code": incident_code,
            "recovery_status": recovery_status,
            "summary": str(incident.get("summary") or ""),
            "recommended_action": str(incident.get("recommended_action") or ""),
            "occurred_at": incident.get("occurred_at"),
        }
        if signal is None:
            display_name = str(project.get("display_name") or project.get("root_path") or "Org Ops")
            signal = {
                "dedupe_key": f"workflow-incident::{project.get('project_key') or 'org'}::{_normalize_key(incident_code)}",
                "signal_type": "workflow_incident",
                "source_kind": "incident",
                "status": "open",
                "title": _signal_title("Workflow incident", display_name, incident_code),
                "summary": f"{display_name} has an active `{incident_code}` incident that needs recovery handling.",
                "severity": str(incident.get("severity") or "medium"),
                "confidence": 0.9,
                "project_key": project.get("project_key"),
                "project_root_path": project.get("root_path"),
                "routing_target_path": project.get("root_path"),
                "evidence": [],
                "occurrence_count": 0,
                "latest_evidence_at": None,
                "incident_family": str(incident.get("incident_family") or ""),
                "incident_code": incident_code,
                "recovery_status": recovery_status,
                "recovery_narrative": str(incident.get("summary") or ""),
            }
            groups[key] = signal
        _record_signal_evidence(signal, evidence, incident.get("occurred_at"))
        signal["severity"] = max(
            [str(signal.get("severity") or "low"), str(incident.get("severity") or "low")],
            key=_severity_rank,
        )
        if recovery_status in {"operator_review_required", "runtime_recovery_required", "replan_required"}:
            signal["confidence"] = 0.94
    return list(groups.values())


def _upsert_signal(db: Session, payload: dict[str, Any]) -> OptimizationSignalRow:
    row = db.query(OptimizationSignalRow).filter(OptimizationSignalRow.dedupe_key == payload["dedupe_key"]).first()
    latest_evidence_at = payload.get("latest_evidence_at")
    if row is None:
        row = OptimizationSignalRow(
            dedupe_key=str(payload["dedupe_key"]),
            signal_type=str(payload["signal_type"]),
            source_kind=str(payload["source_kind"]),
            status=str(payload.get("status") or "open"),
            title=str(payload["title"]),
            summary=str(payload.get("summary") or ""),
            severity=str(payload.get("severity") or "medium"),
            confidence=float(payload.get("confidence") or 0.5),
            project_key=payload.get("project_key"),
            project_root_path=payload.get("project_root_path"),
            routing_target_path=payload.get("routing_target_path"),
            evidence_json=_json_dumps(payload.get("evidence") or []),
            occurrence_count=int(payload.get("occurrence_count") or len(payload.get("evidence") or [])),
            latest_evidence_at=latest_evidence_at,
        )
        db.add(row)
        db.flush()
        return row

    row.signal_type = str(payload["signal_type"])
    row.source_kind = str(payload["source_kind"])
    if row.status not in {"converted", "dismissed"}:
        row.status = str(payload.get("status") or "open")
    row.title = str(payload["title"])
    row.summary = str(payload.get("summary") or "")
    if _severity_rank(payload.get("severity")) >= _severity_rank(row.severity):
        row.severity = str(payload.get("severity") or row.severity)
    row.confidence = max(float(payload.get("confidence") or 0.0), float(row.confidence or 0.0))
    row.project_key = payload.get("project_key")
    row.project_root_path = payload.get("project_root_path")
    row.routing_target_path = payload.get("routing_target_path")
    row.evidence_json = _json_dumps(payload.get("evidence") or [])
    row.occurrence_count = int(payload.get("occurrence_count") or len(payload.get("evidence") or []))
    row.latest_evidence_at = latest_evidence_at
    return row


def _signal_id_from_source_ref(source_ref: str | None) -> int | None:
    raw = str(source_ref or "").strip()
    if not raw.startswith("optimization-signal:"):
        return None
    signal_id = raw.split(":", 1)[-1].strip()
    return int(signal_id) if signal_id.isdigit() else None


def get_optimization_signal_requirement_context(db: Session, source_ref: str | None) -> dict[str, float]:
    signal_id = _signal_id_from_source_ref(source_ref)
    if signal_id is None:
        return {
            "impact": 0.0,
            "risk": 0.0,
            "confidence_component": 0.0,
            "urgency": 0.0,
            "implementation_cost_adjustment": 0.0,
        }
    row = db.query(OptimizationSignalRow).filter(OptimizationSignalRow.id == signal_id).first()
    if row is None:
        return {
            "impact": 0.0,
            "risk": 0.0,
            "confidence_component": 0.0,
            "urgency": 0.0,
            "implementation_cost_adjustment": 0.0,
        }
    breakdown = build_optimization_signal_score_breakdown(row, project_map=_project_map(db))
    return {
        "impact": round(float(breakdown.get("impact") or 0.0) * 0.35, 2),
        "risk": round(float(breakdown.get("risk") or 0.0) * 0.3, 2),
        "confidence_component": round(float(breakdown.get("confidence_component") or 0.0) * 0.4, 2),
        "urgency": round(float(breakdown.get("urgency") or 0.0) * 0.35, 2),
        "implementation_cost_adjustment": round(float(breakdown.get("implementation_cost_adjustment") or 0.0) * 0.35, 2),
    }


def optimization_signal_to_dict(
    row: OptimizationSignalRow,
    *,
    project_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    score_breakdown = build_optimization_signal_score_breakdown(row, project_map=project_map)
    return {
        "id": int(row.id),
        "dedupe_key": str(row.dedupe_key),
        "signal_type": str(row.signal_type),
        "source_kind": str(row.source_kind),
        "status": str(row.status),
        "title": str(row.title),
        "summary": str(row.summary),
        "severity": str(row.severity),
        "confidence": float(row.confidence or 0.0),
        "project_key": row.project_key,
        "project_root_path": row.project_root_path,
        "routing_target_path": row.routing_target_path,
        "evidence": _json_loads(row.evidence_json, []),
        "occurrence_count": int(row.occurrence_count or 0),
        "latest_evidence_at": row.latest_evidence_at,
        "converted_requirement_id": int(row.converted_requirement_id) if row.converted_requirement_id is not None else None,
        "incident_family": next(
            (str(item.get("incident_family") or "") for item in _json_loads(row.evidence_json, []) if isinstance(item, dict) and str(item.get("incident_family") or "").strip()),
            None,
        ),
        "incident_code": next(
            (str(item.get("incident_code") or "") for item in _json_loads(row.evidence_json, []) if isinstance(item, dict) and str(item.get("incident_code") or "").strip()),
            None,
        ),
        "recovery_status": next(
            (str(item.get("recovery_status") or "") for item in _json_loads(row.evidence_json, []) if isinstance(item, dict) and str(item.get("recovery_status") or "").strip()),
            None,
        ),
        "recovery_narrative": next(
            (str(item.get("summary") or item.get("recommended_action") or "") for item in _json_loads(row.evidence_json, []) if isinstance(item, dict) and (str(item.get("summary") or "").strip() or str(item.get("recommended_action") or "").strip())),
            None,
        ),
        "score_breakdown": score_breakdown,
        "recommended_priority": str(score_breakdown.get("recommended_priority") or "normal"),
        "auto_intake_eligible": bool(score_breakdown.get("auto_intake_eligible")),
        "intake_recommendation": str(score_breakdown.get("intake_recommendation") or "observe"),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def refresh_optimization_signals(db: Session) -> list[OptimizationSignalRow]:
    project_map = _project_map(db)
    seen_keys: set[str] = set()
    sources = {
        "bug_reports": 0,
        "delivery_blockers": 0,
        "manual_overrides": 0,
        "workflow_incidents": 0,
    }
    bug_signals = _summarize_bug_signals(db, project_map)
    delivery_signals = _summarize_delivery_blockers(db, project_map)
    manual_override_signals = _summarize_manual_overrides(db, project_map)
    workflow_incident_signals = _summarize_workflow_incidents(db, project_map)
    sources["bug_reports"] = len(bug_signals)
    sources["delivery_blockers"] = len(delivery_signals)
    sources["manual_overrides"] = len(manual_override_signals)
    sources["workflow_incidents"] = len(workflow_incident_signals)
    for payload in bug_signals + delivery_signals + manual_override_signals + workflow_incident_signals:
        seen_keys.add(str(payload["dedupe_key"]))
        _upsert_signal(db, payload)

    resolved = 0
    for row in db.query(OptimizationSignalRow).all():
        if row.dedupe_key in seen_keys or row.status in {"converted", "dismissed"}:
            continue
        row.status = "resolved"
        resolved += 1
    db.commit()
    logger.info(
        "event=optimization_signals_refresh bug_reports=%s delivery_blockers=%s manual_overrides=%s workflow_incidents=%s active=%s resolved=%s",
        sources["bug_reports"],
        sources["delivery_blockers"],
        sources["manual_overrides"],
        sources["workflow_incidents"],
        len(seen_keys),
        resolved,
    )
    return list_optimization_signals(db)


def list_optimization_signals(db: Session, *, status: str | None = None) -> list[OptimizationSignalRow]:
    query = db.query(OptimizationSignalRow)
    if status:
        query = query.filter(OptimizationSignalRow.status == status)
    rows = query.all()
    project_map = _project_map(db)
    rows.sort(
        key=lambda row: (
            -float(build_optimization_signal_score_breakdown(row, project_map=project_map).get("total") or 0.0),
            -(row.latest_evidence_at.timestamp() if row.latest_evidence_at else 0.0),
            -(int(row.id) or 0),
        )
    )
    return rows


def dismiss_optimization_signal(db: Session, signal_id: int) -> OptimizationSignalRow:
    row = db.query(OptimizationSignalRow).filter(OptimizationSignalRow.id == signal_id).first()
    if row is None:
        raise ValueError("Optimization signal not found")
    row.status = "dismissed"
    db.commit()
    db.refresh(row)
    return row


def create_requirement_from_signal(
    db: Session,
    *,
    signal_id: int,
    title: str | None = None,
    auto_start: bool = False,
) -> tuple[OptimizationSignalRow, Any]:
    row = db.query(OptimizationSignalRow).filter(OptimizationSignalRow.id == signal_id).first()
    if row is None:
        raise ValueError("Optimization signal not found")
    if row.converted_requirement_id is not None:
        raise ValueError("Optimization signal already converted to a requirement")

    score_breakdown = build_optimization_signal_score_breakdown(row, project_map=_project_map(db))
    priority = str(score_breakdown.get("recommended_priority") or "normal")
    evidence = _json_loads(row.evidence_json, [])
    template_key = template_key_for_signal(str(row.signal_type))
    body = build_template_instance(
        template_key=template_key,
        title=(title or row.title).strip(),
        context_summary=(
            f"{row.summary}\n\n"
            f"Signal type: {row.signal_type}\n"
            f"Severity: {row.severity}\n"
            f"Confidence: {row.confidence}\n"
            f"Occurrences: {row.occurrence_count}"
        ),
        target_project_path=row.routing_target_path,
        priority=priority,
        source="optimization_signal",
        source_ref=f"optimization-signal:{row.id}",
        evidence=evidence,
        score_breakdown=score_breakdown,
        template_payload_extra={
            "signal_id": int(row.id),
            "signal_type": str(row.signal_type),
            "project_key": row.project_key,
            "project_display_name": str(row.project_key or row.routing_target_path or "Org Ops"),
        },
        auto_start=auto_start,
    )
    body.intake_metadata = normalize_requirement_intake_metadata(
        body.source,
        body.source_ref,
        {
            "intake_reason": f"signal:{row.signal_type}",
            "confidence": float(row.confidence or 0.85),
            "intake_mode": "automatic" if auto_start else "operator",
            "signal_id": int(row.id),
            "registry_hint": "optimization_signal",
            "trigger": "signal_conversion",
        },
    )
    detail = create_requirement(db, body)
    row.status = "converted"
    row.converted_requirement_id = int(detail.requirement.id)
    db.commit()
    db.refresh(row)
    logger.info(
        "event=optimization_signal_converted signal_id=%s signal_type=%s requirement_id=%s project_key=%s priority=%s",
        row.id,
        row.signal_type,
        row.converted_requirement_id,
        row.project_key or "org-ops",
        priority,
    )
    return row, detail


def auto_intake_optimization_signals(
    db: Session,
    *,
    min_score: float = 60.0,
    max_created: int = 1,
    auto_start: bool = False,
    compare_with_requirement_score: float | None = None,
) -> dict[str, Any]:
    refresh_optimization_signals(db)
    rows = list_optimization_signals(db, status="open")
    project_map = _project_map(db)
    created: list[dict[str, Any]] = []
    skipped: list[str] = []
    limit = max(1, min(int(max_created or 1), 5))

    for row in rows:
        breakdown = build_optimization_signal_score_breakdown(row, project_map=project_map)
        total = float(breakdown.get("total") or 0.0)
        if compare_with_requirement_score is not None and total < compare_with_requirement_score + 8.0:
            skipped.append(f"signal #{row.id} below current requirement baseline")
            continue
        if total < min_score:
            skipped.append(f"signal #{row.id} score {round(total, 2)} below min_score {round(min_score, 2)}")
            continue
        if not bool(breakdown.get("auto_intake_eligible")):
            skipped.append(f"signal #{row.id} not auto-intake eligible")
            continue
        try:
            updated_signal, detail = create_requirement_from_signal(
                db,
                signal_id=int(row.id),
                auto_start=auto_start,
            )
        except ValueError as exc:
            skipped.append(f"signal #{row.id}: {exc}")
            continue
        created.append(
            {
                "signal_id": int(updated_signal.id),
                "requirement_id": int(detail.requirement.id),
                "title": str(detail.requirement.title),
                "score": round(total, 2),
            }
        )
        if len(created) >= limit:
            break

    logger.info(
        "event=optimization_signal_auto_intake created=%s skipped=%s min_score=%s max_created=%s compare_with_requirement_score=%s",
        len(created),
        len(skipped),
        round(min_score, 2),
        limit,
        compare_with_requirement_score,
    )
    return {
        "created": created,
        "skipped": skipped,
    }
