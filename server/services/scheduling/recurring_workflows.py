"""Recurring COO workflow registry and runnable skeletons."""
from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server import config
from server.database import (
    BlackboardSnapshotRow,
    HumanGateRequestRow,
    NotificationEventRow,
    NotificationFingerprintRow,
    RecurringWorkflowRow,
    RecurringWorkflowRunRow,
    DeploymentRecordRow,
    ReleaseRecordRow,
    RequirementRow,
    WorkflowArtifactRow,
    WorkflowRunRow,
    utcnow,
)
from server.services.bugs.log_sweep import run_bug_log_sweep
from server.services.reviews.company_review import (
    company_review_to_dict,
    latest_company_operating_review,
    refresh_company_operating_review,
)
from server.services.signals.incidents import list_open_incidents
from server.services.signals.optimization_signals import list_optimization_signals
from server.services.requirements.family import cleanup_requirement_families
from server.services.requirements.sources import intake_requirement_sources
from server.services.runtime.alerting import build_ops_url, deliver_policy_notification
from server.services.scheduling.locks import acquire_scheduler_lock, release_scheduler_lock, scheduler_lock_snapshot
from server.services.forum_feedback import run_forum_feedback_sweep
from server.services.releases.service import sync_release_pr_statuses
from server.services.releases.tasks import sync_release_task_deployment_statuses
from server.services.social.publishing import (
    run_x_social_daily_content_planner,
    run_x_social_reply_candidate_sweep,
    run_x_social_repost_candidate_sweep,
    run_x_social_trend_radar_sweep,
)
from server.services.planning.product_opportunities import run_product_planning_sweep


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
            return _ensure_utc(value).isoformat() if _ensure_utc(value) else None
        return str(value)

    return json.dumps(payload, ensure_ascii=False, default=_default)

def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def _operator_zone() -> ZoneInfo:
    try:
        return ZoneInfo(config.OPERATOR_TIMEZONE)
    except Exception:
        return ZoneInfo("UTC")

