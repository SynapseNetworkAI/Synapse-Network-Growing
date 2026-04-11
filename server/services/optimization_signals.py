"""Optimization signal ingestion and signal-to-requirement helpers."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from server.database import (
    ApprovalRequestRow,
    ApprovalRow,
    ArtifactRow,
    OptimizationSignalRow,
    RequirementRow,
    TaskRow,
    WorkflowStepRow,
)
from server.schemas import RequirementCreate
from server.services.project_intelligence import build_project_catalog
from server.services.workflow_orchestrator import create_requirement


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


def _severity_rank(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(str(value), 0)


def _project_map(db: Session) -> dict[str, dict[str, Any]]:
    catalog = build_project_catalog(db)
    result: dict[str, dict[str, Any]] = {}
    for root, data in catalog.items():
        result[root] = data
    return result


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
                    "latest_evidence_at": artifact.created_at,
                }
                groups[key] = signal
            signal["evidence"].append(evidence)
            signal["latest_evidence_at"] = max(
                signal.get("latest_evidence_at") or artifact.created_at,
                artifact.created_at,
            )
            if len(signal["evidence"]) >= 3:
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
                        "latest_evidence_at": artifact.created_at,
                    }
                    groups[key] = signal
                signal["evidence"].append(evidence)
                signal["latest_evidence_at"] = max(
                    signal.get("latest_evidence_at") or artifact.created_at,
                    artifact.created_at,
                )
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
                    "latest_evidence_at": approval.decided_at or approval.created_at,
                }
                grouped[key] = signal
            signal["evidence"].append(
                {
                    "approval_request_id": int(approval.id),
                    "requirement_id": int(requirement.id),
                    "approval_type": str(approval.approval_type),
                    "status": str(approval.status),
                    "reviewer": approval.reviewer,
                    "comment": approval.comment,
                    "created_at": approval.created_at.isoformat() if approval.created_at else None,
                    "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
                }
            )
            signal["latest_evidence_at"] = max(
                signal.get("latest_evidence_at") or approval.created_at,
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
                "latest_evidence_at": approval.decided_at or approval.created_at,
            }
            grouped[key] = signal
        signal["evidence"].append(
            {
                "approval_id": int(approval.id),
                "task_id": int(task.id),
                "task_description": str(task.description),
                "status": str(approval.status),
                "reviewer": approval.reviewer,
                "comment": approval.comment,
                "created_at": approval.created_at.isoformat() if approval.created_at else None,
                "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
            }
        )
        signal["latest_evidence_at"] = max(
            signal.get("latest_evidence_at") or approval.created_at,
            approval.decided_at or approval.created_at,
        )
        if len(signal["evidence"]) >= 3:
            signal["severity"] = "high"
            signal["confidence"] = 0.82

    return list(grouped.values())


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
            occurrence_count=len(payload.get("evidence") or []),
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
    row.occurrence_count = len(payload.get("evidence") or [])
    row.latest_evidence_at = latest_evidence_at
    return row


def optimization_signal_to_dict(row: OptimizationSignalRow) -> dict[str, Any]:
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
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def refresh_optimization_signals(db: Session) -> list[OptimizationSignalRow]:
    project_map = _project_map(db)
    seen_keys: set[str] = set()
    for payload in (
        _summarize_bug_signals(db, project_map)
        + _summarize_delivery_blockers(db, project_map)
        + _summarize_manual_overrides(db, project_map)
    ):
        seen_keys.add(str(payload["dedupe_key"]))
        _upsert_signal(db, payload)

    for row in db.query(OptimizationSignalRow).all():
        if row.dedupe_key in seen_keys or row.status in {"converted", "dismissed"}:
            continue
        row.status = "resolved"
    db.commit()
    return list_optimization_signals(db)


def list_optimization_signals(db: Session, *, status: str | None = None) -> list[OptimizationSignalRow]:
    query = db.query(OptimizationSignalRow)
    if status:
        query = query.filter(OptimizationSignalRow.status == status)
    return query.order_by(
        OptimizationSignalRow.latest_evidence_at.desc().nullslast(),
        OptimizationSignalRow.updated_at.desc(),
        OptimizationSignalRow.id.desc(),
    ).all()


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

    priority = "high" if row.severity == "high" else ("normal" if row.severity == "medium" else "low")
    evidence = _json_loads(row.evidence_json, [])
    body = RequirementCreate(
        title=(title or row.title).strip(),
        description_markdown=(
            f"## Optimization Signal\n\n{row.summary}\n\n"
            f"- Signal type: `{row.signal_type}`\n"
            f"- Severity: `{row.severity}`\n"
            f"- Confidence: `{row.confidence}`\n"
            f"- Occurrences: `{row.occurrence_count}`\n\n"
            f"## Evidence\n\n```json\n{json.dumps(evidence[:8], ensure_ascii=False, indent=2)}\n```"
        ),
        priority=priority,
        source="optimization_signal",
        source_ref=f"optimization-signal:{row.id}",
        target_project_path=row.routing_target_path,
        auto_start=auto_start,
    )
    detail = create_requirement(db, body)
    row.status = "converted"
    row.converted_requirement_id = int(detail.requirement.id)
    db.commit()
    db.refresh(row)
    return row, detail
