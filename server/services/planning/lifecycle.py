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
    PlanningGoalRow,
    PlannerSweepRow,
    ProjectRow,
    ReleaseRecordRow,
    RequirementCandidateRow,
    RequirementRow,
    WorkflowArtifactRow,
    WorkflowRunRow,
    WorkflowStateEventRow,
    utcnow,
)
from server.schemas import RequirementCreate
from server.services.projects.project_center import ensure_projects_materialized
from server.services.planning.planner_agent import (
    PlannerAgentError,
    failed_candidate_from_planner_error,
    synthesize_candidate_for_goal,
)
from server.services.planning.risk_router import route_candidate
from server.services.requirements.acceptance import (
    AcceptanceValidationError,
    normalize_acceptance_contract,
    validate_acceptance_contract_for_execution,
)
from server.services.requirements.service import create_requirement, start_requirement_workflow


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


def _dogfood_acceptance_contract(goal: dict[str, Any]) -> dict[str, Any]:
    intent = str(goal.get("intent_markdown") or goal.get("intent") or goal.get("title") or goal.get("goal_key") or "Goal dogfood flow").strip()
    return normalize_acceptance_contract(
        {
            "acceptance_kind": "system_dogfood",
            "execution_acceptance_steps": [
                {
                    "step_key": "candidate_materialized",
                    "title": "Planner candidate becomes a formal requirement",
                    "expected_result": "A RequirementCandidate is materialized into a Requirement with stable goal lineage.",
                    "required_db_lineage": [
                        "requirement_candidates.materialized_requirement_id",
                        "requirements.requirement_candidate_id",
                        "requirements.goal_key",
                    ],
                },
                {
                    "step_key": "workflow_evidence_recorded",
                    "title": "Declarative workflow records execution evidence",
                    "expected_result": "The workflow run reaches a terminal state with state events, atom invocations, and artifacts.",
                    "required_db_lineage": [
                        "workflow_runs.requirement_id",
                        "workflow_state_events.workflow_run_id",
                        "atom_invocations.workflow_run_id",
                        "workflow_artifacts.workflow_run_id",
                    ],
                    "required_evidence_types": ["workflow_command_result", "workflow_agent_raw_output"],
                },
            ],
            "markdown": f"## System Dogfood Acceptance\n- Verify the Goal flow for: {intent}",
        }
    )


def _acceptance_contract_for_goal_row(goal: PlanningGoalRow) -> dict[str, Any] | None:
    steps = _json_loads(goal.execution_acceptance_steps_json, [])
    payload: dict[str, Any] = {
        "acceptance_kind": str(goal.acceptance_kind or "business"),
        "execution_acceptance_steps": steps if isinstance(steps, list) else [],
    }
    if str(goal.acceptance_kind or "").strip() == "system_dogfood":
        if not payload["execution_acceptance_steps"]:
            return _dogfood_acceptance_contract(goal_to_dict(goal, include_intent=True))
        return normalize_acceptance_contract(payload)
    if payload["execution_acceptance_steps"]:
        return normalize_acceptance_contract(payload)
    return None


def _candidate_acceptance_contract(row: RequirementCandidateRow) -> dict[str, Any]:
    metadata = _json_loads(row.metadata_json, {})
    contract = metadata.get("acceptance_contract") if isinstance(metadata, dict) else None
    return normalize_acceptance_contract(contract if isinstance(contract, dict) else {})


def _mark_candidate_acceptance_validation_failed(db: Session, row: RequirementCandidateRow, reason: str) -> None:
    metadata = _json_loads(row.metadata_json, {})
    metadata = metadata if isinstance(metadata, dict) else {}
    metadata["acceptance_validation_error"] = reason
    row.metadata_json = _json_dumps(metadata)
    row.status = "validation_failed"
    row.suppression_reason = "acceptance_validation_failed"
    row.updated_at = utcnow()
    db.flush()


def _now_iso() -> str:
    return utcnow().isoformat()


def _manifest_payload(row: OperatingManifestRow) -> dict[str, Any]:
    payload = _json_loads(row.payload_json, {})
    if not isinstance(payload, dict):
        return {}
    payload = dict(payload)
    payload.pop("goals", None)
    return payload