BUILTIN_RECURRING_WORKFLOWS: list[dict[str, Any]] = [
    {
        "workflow_key": "bug_log_sweep",
        "display_name": "Bug Log Sweep",
        "description": "Sweep runtime logs and workflow incidents into bug backlog records, then auto-materialize high-value bugs.",
        "trigger_type": "scheduled",
        "owner_role": "runtime_reliability_engineer",
        "schedule": {"cadence": "interval", "interval_minutes": config.BUG_LOG_SWEEP_INTERVAL_MINUTES},
        "input_query": {"sources": ["runtime_log_error", "workflow_incident"]},
        "output_action": {"kind": "update_bug_backlog", "auto_materialize_high_value_bugs": True},
        "escalation_rule": {"on_new_critical_bug": "notify_portfolio_operator"},
        "validation_signal": {"success_metric": "materialized_requirement_ids"},
    },
    {
        "workflow_key": "morning_intake_sweep",
        "display_name": "Morning Intake Sweep",
        "description": "Refresh intake sources and create high-confidence backlog candidates.",
        "trigger_type": "scheduled",
        "owner_role": "ops_intake_manager",
        "schedule": {"cadence": "daily", "window": "morning", "suggested_local_time": "09:00"},
        "input_query": {"sources": ["optimization_signal", "company_review_bundle", "automation_candidate", "bug_intake"], "refresh": True},
        "output_action": {"kind": "create_requirements", "auto_start": False, "max_created": 2},
        "escalation_rule": {"on_failure": "notify_portfolio_operator", "on_empty": "no_op"},
        "validation_signal": {"success_metric": "created_requirement_ids", "min_expected": 0},
    },
    {
        "workflow_key": "goal_planner_sweep",
        "display_name": "Goal Planner Sweep",
        "description": "Evaluate the active Operating Manifest and create Requirement Candidates for active goals.",
        "trigger_type": "scheduled",
        "owner_role": "portfolio_planner",
        "schedule": {"cadence": "daily", "window": "morning", "suggested_local_time": "09:00"},
        "input_query": {"active_manifest": True, "goal_lifecycle": ["active"]},
        "output_action": {"kind": "create_requirement_candidates", "auto_materialize": False},
        "escalation_rule": {"on_failure": "notify_portfolio_operator", "on_empty": "no_op"},
        "validation_signal": {"success_metric": "created_candidate_ids", "min_expected": 0},
    },
    {"workflow_key": "product_planning_sweep", "display_name": "Product Planning Sweep", "description": "Surface product gaps and goal proposals without creating official goals or starting workflows.", "trigger_type": "scheduled", "owner_role": "product_planner", "schedule": {"cadence": "daily", "suggested_local_time": "09:15"}, "input_query": {"sources": ["active_manifest", "release_records", "bugs", "social_metrics", "docs_gaps"]}, "output_action": {"kind": "create_product_opportunities", "auto_create_goal": False, "auto_start_workflow": False}, "escalation_rule": {"on_failure": "notify_portfolio_operator", "on_empty": "no_op"}, "validation_signal": {"success_metric": "created_opportunity_ids", "min_expected": 0}},
    {
        "workflow_key": "forum_feedback_sweep",
        "display_name": "Forum Feedback Sweep",
        "description": "Pull unreplied forum posts from gateway-admin, classify them, create bug candidates when needed, and push reply drafts back for human review.",
        "trigger_type": "scheduled",
        "owner_role": "support_triage_agent",
        "schedule": {"cadence": "hourly", "interval_hours": 1},
        "input_query": {"source": "gateway_admin_forum_response_tasks", "status": ["awaiting_response", "draft_ready"]},
        "output_action": {"kind": "push_forum_reply_suggestions", "auto_reply": False, "create_bug_candidates": True},
        "escalation_rule": {"on_high_risk": "candidate_human_review", "on_push_failure": "notify_portfolio_operator"},
        "validation_signal": {"success_metric": "pushed_task_ids", "min_expected": 0},
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
    {
        "workflow_key": "approval_sweep",
        "display_name": "Approval Sweep",
        "description": "Re-evaluate pending requirement approvals, auto-approve low-risk work, and summarize stale approval backlog.",
        "trigger_type": "scheduled",
        "owner_role": "portfolio_operator",
        "schedule": {"cadence": "hourly", "interval_hours": 1},
        "input_query": {"status": ["awaiting_operator"]},
        "output_action": {"kind": "refresh_workflow_human_gates", "auto_approve": False},
        "escalation_rule": {"on_stale_backlog": "notify_portfolio_operator"},
        "validation_signal": {"success_metric": "auto_approved_requirement_ids"},
    },
    {
        "workflow_key": "requirement_family_cleanup_sweep",
        "display_name": "Requirement Family Cleanup Sweep",
        "description": "Archive duplicate validation experiment requirements and surface merge recommendations for repeated active families.",
        "trigger_type": "scheduled",
        "owner_role": "portfolio_operator",
        "schedule": {"cadence": "daily", "window": "evening", "suggested_local_time": "20:00"},
        "input_query": {"status": ["draft", "ready", "paused", "blocked"], "family_cleanup": True},
        "output_action": {"kind": "cleanup_requirement_families", "archive_validation_experiments": True},
        "escalation_rule": {"on_duplicate_growth": "notify_portfolio_operator"},
        "validation_signal": {"success_metric": "archived_requirement_ids"},
    },
    {
        "workflow_key": "ci_status_sweep",
        "display_name": "CI Status Sweep",
        "description": "Close out marker-file final regression runs without blocking workflow workers.",
        "trigger_type": "scheduled",
        "owner_role": "runtime_reliability_engineer",
        "schedule": {"cadence": "interval", "interval_minutes": 1},
        "input_query": {"workflow_state": ["awaiting_ci", "processing_ci_result"], "ci_backend": "local_marker"},
        "output_action": {"kind": "advance_final_regression_results"},
        "escalation_rule": {"on_failed_ci": "awaiting_operator", "on_timeout": "awaiting_operator"},
        "validation_signal": {"success_metric": "processed_count"},
    },
    {
        "workflow_key": "release_pr_status_sweep",
        "display_name": "Release PR Status Sweep",
        "description": "Read GitHub PR state for open release records and update merged, closed, or missing PRs.",
        "trigger_type": "scheduled",
        "owner_role": "release_operator",
        "schedule": {"cadence": "interval", "interval_minutes": 30},
        "input_query": {"release_status": ["pr_opened", "pr_open", "ready_for_merge"], "has_pr": True},
        "output_action": {"kind": "sync_release_pr_status", "read_only_github": True},
        "escalation_rule": {"on_sync_failure": "notify_portfolio_operator"},
        "validation_signal": {"success_metric": "processed_count"},
    },
    {
        "workflow_key": "release_deployment_status_sweep",
        "display_name": "Release Deployment Status Sweep",
        "description": "Read GitHub Actions staging deployment runs and reconcile Release Tasks and Deployment Records.",
        "trigger_type": "scheduled",
        "owner_role": "release_operator",
        "schedule": {"cadence": "interval", "interval_minutes": 1},
        "input_query": {"deployment_status": ["requested", "running", "pending"], "trigger_source": "release_task"},
        "output_action": {"kind": "sync_release_deployment_status", "read_only_github": True},
        "escalation_rule": {"on_sync_failure": "notify_portfolio_operator"},
        "validation_signal": {"success_metric": "processed_count"},
    },
    {
        "workflow_key": "x_social_daily_content_planner",
        "display_name": "X Social Daily Content Planner",
        "description": "Hourly tick that creates at most one human-reviewed X official-account draft per operator-local day.",
        "trigger_type": "scheduled",
        "owner_role": "growth_lead",
        "schedule": {"cadence": "hourly", "interval_hours": 1},
        "input_query": {"platform": "x", "source_type": "daily_planner", "idempotency": "one_draft_per_local_day"},
        "output_action": {"kind": "create_social_draft", "auto_publish": False, "human_gate_required": True},
        "escalation_rule": {"on_generation_failure": "notify_portfolio_operator", "on_already_created": "no_op"},
        "validation_signal": {"success_metric": "created_post_id"},
    },
    {
        "workflow_key": "x_social_trend_radar_sweep",
        "display_name": "X Social Trend Radar Sweep",
        "description": "Read-only X trend/watchlist sweep for AI, agent, API, and payment topics with quality filtering.",
        "trigger_type": "scheduled",
        "owner_role": "growth_lead",
        "schedule": {"cadence": "interval", "interval_minutes": 240},
        "input_query": {"platform": "x", "sources": ["watchlist", "trend_items"], "read_only": True},
        "output_action": {"kind": "refresh_social_trend_radar", "external_actions": []},
        "escalation_rule": {"on_connector_missing": "diagnostic_only", "on_failure": "notify_portfolio_operator"},
        "validation_signal": {"success_metric": "retained_count"},
    },
    {
        "workflow_key": "x_social_repost_candidate_sweep",
        "display_name": "X Social Repost Candidate Sweep",
        "description": "Generate human-gated quote/repost candidates from high-quality X trend radar items.",
        "trigger_type": "scheduled",
        "owner_role": "growth_lead",
        "schedule": {"cadence": "interval", "interval_minutes": 720},
        "input_query": {"platform": "x", "trend_min_relevance_score": 0.75},
        "output_action": {"kind": "create_repost_candidates", "auto_repost": False, "human_gate_required": True},
        "escalation_rule": {"on_empty": "no_op", "on_failure": "notify_portfolio_operator"},
        "validation_signal": {"success_metric": "created_candidate_ids"},
    },
    {
        "workflow_key": "x_social_reply_candidate_sweep",
        "display_name": "X Social Reply Candidate Sweep",
        "description": "Generate one human-gated positive reply draft from real X repost candidates every 30 minutes.",
        "trigger_type": "scheduled",
        "owner_role": "growth_lead",
        "schedule": {"cadence": "interval", "interval_minutes": 30},
        "input_query": {"platform": "x", "source": "social_repost_candidates", "requires_source_url": True},
        "output_action": {"kind": "create_reply_draft", "auto_reply": False, "human_gate_required": True},
        "escalation_rule": {"on_empty": "no_op", "on_failure": "notify_portfolio_operator"},
        "validation_signal": {"success_metric": "created_reply_ids"},
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

    pending_gates = db.query(HumanGateRequestRow).filter(HumanGateRequestRow.status == "pending").all()
    gates_by_requirement: dict[int, list[HumanGateRequestRow]] = {}
    for gate in pending_gates:
        if gate.requirement_id is not None:
            gates_by_requirement.setdefault(int(gate.requirement_id), []).append(gate)

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
        pending = gates_by_requirement.get(requirement_id, [])

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
                        "action": "human_gate_reminder",
                        "requirement_id": requirement_id,
                        "title": str(requirement.title),
                        "reason": str(pending[0].gate_type or "pending_human_gate"),
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
    for gate in pending_gates:
        created = _ensure_utc(gate.created_at) or now
        if created.timestamp() > approval_cutoff:
            continue
        approval_reminders.append(
            {
                "human_gate_id": int(gate.id),
                "requirement_id": int(gate.requirement_id) if gate.requirement_id is not None else None,
                "gate_type": str(gate.gate_type),
                "reviewer": str(gate.decided_by or ""),
                "age_hours": round((now - created).total_seconds() / 3600, 2),
            }
        )
        if gate.requirement_id is not None:
            follow_up_actions.append(
                {
                    "action": "human_gate_reminder",
                    "requirement_id": int(gate.requirement_id),
                    "title": f"Human gate {gate.gate_type}",
                    "reason": str(gate.gate_type),
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
    return False


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
    artifact_types: list[str] = []
    delivery_payload: dict[str, Any] = {}
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
    updated = _ensure_utc(requirement.updated_at or requirement.created_at) or now
    payload = {
        "requirement_id": int(requirement.id),
        "title": str(requirement.title),
        "status": str(requirement.status or ""),
        "active_workflow_run_id": int(requirement.active_workflow_run_id) if requirement.active_workflow_run_id is not None else None,
        "recent_artifact_types": [],
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


def _next_run_at(row: RecurringWorkflowRow, *, now: datetime | None = None) -> datetime | None:
    schedule = _json_loads(row.schedule_json, {})
    current = _ensure_utc(now) or datetime.now(timezone.utc)
    last_run = _ensure_utc(row.last_run_at)
    cadence = str(schedule.get("cadence") or "").strip().lower()
    if cadence == "interval":
        minutes = max(1, int(schedule.get("interval_minutes") or config.BUG_LOG_SWEEP_INTERVAL_MINUTES))
        return (last_run or current) + timedelta(minutes=minutes)
    if cadence == "hourly":
        hours = max(1, int(schedule.get("interval_hours") or 1))
        return (last_run or current) + timedelta(hours=hours)
    if cadence == "daily":
        hour, minute = _parse_local_time(str(schedule.get("suggested_local_time") or "09:00"))
        local_current = current.astimezone(_operator_zone())
        candidate = local_current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_current:
            candidate = candidate + timedelta(days=1)
        return candidate.astimezone(timezone.utc)
    if cadence == "weekly":
        hour, minute = _parse_local_time(str(schedule.get("suggested_local_time") or "10:00"))
        day_token = str(schedule.get("day") or "MON").strip().upper()
        day_index = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}.get(day_token, 0)
        local_current = current.astimezone(_operator_zone())
        days_ahead = (day_index - local_current.weekday()) % 7
        candidate = (local_current + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_current:
            candidate = candidate + timedelta(days=7)
        return candidate.astimezone(timezone.utc)
    return None


def _parse_local_time(value: str) -> tuple[int, int]:
    raw = str(value or "").strip()
    try:
        hour_text, minute_text = raw.split(":", 1)
        return max(0, min(23, int(hour_text))), max(0, min(59, int(minute_text)))
    except Exception:
        return 9, 0


def _workflow_health_status(row: RecurringWorkflowRow, *, next_run_at: datetime | None, now: datetime | None = None) -> str:
    if str(row.status or "") != "active":
        return "paused"
    if str(_json_loads(row.last_result_json, {}).get("status") or "").lower() == "failed":
        return "failed"
    current = _ensure_utc(now) or datetime.now(timezone.utc)
    if next_run_at is not None and next_run_at <= current:
        return "due"
    return "healthy"


def recurring_workflow_to_dict(row: RecurringWorkflowRow) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    next_run_at = _next_run_at(row, now=now)
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
        "next_run_at": next_run_at,
        "is_due": bool(next_run_at is not None and next_run_at <= now),
        "health_status": _workflow_health_status(row, next_run_at=next_run_at, now=now),
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
    acceptance_candidates = (
        db.query(RequirementRow)
        .filter(RequirementRow.status.in_(["done", "paused", "blocked", "needs_revision"]))
        .order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc())
        .limit(max(1, min(int(acceptance_limit or 20), 200)))
        .all()
    )
    acceptance_result = {
        "scanned": len(acceptance_candidates),
        "candidates": [int(row.id) for row in acceptance_candidates],
        "dispatched_requirement_ids": [],
        "auto_dispatch": bool(auto_dispatch_acceptance),
        "note": "Legacy fixed-step acceptance dispatch is retired; declarative workflows own verification.",
    }
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


def _approval_sweep(db: Session) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(hours=4)
    pending_gates = db.query(HumanGateRequestRow).filter(HumanGateRequestRow.status == "pending").all()
    requirement_ids: set[int] = {int(row.requirement_id) for row in pending_gates if row.requirement_id is not None}
    stale_approval_request_ids: list[int] = []
    gate_type_counts: dict[str, int] = {}
    pending_items: list[dict[str, Any]] = []

    for pending_request in pending_gates:
        requirement_id = int(pending_request.requirement_id or 0)
        age_hours = 0.0
        created = _ensure_utc(pending_request.created_at) or now
        age_hours = round((now - created).total_seconds() / 3600, 2)
        if created <= stale_cutoff:
            stale_approval_request_ids.append(int(pending_request.id))
        gate_type = str(pending_request.gate_type or "human_gate")
        gate_type_counts[gate_type] = gate_type_counts.get(gate_type, 0) + 1
        requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first() if requirement_id else None

        pending_items.append(
            {
                "requirement_id": requirement_id,
                "workflow_run_id": int(pending_request.workflow_run_id) if pending_request.workflow_run_id is not None else None,
                "human_gate_id": int(pending_request.id),
                "title": str(getattr(requirement, "title", "") or f"Human gate #{int(pending_request.id)}"),
                "gate_type": gate_type,
                "needs_human_gate": True,
                "age_hours": age_hours,
            }
        )

    return {
        "scanned_requirement_ids": sorted(requirement_ids),
        "pending_count": len(pending_items),
        "auto_approved_requirement_ids": [],
        "stale_approval_request_ids": stale_approval_request_ids,
        "approval_source_counts": gate_type_counts,
        "pending_items": pending_items,
    }


def _requirement_family_cleanup_sweep(db: Session) -> dict[str, Any]:
    return cleanup_requirement_families(
        db,
        categories={"validation_experiment", "release_bottleneck", "approval_automation", "incident_recovery", "bug_fix"},
        archive_validation_experiments=True,
    )


def _workflow_blackboard(row: WorkflowRunRow) -> dict[str, Any]:
    payload = _json_loads(row.blackboard_json, {})
    return dict(payload) if isinstance(payload, dict) else {}


def _persist_workflow_blackboard(db: Session, row: WorkflowRunRow, blackboard: dict[str, Any]) -> None:
    row.blackboard_json = _json_dumps(blackboard)
    row.updated_at = utcnow()
    db.add(
        BlackboardSnapshotRow(
            workflow_run_id=int(row.id),
            state_key=str(row.current_state or ""),
            snapshot_json=row.blackboard_json,
        )
    )


def _read_marker_exit_code(path: str | None) -> int | None:
    if not path:
        return None
    marker = Path(path)
    if not marker.is_file():
        return None
    try:
        return int(marker.read_text(encoding="utf-8").strip())
    except Exception:
        return 125


def _parse_iso_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return _ensure_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except Exception:
        return None


def _bounded_log_tail(path: str | None, *, max_bytes: int = 8192, max_lines: int = 50) -> str:
    if not path:
        return ""
    log_path = Path(path)
    if not log_path.is_file():
        return ""
    try:
        with log_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            data = handle.read(max_bytes)
        text = data.decode("utf-8", errors="replace")
        return "\n".join(text.splitlines()[-max_lines:])
    except Exception as exc:
        return f"[CI LOG TAIL ERROR] {exc.__class__.__name__}: {str(exc)[:300]}"


def _ci_runner_marker(exit_code: int | None) -> str:
    if exit_code == 124:
        return "timeout"
    if exit_code == 125:
        return "error"
    return "none"


def _record_ci_evidence(
    db: Session,
    row: WorkflowRunRow,
    *,
    exit_code: int | None,
    log_tail: str,
    status: str,
) -> int:
    ci = _workflow_blackboard(row).get("ci")
    ci_payload = ci if isinstance(ci, dict) else {}
    artifact = WorkflowArtifactRow(
        workflow_run_id=int(row.id),
        artifact_type="workflow_command_result",
        state_key="awaiting_ci",
        atom_key="ci_status_sweep",
        content_summary=f"Final regression {status}",
        human_readable_body=log_tail,
        machine_readable_payload=_json_dumps(
            {
                "command": ci_payload.get("ci_command") or [],
                "cwd": str(config.PROJECT_ROOT),
                "exit_code": exit_code,
                "simulated": False,
                "ci_exit_code": exit_code,
                "ci_log_tail": log_tail,
                "ci_log_path": ci_payload.get("ci_log_path"),
                "ci_runner_marker": _ci_runner_marker(exit_code),
            }
        ),
    )
    db.add(artifact)
    db.flush()
    return int(artifact.id)


def _ensure_ci_human_gate(db: Session, row: WorkflowRunRow, *, reason: str) -> None:
    existing = (
        db.query(HumanGateRequestRow)
        .filter(
            HumanGateRequestRow.workflow_run_id == int(row.id),
            HumanGateRequestRow.state_key == "awaiting_operator",
            HumanGateRequestRow.status == "pending",
        )
        .first()
    )
    if existing is not None:
        return
    gate = HumanGateRequestRow(
        workflow_run_id=int(row.id),
        state_key="awaiting_operator",
        gate_type="ci_final_regression_failed",
        risk_level=str(row.risk_level or "normal"),
        status="pending",
        reason=reason,
        payload_json=_json_dumps(
            {
                "workflow_run_id": int(row.id),
                "workflow_key": str(row.workflow_key or ""),
                "current_state": "awaiting_operator",
                "reason": reason,
            }
        ),
    )
    db.add(gate)


def _mark_ci_failed(
    db: Session,
    row: WorkflowRunRow,
    *,
    exit_code: int | None,
    log_tail: str,
    resolution: str,
    reason: str,
) -> None:
    blackboard = _workflow_blackboard(row)
    ci = dict(blackboard.get("ci") or {})
    artifact_id = _record_ci_evidence(db, row, exit_code=exit_code, log_tail=log_tail, status="failed")
    ci.update(
        {
            "status": "failed",
            "ci_exit_code": exit_code,
            "ci_log_tail": log_tail,
            "ci_runner_marker": _ci_runner_marker(exit_code),
            "ci_evidence_artifact_id": artifact_id,
            "completed_at": utcnow().isoformat(),
        }
    )
    blackboard["ci"] = ci
    blackboard["final_regression"] = dict(ci)
    blackboard["current_state"] = "awaiting_operator"
    row.current_state = "awaiting_operator"
    row.status = "awaiting_operator"
    row.resolution = resolution
    row.completed_at = utcnow()
    if row.requirement is not None:
        row.requirement.workflow_state = "awaiting_operator"
        row.requirement.status = "blocked"
        row.requirement.phase = "blocked"
        row.requirement.attention_reason = resolution
    _ensure_ci_human_gate(db, row, reason=reason)
    _persist_workflow_blackboard(db, row, blackboard)


def _resume_ci_passed_workflow(db: Session, row: WorkflowRunRow, *, artifact_id: int) -> None:
    from server.services.workflows.declarative import (
        _mark_requirement_for_run_decision,
        built_in_workflow_specs,
        default_atom_registry,
        run_workflow_state_machine,
    )

    blackboard = _workflow_blackboard(row)
    ci = dict(blackboard.get("ci") or {})
    ci.update(
        {
            "status": "passed",
            "ci_exit_code": 0,
            "ci_runner_marker": "none",
            "ci_evidence_artifact_id": artifact_id,
            "completed_at": utcnow().isoformat(),
        }
    )
    blackboard["ci"] = ci
    blackboard["final_regression"] = dict(ci)
    blackboard["current_state"] = "open_pr"
    row.current_state = "open_pr"
    row.status = "running"
    row.resolution = "ci_passed"
    row.completed_at = None
    _persist_workflow_blackboard(db, row, blackboard)
    db.flush()
    spec = built_in_workflow_specs()[str(row.workflow_key)]
    run_workflow_state_machine(db, workflow_run=row, spec=spec, registry=default_atom_registry(), initial_blackboard=blackboard)
    _mark_requirement_for_run_decision(row, status=str(row.status or ""))


def _workflow_stale_threshold_seconds(row: WorkflowRunRow) -> int:
    if str(row.workflow_key or "") == "agent_self_repair":
        return int(config.WORKFLOW_RUNNER_STALE_AGENT_SELF_REPAIR_SECONDS)
    return int(config.WORKFLOW_RUNNER_STALE_DEFAULT_SECONDS)


def _runner_stale_sweep(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    current = _ensure_utc(now) or datetime.now(timezone.utc)
    scanned_count = 0
    stale_ids: list[int] = []
    notified_count = 0
    rows = db.query(WorkflowRunRow).filter(WorkflowRunRow.status == "running").order_by(WorkflowRunRow.id.asc()).all()
    for row in rows:
        scanned_count += 1
        updated = _ensure_utc(row.updated_at or row.created_at) or current
        threshold_seconds = _workflow_stale_threshold_seconds(row)
        stale_seconds = max(0, int((current - updated).total_seconds()))
        if stale_seconds <= threshold_seconds:
            continue
        stale_ids.append(int(row.id))
        requirement = getattr(row, "requirement", None)
        service_name = (
            str(getattr(requirement, "project_display_name", "") or "").strip()
            or str(getattr(requirement, "project_key", "") or "").strip()
            or "Synapse Ops"
        )
        delivery = deliver_policy_notification(
            db,
            event_type="runner_stale",
            object_type="workflow_run",
            object_key=str(int(row.id)),
            service_name=service_name,
            severity="high",
            risk_level=str(row.risk_level or "high"),
            status="stale",
            workflow_key=str(row.workflow_key or ""),
            current_state=str(row.current_state or ""),
            summary=(
                f"Workflow #{int(row.id)} has been running without updates for {stale_seconds}s "
                f"(threshold {threshold_seconds}s)."
            ),
            next_action="Open the workflow evidence and decide whether to recover, retry, or route to human operator.",
            actor_or_source="ci_status_sweep",
            occurred_at=current,
            object_refs={
                "requirement_id": int(row.requirement_id) if row.requirement_id is not None else None,
                "workflow_run_id": int(row.id),
                "workflow_key": row.workflow_key,
                "current_state": row.current_state,
                "root_cause_kind": "runner_stale",
                "last_updated_at": updated.isoformat(),
                "stale_seconds": stale_seconds,
                "stale_threshold_seconds": threshold_seconds,
            },
            links={
                "工作流": build_ops_url(f"/workflows/{int(row.id)}") or "",
                "证据": build_ops_url(f"/workflows/{int(row.id)}?tab=evidence") or "",
                "门禁": build_ops_url(f"/workflows/{int(row.id)}?tab=gates") or "",
                "需求": build_ops_url(f"/requirements/{int(row.requirement_id)}") or "" if row.requirement_id is not None else "",
            },
            extra_fields={
                "title": f"P1｜Workflow #{int(row.id)} stale: no runner progress",
                "root_cause_kind": "runner_stale",
                "root_cause": f"No workflow runner progress since {updated.isoformat()} UTC.",
                "error_excerpt": f"Last state `{row.current_state}` has not updated for {stale_seconds}s.",
            },
        )
        if delivery is not None:
            notified_count += 1
    db.flush()
    return {
        "scanned_running_workflow_count": scanned_count,
        "stale_workflow_run_ids": stale_ids,
        "runner_stale_notified_count": notified_count,
    }


def _ci_status_sweep(
    db: Session,
    *,
    runtime_cap_seconds: int | None = None,
    stale_lock_seconds: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    cap_seconds = max(1, int(runtime_cap_seconds or config.CI_STATUS_SWEEP_RUNTIME_CAP_SECONDS))
    stale_seconds = max(cap_seconds + 1, int(stale_lock_seconds or config.CI_STATUS_SWEEP_STALE_LOCK_SECONDS))
    current = _ensure_utc(now) or datetime.now(timezone.utc)
    stale_runner = _runner_stale_sweep(db, now=current)
    stale_cutoff = current - timedelta(seconds=stale_seconds)
    recovered = (
        db.query(WorkflowRunRow)
        .filter(
            WorkflowRunRow.current_state == "processing_ci_result",
            WorkflowRunRow.updated_at < stale_cutoff,
        )
        .update(
            {
                WorkflowRunRow.current_state: "awaiting_ci",
                WorkflowRunRow.status: "awaiting_ci",
                WorkflowRunRow.updated_at: utcnow(),
            },
            synchronize_session=False,
        )
    )
    db.commit()

    processed_count = 0
    cap_reached = False
    candidate_ids = [
        int(item.id)
        for item in db.query(WorkflowRunRow.id)
        .filter(WorkflowRunRow.current_state == "awaiting_ci")
        .order_by(WorkflowRunRow.id.asc())
        .all()
    ]

    for workflow_run_id in candidate_ids:
        if time.monotonic() - started >= cap_seconds:
            cap_reached = True
            break
        claimed = (
            db.query(WorkflowRunRow)
            .filter(WorkflowRunRow.id == workflow_run_id, WorkflowRunRow.current_state == "awaiting_ci")
            .update({WorkflowRunRow.current_state: "processing_ci_result", WorkflowRunRow.updated_at: utcnow()}, synchronize_session=False)
        )
        db.commit()
        if int(claimed or 0) != 1:
            continue
        # Bulk updates do not refresh ORM instances already present in the
        # session. Expire before reading blackboard_json so CI retries use the
        # latest marker paths, not stale failed markers from the previous run.
        db.expire_all()
        row = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == workflow_run_id).one()
        blackboard = _workflow_blackboard(row)
        ci = dict(blackboard.get("ci") or {})
        exit_code = _read_marker_exit_code(str(ci.get("ci_exit_code_path") or ""))
        timeout_at = _parse_iso_datetime(ci.get("ci_timeout_at"))
        current = datetime.now(timezone.utc)
        if exit_code is None and (timeout_at is None or current < timeout_at):
            row.current_state = "awaiting_ci"
            row.status = "awaiting_ci"
            row.updated_at = utcnow()
            db.commit()
            continue
        processed_count += 1
        if exit_code is None:
            exit_code = 124
            log_tail = _bounded_log_tail(str(ci.get("ci_log_path") or ""))
            _mark_ci_failed(
                db,
                row,
                exit_code=exit_code,
                log_tail=log_tail,
                resolution="ci_timeout_needs_human",
                reason="Final regression timed out before writing an exit marker.",
            )
            db.commit()
            continue
        if int(exit_code) == 0:
            artifact_id = _record_ci_evidence(db, row, exit_code=0, log_tail="", status="passed")
            _resume_ci_passed_workflow(db, row, artifact_id=artifact_id)
            db.commit()
            continue
        log_tail = _bounded_log_tail(str(ci.get("ci_log_path") or ""))
        resolution = "ci_runner_failed_needs_human" if int(exit_code) == 125 else "ci_timeout_needs_human" if int(exit_code) == 124 else "ci_failed_needs_human"
        _mark_ci_failed(
            db,
            row,
            exit_code=int(exit_code),
            log_tail=log_tail,
            resolution=resolution,
            reason=f"Final regression failed with exit code {int(exit_code)}.",
        )
        db.commit()

    remaining_count = db.query(WorkflowRunRow).filter(WorkflowRunRow.current_state == "awaiting_ci").count()
    return {
        "processed_count": processed_count,
        "remaining_count": int(remaining_count),
        "sweep_runtime_cap_seconds": cap_seconds,
        "sweep_runtime_cap_reached": cap_reached,
        "stale_processing_locks_recovered": int(recovered or 0),
        "stale_lock_threshold_seconds": stale_seconds,
        "runner_stale": stale_runner,
    }


def run_recurring_workflow(
    db: Session,
    *,
    workflow_key: str,
    dry_run: bool = False,
    triggered_by: str = "operator",
    auto_start: bool = False,
    intake_min_score: float = 60.0,
    intake_max_created: int = 2,
    acceptance_limit: int = 20,
    auto_dispatch_acceptance: bool = False,
) -> dict[str, Any]:
    row = get_recurring_workflow(db, workflow_key)
    if str(row.status) != "active":
        raise ValueError("Recurring workflow is not active")
    params = {
        "dry_run": bool(dry_run),
        "auto_start": bool(auto_start),
        "intake_min_score": float(intake_min_score),
        "intake_max_created": int(intake_max_created),
        "acceptance_limit": int(acceptance_limit),
        "auto_dispatch_acceptance": bool(auto_dispatch_acceptance),
    }
    started_at = utcnow()
    run_row = RecurringWorkflowRunRow(
        workflow_key=str(row.workflow_key),
        status="running",
        triggered_by=str(triggered_by or "operator"),
        dry_run=bool(dry_run),
        params_json=_json_dumps(params),
        started_at=started_at,
    )
    db.add(run_row)
    db.flush()
    lock_key = f"scheduler:{workflow_key}"
    lock_owner_id = f"{socket.gethostname()}:{os.getpid()}:{workflow_key}:{int(run_row.id)}"
    lock_acquired = False
    if workflow_key == "bug_log_sweep":
        ttl_seconds = max(int(config.BUG_LOG_SWEEP_INTERVAL_MINUTES) * 60, 300)
        lock = acquire_scheduler_lock(
            db,
            lock_key=lock_key,
            owner_id=lock_owner_id,
            ttl_seconds=ttl_seconds,
            metadata={"workflow_key": workflow_key, "run_id": int(run_row.id), "triggered_by": triggered_by},
        )
        if lock is None:
            completed_at = utcnow()
            result = {
                "status": "skipped_locked",
                "reason": "bug_log_sweep is already running under scheduler lock",
                "lock": scheduler_lock_snapshot(db, lock_key),
            }
            run_row.status = "skipped_locked"
            run_row.result_json = _json_dumps(result)
            run_row.completed_at = completed_at
            run_row.duration_ms = _duration_ms(started_at, completed_at)
            db.commit()
            db.refresh(run_row)
            return {
                "workflow_key": str(row.workflow_key),
                "status": "skipped_locked",
                "run_started_at": run_row.started_at,
                "run_id": int(run_row.id),
                "result": result,
            }
        lock_acquired = True
    try:
        result = _execute_recurring_workflow(
            db,
            row=row,
            workflow_key=workflow_key,
            dry_run=dry_run,
            auto_start=auto_start,
            intake_min_score=intake_min_score,
            intake_max_created=intake_max_created,
            acceptance_limit=acceptance_limit,
            auto_dispatch_acceptance=auto_dispatch_acceptance,
        )
    except Exception as exc:
        completed_at = utcnow()
        if lock_acquired:
            release_scheduler_lock(db, lock_key=lock_key, owner_id=lock_owner_id)
        run_row.status = "failed"
        run_row.error_excerpt = str(exc)[:1000]
        run_row.completed_at = completed_at
        run_row.duration_ms = _duration_ms(started_at, completed_at)
        db.commit()
        raise

    completed_at = utcnow()
    if lock_acquired:
        release_scheduler_lock(db, lock_key=lock_key, owner_id=lock_owner_id)
    row.last_run_at = completed_at
    row.last_result_json = _json_dumps(result)
    run_row.status = "succeeded"
    run_row.result_json = _json_dumps(result)
    run_row.completed_at = completed_at
    run_row.duration_ms = _duration_ms(started_at, completed_at)
    db.commit()
    db.refresh(row)
    db.refresh(run_row)
    return {
        "workflow_key": str(row.workflow_key),
        "status": "completed",
        "run_started_at": run_row.started_at,
        "run_id": int(run_row.id),
        "result": result,
    }


def _execute_recurring_workflow(
    db: Session,
    *,
    row: RecurringWorkflowRow,
    workflow_key: str,
    dry_run: bool,
    auto_start: bool,
    intake_min_score: float,
    intake_max_created: int,
    acceptance_limit: int,
    auto_dispatch_acceptance: bool,
) -> dict[str, Any]:
    if dry_run:
        if workflow_key == "goal_planner_sweep":
            from server.services.planning.lifecycle import run_planner_sweep, sweep_to_dict

            sweep = run_planner_sweep(db, dry_run=True, triggered_by="scheduler_dry_run")
            return sweep_to_dict(sweep)
        if workflow_key == "product_planning_sweep":
            return run_product_planning_sweep(db, dry_run=True)
        if workflow_key == "forum_feedback_sweep":
            return run_forum_feedback_sweep(db, dry_run=True)
        if workflow_key == "ci_status_sweep":
            awaiting_count = db.query(WorkflowRunRow).filter(WorkflowRunRow.current_state == "awaiting_ci").count()
            processing_count = db.query(WorkflowRunRow).filter(WorkflowRunRow.current_state == "processing_ci_result").count()
            return {
                "dry_run": True,
                "workflow_key": workflow_key,
                "awaiting_ci_count": int(awaiting_count),
                "processing_ci_result_count": int(processing_count),
                "sweep_runtime_cap_seconds": int(config.CI_STATUS_SWEEP_RUNTIME_CAP_SECONDS),
            }
        if workflow_key == "release_pr_status_sweep":
            pending_count = (
                db.query(ReleaseRecordRow)
                .filter(
                    or_(
                        ReleaseRecordRow.pr_url.isnot(None),
                        ReleaseRecordRow.pr_number.isnot(None),
                    ),
                    or_(
                        ReleaseRecordRow.status.in_(("pr_opened", "ready_for_merge")),
                        ReleaseRecordRow.delivery_state.in_(("pr_open", "ready_for_merge")),
                    ),
                )
                .count()
            )
            return {
                "dry_run": True,
                "workflow_key": workflow_key,
                "candidate_release_count": int(pending_count),
                "max_records": 50,
                "read_only_github": True,
            }
        if workflow_key == "release_deployment_status_sweep":
            pending_count = (
                db.query(DeploymentRecordRow)
                .filter(
                    DeploymentRecordRow.trigger_source == "release_task",
                    DeploymentRecordRow.status.in_(("requested", "running", "pending")),
                )
                .count()
            )
            return {
                "dry_run": True,
                "workflow_key": workflow_key,
                "candidate_deployment_count": int(pending_count),
                "max_records": 50,
                "read_only_github": True,
            }
        if workflow_key == "x_social_daily_content_planner":
            return {
                "dry_run": True,
                "workflow_key": workflow_key,
                "platform": "x",
                "cadence": "hourly",
                "idempotency": "one_draft_per_operator_local_day",
                "auto_publish": False,
                "human_gate_required": True,
            }
        if workflow_key == "x_social_trend_radar_sweep":
            return {
                "dry_run": True,
                "workflow_key": workflow_key,
                "platform": "x",
                "read_only": True,
                "min_relevance_score": 0.70,
                "external_actions": [],
            }
        if workflow_key == "x_social_repost_candidate_sweep":
            return {
                "dry_run": True,
                "workflow_key": workflow_key,
                "platform": "x",
                "auto_repost": False,
                "human_gate_required": True,
                "min_relevance_score": 0.75,
            }
        if workflow_key == "x_social_reply_candidate_sweep":
            return {
                "dry_run": True,
                "workflow_key": workflow_key,
                "platform": "x",
                "cadence": "every_30_minutes",
                "source": "social_repost_candidates",
                "max_created_per_run": 1,
                "auto_reply": False,
                "human_gate_required": True,
            }
        return {
            "dry_run": True,
            "workflow_key": workflow_key,
            "owner_role": row.owner_role,
            "schedule": _json_loads(row.schedule_json, {}),
            "output_action": _json_loads(row.output_action_json, {}),
        }
    if workflow_key == "morning_intake_sweep":
        return _morning_intake_sweep(
            db,
            auto_start=auto_start,
            intake_min_score=intake_min_score,
            intake_max_created=intake_max_created,
        )
    if workflow_key == "goal_planner_sweep":
        from server.services.planning.lifecycle import run_planner_sweep, sweep_to_dict

        sweep = run_planner_sweep(db, dry_run=False, triggered_by="scheduler")
        return sweep_to_dict(sweep)
    if workflow_key == "product_planning_sweep":
        return run_product_planning_sweep(db, dry_run=False)
    if workflow_key == "forum_feedback_sweep":
        return run_forum_feedback_sweep(db, dry_run=False)
    if workflow_key == "dispatcher_loop":
        follow_through = _dispatcher_follow_through(db)
        return {
            "started_ids": [],
            "created_requirement_ids": [],
            "preempted_ids": [],
            "rebalanced_ids": [],
            "skipped": ["Legacy fixed-step dispatcher is retired; declarative workflow runs are started from requirement workflow APIs."],
            **follow_through,
        }
    if workflow_key == "bug_log_sweep":
        sweep_result = run_bug_log_sweep(db)
        materialize_result = intake_requirement_sources(
            db,
            source_key="bug_intake",
            refresh=False,
            auto_start=auto_start,
            min_score=max(float(intake_min_score), 70.0),
            max_created=max(1, min(int(intake_max_created or 2), 5)),
        )
        return {
            **sweep_result,
            "auto_materialize_enabled": True,
            "materialized_requirement_ids": list(materialize_result.get("created_requirement_ids") or []),
            "reused_requirement_ids": list(materialize_result.get("reused_requirement_ids") or []),
            "skipped_materializations": list(materialize_result.get("skipped") or []),
            "materialization_items": list(materialize_result.get("items") or []),
            "requires_operator_review": bool(materialize_result.get("created_requirement_ids") or materialize_result.get("reused_requirement_ids")),
        }
    if workflow_key == "closeout_and_compact_sweep":
        return _closeout_and_compact_sweep(
            db,
            acceptance_limit=acceptance_limit,
            auto_dispatch_acceptance=auto_dispatch_acceptance,
        )
    if workflow_key == "approval_sweep":
        return _approval_sweep(db)
    if workflow_key == "requirement_family_cleanup_sweep":
        return _requirement_family_cleanup_sweep(db)
    if workflow_key == "ci_status_sweep":
        return _ci_status_sweep(db)
    if workflow_key == "release_pr_status_sweep":
        return sync_release_pr_statuses(db, max_records=50, per_record_sleep_seconds=1.0)
    if workflow_key == "release_deployment_status_sweep":
        return sync_release_task_deployment_statuses(db, max_records=50)
    if workflow_key == "x_social_daily_content_planner":
        return run_x_social_daily_content_planner(db)
    if workflow_key == "x_social_trend_radar_sweep":
        return run_x_social_trend_radar_sweep(db)
    if workflow_key == "x_social_repost_candidate_sweep":
        return run_x_social_repost_candidate_sweep(db)
    if workflow_key == "x_social_reply_candidate_sweep":
        return run_x_social_reply_candidate_sweep(db)
    if workflow_key == "weekly_operating_review":
        review = refresh_company_operating_review(db)
        payload = company_review_to_dict(review)
        rituals = dict((payload.get("source_snapshot") or {}).get("workflow_rituals") or {})
        operator_package = dict(payload.get("operator_review_package") or {})
        return {
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
                "autonomous_decision_count": int(operator_package.get("autonomous_decision_count") or 0),
                "recommended_bundle_item_keys": list(operator_package.get("recommended_bundle_item_keys") or []),
                "summary_markdown": str(operator_package.get("summary_markdown") or ""),
            },
            "autonomous_coo_posture": dict(payload.get("autonomous_coo_posture") or {}),
        }
    raise ValueError("Unsupported recurring workflow")


def _duration_ms(started_at: datetime, completed_at: datetime) -> int:
    return max(0, int((completed_at - started_at).total_seconds() * 1000))


def recurring_workflow_run_to_dict(row: RecurringWorkflowRunRow) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "workflow_key": str(row.workflow_key),
        "status": str(row.status),
        "triggered_by": str(row.triggered_by or "operator"),
        "dry_run": bool(row.dry_run),
        "params": _json_loads(row.params_json, {}),
        "result": _json_loads(row.result_json, {}),
        "error_excerpt": str(row.error_excerpt or "").strip() or None,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "duration_ms": int(row.duration_ms or 0),
    }


def list_recurring_workflow_runs(db: Session, workflow_key: str, *, limit: int = 50) -> list[RecurringWorkflowRunRow]:
    get_recurring_workflow(db, workflow_key)
    return (
        db.query(RecurringWorkflowRunRow)
        .filter(RecurringWorkflowRunRow.workflow_key == workflow_key)
        .order_by(RecurringWorkflowRunRow.id.desc())
        .limit(max(1, min(200, int(limit or 50))))
        .all()
    )


def recurring_workflow_health(
    db: Session,
    *,
    bug_scheduler_status: dict[str, Any] | None = None,
    goal_planner_scheduler_status: dict[str, Any] | None = None,
    ci_status_scheduler_status: dict[str, Any] | None = None,
    release_pr_status_scheduler_status: dict[str, Any] | None = None,
    release_deployment_status_scheduler_status: dict[str, Any] | None = None,
    x_social_scheduler_status: dict[str, Any] | None = None,
    notification_dispatcher_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = list_recurring_workflows(db)
    queued_count = db.query(NotificationEventRow).filter(NotificationEventRow.status == "queued").count()
    dead_letter_count = db.query(NotificationEventRow).filter(NotificationEventRow.status == "dead_letter").count()
    open_fingerprint_count = db.query(NotificationFingerprintRow).filter(NotificationFingerprintRow.status == "open").count()
    suppressed_fingerprint_count = (
        db.query(NotificationFingerprintRow)
        .filter(NotificationFingerprintRow.suppressed_count > 0)
        .count()
    )
    bug_status = bug_scheduler_status or {"enabled": bool(config.BUG_LOG_SWEEP_SCHEDULER_ENABLED), "running": False}
    bug_status = {**bug_status, "lock": scheduler_lock_snapshot(db, "scheduler:bug_log_sweep")}
    return {
        "bug_log_scheduler": bug_status,
        "goal_planner_scheduler": goal_planner_scheduler_status or {
            "enabled": bool(getattr(config, "GOAL_PLANNER_SWEEP_SCHEDULER_ENABLED", False)),
            "running": False,
        },
        "ci_status_scheduler": ci_status_scheduler_status or {
            "enabled": bool(getattr(config, "CI_STATUS_SWEEP_SCHEDULER_ENABLED", False)),
            "running": False,
        },
        "release_pr_status_scheduler": release_pr_status_scheduler_status or {
            "enabled": bool(getattr(config, "RELEASE_PR_STATUS_SWEEP_SCHEDULER_ENABLED", False)),
            "running": False,
        },
        "release_deployment_status_scheduler": release_deployment_status_scheduler_status or {
            "enabled": bool(getattr(config, "RELEASE_DEPLOYMENT_STATUS_SWEEP_SCHEDULER_ENABLED", False)),
            "running": False,
        },
        "x_social_scheduler": x_social_scheduler_status or {
            "enabled": bool(getattr(config, "X_SOCIAL_SWEEP_SCHEDULER_ENABLED", False)),
            "running": False,
        },
        "notification_dispatcher": {
            **(notification_dispatcher_status or {"enabled": bool(config.NOTIFICATION_DISPATCHER_ENABLED), "running": False}),
            "queued_count": int(queued_count),
            "dead_letter_count": int(dead_letter_count),
            "open_fingerprint_count": int(open_fingerprint_count),
            "suppressed_fingerprint_count": int(suppressed_fingerprint_count),
        },
        "recurring_registry": {
            "total_count": len(rows),
            "active_count": sum(1 for row in rows if str(row.status or "") == "active"),
            "due_count": sum(1 for row in rows if bool(recurring_workflow_to_dict(row).get("is_due"))),
        },
    }
