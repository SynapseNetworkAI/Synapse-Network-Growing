from __future__ import annotations

"""Planning lifecycle service for Operating Manifest and goal-driven work."""

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database import (
    HumanGateRequestRow,
    OperatingManifestRow,
    PlannerSweepRow,
    ProjectRow,
    ReleaseRecordRow,
    RequirementCandidateRow,
    RequirementRow,
    WorkflowRunRow,
    WorkflowStateEventRow,
    utcnow,
)
from server.schemas import RequirementCreate
from server.services.projects.project_center import ensure_projects_materialized
from server.services.workflows.agent_first import create_requirement


GOAL_ACTIVE = "active"
GOAL_ACHIEVED = "achieved"
GOAL_DROPPED = "dropped"
ACTIVE_MANIFEST_SLOT = "global"


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _json_dumps(payload: Any) -> str:
    def _default(value: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc).isoformat()
            return value.astimezone(timezone.utc).isoformat()
        return str(value)

    return json.dumps(payload, ensure_ascii=False, default=_default)


def _now_iso() -> str:
    return utcnow().isoformat()


def _manifest_payload(row: OperatingManifestRow) -> dict[str, Any]:
    payload = _json_loads(row.payload_json, {})
    return payload if isinstance(payload, dict) else {}


def _goal_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    goals = payload.get("goals")
    if not isinstance(goals, list):
        return []
    return [goal for goal in goals if isinstance(goal, dict)]


def _goal_by_key(payload: dict[str, Any], goal_key: str) -> dict[str, Any] | None:
    for goal in _goal_list(payload):
        if str(goal.get("goal_key") or "") == goal_key:
            return goal
    return None


def _goal_domain(goal: dict[str, Any]) -> str:
    return str(goal.get("domain") or "operations").strip() or "operations"


def _goal_status(goal: dict[str, Any]) -> str:
    return str(goal.get("status") or GOAL_ACTIVE).strip() or GOAL_ACTIVE


def _default_manifest_payload() -> dict[str, Any]:
    return {
        "global_budget": {
            "daily_usd_limit": 25,
            "max_concurrent_workers": 2,
        },
        "focus_weights": {
            "reliability": 0.6,
            "growth": 0.25,
            "support": 0.15,
        },
        "global_constraints": [
            "No production deploy without human approval.",
            "Drop Goal never triggers automatic rollback or revert.",
            "Funds, settlement, auth, contract and deploy actions require human gate.",
        ],
        "goals": [
            {
                "goal_key": "gateway_reliability",
                "domain": "reliability",
                "status": GOAL_ACTIVE,
                "intent": "Keep the gateway, workflow runner and agent self-repair loop healthy.",
                "success_metric": "critical runtime incidents remain at 0 and failed workflows are triaged.",
                "weight": 0.6,
            },
            {
                "goal_key": "operator_growth",
                "domain": "growth",
                "status": GOAL_ACTIVE,
                "intent": "Continuously discover practical growth and DevRel work for Synapse Network.",
                "success_metric": "approved candidate throughput increases without operator overload.",
                "weight": 0.4,
            },
        ],
    }


def validate_manifest_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("manifest payload must be an object")
    goals = _goal_list(payload)
    keys: set[str] = set()
    for goal in goals:
        goal_key = str(goal.get("goal_key") or "").strip()
        if not goal_key:
            raise ValueError("each goal must include goal_key")
        if goal_key in keys:
            raise ValueError(f"duplicate goal_key: {goal_key}")
        keys.add(goal_key)
        status = _goal_status(goal)
        if status not in {GOAL_ACTIVE, GOAL_ACHIEVED, GOAL_DROPPED}:
            raise ValueError(f"unsupported goal status for {goal_key}: {status}")
    weights = payload.get("focus_weights")
    if isinstance(weights, dict) and weights:
        total = 0.0
        for value in weights.values():
            try:
                total += float(value)
            except Exception as exc:
                raise ValueError("focus_weights values must be numeric") from exc
        if total > 1.001 and total > 100.001:
            raise ValueError("focus_weights must sum to 1.0 or 100")


