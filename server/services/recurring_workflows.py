"""Recurring COO workflow registry and runnable skeletons."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import ApprovalRequestRow, ArtifactRow, RecurringWorkflowRow, RequirementRow, utcnow
from server.services.company_review import company_review_to_dict, latest_company_operating_review, refresh_company_operating_review
from server.services.incidents import list_open_incidents
from server.services.optimization_signals import list_optimization_signals
from server.services.requirement_sources import intake_requirement_sources
from server.services.workflow_orchestrator import advance_requirement_queue, dispatch_acceptance_sweep


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


BUILTIN_RECURRING_WORKFLOWS: list[dict[str, Any]] = [
    {
        "workflow_key": "morning_intake_sweep",
        "display_name": "Morning Intake Sweep",
        "description": "Refresh intake sources and create high-confidence backlog candidates.",
        "trigger_type": "scheduled",
        "owner_role": "ops_intake_manager",
        "schedule": {"cadence": "daily", "window": "morning", "suggested_local_time": "09:00"},
        "input_query": {"sources": ["optimization_signal", "company_review_bundle", "automation_candidate"], "refresh": True},
        "output_action": {"kind": "create_requirements", "auto_start": False, "max_created": 2},
        "escalation_rule": {"on_failure": "notify_portfolio_operator", "on_empty": "no_op"},
        "validation_signal": {"success_metric": "created_requirement_ids", "min_expected": 0},
    },
    {
        "workflow_key": "dispatcher_loop",
        "display_name": "Dispatcher Loop",
        "description": "Advance the requirement queue like a COO duty cycle.",
        "trigger_type": "scheduled",
        "owner_role": "portfolio_operator",
        "schedule": {"cadence": "hourly", "interval_hours": 2},
        "input_query": {"status": ["ready", "blocked", "paused"], "scheduler": True},
        "output_action": {"kind": "advance_requirement_queue"},
        "escalation_rule": {"on_repeated_idle": "review_scheduler_posture"},
        "validation_signal": {"success_metric": "started_ids"},
    },
    {
        "workflow_key": "closeout_and_compact_sweep",
        "display_name": "Closeout And Compact Sweep",
        "description": "Sweep for acceptance-ready work and compact the day’s execution context.",
        "trigger_type": "scheduled",
        "owner_role": "tester",
        "schedule": {"cadence": "daily", "window": "evening", "suggested_local_time": "18:00"},
        "input_query": {"acceptance_ready": True, "long_running_requirement_hours": 8},
        "output_action": {"kind": "dispatch_acceptance_candidates", "auto_dispatch": False},
        "escalation_rule": {"on_backlog_growth": "notify_portfolio_operator"},
        "validation_signal": {"success_metric": "acceptance_candidates"},
    },
    {
        "workflow_key": "weekly_operating_review",
        "display_name": "Weekly Operating Review",
        "description": "Refresh company review, next-cycle bundle, and operator package.",
        "trigger_type": "scheduled",
        "owner_role": "company_reviewer",
        "schedule": {"cadence": "weekly", "day": "MON", "suggested_local_time": "10:00"},
        "input_query": {"refresh_company_review": True},
        "output_action": {"kind": "refresh_company_review"},
        "escalation_rule": {"on_high_incidents": "open_operator_summary"},
        "validation_signal": {"success_metric": "bundle_item_count"},
    },
]


def _signal_candidate_summary(db: Session, *, limit: int = 5) -> list[dict[str, Any]]:
    rows = list_optimization_signals(db, status="open")
    items: list[dict[str, Any]] = []
    for row in rows[:limit]:
        items.append(
            {
                "signal_id": int(row.id),
                "title": str(row.title),
                "severity": str(row.severity),
                "confidence": float(row.confidence or 0.0),
                "project_key": str(row.project_key or "org-ops"),
                "occurrence_count": int(row.occurrence_count or 0),
                "latest_evidence_at": _ensure_utc(row.latest_evidence_at).isoformat() if _ensure_utc(row.latest_evidence_at) else None,
            }
        )
    return items


def _bundle_candidate_summary(review_payload: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in list(review_payload.get("next_cycle_requirement_bundle") or [])[:limit]:
        items.append(
            {
                "bundle_item_key": str(row.get("bundle_item_key") or ""),
                "title": str(row.get("title") or ""),
                "priority": str(row.get("priority") or "normal"),
                "project_key": str(row.get("project_key") or "org-ops"),
                "source_ref": str(row.get("source_ref") or "") or None,
            }
        )
    return items


def _dispatcher_follow_through(
    db: Session,
    *,
    stuck_after_hours: int = 4,
    approval_reminder_after_hours: int = 4,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    stuck_cutoff = now.timestamp() - (max(1, stuck_after_hours) * 3600)
    approval_cutoff = now.timestamp() - (max(1, approval_reminder_after_hours) * 3600)
    incidents = list_open_incidents(db)
    incidents_by_requirement: dict[int, list[dict[str, Any]]] = {}
    for incident in incidents:
        req_id = int(incident.get("requirement_id") or 0)
        if req_id:
            incidents_by_requirement.setdefault(req_id, []).append(incident)

    pending_approvals = db.query(ApprovalRequestRow).filter(ApprovalRequestRow.status == "pending").all()
    approval_by_requirement: dict[int, list[ApprovalRequestRow]] = {}
    for approval in pending_approvals:
        if approval.requirement_id is not None:
            approval_by_requirement.setdefault(int(approval.requirement_id), []).append(approval)

    follow_up_actions: list[dict[str, Any]] = []
    stuck_requirement_ids: list[int] = []
    paused_requirement_ids: list[int] = []
    blocked_requirement_ids: list[int] = []
    needs_revision_ids: list[int] = []

    for requirement in db.query(RequirementRow).all():
        requirement_id = int(requirement.id)
        status = str(requirement.status or "")
        updated = _ensure_utc(requirement.updated_at or requirement.created_at) or now
        requirement_incidents = incidents_by_requirement.get(requirement_id, [])
        pending = approval_by_requirement.get(requirement_id, [])

        if status == "in_progress" and updated.timestamp() <= stuck_cutoff:
            stuck_requirement_ids.append(requirement_id)
            follow_up_actions.append(
                {
                    "action": "investigate_stuck",
                    "requirement_id": requirement_id,
                    "title": str(requirement.title),
                    "reason": "requirement_in_progress_without_recent_progress",
                }
            )
        if status == "paused":
            paused_requirement_ids.append(requirement_id)
            recovery_incident = next(
                (
                    item for item in requirement_incidents
                    if str(item.get("recovery_status") or "") in {"runtime_recovery_required", "operator_review_required"}
                ),
                None,
            )
            follow_up_actions.append(
                {
                    "action": "incident_recovery" if recovery_incident else "retry",
                    "requirement_id": requirement_id,
                    "title": str(requirement.title),
                    "reason": str((recovery_incident or {}).get("recovery_status") or "paused_requirement_ready_for_retry"),
                }
            )
        if status == "blocked":
            blocked_requirement_ids.append(requirement_id)
            if requirement.blocked_by_count:
                follow_up_actions.append(
                    {
                        "action": "wait_dependency",
                        "requirement_id": requirement_id,
                        "title": str(requirement.title),
                        "reason": f"blocked_by_{int(requirement.blocked_by_count)}_dependencies",
                    }
                )
            elif pending:
                follow_up_actions.append(
                    {
                        "action": "approval_reminder",
                        "requirement_id": requirement_id,
                        "title": str(requirement.title),
                        "reason": str(pending[0].approval_type or "pending_approval"),
                    }
                )
            elif requirement_incidents:
                follow_up_actions.append(
                    {
                        "action": "incident_recovery",
                        "requirement_id": requirement_id,
                        "title": str(requirement.title),
                        "reason": str(requirement_incidents[0].get("recovery_status") or "blocked_incident"),
                    }
                )
        if status == "needs_revision":
            needs_revision_ids.append(requirement_id)
            follow_up_actions.append(
                {
                    "action": "replan",
                    "requirement_id": requirement_id,
                    "title": str(requirement.title),
                    "reason": "requirement_needs_revision",
                }
            )

    approval_reminders: list[dict[str, Any]] = []
    for approval in pending_approvals:
        created = _ensure_utc(approval.created_at) or now
        if created.timestamp() > approval_cutoff:
            continue
        approval_reminders.append(
            {
                "approval_request_id": int(approval.id),
                "requirement_id": int(approval.requirement_id) if approval.requirement_id is not None else None,
                "approval_type": str(approval.approval_type),
                "reviewer": str(approval.reviewer or ""),
                "age_hours": round((now - created).total_seconds() / 3600, 2),
            }
        )
        if approval.requirement_id is not None:
            follow_up_actions.append(
                {
                    "action": "approval_reminder",
                    "requirement_id": int(approval.requirement_id),
                    "title": f"Approval {approval.approval_type}",
                    "reason": str(approval.approval_type),
                }
            )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in follow_up_actions:
        req_id = int(item.get("requirement_id") or 0)
        key = (str(item.get("action") or ""), req_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return {
        "stuck_requirement_ids": sorted(set(stuck_requirement_ids)),
        "paused_requirement_ids": sorted(set(paused_requirement_ids)),
        "blocked_requirement_ids": sorted(set(blocked_requirement_ids)),
        "needs_revision_ids": sorted(set(needs_revision_ids)),
        "approval_reminders": approval_reminders,
        "follow_up_actions": deduped,
    }


def _operator_attention_items(
    *,
    signal_candidates: list[dict[str, Any]],
    incident_candidates: list[dict[str, Any]],
    bundle_candidates: list[dict[str, Any]],
    intake_result: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for signal in signal_candidates:
        if str(signal.get("severity") or "") == "high":
            items.append(
                {
                    "kind": "signal",
                    "title": str(signal.get("title") or ""),
                    "reason": "high_severity_signal",
                }
            )
    for incident in incident_candidates[:3]:
        if str(incident.get("severity") or "") in {"critical", "high"}:
            items.append(
                {
                    "kind": "incident",
                    "title": str(incident.get("title") or ""),
                    "reason": str(incident.get("recovery_status") or "operator_review_required"),
                }
            )
    for bundle in bundle_candidates:
        if str(bundle.get("priority") or "") == "high":
            items.append(
                {
                    "kind": "bundle",
                    "title": str(bundle.get("title") or ""),
                    "reason": "high_priority_bundle_candidate",
                }
            )
    for skipped in list(intake_result.get("skipped") or [])[:5]:
        items.append({"kind": "intake_skip", "title": str(skipped), "reason": "intake_skipped"})
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("kind") or ""), str(item.get("title") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:8]


def _daily_intake_summary_markdown(
    *,
    intake_result: dict[str, Any],
    signal_candidates: list[dict[str, Any]],
    incident_candidates: list[dict[str, Any]],
    bundle_candidates: list[dict[str, Any]],
    operator_attention_items: list[dict[str, Any]],
) -> str:
    lines = [
        "# Daily Intake Summary",
        "",
        f"- created requirements: `{len(intake_result.get('created_requirement_ids') or [])}`",
        f"- reused requirements: `{len(intake_result.get('reused_requirement_ids') or [])}`",
        f"- open signal candidates reviewed: `{len(signal_candidates)}`",
        f"- open incidents reviewed: `{len(incident_candidates)}`",
        f"- bundle candidates reviewed: `{len(bundle_candidates)}`",
        f"- operator attention items: `{len(operator_attention_items)}`",
    ]
    if operator_attention_items:
        lines.extend(["", "## Needs Operator Attention"])
        lines.extend(
            f"- [{item.get('kind')}] {item.get('title')} ({item.get('reason')})"
            for item in operator_attention_items
        )
    if signal_candidates:
        lines.extend(["", "## Top Signal Candidates"])
        lines.extend(
            f"- {item.get('title')} / severity `{item.get('severity')}` / confidence `{item.get('confidence')}`"
            for item in signal_candidates
        )
    return "\n".join(lines)


def _morning_intake_sweep(
    db: Session,
    *,
    auto_start: bool,
    intake_min_score: float,
    intake_max_created: int,
) -> dict[str, Any]:
    intake_result = intake_requirement_sources(
        db,
        source_key="all",
        refresh=True,
        auto_start=auto_start,
        min_score=intake_min_score,
        max_created=intake_max_created,
    )
    review = latest_company_operating_review(db)
    review_payload = company_review_to_dict(review)
    signal_candidates = _signal_candidate_summary(db)
    incident_candidates = list_open_incidents(db)[:5]
    bundle_candidates = _bundle_candidate_summary(review_payload)
    operator_attention_items = _operator_attention_items(
        signal_candidates=signal_candidates,
        incident_candidates=incident_candidates,
        bundle_candidates=bundle_candidates,
        intake_result=intake_result,
    )
    return {
        **intake_result,
        "daily_summary_markdown": _daily_intake_summary_markdown(
            intake_result=intake_result,
            signal_candidates=signal_candidates,
            incident_candidates=incident_candidates,
            bundle_candidates=bundle_candidates,
            operator_attention_items=operator_attention_items,
        ),
        "signal_candidates": signal_candidates,
        "incident_candidates": incident_candidates,
        "bundle_candidates": bundle_candidates,
        "operator_attention_items": operator_attention_items,
        "requires_operator_review": bool(operator_attention_items),
        "company_review_id": int(review.id),
    }


def _maybe_record_requirement_artifact(
    db: Session,
    *,
    requirement: RequirementRow,
    artifact_type: str,
    summary: str,
    payload: dict[str, Any],
    body: str,
) -> bool:
    latest = (
        db.query(ArtifactRow)
        .filter(
            ArtifactRow.requirement_id == int(requirement.id),
            ArtifactRow.artifact_type == artifact_type,
        )
        .order_by(ArtifactRow.id.desc())
        .first()
    )
    payload_marker = str(payload.get("requirement_updated_at") or "")
    if latest is not None:
        latest_payload = _json_loads(latest.machine_readable_payload, {})
        if isinstance(latest_payload, dict) and str(latest_payload.get("requirement_updated_at") or "") == payload_marker:
            return False
    db.add(
        ArtifactRow(
            requirement_id=int(requirement.id),
            workflow_run_id=int(requirement.active_workflow_run_id) if requirement.active_workflow_run_id is not None else None,
            artifact_type=artifact_type,
            content_summary=summary,
            human_readable_body=body,
            machine_readable_payload=_json_dumps(payload),
        )
    )
    db.flush()
    return True


def _review_snapshot_markdown(requirement: RequirementRow, payload: dict[str, Any]) -> str:
    lines = [
        "# Review Snapshot",
        "",
        f"- requirement: `{requirement.title}`",
        f"- status: `{payload.get('status')}`",
        f"- priority: `{payload.get('priority')}`",
        f"- active workflow run: `{payload.get('active_workflow_run_id')}`",
        f"- artifact types: `{', '.join(payload.get('artifact_types') or [])}`",
    ]
    delivery = payload.get("delivery_state") or {}
    if isinstance(delivery, dict) and delivery:
        lines.append(f"- publish status: `{delivery.get('publish_status') or 'unknown'}`")
    return "\n".join(lines)


def _record_review_snapshot(db: Session, requirement: RequirementRow) -> bool:
    artifacts = (
        db.query(ArtifactRow)
        .filter(ArtifactRow.requirement_id == int(requirement.id))
        .order_by(ArtifactRow.id.asc())
        .all()
    )
    artifact_types = [str(item.artifact_type) for item in artifacts[-8:]]
    latest_delivery = next((item for item in reversed(artifacts) if str(item.artifact_type) == "delivery_state"), None)
    delivery_payload = _json_loads(getattr(latest_delivery, "machine_readable_payload", None), {})
    updated = _ensure_utc(requirement.updated_at or requirement.created_at) or datetime.now(timezone.utc)
    payload = {
        "requirement_id": int(requirement.id),
        "title": str(requirement.title),
        "status": str(requirement.status or ""),
        "priority": str(requirement.priority or "normal"),
        "active_workflow_run_id": int(requirement.active_workflow_run_id) if requirement.active_workflow_run_id is not None else None,
        "artifact_types": artifact_types,
        "delivery_state": delivery_payload if isinstance(delivery_payload, dict) else {},
        "requirement_updated_at": updated.isoformat(),
        "generated_at": utcnow().isoformat(),
    }
    return _maybe_record_requirement_artifact(
        db,
        requirement=requirement,
        artifact_type="review_snapshot",
        summary=f"End-of-day review snapshot for requirement #{int(requirement.id)}",
        payload=payload,
        body=_review_snapshot_markdown(requirement, payload),
    )


def _compaction_markdown(requirement: RequirementRow, payload: dict[str, Any]) -> str:
    lines = [
        "# End Of Day Compaction",
        "",
        f"- requirement: `{requirement.title}`",
        f"- status: `{payload.get('status')}`",
        f"- stale for hours: `{payload.get('stale_hours')}`",
        f"- recent artifacts: `{', '.join(payload.get('recent_artifact_types') or [])}`",
        "",
        "This compaction snapshot is intended to reduce the next-day context rebuild cost.",
    ]
    return "\n".join(lines)


def _record_end_of_day_compaction(db: Session, requirement: RequirementRow, *, now: datetime) -> bool:
    artifacts = (
        db.query(ArtifactRow)
        .filter(ArtifactRow.requirement_id == int(requirement.id))
        .order_by(ArtifactRow.id.asc())
        .all()
    )
    updated = _ensure_utc(requirement.updated_at or requirement.created_at) or now
    payload = {
        "requirement_id": int(requirement.id),
        "title": str(requirement.title),
        "status": str(requirement.status or ""),
        "active_workflow_run_id": int(requirement.active_workflow_run_id) if requirement.active_workflow_run_id is not None else None,
        "recent_artifact_types": [str(item.artifact_type) for item in artifacts[-8:]],
        "stale_hours": round(max(0.0, (now - updated).total_seconds()) / 3600, 2),
        "requirement_updated_at": updated.isoformat(),
        "generated_at": utcnow().isoformat(),
    }
    return _maybe_record_requirement_artifact(
        db,
        requirement=requirement,
        artifact_type="end_of_day_compaction",
        summary=f"End-of-day compaction snapshot for requirement #{int(requirement.id)}",
        payload=payload,
        body=_compaction_markdown(requirement, payload),
    )


def _end_of_day_summary_markdown(
    *,
    acceptance_result: dict[str, Any],
    compacted_requirement_ids: list[int],
    review_snapshot_requirement_ids: list[int],
    stale_requirement_ids: list[int],
    company_review_id: int | None,
) -> str:
    return "\n".join(
        [
            "# End Of Day Summary",
            "",
            f"- acceptance candidates scanned: `{int(acceptance_result.get('scanned') or 0)}`",
            f"- acceptance dispatched: `{len(acceptance_result.get('dispatched_requirement_ids') or [])}`",
            f"- stale requirements compacted: `{len(compacted_requirement_ids)}`",
            f"- review snapshots recorded: `{len(review_snapshot_requirement_ids)}`",
            f"- stale requirement ids: `{', '.join(str(item) for item in stale_requirement_ids) or 'none'}`",
            f"- company review refreshed: `{company_review_id if company_review_id is not None else 'no'}`",
        ]
    )


def recurring_workflow_to_dict(row: RecurringWorkflowRow) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "workflow_key": str(row.workflow_key),
        "display_name": str(row.display_name),
        "description": str(row.description or ""),
        "status": str(row.status),
        "trigger_type": str(row.trigger_type),
        "owner_role": str(row.owner_role),
        "schedule": _json_loads(row.schedule_json, {}),
        "input_query": _json_loads(row.input_query_json, {}),
        "output_action": _json_loads(row.output_action_json, {}),
        "escalation_rule": _json_loads(row.escalation_rule_json, {}),
        "validation_signal": _json_loads(row.validation_signal_json, {}),
        "is_builtin": bool(row.is_builtin),
        "last_run_at": row.last_run_at,
        "last_result": _json_loads(row.last_result_json, {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def sync_recurring_workflows(db: Session) -> list[RecurringWorkflowRow]:
    by_key = {
        str(row.workflow_key): row
        for row in db.query(RecurringWorkflowRow).all()
    }
    touched: list[RecurringWorkflowRow] = []
    for definition in BUILTIN_RECURRING_WORKFLOWS:
        row = by_key.get(str(definition["workflow_key"]))
        if row is None:
            row = RecurringWorkflowRow(
                workflow_key=str(definition["workflow_key"]),
                display_name=str(definition["display_name"]),
                description=str(definition["description"]),
                status="active",
                trigger_type=str(definition["trigger_type"]),
                owner_role=str(definition["owner_role"]),
                schedule_json=_json_dumps(definition["schedule"]),
                input_query_json=_json_dumps(definition["input_query"]),
                output_action_json=_json_dumps(definition["output_action"]),
                escalation_rule_json=_json_dumps(definition["escalation_rule"]),
                validation_signal_json=_json_dumps(definition["validation_signal"]),
                is_builtin=True,
            )
            db.add(row)
            db.flush()
        else:
            row.display_name = str(definition["display_name"])
            row.description = str(definition["description"])
            row.trigger_type = str(definition["trigger_type"])
            row.owner_role = str(definition["owner_role"])
            row.schedule_json = _json_dumps(definition["schedule"])
            row.input_query_json = _json_dumps(definition["input_query"])
            row.output_action_json = _json_dumps(definition["output_action"])
            row.escalation_rule_json = _json_dumps(definition["escalation_rule"])
            row.validation_signal_json = _json_dumps(definition["validation_signal"])
            row.is_builtin = True
        touched.append(row)
    db.commit()
    return db.query(RecurringWorkflowRow).order_by(
        RecurringWorkflowRow.is_builtin.desc(),
        RecurringWorkflowRow.workflow_key.asc(),
    ).all()


def list_recurring_workflows(db: Session) -> list[RecurringWorkflowRow]:
    sync_recurring_workflows(db)
    return db.query(RecurringWorkflowRow).order_by(
        RecurringWorkflowRow.is_builtin.desc(),
        RecurringWorkflowRow.workflow_key.asc(),
    ).all()


def get_recurring_workflow(db: Session, workflow_key: str) -> RecurringWorkflowRow:
    sync_recurring_workflows(db)
    row = db.query(RecurringWorkflowRow).filter(RecurringWorkflowRow.workflow_key == workflow_key).first()
    if row is None:
        raise ValueError("Recurring workflow not found")
    return row


def _closeout_and_compact_sweep(db: Session, *, acceptance_limit: int, auto_dispatch_acceptance: bool) -> dict[str, Any]:
    acceptance_result = dispatch_acceptance_sweep(
        db,
        limit=acceptance_limit,
        auto_dispatch=auto_dispatch_acceptance,
    )
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(hours=8)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    stale_candidates = db.query(RequirementRow).filter(RequirementRow.status.in_(["in_progress", "paused", "blocked"])).all()
    stale_ids: list[int] = []
    compacted_requirement_ids: list[int] = []
    for row in stale_candidates:
        updated = _ensure_utc(row.updated_at or row.created_at) or now
        if updated >= stale_cutoff:
            continue
        stale_ids.append(int(row.id))
        if _record_end_of_day_compaction(db, row, now=now):
            compacted_requirement_ids.append(int(row.id))

    review_snapshot_requirement_ids: list[int] = []
    review_candidates = db.query(RequirementRow).filter(
        RequirementRow.status.in_(["done", "paused", "blocked", "needs_revision"])
    ).all()
    for row in review_candidates:
        updated = _ensure_utc(row.updated_at or row.created_at) or now
        if updated < day_start:
            continue
        if _record_review_snapshot(db, row):
            review_snapshot_requirement_ids.append(int(row.id))

    review = refresh_company_operating_review(db)
    return {
        "acceptance_candidates": len(acceptance_result.get("candidates") or []),
        "acceptance_dispatch": acceptance_result,
        "stale_requirement_ids": stale_ids,
        "compacted_requirement_ids": compacted_requirement_ids,
        "review_snapshot_requirement_ids": review_snapshot_requirement_ids,
        "company_review_id": int(review.id),
        "daily_summary_markdown": _end_of_day_summary_markdown(
            acceptance_result=acceptance_result,
            compacted_requirement_ids=compacted_requirement_ids,
            review_snapshot_requirement_ids=review_snapshot_requirement_ids,
            stale_requirement_ids=stale_ids,
            company_review_id=int(review.id),
        ),
    }


def run_recurring_workflow(
    db: Session,
    *,
    workflow_key: str,
    dry_run: bool = False,
    auto_start: bool = False,
    intake_min_score: float = 60.0,
    intake_max_created: int = 2,
    acceptance_limit: int = 20,
    auto_dispatch_acceptance: bool = False,
) -> dict[str, Any]:
    row = get_recurring_workflow(db, workflow_key)
    if str(row.status) != "active":
        raise ValueError("Recurring workflow is not active")

    if dry_run:
        result = {
            "dry_run": True,
            "workflow_key": workflow_key,
            "owner_role": row.owner_role,
            "schedule": _json_loads(row.schedule_json, {}),
            "output_action": _json_loads(row.output_action_json, {}),
        }
    elif workflow_key == "morning_intake_sweep":
        result = _morning_intake_sweep(
            db,
            auto_start=auto_start,
            intake_min_score=intake_min_score,
            intake_max_created=intake_max_created,
        )
    elif workflow_key == "dispatcher_loop":
        queue_result = advance_requirement_queue(db)
        follow_through = _dispatcher_follow_through(db)
        result = {
            **queue_result,
            **follow_through,
        }
    elif workflow_key == "closeout_and_compact_sweep":
        result = _closeout_and_compact_sweep(
            db,
            acceptance_limit=acceptance_limit,
            auto_dispatch_acceptance=auto_dispatch_acceptance,
        )
    elif workflow_key == "weekly_operating_review":
        review = refresh_company_operating_review(db)
        payload = company_review_to_dict(review)
        rituals = dict((payload.get("source_snapshot") or {}).get("workflow_rituals") or {})
        operator_package = dict(payload.get("operator_review_package") or {})
        result = {
            "review_id": int(review.id),
            "cycle_label": str(review.cycle_label),
            "bundle_item_count": len(payload.get("next_cycle_requirement_bundle") or []),
            "recommendation_count": len(payload.get("next_cycle_recommendations") or []),
            "incident_count": len(payload.get("incidents") or []),
            "human_gate_hotspot_count": len(payload.get("human_gate_hotspots") or []),
            "automation_candidate_count": len(payload.get("automation_candidates") or []),
            "workflow_rituals": rituals,
            "weekly_coo_review_package": {
                "title": str(operator_package.get("title") or "Operator Review Package"),
                "decision_count": len(operator_package.get("decisions") or []),
                "recommended_bundle_item_keys": list(operator_package.get("recommended_bundle_item_keys") or []),
                "summary_markdown": str(operator_package.get("summary_markdown") or ""),
            },
        }
    else:
        raise ValueError("Unsupported recurring workflow")

    row.last_run_at = utcnow()
    row.last_result_json = _json_dumps(result)
    db.commit()
    db.refresh(row)
    return {
        "workflow_key": str(row.workflow_key),
        "status": "completed",
        "run_started_at": row.last_run_at,
        "result": result,
    }