def _intent_excerpt(value: str, *, limit: int = 200) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def goal_to_dict(row: PlanningGoalRow, *, include_intent: bool = False) -> dict[str, Any]:
    intent = str(row.intent_markdown or "")
    payload = {
        "id": int(row.id),
        "manifest_id": int(row.manifest_id),
        "goal_key": str(row.goal_key or ""),
        "title": str(row.title or ""),
        "intent_excerpt": _intent_excerpt(intent),
        "success_metric": str(row.success_metric or ""),
        "domain": str(row.domain or "ops"),
        "status": str(row.status or GOAL_ACTIVE),
        "workflow_key": str(row.workflow_key or ""),
        "project_key": str(row.project_key or "") or None,
        "priority": str(row.priority or "normal"),
        "risk_level": str(row.risk_level or "normal"),
        "weight": float(row.weight or 0.0),
        "acceptance_kind": str(row.acceptance_kind or "business"),
        "execution_acceptance_steps": _json_loads(row.execution_acceptance_steps_json, []),
        "metadata": _json_loads(row.metadata_json, {}),
        "closed_at": row.closed_at,
        "review_note": str(row.review_note or "") or None,
        "drop_decision": _json_loads(row.drop_decision_json, {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if include_intent:
        payload["intent_markdown"] = intent
    return payload


def _goal_by_key(db: Session, manifest_id: int, goal_key: str) -> PlanningGoalRow | None:
    return (
        db.query(PlanningGoalRow)
        .filter(
            PlanningGoalRow.manifest_id == manifest_id,
            PlanningGoalRow.goal_key == goal_key,
        )
        .first()
    )


def _goal_rows(db: Session, manifest_id: int, *, status: str | None = None) -> list[PlanningGoalRow]:
    query = db.query(PlanningGoalRow).filter(PlanningGoalRow.manifest_id == manifest_id)
    if status:
        query = query.filter(PlanningGoalRow.status == status)
    return query.order_by(PlanningGoalRow.id.asc()).all()


def _goal_domain(goal: PlanningGoalRow | dict[str, Any]) -> str:
    if isinstance(goal, PlanningGoalRow):
        return str(goal.domain or "operations").strip() or "operations"
    return str(goal.get("domain") or "operations").strip() or "operations"


def _goal_status(goal: PlanningGoalRow | dict[str, Any]) -> str:
    if isinstance(goal, PlanningGoalRow):
        return str(goal.status or GOAL_ACTIVE).strip() or GOAL_ACTIVE
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
    }


def validate_manifest_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("manifest payload must be an object")
    if "goals" in payload:
        raise ValueError("goals are first-class records; use /api/planning/goals")
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


def _default_goal_specs() -> list[dict[str, Any]]:
    return [
        {
            "goal_key": "gateway_reliability",
            "title": "Gateway reliability",
            "domain": "reliability",
            "intent_markdown": "Keep the gateway, workflow runner and agent self-repair loop healthy.",
            "success_metric": "critical runtime incidents remain at 0 and failed workflows are triaged.",
            "workflow_key": "gateway_reliability_repair",
            "project_key": "synapse-network-growing",
            "priority": "normal",
            "risk_level": "normal",
            "weight": 0.6,
        },
        {
            "goal_key": "operator_growth",
            "title": "Operator growth",
            "domain": "growth",
            "intent_markdown": "Continuously discover practical growth and DevRel work for Synapse Network.",
            "success_metric": "approved candidate throughput increases without operator overload.",
            "workflow_key": "agent_self_repair",
            "project_key": "synapse-network-growing",
            "priority": "normal",
            "risk_level": "normal",
            "weight": 0.4,
        },
    ]


def _create_goal_from_spec(db: Session, manifest_id: int, spec: dict[str, Any]) -> PlanningGoalRow:
    goal_key = str(spec.get("goal_key") or "").strip()
    if not goal_key:
        raise ValueError("goal_key is required")
    status = str(spec.get("status") or GOAL_ACTIVE).strip() or GOAL_ACTIVE
    if status not in {GOAL_ACTIVE, GOAL_ACHIEVED, GOAL_DROPPED}:
        raise ValueError(f"unsupported goal status for {goal_key}: {status}")
    row = PlanningGoalRow(
        manifest_id=manifest_id,
        goal_key=goal_key,
        title=str(spec.get("title") or goal_key).strip() or goal_key,
        intent_markdown=str(spec.get("intent_markdown") or spec.get("intent") or "").strip(),
        success_metric=str(spec.get("success_metric") or "").strip(),
        domain=str(spec.get("domain") or "ops").strip() or "ops",
        status=status,
        workflow_key=str(spec.get("workflow_key") or "gateway_reliability_repair").strip() or "gateway_reliability_repair",
        project_key=str(spec.get("project_key") or "").strip() or None,
        priority=str(spec.get("priority") or "normal").strip() or "normal",
        risk_level=str(spec.get("risk_level") or "normal").strip() or "normal",
        weight=float(spec.get("weight") or 0.0),
        acceptance_kind=str(spec.get("acceptance_kind") or "business").strip() or "business",
        execution_acceptance_steps_json=_json_dumps(spec.get("execution_acceptance_steps") or []),
        metadata_json=_json_dumps(spec.get("metadata") or {}),
    )
    db.add(row)
    db.flush()
    return row


def _ensure_default_goals(db: Session, manifest: OperatingManifestRow) -> None:
    count = db.query(PlanningGoalRow).filter(PlanningGoalRow.manifest_id == int(manifest.id)).count()
    if count > 0:
        return
    for spec in _default_goal_specs():
        _create_goal_from_spec(db, int(manifest.id), spec)
    db.commit()


def _goal_counts(db: Session, manifest_id: int) -> dict[str, int]:
    rows = _goal_rows(db, manifest_id)
    return {
        "goal_count": len(rows),
        "active_goal_count": sum(1 for goal in rows if _goal_status(goal) == GOAL_ACTIVE),
        "dropped_goal_count": sum(1 for goal in rows if _goal_status(goal) == GOAL_DROPPED),
        "achieved_goal_count": sum(1 for goal in rows if _goal_status(goal) == GOAL_ACHIEVED),
    }


def manifest_to_dict(row: OperatingManifestRow, db: Session | None = None) -> dict[str, Any]:
    payload = _manifest_payload(row)
    counts = _goal_counts(db, int(row.id)) if db is not None and row.id is not None else {
        "goal_count": 0,
        "active_goal_count": 0,
        "dropped_goal_count": 0,
        "achieved_goal_count": 0,
    }
    return {
        "id": int(row.id),
        "manifest_key": str(row.manifest_key or ""),
        "version_name": str(row.version_name or ""),
        "cycle_label": str(row.cycle_label or ""),
        "status": str(row.status or "draft"),
        "revision": int(row.revision or 1),
        "payload": payload,
        **counts,
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
    parsed_output = _json_loads(row.parsed_output_json, {})
    return {
        "id": int(row.id),
        "manifest_id": int(row.manifest_id),
        "status": str(row.status or "running"),
        "triggered_by": str(row.triggered_by or "operator"),
        "dry_run": bool(row.dry_run),
        "input_snapshot": _json_loads(row.input_snapshot_json, {}),
        "parsed_output": parsed_output,
        "created_candidate_ids": _json_loads(row.created_candidate_ids_json, []),
        "suppressed_items": _json_loads(row.suppressed_items_json, []),
        "routing_results": list(parsed_output.get("routing_results") or []),
        "auto_materialized_requirement_ids": list(parsed_output.get("auto_materialized_requirement_ids") or []),
        "auto_started_workflow_run_ids": list(parsed_output.get("auto_started_workflow_run_ids") or []),
        "routing_suppressed_items": list(parsed_output.get("routing_suppressed_items") or []),
        "validation_failed_candidate_ids": list(parsed_output.get("validation_failed_candidate_ids") or []),
        "planner_validation_errors": list(parsed_output.get("planner_validation_errors") or []),
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
        _ensure_default_goals(db, row)
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
    db.flush()
    for spec in _default_goal_specs():
        _create_goal_from_spec(db, int(row.id), spec)
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
        goal_manifest_ids = [
            int(row[0])
            for row in db.query(PlanningGoalRow.manifest_id)
            .filter(
                or_(
                    PlanningGoalRow.goal_key.ilike(pattern),
                    PlanningGoalRow.title.ilike(pattern),
                    PlanningGoalRow.intent_markdown.ilike(pattern),
                    PlanningGoalRow.status.ilike(pattern),
                )
            )
            .distinct()
            .all()
        ]
        query = query.filter(
            or_(
                OperatingManifestRow.manifest_key.ilike(pattern),
                OperatingManifestRow.version_name.ilike(pattern),
                OperatingManifestRow.cycle_label.ilike(pattern),
                OperatingManifestRow.status.ilike(pattern),
                OperatingManifestRow.id.in_(goal_manifest_ids) if goal_manifest_ids else False,
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
        "items": [manifest_to_dict(row, db) for row in rows],
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
    goal = _goal_by_key(db, manifest_id, goal_key)
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
        "goal": goal_to_dict(goal, include_intent=False),
        "candidate_status_counts": _candidate_status_counts(db, manifest_id, goal_key),
        "requirement_status_counts": _requirement_status_counts(db, manifest_id, goal_key),
        "workflow_status_counts": _count_by_status(workflows, "status"),
        "release_status_counts": _count_by_status(releases, "status"),
    }


def _global_steering_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    focus_weights = payload.get("focus_weights")
    global_budget = payload.get("global_budget")
    global_constraints = payload.get("global_constraints")
    return {
        "focus_weights": focus_weights if isinstance(focus_weights, dict) else {},
        "global_budget": global_budget if isinstance(global_budget, dict) else {},
        "global_constraints": global_constraints if isinstance(global_constraints, list) else [],
    }


def _candidate_totals(db: Session, manifest_id: int) -> dict[str, int]:
    rows = db.query(RequirementCandidateRow).filter(RequirementCandidateRow.manifest_id == manifest_id)
    result: dict[str, int] = {}
    for row in rows:
        status = str(row.status or "pending")
        result[status] = result.get(status, 0) + 1
    for status in ["pending", "approved", "materialized", "rejected", "suppressed"]:
        result.setdefault(status, 0)
    return result


def mission_control_snapshot(db: Session) -> dict[str, Any]:
    manifest = ensure_active_manifest(db)
    manifest_id = int(manifest.id)
    payload = _manifest_payload(manifest)
    all_candidates = (
        db.query(RequirementCandidateRow)
        .filter(RequirementCandidateRow.manifest_id == manifest_id)
        .order_by(RequirementCandidateRow.updated_at.desc(), RequirementCandidateRow.id.desc())
        .all()
    )
    candidates_by_goal: dict[str, list[dict[str, Any]]] = {}
    for candidate in all_candidates:
        candidates_by_goal.setdefault(str(candidate.goal_key or ""), []).append(candidate_to_dict(candidate))

    lanes: list[dict[str, Any]] = []
    for goal in _goal_rows(db, manifest_id):
        goal_key = str(goal.goal_key or "").strip()
        if not goal_key:
            continue
        lanes.append(
            {
                "goal_key": goal_key,
                "goal": goal_to_dict(goal, include_intent=False),
                "rollup": goal_rollup(db, manifest_id, goal_key),
                "candidates": candidates_by_goal.get(goal_key, []),
            }
        )

    latest_sweep = (
        db.query(PlannerSweepRow)
        .filter(PlannerSweepRow.manifest_id == manifest_id)
        .order_by(PlannerSweepRow.started_at.desc(), PlannerSweepRow.id.desc())
        .first()
    )
    return {
        "manifest": manifest_to_dict(manifest, db),
        "global_steering": _global_steering_from_payload(payload),
        "goal_lanes": lanes,
        "candidate_totals": _candidate_totals(db, manifest_id),
        "history_preview": list_manifest_history(db, page=1, page_size=5),
        "last_sweep": sweep_to_dict(latest_sweep) if latest_sweep is not None else None,
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
    active_goals = _goal_rows(db, int(active.id), status=GOAL_ACTIVE)
    active.review_summary_json = _json_dumps(_manifest_review_summary(db, active))
    active.status = "archived"
    active.active_slot = None
    active.archived_at = utcnow()
    db.flush()

    next_payload = dict(active_payload)
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
    db.flush()
    for goal in active_goals:
        _create_goal_from_spec(
            db,
            int(row.id),
            {
                **goal_to_dict(goal, include_intent=True),
                "execution_acceptance_steps": _json_loads(goal.execution_acceptance_steps_json, []),
                "metadata": _json_loads(goal.metadata_json, {}),
            },
        )
    db.commit()
    db.refresh(row)
    return row


def _manifest_review_summary(db: Session, row: OperatingManifestRow) -> dict[str, Any]:
    goal_summaries = [goal_rollup(db, int(row.id), str(goal.goal_key)) for goal in _goal_rows(db, int(row.id))]
    return {
        "manifest_id": int(row.id),
        "cycle_label": str(row.cycle_label or ""),
        "version_name": str(row.version_name or ""),
        "generated_at": _now_iso(),
        "goals": goal_summaries,
    }


def _default_workflow_for_goal(goal: PlanningGoalRow | dict[str, Any]) -> str:
    domain = _goal_domain(goal).lower()
    if "reliability" in domain or "ops" in domain:
        return "gateway_reliability_repair"
    return "agent_self_repair"


def _default_project(db: Session, goal: PlanningGoalRow | dict[str, Any]) -> ProjectRow | None:
    if isinstance(goal, PlanningGoalRow):
        project_key = str(goal.project_key or "").strip()
    else:
        project_key = str(goal.get("project_key") or "").strip()
    query = db.query(ProjectRow)
    if project_key:
        row = query.filter(ProjectRow.project_key == project_key).first()
        if row is not None:
            return row
    return query.order_by(ProjectRow.id.asc()).first()


def _candidate_fingerprint(manifest_id: int, goal_key: str, intent: str, workflow_key: str, sequence: int) -> str:
    raw = f"{manifest_id}:{goal_key}:{workflow_key}:{intent}:{sequence}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


TERMINAL_REQUIREMENT_STATUSES = {"completed", "succeeded", "done", "cancelled", "deleted"}


def _build_goal_snapshot(db: Session, manifest: OperatingManifestRow) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for goal in _goal_rows(db, int(manifest.id)):
        goal_key = str(goal.goal_key or "")
        snapshot.append(
            {
                "id": int(goal.id),
                "goal_key": goal_key,
                "domain": _goal_domain(goal),
                "status": _goal_status(goal),
                "title": str(goal.title or ""),
                "intent_excerpt": _intent_excerpt(str(goal.intent_markdown or "")),
                "success_metric": str(goal.success_metric or ""),
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
        snapshot = {
            "manifest": manifest_to_dict(manifest, db),
            "goals": _build_goal_snapshot(db, manifest),
        }
        created_ids: list[int] = []
        suppressed: list[dict[str, Any]] = []
        proposed: list[dict[str, Any]] = []
        routing_results: list[dict[str, Any]] = []
        auto_materialized_requirement_ids: list[int] = []
        auto_started_workflow_run_ids: list[int] = []
        routing_suppressed_items: list[dict[str, Any]] = []
        validation_failed_candidate_ids: list[int] = []
        planner_validation_errors: list[dict[str, Any]] = []
        for goal in _goal_rows(db, int(manifest.id)):
            goal_key = str(goal.goal_key or "").strip()
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
                    RequirementRow.status.notin_(sorted(TERMINAL_REQUIREMENT_STATUSES)),
                )
                .count()
            )
            if pending_count >= max_candidates_per_goal:
                suppressed.append({"goal_key": goal_key, "reason": "candidate_capacity_reached", "count": pending_count})
                continue
            if active_requirements > 0:
                suppressed.append({"goal_key": goal_key, "reason": "active_requirement_exists", "count": active_requirements})
                continue
            workflow_key = str(goal.workflow_key or "").strip() or _default_workflow_for_goal(goal)
            intent = str(goal.intent_markdown or goal.title or goal_key)
            title = str(goal.title or goal_key).strip() or goal_key
            sequence = (
                db.query(RequirementCandidateRow)
                .filter(
                    RequirementCandidateRow.manifest_id == manifest.id,
                    RequirementCandidateRow.goal_key == goal_key,
                )
                .count()
                + 1
            )
            fingerprint = _candidate_fingerprint(int(manifest.id), goal_key, intent, workflow_key, sequence)
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
            project_id = int(project.id) if project is not None else None
            project_key = str(project.project_key or "") if project is not None else None
            acceptance_contract = _acceptance_contract_for_goal_row(goal)
            try:
                planner_candidate = synthesize_candidate_for_goal(
                    manifest_payload=_manifest_payload(manifest),
                    goal=goal,
                    project_key=str(project_key or ""),
                    default_workflow_key=workflow_key,
                    acceptance_contract=acceptance_contract,
                )
                workflow_key = planner_candidate.workflow_key
                acceptance_steps = list((planner_candidate.acceptance_contract or {}).get("execution_acceptance_steps") or [])
                candidate_metadata = dict(planner_candidate.metadata or {})
                candidate_metadata["acceptance_contract"] = planner_candidate.acceptance_contract
                candidate_payload = {
                    "manifest_id": int(manifest.id),
                    "goal_key": goal_key,
                    "candidate_fingerprint": fingerprint,
                    "title": planner_candidate.title,
                    "description_markdown": planner_candidate.description_markdown,
                    "project_id": project_id,
                    "project_key": project_key,
                    "workflow_key": workflow_key,
                    "priority": planner_candidate.priority,
                    "risk_level": planner_candidate.risk_level,
                    "confidence": planner_candidate.confidence,
                    "rationale": planner_candidate.rationale,
                    "expected_evidence_json": _json_dumps([str(step.get("title") or step.get("step_key") or "") for step in acceptance_steps if isinstance(step, dict)]),
                    "status": "pending",
                    "metadata_json": _json_dumps(candidate_metadata),
                }
            except PlannerAgentError as exc:
                planner_validation_errors.append({"goal_key": goal_key, "error": str(exc)})
                candidate_payload = failed_candidate_from_planner_error(
                    error=exc,
                    goal=goal,
                    workflow_key=workflow_key,
                    project_id=project_id,
                    project_key=project_key,
                    manifest_id=int(manifest.id),
                    fingerprint=fingerprint,
                )
            proposed.append(candidate_payload)
            if not dry_run:
                candidate = RequirementCandidateRow(**candidate_payload)
                db.add(candidate)
                db.flush()
                created_ids.append(int(candidate.id))
                if "planner_agent_error" in _json_loads(candidate.metadata_json, {}):
                    _mark_candidate_acceptance_validation_failed(db, candidate, str(_json_loads(candidate.metadata_json, {}).get("planner_agent_error") or "planner agent failed"))
                    validation_failed_candidate_ids.append(int(candidate.id))
                    routing_item = {
                        "candidate_id": int(candidate.id),
                        "goal_key": goal_key,
                        "workflow_key": workflow_key,
                        "decision": "blocked_requires_operator",
                        "reason": "planner_agent_validation_failed",
                        "policy_version": "candidate_risk_router_v1",
                        "error": str(_json_loads(candidate.metadata_json, {}).get("planner_agent_error") or "planner agent failed"),
                    }
                    routing_results.append(routing_item)
                    routing_suppressed_items.append(routing_item)
                    continue
                try:
                    validate_acceptance_contract_for_execution(
                        _candidate_acceptance_contract(candidate),
                        source="planner_candidate",
                        goal_key=goal_key,
                    )
                except AcceptanceValidationError as exc:
                    _mark_candidate_acceptance_validation_failed(db, candidate, str(exc))
                    validation_failed_candidate_ids.append(int(candidate.id))
                    routing_item = {
                        "candidate_id": int(candidate.id),
                        "goal_key": goal_key,
                        "workflow_key": workflow_key,
                        "decision": "blocked_requires_operator",
                        "reason": "acceptance_validation_failed",
                        "policy_version": "candidate_risk_router_v1",
                        "error": str(exc),
                    }
                    routing_results.append(routing_item)
                    routing_suppressed_items.append(routing_item)
                    continue
                routing = route_candidate(db, candidate)
                routing_item = {
                    "candidate_id": int(candidate.id),
                    "goal_key": goal_key,
                    "workflow_key": workflow_key,
                    **routing.to_dict(),
                }
                routing_results.append(routing_item)
                metadata = _json_loads(candidate.metadata_json, {})
                metadata.update(
                    {
                        "routing_decision": routing.decision,
                        "routing_reason": routing.reason,
                        "router_policy_version": routing.policy_version,
                    }
                )
                candidate.metadata_json = _json_dumps(metadata)
                db.flush()
                if routing.decision == "auto_materialize_and_start":
                    try:
                        auto_result = approve_and_run_candidate(db, int(candidate.id), operator="candidate_risk_router")
                        requirement_id = int(auto_result["requirement_id"])
                        workflow_run_id = auto_result.get("workflow_run_id")
                        auto_materialized_requirement_ids.append(requirement_id)
                        if workflow_run_id is not None:
                            auto_started_workflow_run_ids.append(int(workflow_run_id))
                        refreshed = db.get(RequirementCandidateRow, int(candidate.id))
                        if refreshed is not None:
                            metadata = _json_loads(refreshed.metadata_json, {})
                            metadata.update(
                                {
                                    "auto_materialized_requirement_id": requirement_id,
                                    "auto_started_workflow_run_id": int(workflow_run_id) if workflow_run_id is not None else None,
                                }
                            )
                            refreshed.metadata_json = _json_dumps(metadata)
                            db.flush()
                    except Exception as exc:
                        routing_suppressed_items.append(
                            {
                                "candidate_id": int(candidate.id),
                                "goal_key": goal_key,
                                "reason": "auto_materialize_failed",
                                "error": str(exc)[:500],
                            }
                        )
                elif routing.decision == "blocked_requires_operator":
                    candidate.status = "suppressed"
                    candidate.suppression_reason = routing.reason
                    routing_suppressed_items.append(routing_item)
                    db.flush()
            else:
                routing_results.append(
                    {
                        "candidate_id": 0,
                        "goal_key": goal_key,
                        "workflow_key": workflow_key,
                        "decision": "dry_run_only",
                        "reason": "dry_run_does_not_route_candidates",
                        "policy_version": "candidate_risk_router_v1",
                    }
                )
        completed = utcnow()
        row.status = "succeeded"
        row.input_snapshot_json = _json_dumps(snapshot)
        row.parsed_output_json = _json_dumps(
            {
                "proposed_candidates": proposed,
                "routing_results": routing_results,
                "auto_materialized_requirement_ids": auto_materialized_requirement_ids,
                "auto_started_workflow_run_ids": auto_started_workflow_run_ids,
                "routing_suppressed_items": routing_suppressed_items,
                "validation_failed_candidate_ids": validation_failed_candidate_ids,
                "planner_validation_errors": planner_validation_errors,
            }
        )
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


def list_goals(
    db: Session,
    *,
    manifest_id: int | None = None,
    status: str | None = None,
    include_intent: bool = False,
) -> list[dict[str, Any]]:
    manifest = ensure_active_manifest(db) if manifest_id is None else db.get(OperatingManifestRow, manifest_id)
    if manifest is None:
        raise ValueError("manifest not found")
    return [goal_to_dict(row, include_intent=include_intent) for row in _goal_rows(db, int(manifest.id), status=status)]


def get_goal(db: Session, goal_id: int) -> dict[str, Any]:
    row = db.get(PlanningGoalRow, goal_id)
    if row is None:
        raise ValueError("goal not found")
    return goal_to_dict(row, include_intent=True)


def _trace_node(
    kind: str,
    status: str,
    title: str,
    *,
    summary: str = "",
    object_id: int | None = None,
    deep_link: str | None = None,
    diagnostic: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "status": status,
        "title": title,
        "summary": summary,
        "object_id": object_id,
        "deep_link": deep_link,
        "diagnostic": diagnostic,
        "metadata": metadata or {},
    }


def _goal_sweep_diagnostics(db: Session, goal: PlanningGoalRow) -> list[dict[str, Any]]:
    rows = (
        db.query(PlannerSweepRow)
        .filter(PlannerSweepRow.manifest_id == int(goal.manifest_id))
        .order_by(PlannerSweepRow.started_at.desc(), PlannerSweepRow.id.desc())
        .limit(20)
        .all()
    )
    diagnostics: list[dict[str, Any]] = []
    for sweep in rows:
        goal_key = str(goal.goal_key or "")
        suppressed = _json_loads(sweep.suppressed_items_json, [])
        parsed = _json_loads(sweep.parsed_output_json, {})
        candidates = []
        for collection in [
            suppressed,
            parsed.get("routing_suppressed_items") if isinstance(parsed, dict) else [],
            parsed.get("planner_validation_errors") if isinstance(parsed, dict) else [],
        ]:
            if isinstance(collection, list):
                candidates.extend(item for item in collection if isinstance(item, dict))
        for item in candidates:
            if str(item.get("goal_key") or "") != goal_key:
                continue
            diagnostics.append(
                {
                    "reason": str(item.get("reason") or item.get("error") or item.get("message") or "planner_suppressed"),
                    "source": "planner_sweep",
                    "timestamp": sweep.completed_at or sweep.started_at,
                    "sweep_id": int(sweep.id),
                    "goal_key": goal_key,
                }
            )
            if len(diagnostics) >= 3:
                return diagnostics
    return diagnostics


def _workflow_evidence_metadata(db: Session, workflow: WorkflowRunRow | None) -> dict[str, Any]:
    if workflow is None:
        return {}
    artifacts = (
        db.query(WorkflowArtifactRow)
        .filter(WorkflowArtifactRow.workflow_run_id == int(workflow.id))
        .order_by(WorkflowArtifactRow.id.desc())
        .all()
    )
    changed_files: list[str] = []
    command_count = 0
    command_evidence: list[dict[str, Any]] = []
    pr_url = str(getattr(workflow, "delivery_pr_url", "") or "").strip()
    for artifact in artifacts:
        payload = _json_loads(artifact.machine_readable_payload, {})
        if artifact.artifact_type == "workflow_file_change_summary" and isinstance(payload, dict):
            changed_files.extend(str(item) for item in payload.get("changed_files") or [] if str(item))
        if artifact.artifact_type == "workflow_command_result":
            command_count += 1
            command_evidence.append(
                {
                    "artifact_id": int(artifact.id),
                    "command": str(payload.get("command") or ""),
                    "purpose": str(payload.get("purpose") or ""),
                    "exit_code": int(payload.get("exit_code") or 0),
                    "status": "passed" if int(payload.get("exit_code") or 0) == 0 else "failed",
                }
            )
        if artifact.artifact_type == "workflow_review_pr_sync" and isinstance(payload, dict) and not pr_url:
            pr_url = str(payload.get("pr_url") or "").strip()
    return {
        "artifact_count": len(artifacts),
        "command_evidence_count": command_count,
        "command_evidence": command_evidence,
        "changed_files": sorted(set(changed_files)),
        "changed_files_count": len(set(changed_files)),
        "pr_url": pr_url or None,
        "delivery_status": str(getattr(workflow, "delivery_status", "") or "") or None,
        "delivery_is_simulated": bool(getattr(workflow, "delivery_is_simulated", False)),
    }


def _goal_hard_gate_missing_evidence(workflow: WorkflowRunRow | None, evidence: dict[str, Any]) -> list[str]:
    """Return objective-level evidence gaps for the latest goal chain.

    Workflow terminal state proves execution mechanics. The goal objective is stricter:
    for self-repair quality hardening, the trace must see the actual guardrail bundle,
    backend tests, dashboard tests/build, changed files, and delivery evidence.
    """

    if workflow is None:
        return ["missing_workflow"]
    missing: list[str] = []
    command_text = "\n".join(
        f"{item.get('purpose', '')} {item.get('command', '')}".lower()
        for item in evidence.get("command_evidence") or []
        if isinstance(item, dict)
    )
    workflow_key = str(workflow.workflow_key or "")
    if workflow_key == "agent_self_repair":
        required_signals = [
            ("missing_architecture_contracts", "agent_guardrails.sh"),
            ("missing_backend_tests", "pytest"),
            ("missing_dashboard_tests", "npm test"),
            ("missing_dashboard_build", "npm run build"),
        ]
        for missing_key, needle in required_signals:
            if needle not in command_text:
                missing.append(missing_key)
        if "docs" not in command_text and "doc" not in command_text:
            missing.append("missing_doc_sync_gate")
    if not evidence.get("command_evidence_count"):
        missing.append("missing_command_evidence")
    if not evidence.get("changed_files_count"):
        missing.append("missing_changed_files")
    if not evidence.get("pr_url"):
        missing.append("missing_pr_url")
    return sorted(set(missing))


def goal_trace(db: Session, goal_id: int) -> dict[str, Any]:
    goal = db.get(PlanningGoalRow, goal_id)
    if goal is None:
        raise ValueError("goal not found")
    manifest_id = int(goal.manifest_id)
    goal_key = str(goal.goal_key or "")
    diagnostics = _goal_sweep_diagnostics(db, goal)
    candidates = (
        db.query(RequirementCandidateRow)
        .filter(
            RequirementCandidateRow.manifest_id == manifest_id,
            RequirementCandidateRow.goal_key == goal_key,
        )
        .order_by(RequirementCandidateRow.updated_at.desc(), RequirementCandidateRow.id.desc())
        .all()
    )
    requirements = (
        db.query(RequirementRow)
        .filter(RequirementRow.operating_manifest_id == manifest_id, RequirementRow.goal_key == goal_key)
        .order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc())
        .all()
    )
    latest_requirement = requirements[0] if requirements else None
    latest_candidate = candidates[0] if candidates else None
    if latest_requirement is not None and latest_requirement.requirement_candidate_id:
        chain_candidate = next(
            (candidate for candidate in candidates if int(candidate.id) == int(latest_requirement.requirement_candidate_id)),
            None,
        )
        if chain_candidate is not None:
            latest_candidate = chain_candidate
    latest_workflow = None
    if latest_requirement is not None and latest_requirement.active_workflow_run_id:
        latest_workflow = db.get(WorkflowRunRow, int(latest_requirement.active_workflow_run_id))
    if latest_workflow is None:
        latest_workflow = (
            db.query(WorkflowRunRow)
            .filter(WorkflowRunRow.operating_manifest_id == manifest_id, WorkflowRunRow.goal_key == goal_key)
            .order_by(WorkflowRunRow.updated_at.desc(), WorkflowRunRow.id.desc())
            .first()
        )
    nodes: list[dict[str, Any]] = [
        _trace_node(
            "goal",
            "ok" if str(goal.intent_markdown or "").strip() else "warning",
            "Goal PRD saved" if str(goal.intent_markdown or "").strip() else "Goal PRD missing",
            summary=f"{len(str(goal.intent_markdown or ''))} Markdown characters stored in planning_goals.",
            object_id=int(goal.id),
            deep_link=f"/planning?goal={goal_key}",
            metadata={"intent_present": bool(str(goal.intent_markdown or "").strip())},
        )
    ]
    if latest_candidate is None:
        diagnostic = diagnostics[0] if diagnostics else {
            "reason": "no_candidate_for_goal",
            "source": "planning_trace",
            "timestamp": goal.updated_at,
            "goal_key": goal_key,
        }
        nodes.append(_trace_node("candidate", "missing", "No candidate for this goal", diagnostic=diagnostic))
    else:
        candidate_metadata = _json_loads(latest_candidate.metadata_json, {})
        status = str(latest_candidate.status or "")
        blocked = status in {"validation_failed", "rejected", "suppressed"}
        nodes.append(
            _trace_node(
                "candidate",
                "blocked" if blocked else "ok",
                f"Candidate #{int(latest_candidate.id)}: {latest_candidate.title}",
                summary=f"{status} · {latest_candidate.workflow_key}",
                object_id=int(latest_candidate.id),
                deep_link=f"/planning?candidate={int(latest_candidate.id)}",
                diagnostic={
                    "reason": str(
                        candidate_metadata.get("acceptance_validation_error")
                        or candidate_metadata.get("planner_agent_error")
                        or latest_candidate.suppression_reason
                        or latest_candidate.reject_reason
                        or ""
                    ),
                    "source": "requirement_candidate",
                    "timestamp": latest_candidate.updated_at,
                    "goal_key": goal_key,
                } if blocked else None,
                metadata={
                    "generated_by": candidate_metadata.get("generated_by"),
                    "routing_decision": candidate_metadata.get("routing_decision"),
                    "acceptance_step_count": len((candidate_metadata.get("acceptance_contract") or {}).get("execution_acceptance_steps") or []),
                },
            )
        )
    if latest_requirement is None:
        nodes.append(
            _trace_node(
                "requirement",
                "missing" if latest_candidate is None else "warning",
                "No materialized requirement for this goal",
                summary="Candidate has not produced a Requirement yet.",
                diagnostic=diagnostics[0] if latest_candidate is None and diagnostics else None,
            )
        )
    else:
        nodes.append(
            _trace_node(
                "requirement",
                "ok" if str(latest_requirement.status or "") not in {"failed", "cancelled", "deleted"} else "blocked",
                f"Requirement #{int(latest_requirement.id)}: {latest_requirement.title}",
                summary=f"{latest_requirement.status} · workflow_state={latest_requirement.workflow_state}",
                object_id=int(latest_requirement.id),
                deep_link=f"/requirements/{int(latest_requirement.id)}",
                metadata={
                    "candidate_id": int(latest_requirement.requirement_candidate_id) if latest_requirement.requirement_candidate_id else None,
                    "assets_status": latest_requirement.assets_status,
                },
            )
        )
    if latest_workflow is None:
        nodes.append(
            _trace_node(
                "workflow",
                "missing" if latest_requirement is None else "warning",
                "No workflow run for this goal",
                summary="Requirement has not started a declarative workflow run.",
                deep_link=f"/requirements/{int(latest_requirement.id)}" if latest_requirement is not None else None,
            )
        )
        evidence = {}
    else:
        evidence = _workflow_evidence_metadata(db, latest_workflow)
        workflow_status = str(latest_workflow.status or "")
        nodes.append(
            _trace_node(
                "workflow",
                "ok" if workflow_status in {"succeeded", "completed", "done"} else "warning" if workflow_status != "failed" else "blocked",
                f"WorkflowRun #{int(latest_workflow.id)}: {latest_workflow.workflow_key}",
                summary=f"{workflow_status} · state={latest_workflow.current_state}",
                object_id=int(latest_workflow.id),
                deep_link=f"/workflows/{int(latest_workflow.id)}?tab=evidence",
                metadata={
                    "current_state": latest_workflow.current_state,
                    "resolution": latest_workflow.resolution,
                    **evidence,
                },
            )
        )
        missing = _goal_hard_gate_missing_evidence(latest_workflow, evidence)
        nodes.append(
            _trace_node(
                "evidence",
                "ok" if not missing else "warning",
                "Evidence and delivery",
                summary="All key evidence is linked." if not missing else ", ".join(missing),
                object_id=int(latest_workflow.id),
                deep_link=f"/workflows/{int(latest_workflow.id)}?tab=evidence",
                diagnostic={
                    "reason": ", ".join(missing),
                    "source": "workflow_artifacts",
                    "timestamp": latest_workflow.updated_at,
                    "goal_key": goal_key,
                } if missing else None,
                metadata=evidence,
            )
        )
    objective_missing = _goal_hard_gate_missing_evidence(latest_workflow, evidence if latest_workflow is not None else {})
    terminal_statuses = {"succeeded", "completed", "done"}
    workflow_status = str(latest_workflow.status or "") if latest_workflow is not None else ""
    blocked_states = {str(node.get("status") or "") for node in nodes}
    if "blocked" in blocked_states:
        objective_status = "blocked"
    elif latest_workflow is not None and workflow_status in terminal_statuses and not objective_missing:
        objective_status = "satisfied"
    elif latest_workflow is not None:
        objective_status = "incomplete"
    else:
        objective_status = "blocked" if diagnostics else "incomplete"
    return {
        "goal": {
            "id": int(goal.id),
            "goal_key": goal_key,
            "title": str(goal.title or ""),
            "intent_present": bool(str(goal.intent_markdown or "").strip()),
            "intent_length": len(str(goal.intent_markdown or "")),
            "intent_hash": hashlib.sha256(str(goal.intent_markdown or "").encode("utf-8")).hexdigest(),
            "intent_excerpt": _intent_excerpt(str(goal.intent_markdown or "")),
        },
        "objective_status": objective_status,
        "missing_evidence": objective_missing,
        "latest_chain": {
            "candidate_id": int(latest_candidate.id) if latest_candidate is not None else None,
            "requirement_id": int(latest_requirement.id) if latest_requirement is not None else None,
            "workflow_run_id": int(latest_workflow.id) if latest_workflow is not None else None,
            "delivery_pr_url": evidence.get("pr_url") if latest_workflow is not None else None,
        },
        "scheduler_diagnostics": {
            "goal_key": goal_key,
            "planner_suppression": diagnostics[0] if diagnostics else None,
        },
        "nodes": nodes,
        "diagnostics": diagnostics,
        "next_actions": [
            item
            for item in [
                {"label": "Open Planning", "deep_link": "/planning"},
                {"label": "Open latest workflow", "deep_link": f"/workflows/{int(latest_workflow.id)}?tab=evidence"} if latest_workflow is not None else None,
            ]
            if item is not None
        ],
        "history": [
            {
                "candidate_id": int(candidate.id),
                "status": str(candidate.status or ""),
                "requirement_id": int(candidate.materialized_requirement_id) if candidate.materialized_requirement_id else None,
                "updated_at": candidate.updated_at,
            }
            for candidate in candidates[:5]
        ],
    }


def create_goal(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    manifest_id = payload.get("manifest_id")
    manifest = ensure_active_manifest(db) if manifest_id is None else db.get(OperatingManifestRow, int(manifest_id))
    if manifest is None:
        raise ValueError("manifest not found")
    goal_key = str(payload.get("goal_key") or "").strip()
    if not goal_key:
        raise ValueError("goal_key is required")
    existing = _goal_by_key(db, int(manifest.id), goal_key)
    if existing is not None:
        raise ValueError(f"duplicate goal_key: {goal_key}")
    row = _create_goal_from_spec(db, int(manifest.id), payload)
    manifest.revision = int(manifest.revision or 1) + 1
    manifest.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return goal_to_dict(row, include_intent=True)


def update_goal(db: Session, goal_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = db.get(PlanningGoalRow, goal_id)
    if row is None:
        raise ValueError("goal not found")
    if "status" in payload and payload["status"] is not None:
        status = str(payload["status"] or "").strip()
        if status not in {GOAL_ACTIVE, GOAL_ACHIEVED, GOAL_DROPPED}:
            raise ValueError(f"unsupported goal status: {status}")
        row.status = status
        if status in {GOAL_ACHIEVED, GOAL_DROPPED} and row.closed_at is None:
            row.closed_at = utcnow()
    for key in ["title", "intent_markdown", "success_metric", "domain", "workflow_key", "priority", "risk_level", "acceptance_kind", "review_note"]:
        if key in payload and payload[key] is not None:
            setattr(row, key, str(payload[key] or "").strip())
    if "project_key" in payload:
        row.project_key = str(payload.get("project_key") or "").strip() or None
    if "weight" in payload and payload["weight"] is not None:
        row.weight = float(payload["weight"] or 0.0)
    if "execution_acceptance_steps" in payload and payload["execution_acceptance_steps"] is not None:
        row.execution_acceptance_steps_json = _json_dumps(payload["execution_acceptance_steps"] or [])
    if "metadata" in payload and payload["metadata"] is not None:
        row.metadata_json = _json_dumps(payload["metadata"] or {})
    row.updated_at = utcnow()
    manifest = db.get(OperatingManifestRow, int(row.manifest_id))
    if manifest is not None:
        manifest.revision = int(manifest.revision or 1) + 1
        manifest.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return goal_to_dict(row, include_intent=True)


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
    goal = _goal_by_key(db, int(manifest.id), str(row.goal_key or ""))
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
    goal = _goal_by_key(db, int(manifest.id), str(row.goal_key or ""))
    if goal is None or _goal_status(goal) == GOAL_DROPPED:
        raise ValueError("cannot materialize candidate for dropped or missing goal")
    project = db.get(ProjectRow, int(row.project_id)) if row.project_id else None
    if project is None and row.project_key:
        project = db.query(ProjectRow).filter(ProjectRow.project_key == row.project_key).first()
    if project is None:
        project = db.query(ProjectRow).order_by(ProjectRow.id.asc()).first()
    if project is None:
        raise ValueError("candidate cannot be materialized without a project")
    try:
        acceptance_contract = validate_acceptance_contract_for_execution(
            _candidate_acceptance_contract(row),
            source="planner_candidate",
            goal_key=str(row.goal_key or ""),
        )
    except AcceptanceValidationError as exc:
        _mark_candidate_acceptance_validation_failed(db, row, str(exc))
        db.commit()
        raise ValueError(
            "Planner candidate failed acceptance validation: Planner Agent did not generate concrete, evidence-bound execution_acceptance_steps."
        ) from exc
    risk_level = str(row.risk_level or "").strip().lower() or "normal"
    priority = str(row.priority or "").strip().lower() or "normal"
    severity = risk_level if risk_level in {"high", "critical"} else priority
    body = RequirementCreate(
        title=str(row.title or "").strip(),
        description_markdown=str(row.description_markdown or "").strip(),
        priority=str(row.priority or "normal"),
        source="planner_candidate",
        source_ref=f"planner-candidate:{int(row.id)}",
        project_id=int(project.id),
        acceptance_contract=acceptance_contract,
        intake_metadata={
            "operating_manifest_id": int(row.manifest_id),
            "goal_key": str(row.goal_key or ""),
            "requirement_candidate_id": int(row.id),
            "workflow_key": str(row.workflow_key or ""),
            "materialized_by": operator,
            "risk_level": risk_level,
            "severity": severity,
            "candidate_priority": priority,
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
            "risk_level": risk_level,
            "severity": severity,
            "candidate_priority": priority,
        }
    )
    requirement.intake_metadata_json = _json_dumps(metadata)
    row.status = "materialized"
    row.materialized_requirement_id = int(requirement.id)
    row.updated_at = utcnow()
    db.commit()
    return {"candidate": candidate_to_dict(row), "requirement_id": int(requirement.id)}


def _workflow_next_action(detail: dict[str, Any]) -> str:
    pending_gate_count = int(detail.get("pending_human_gate_count") or 0)
    status = str(detail.get("status") or "").strip()
    current_state = str(detail.get("current_state") or "").strip()
    if pending_gate_count > 0 or status == "awaiting_operator" or current_state == "awaiting_operator":
        return "review_human_gate"
    if status in {"succeeded", "completed", "done"}:
        return "view_completion_evidence"
    if status == "failed":
        return "inspect_failure"
    return "view_workflow"


def _auto_run_status(detail: dict[str, Any]) -> str:
    next_action = _workflow_next_action(detail)
    status = str(detail.get("status") or "").strip()
    if next_action == "review_human_gate":
        return "workflow_needs_human"
    if status in {"succeeded", "completed", "done"}:
        return "workflow_completed"
    if status == "failed":
        return "workflow_failed"
    return "workflow_started"


def approve_and_run_candidate(db: Session, candidate_id: int, *, operator: str = "operator") -> dict[str, Any]:
    """Approve a candidate, materialize it, and immediately start its workflow.

    This is intentionally not a resurrection of legacy requirement approval. The
    only automatic progression after candidate approval is the current
    declarative workflow runner, where high-risk work still stops at a Human Gate.
    """

    row = db.get(RequirementCandidateRow, candidate_id)
    if row is None:
        raise ValueError("candidate not found")
    status = str(row.status or "").strip()
    if status in {"pending", "rejected"}:
        row = approve_candidate(db, candidate_id, operator=operator)
        status = str(row.status or "").strip()
    if status == "approved":
        materialized = materialize_candidate(db, candidate_id, operator=operator)
        row = db.get(RequirementCandidateRow, candidate_id)
        requirement_id = int(materialized["requirement_id"])
    elif status == "materialized" and row.materialized_requirement_id:
        requirement_id = int(row.materialized_requirement_id)
    else:
        raise ValueError(f"candidate cannot be approved and run from status {row.status}")

    workflow_detail = start_requirement_workflow(
        db,
        requirement_id,
        workflow_key=str(getattr(row, "workflow_key", "") or "").strip() or None,
        triggered_by="candidate_approve_and_run",
        run_immediately=True,
    )
    db.commit()
    refreshed = db.get(RequirementCandidateRow, candidate_id)
    return {
        "candidate": candidate_to_dict(refreshed or row),
        "requirement_id": requirement_id,
        "workflow_run_id": int(workflow_detail.get("id")) if workflow_detail.get("id") is not None else None,
        "workflow_status": str(workflow_detail.get("status") or ""),
        "workflow_current_state": str(workflow_detail.get("current_state") or ""),
        "auto_run_status": _auto_run_status(workflow_detail),
        "next_action": _workflow_next_action(workflow_detail),
    }


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
    goal = _goal_by_key(db, manifest_id, goal_key)
    if goal is None:
        raise ValueError("goal not found")
    decision = {
        "reason": reason.strip(),
        "operator": operator,
        "halt_mode": halt_mode or "safe_halt",
        "decided_at": _now_iso(),
        "rollback_policy": "drop_goal_never_rolls_back_releases",
    }
    goal.status = GOAL_DROPPED
    goal.closed_at = utcnow()
    goal.review_note = reason.strip()
    goal.drop_decision_json = _json_dumps(decision)
    goal.updated_at = utcnow()
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
        if status in {"draft", "ready", "blocked", "planning"}:
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
        "manifest": manifest_to_dict(manifest, db),
        "goal_key": goal_key,
        "halt_summary": summary,
        "decision": decision,
    }