def manifest_to_dict(row: OperatingManifestRow) -> dict[str, Any]:
    payload = _manifest_payload(row)
    goals = _goal_list(payload)
    return {
        "id": int(row.id),
        "manifest_key": str(row.manifest_key or ""),
        "version_name": str(row.version_name or ""),
        "cycle_label": str(row.cycle_label or ""),
        "status": str(row.status or "draft"),
        "revision": int(row.revision or 1),
        "payload": payload,
        "goal_count": len(goals),
        "active_goal_count": sum(1 for goal in goals if _goal_status(goal) == GOAL_ACTIVE),
        "dropped_goal_count": sum(1 for goal in goals if _goal_status(goal) == GOAL_DROPPED),
        "achieved_goal_count": sum(1 for goal in goals if _goal_status(goal) == GOAL_ACHIEVED),
        "review_summary": _json_loads(row.review_summary_json, {}),
        "change_log": _json_loads(row.change_log_json, []),
        "created_by": str(row.created_by or "operator"),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "archived_at": row.archived_at,
    }


def candidate_to_dict(row: RequirementCandidateRow) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "manifest_id": int(row.manifest_id),
        "goal_key": str(row.goal_key or ""),
        "candidate_fingerprint": str(row.candidate_fingerprint or ""),
        "title": str(row.title or ""),
        "description_markdown": str(row.description_markdown or ""),
        "project_id": int(row.project_id) if row.project_id is not None else None,
        "project_key": str(row.project_key or "") or None,
        "workflow_key": str(row.workflow_key or ""),
        "priority": str(row.priority or "normal"),
        "risk_level": str(row.risk_level or "normal"),
        "confidence": float(row.confidence or 0.0),
        "rationale": str(row.rationale or ""),
        "expected_evidence": _json_loads(row.expected_evidence_json, []),
        "status": str(row.status or "pending"),
        "suppression_reason": str(row.suppression_reason or "") or None,
        "reject_reason": str(row.reject_reason or "") or None,
        "reject_comment": str(row.reject_comment or "") or None,
        "approved_by": str(row.approved_by or "") or None,
        "materialized_requirement_id": int(row.materialized_requirement_id) if row.materialized_requirement_id else None,
        "metadata": _json_loads(row.metadata_json, {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "approved_at": row.approved_at,
        "rejected_at": row.rejected_at,
    }


def sweep_to_dict(row: PlannerSweepRow) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "manifest_id": int(row.manifest_id),
        "status": str(row.status or "running"),
        "triggered_by": str(row.triggered_by or "operator"),
        "dry_run": bool(row.dry_run),
        "input_snapshot": _json_loads(row.input_snapshot_json, {}),
        "parsed_output": _json_loads(row.parsed_output_json, {}),
        "created_candidate_ids": _json_loads(row.created_candidate_ids_json, []),
        "suppressed_items": _json_loads(row.suppressed_items_json, []),
        "error_excerpt": str(row.error_excerpt or "") or None,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "duration_ms": int(row.duration_ms or 0),
    }


def ensure_active_manifest(db: Session) -> OperatingManifestRow:
    row = (
        db.query(OperatingManifestRow)
        .filter(OperatingManifestRow.status == "active", OperatingManifestRow.active_slot == ACTIVE_MANIFEST_SLOT)
        .order_by(OperatingManifestRow.id.desc())
        .first()
    )
    if row is not None:
        return row
    row = OperatingManifestRow(
        manifest_key=f"manifest-{utcnow().strftime('%Y%m%d%H%M%S')}",
        version_name="Default Operating Manifest",
        cycle_label=utcnow().strftime("%Y-W%W"),
        status="active",
        active_slot=ACTIVE_MANIFEST_SLOT,
        revision=1,
        payload_json=_json_dumps(_default_manifest_payload()),
        change_log_json=_json_dumps([{"at": _now_iso(), "event": "default_manifest_created"}]),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save_active_manifest(
    db: Session,
    *,
    payload: dict[str, Any],
    version_name: str | None = None,
    cycle_label: str | None = None,
    operator: str = "operator",
) -> OperatingManifestRow:
    validate_manifest_payload(payload)
    row = ensure_active_manifest(db)
    changes = _json_loads(row.change_log_json, [])
    if not isinstance(changes, list):
        changes = []
    changes.append({"at": _now_iso(), "event": "minor_revision", "operator": operator})
    row.payload_json = _json_dumps(payload)
    if version_name is not None:
        row.version_name = version_name
    if cycle_label is not None:
        row.cycle_label = cycle_label
    row.revision = int(row.revision or 1) + 1
    row.change_log_json = _json_dumps(changes[-100:])
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def list_manifest_history(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    query = db.query(OperatingManifestRow)
    if status:
        query = query.filter(OperatingManifestRow.status == status)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                OperatingManifestRow.manifest_key.ilike(pattern),
                OperatingManifestRow.version_name.ilike(pattern),
                OperatingManifestRow.cycle_label.ilike(pattern),
                OperatingManifestRow.status.ilike(pattern),
                OperatingManifestRow.payload_json.ilike(pattern),
            )
        )
    total = query.count()
    rows = (
        query.order_by(OperatingManifestRow.updated_at.desc(), OperatingManifestRow.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [manifest_to_dict(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)) if total else 1,
    }


def _candidate_status_counts(db: Session, manifest_id: int, goal_key: str) -> dict[str, int]:
    rows = db.query(RequirementCandidateRow).filter(
        RequirementCandidateRow.manifest_id == manifest_id,
        RequirementCandidateRow.goal_key == goal_key,
    )
    result: dict[str, int] = {}
    for row in rows:
        status = str(row.status or "pending")
        result[status] = result.get(status, 0) + 1
    return result


def _requirement_status_counts(db: Session, manifest_id: int, goal_key: str) -> dict[str, int]:
    rows = db.query(RequirementRow).filter(
        RequirementRow.operating_manifest_id == manifest_id,
        RequirementRow.goal_key == goal_key,
    )
    result: dict[str, int] = {}
    for row in rows:
        status = str(row.status or "draft")
        result[status] = result.get(status, 0) + 1
    return result


def goal_rollup(db: Session, manifest_id: int, goal_key: str) -> dict[str, Any]:
    manifest = db.get(OperatingManifestRow, manifest_id)
    if manifest is None:
        raise ValueError("manifest not found")
    payload = _manifest_payload(manifest)
    goal = _goal_by_key(payload, goal_key)
    if goal is None:
        raise ValueError("goal not found")
    workflows = db.query(WorkflowRunRow).filter(
        WorkflowRunRow.operating_manifest_id == manifest_id,
        WorkflowRunRow.goal_key == goal_key,
    )
    releases = db.query(ReleaseRecordRow).filter(
        ReleaseRecordRow.operating_manifest_id == manifest_id,
        ReleaseRecordRow.goal_key == goal_key,
    )
    return {
        "manifest_id": manifest_id,
        "goal_key": goal_key,
        "goal": goal,
        "candidate_status_counts": _candidate_status_counts(db, manifest_id, goal_key),
        "requirement_status_counts": _requirement_status_counts(db, manifest_id, goal_key),
        "workflow_status_counts": _count_by_status(workflows, "status"),
        "release_status_counts": _count_by_status(releases, "status"),
    }


def _count_by_status(query: Any, attr: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in query.all():
        status = str(getattr(row, attr, None) or "unknown")
        result[status] = result.get(status, 0) + 1
    return result


def archive_and_start_new_cycle(
    db: Session,
    *,
    version_name: str,
    cycle_label: str,
    operator: str = "operator",
    payload_patch: dict[str, Any] | None = None,
) -> OperatingManifestRow:
    active = ensure_active_manifest(db)
    active_payload = _manifest_payload(active)
    active.review_summary_json = _json_dumps(_manifest_review_summary(db, active))
    active.status = "archived"
    active.active_slot = None
    active.archived_at = utcnow()
    db.flush()

    next_payload = dict(active_payload)
    retained_goals = [
        goal
        for goal in _goal_list(active_payload)
        if _goal_status(goal) == GOAL_ACTIVE
    ]
    next_payload["goals"] = retained_goals
    if payload_patch:
        next_payload.update(payload_patch)
    validate_manifest_payload(next_payload)
    row = OperatingManifestRow(
        manifest_key=f"manifest-{utcnow().strftime('%Y%m%d%H%M%S')}",
        version_name=version_name,
        cycle_label=cycle_label,
        status="active",
        active_slot=ACTIVE_MANIFEST_SLOT,
        revision=1,
        payload_json=_json_dumps(next_payload),
        change_log_json=_json_dumps(
            [
                {
                    "at": _now_iso(),
                    "event": "archive_and_start_new_cycle",
                    "operator": operator,
                    "archived_manifest_id": int(active.id),
                }
            ]
        ),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _manifest_review_summary(db: Session, row: OperatingManifestRow) -> dict[str, Any]:
    payload = _manifest_payload(row)
    goal_summaries = [goal_rollup(db, int(row.id), str(goal.get("goal_key"))) for goal in _goal_list(payload)]
    return {
        "manifest_id": int(row.id),
        "cycle_label": str(row.cycle_label or ""),
        "version_name": str(row.version_name or ""),
        "generated_at": _now_iso(),
        "goals": goal_summaries,
    }


def _default_workflow_for_goal(goal: dict[str, Any]) -> str:
    domain = _goal_domain(goal).lower()
    if "reliability" in domain or "ops" in domain:
        return "gateway_reliability_repair"
    return "agent_self_repair"


def _default_project(db: Session, goal: dict[str, Any]) -> ProjectRow | None:
    project_key = str(goal.get("project_key") or "").strip()
    query = db.query(ProjectRow)
    if project_key:
        row = query.filter(ProjectRow.project_key == project_key).first()
        if row is not None:
            return row
    return query.order_by(ProjectRow.id.asc()).first()


def _candidate_fingerprint(manifest_id: int, goal_key: str, intent: str, workflow_key: str) -> str:
    raw = f"{manifest_id}:{goal_key}:{workflow_key}:{intent}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _build_goal_snapshot(db: Session, manifest: OperatingManifestRow) -> list[dict[str, Any]]:
    payload = _manifest_payload(manifest)
    snapshot: list[dict[str, Any]] = []
    for goal in _goal_list(payload):
        goal_key = str(goal.get("goal_key") or "")
        snapshot.append(
            {
                "goal_key": goal_key,
                "domain": _goal_domain(goal),
                "status": _goal_status(goal),
                "intent": str(goal.get("intent") or ""),
                "success_metric": str(goal.get("success_metric") or ""),
                "candidate_status_counts": _candidate_status_counts(db, int(manifest.id), goal_key),
                "requirement_status_counts": _requirement_status_counts(db, int(manifest.id), goal_key),
            }
        )
    return snapshot


def run_planner_sweep(
    db: Session,
    *,
    dry_run: bool = False,
    triggered_by: str = "operator",
    max_candidates_per_goal: int = 1,
) -> PlannerSweepRow:
    ensure_projects_materialized(db)
    manifest = ensure_active_manifest(db)
    started = utcnow()
    row = PlannerSweepRow(
        manifest_id=int(manifest.id),
        status="running",
        triggered_by=triggered_by,
        dry_run=bool(dry_run),
        started_at=started,
    )
    db.add(row)
    db.flush()
    try:
        payload = _manifest_payload(manifest)
        snapshot = {
            "manifest": manifest_to_dict(manifest),
            "goals": _build_goal_snapshot(db, manifest),
        }
        created_ids: list[int] = []
        suppressed: list[dict[str, Any]] = []
        proposed: list[dict[str, Any]] = []
        for goal in _goal_list(payload):
            goal_key = str(goal.get("goal_key") or "").strip()
            if _goal_status(goal) != GOAL_ACTIVE:
                suppressed.append({"goal_key": goal_key, "reason": f"goal_{_goal_status(goal)}"})
                continue
            pending_count = (
                db.query(RequirementCandidateRow)
                .filter(
                    RequirementCandidateRow.manifest_id == manifest.id,
                    RequirementCandidateRow.goal_key == goal_key,
                    RequirementCandidateRow.status.in_(["pending", "approved"]),
                )
                .count()
            )
            active_requirements = (
                db.query(RequirementRow)
                .filter(
                    RequirementRow.operating_manifest_id == manifest.id,
                    RequirementRow.goal_key == goal_key,
                    RequirementRow.status.notin_(["done", "cancelled", "deleted"]),
                )
                .count()
            )
            if pending_count >= max_candidates_per_goal:
                suppressed.append({"goal_key": goal_key, "reason": "candidate_capacity_reached", "count": pending_count})
                continue
            if active_requirements > 0:
                suppressed.append({"goal_key": goal_key, "reason": "active_requirement_exists", "count": active_requirements})
                continue
            workflow_key = str(goal.get("workflow_key") or "").strip() or _default_workflow_for_goal(goal)
            intent = str(goal.get("intent") or goal_key)
            fingerprint = _candidate_fingerprint(int(manifest.id), goal_key, intent, workflow_key)
            existing = (
                db.query(RequirementCandidateRow)
                .filter(
                    RequirementCandidateRow.manifest_id == manifest.id,
                    RequirementCandidateRow.goal_key == goal_key,
                    RequirementCandidateRow.candidate_fingerprint == fingerprint,
                    RequirementCandidateRow.status.in_(["pending", "approved", "materialized"]),
                )
                .first()
            )
            if existing is not None:
                suppressed.append({"goal_key": goal_key, "reason": "duplicate_candidate", "candidate_id": int(existing.id)})
                continue
            project = _default_project(db, goal)
            candidate_payload = {
                "manifest_id": int(manifest.id),
                "goal_key": goal_key,
                "candidate_fingerprint": fingerprint,
                "title": f"Advance goal: {intent[:72]}",
                "description_markdown": (
                    f"## Goal\n{intent}\n\n"
                    f"## Success Metric\n{str(goal.get('success_metric') or 'Define concrete evidence before execution.')}\n\n"
                    "## Planner Rationale\nThis candidate was generated from the active Operating Manifest. "
                    "Operator approval is required before it becomes a requirement."
                ),
                "project_id": int(project.id) if project is not None else None,
                "project_key": str(project.project_key or "") if project is not None else None,
                "workflow_key": workflow_key,
                "priority": str(goal.get("priority") or "normal"),
                "risk_level": str(goal.get("risk_level") or "normal"),
                "confidence": 0.72,
                "rationale": "Active goal has no active requirement and has candidate capacity.",
                "expected_evidence_json": _json_dumps(["accepted candidate", "created requirement", "workflow evidence"]),
                "status": "pending",
                "metadata_json": _json_dumps({"generated_by": "deterministic_planner_sweep_v1"}),
            }
            proposed.append(candidate_payload)
            if not dry_run:
                candidate = RequirementCandidateRow(**candidate_payload)
                db.add(candidate)
                db.flush()
                created_ids.append(int(candidate.id))
        completed = utcnow()
        row.status = "succeeded"
        row.input_snapshot_json = _json_dumps(snapshot)
        row.parsed_output_json = _json_dumps({"proposed_candidates": proposed})
        row.created_candidate_ids_json = _json_dumps(created_ids)
        row.suppressed_items_json = _json_dumps(suppressed)
        row.completed_at = completed
        row.duration_ms = int((completed - started).total_seconds() * 1000)
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:
        completed = utcnow()
        row.status = "failed"
        row.error_excerpt = str(exc)[:2000]
        row.completed_at = completed
        row.duration_ms = int((completed - started).total_seconds() * 1000)
        db.commit()
        raise


def list_candidates(
    db: Session,
    *,
    manifest_id: int | None = None,
    status: str | None = None,
    goal_key: str | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict[str, Any]:
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 30)))
    query = db.query(RequirementCandidateRow)
    if manifest_id is not None:
        query = query.filter(RequirementCandidateRow.manifest_id == manifest_id)
    if status:
        query = query.filter(RequirementCandidateRow.status == status)
    if goal_key:
        query = query.filter(RequirementCandidateRow.goal_key == goal_key)
    total = query.count()
    rows = (
        query.order_by(RequirementCandidateRow.updated_at.desc(), RequirementCandidateRow.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [candidate_to_dict(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)) if total else 1,
    }


def approve_candidate(db: Session, candidate_id: int, *, operator: str = "operator") -> RequirementCandidateRow:
    row = db.get(RequirementCandidateRow, candidate_id)
    if row is None:
        raise ValueError("candidate not found")
    if str(row.status or "") not in {"pending", "rejected"}:
        raise ValueError(f"candidate cannot be approved from status {row.status}")
    manifest = db.get(OperatingManifestRow, int(row.manifest_id))
    if manifest is None:
        raise ValueError("manifest not found")
    goal = _goal_by_key(_manifest_payload(manifest), str(row.goal_key or ""))
    if goal is None or _goal_status(goal) == GOAL_DROPPED:
        raise ValueError("cannot approve candidate for dropped or missing goal")
    row.status = "approved"
    row.approved_by = operator
    row.approved_at = utcnow()
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def reject_candidate(
    db: Session,
    candidate_id: int,
    *,
    reason: str,
    operator: str = "operator",
    comment: str | None = None,
) -> RequirementCandidateRow:
    if not reason.strip():
        raise ValueError("reject reason is required")
    row = db.get(RequirementCandidateRow, candidate_id)
    if row is None:
        raise ValueError("candidate not found")
    row.status = "rejected"
    row.reject_reason = reason.strip()
    row.reject_comment = comment
    row.rejected_by = operator
    row.rejected_at = utcnow()
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def materialize_candidate(db: Session, candidate_id: int, *, operator: str = "operator") -> dict[str, Any]:
    row = db.get(RequirementCandidateRow, candidate_id)
    if row is None:
        raise ValueError("candidate not found")
    if str(row.status or "") != "approved":
        raise ValueError("candidate must be approved before materialization")
    manifest = db.get(OperatingManifestRow, int(row.manifest_id))
    if manifest is None:
        raise ValueError("manifest not found")
    goal = _goal_by_key(_manifest_payload(manifest), str(row.goal_key or ""))
    if goal is None or _goal_status(goal) == GOAL_DROPPED:
        raise ValueError("cannot materialize candidate for dropped or missing goal")
    project = db.get(ProjectRow, int(row.project_id)) if row.project_id else None
    if project is None and row.project_key:
        project = db.query(ProjectRow).filter(ProjectRow.project_key == row.project_key).first()
    if project is None:
        project = db.query(ProjectRow).order_by(ProjectRow.id.asc()).first()
    if project is None:
        raise ValueError("candidate cannot be materialized without a project")
    body = RequirementCreate(
        title=str(row.title or "").strip(),
        description_markdown=str(row.description_markdown or "").strip(),
        priority=str(row.priority or "normal"),
        source="planner_candidate",
        source_ref=f"planner-candidate:{int(row.id)}",
        project_id=int(project.id),
        intake_metadata={
            "operating_manifest_id": int(row.manifest_id),
            "goal_key": str(row.goal_key or ""),
            "requirement_candidate_id": int(row.id),
            "workflow_key": str(row.workflow_key or ""),
            "materialized_by": operator,
        },
    )
    result = create_requirement(db, body)
    requirement = db.get(RequirementRow, int(result.requirement.id))
    if requirement is None:
        raise ValueError("materialized requirement was not found")
    requirement.operating_manifest_id = int(row.manifest_id)
    requirement.goal_key = str(row.goal_key or "")
    requirement.requirement_candidate_id = int(row.id)
    metadata = _json_loads(requirement.intake_metadata_json, {})
    metadata.update(
        {
            "operating_manifest_id": int(row.manifest_id),
            "goal_key": str(row.goal_key or ""),
            "requirement_candidate_id": int(row.id),
            "workflow_key": str(row.workflow_key or ""),
            "materialized_by": operator,
        }
    )
    requirement.intake_metadata_json = _json_dumps(metadata)
    row.status = "materialized"
    row.materialized_requirement_id = int(requirement.id)
    row.updated_at = utcnow()
    db.commit()
    return {"candidate": candidate_to_dict(row), "requirement_id": int(requirement.id)}


def drop_goal(
    db: Session,
    *,
    manifest_id: int,
    goal_key: str,
    reason: str,
    operator: str = "operator",
    halt_mode: str = "safe_halt",
) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("drop reason is required")
    manifest = db.get(OperatingManifestRow, manifest_id)
    if manifest is None:
        raise ValueError("manifest not found")
    payload = _manifest_payload(manifest)
    goal = _goal_by_key(payload, goal_key)
    if goal is None:
        raise ValueError("goal not found")
    decision = {
        "reason": reason.strip(),
        "operator": operator,
        "halt_mode": halt_mode or "safe_halt",
        "decided_at": _now_iso(),
        "rollback_policy": "drop_goal_never_rolls_back_releases",
    }
    goal["status"] = GOAL_DROPPED
    goal["closed_at"] = _now_iso()
    goal["review_note"] = reason.strip()
    goal["drop_decision_json"] = decision
    manifest.payload_json = _json_dumps(payload)
    manifest.revision = int(manifest.revision or 1) + 1
    manifest.updated_at = utcnow()

    summary = {
        "suppressed_candidates": 0,
        "cancelled_requirements": 0,
        "paused_workflows": 0,
        "blocked_releases": 0,
        "delivered_artifacts_retained": 0,
        "rollback_triggered": False,
    }
    candidates = db.query(RequirementCandidateRow).filter(
        RequirementCandidateRow.manifest_id == manifest_id,
        RequirementCandidateRow.goal_key == goal_key,
        RequirementCandidateRow.status.in_(["pending", "approved"]),
    )
    for candidate in candidates.all():
        candidate.status = "suppressed"
        candidate.suppression_reason = "goal_dropped"
        metadata = _json_loads(candidate.metadata_json, {})
        metadata["goal_drop_decision"] = decision
        candidate.metadata_json = _json_dumps(metadata)
        candidate.updated_at = utcnow()
        summary["suppressed_candidates"] += 1

    requirements = db.query(RequirementRow).filter(
        RequirementRow.operating_manifest_id == manifest_id,
        RequirementRow.goal_key == goal_key,
    ).all()
    for requirement in requirements:
        active_run_id = int(requirement.active_workflow_run_id or 0)
        if active_run_id:
            continue
        status = str(requirement.status or "")
        if status in {"draft", "ready", "blocked", "planning", "pending_approval"} or str(requirement.approval_status or "") == "pending_approval":
            requirement.status = "cancelled"
            requirement.phase = "cancelled"
            requirement.workflow_state = "cancelled"
            requirement.attention_reason = "goal_dropped"
            requirement.failure_reason = "cancelled_by_goal_drop"
            metadata = _json_loads(requirement.intake_metadata_json, {})
            metadata["goal_drop_decision"] = decision
            requirement.intake_metadata_json = _json_dumps(metadata)
            requirement.updated_at = utcnow()
            summary["cancelled_requirements"] += 1

    workflows = db.query(WorkflowRunRow).filter(
        WorkflowRunRow.operating_manifest_id == manifest_id,
        WorkflowRunRow.goal_key == goal_key,
        WorkflowRunRow.status.in_(["pending", "running", "awaiting_operator", "paused", "failed"]),
    ).all()
    for run in workflows:
        blackboard = _json_loads(run.blackboard_json, {})
        blackboard["goal_drop_decision"] = decision
        blackboard["halt_reason"] = "goal_dropped_safe_halt"
        from_state = str(run.current_state or "")
        run.blackboard_json = _json_dumps(blackboard)
        run.status = "awaiting_operator"
        run.resolution = "goal_dropped_safe_halt"
        run.current_state = "awaiting_operator"
        run.updated_at = utcnow()
        db.add(
            WorkflowStateEventRow(
                workflow_run_id=int(run.id),
                event_type="goal_dropped_halt_requested",
                from_state=from_state,
                to_state="awaiting_operator",
                condition="goal_dropped",
                payload_json=_json_dumps(decision),
            )
        )
        existing_gate = db.query(HumanGateRequestRow).filter(
            HumanGateRequestRow.workflow_run_id == int(run.id),
            HumanGateRequestRow.gate_type == "goal_dropped_halt",
            HumanGateRequestRow.status == "pending",
        ).first()
        if existing_gate is None:
            db.add(
                HumanGateRequestRow(
                    workflow_run_id=int(run.id),
                    state_key="awaiting_operator",
                    gate_type="goal_dropped_halt",
                    risk_level="medium",
                    status="pending",
                    reason="Goal was dropped; operator must decide whether to stop, continue, or decommission.",
                    payload_json=_json_dumps(decision),
                )
            )
        requirement = db.get(RequirementRow, int(run.requirement_id))
        if requirement is not None:
            requirement.workflow_state = "awaiting_operator"
            requirement.attention_reason = "goal_dropped_safe_halt"
            requirement.updated_at = utcnow()
        summary["paused_workflows"] += 1

    releases = db.query(ReleaseRecordRow).filter(
        ReleaseRecordRow.operating_manifest_id == manifest_id,
        ReleaseRecordRow.goal_key == goal_key,
    ).all()
    for release in releases:
        status = str(release.status or "")
        delivery_state = str(release.delivery_state or "")
        if release.delivered_at is not None or status in {"delivered", "released", "done", "succeeded"} or delivery_state in {"delivered", "released", "completed"}:
            summary["delivered_artifacts_retained"] += 1
            continue
        release.status = "blocked"
        release.delivery_state = "blocked"
        release.blocker_kind = "goal_dropped_requires_operator_review"
        release.delivery_blocker_type = "goal_dropped_requires_operator_review"
        note = str(release.notes or "")
        release.notes = (note + "\n" if note else "") + "Blocked because linked goal was dropped. No rollback was triggered."
        metadata = _json_loads(release.metadata_json, {})
        metadata["goal_drop_decision"] = decision
        release.metadata_json = _json_dumps(metadata)
        release.updated_at = utcnow()
        summary["blocked_releases"] += 1

    db.commit()
    db.refresh(manifest)
    return {
        "manifest": manifest_to_dict(manifest),
        "goal_key": goal_key,
        "halt_summary": summary,
        "decision": decision,
    }
