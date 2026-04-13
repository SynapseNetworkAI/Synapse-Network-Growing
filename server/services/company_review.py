"""Company-level operating review aggregation and persistence."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from collections import defaultdict

from server.database import ApprovalRequestRow, ArtifactRow, BugRecordRow, CompanyOperatingReviewRow, RecurringWorkflowRow, RequirementRow, TaskRow, WorkflowStepRow
from server.schemas import CompanyReviewBundleMaterializeResultOut, RequirementCreate
from server.services.incidents import list_open_incidents
from server.services.optimization_signals import list_optimization_signals, refresh_optimization_signals
from server.services.optimization_templates import build_template_instance, template_key_for_signal
from server.services.portfolio_scheduler import build_portfolio_schedule
from server.services.project_intelligence import build_project_catalog
from server.services.requirement_sources import normalize_requirement_intake_metadata
from server.services.workflow_orchestrator import create_requirement
from server.config import PROJECT_ROOT

logger = logging.getLogger("ops-dashboard.company_review")


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _json_dumps(value: Any) -> str:
    def _default(item: Any) -> Any:
        if isinstance(item, datetime):
            return _ensure_utc(item).isoformat() if _ensure_utc(item) else None
        return str(item)

    return json.dumps(value, ensure_ascii=False, default=_default)


def _cycle_label(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    iso = moment.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cycle_summary_markdown(
    portfolio_summary: dict[str, Any],
    bottlenecks: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> str:
    lead_bottleneck = bottlenecks[0]["title"] if bottlenecks else "No major blockers"
    lead_recommendation = recommendations[0]["title"] if recommendations else "No immediate recommendation"
    return (
        f"Cycle focus: {lead_bottleneck}.\n\n"
        f"Portfolio active requirements: {portfolio_summary['active_requirements']}, "
        f"open signals: {portfolio_summary['open_signals']}, "
        f"approval-required decisions: {portfolio_summary['approval_required_decisions']}.\n\n"
        f"Completion rate: {portfolio_summary['completion_rate']}%, "
        f"budget spent: {portfolio_summary['budget_spent_points']} pts, "
        f"prompt cache saved chars: {portfolio_summary['prompt_cache_saved_chars']}, "
        f"human gate hotspots: {portfolio_summary['human_gate_hotspots']}, "
        f"open bug pressure: {portfolio_summary['open_bug_pressure']}.\n\n"
        f"Recommended next move: {lead_recommendation}."
    )


def _requirement_target_paths(requirement: RequirementRow) -> list[str]:
    return [
        str(item).strip()
        for item in str(requirement.target_project_path or "").splitlines()
        if str(item).strip()
    ]


def _requirement_project_keys(
    requirement: RequirementRow,
    project_catalog: dict[str, dict[str, Any]],
) -> list[str]:
    target_paths = _requirement_target_paths(requirement)
    matches: list[str] = []
    for project in project_catalog.values():
        project_key = str(project.get("project_key") or "").strip()
        root_path = str(project.get("root_path") or "").strip()
        if not project_key or not root_path:
            continue
        if any(path == root_path or path.startswith(f"{root_path}/") for path in target_paths):
            matches.append(project_key)
    return list(dict.fromkeys(matches))


def _empty_runtime_metric_bucket() -> dict[str, Any]:
    return {
        "completed_requirements": 0,
        "budget_spent_points": 0,
        "tokens_used": 0,
        "prompt_cache_saved_chars": 0,
        "deduped_bindings": 0,
        "escalations": 0,
        "downgrades": 0,
        "tier_mix": {"mini": 0, "standard": 0, "max": 0},
    }


def _aggregate_runtime_metrics(
    db: Session,
    *,
    project_catalog: dict[str, dict[str, Any]],
    requirements: dict[int, RequirementRow],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    overall = _empty_runtime_metric_bucket()
    per_project: dict[str, dict[str, Any]] = defaultdict(_empty_runtime_metric_bucket)
    requirement_by_task_id: dict[int, RequirementRow] = {}

    scoped_requirements = [req for req in requirements.values() if str(req.status or "") != "deleted"]
    for requirement in scoped_requirements:
        if str(requirement.status or "") == "done":
            overall["completed_requirements"] += 1
        for project_key in _requirement_project_keys(requirement, project_catalog):
            if str(requirement.status or "") == "done":
                per_project[project_key]["completed_requirements"] += 1

    for step in db.query(WorkflowStepRow).filter(WorkflowStepRow.compatibility_task_id.isnot(None)).all():
        task_id = int(step.compatibility_task_id or 0)
        requirement = requirements.get(int(step.requirement_id or 0))
        if task_id > 0 and requirement is not None:
            requirement_by_task_id[task_id] = requirement

    for task in db.query(TaskRow).all():
        requirement = requirement_by_task_id.get(int(task.id or 0))
        if requirement is None:
            continue
        budget_cost = int(task.budget_cost_points or 0)
        tokens_used = int(task.tokens_used or 0)
        overall["budget_spent_points"] += budget_cost
        overall["tokens_used"] += tokens_used
        for project_key in _requirement_project_keys(requirement, project_catalog):
            per_project[project_key]["budget_spent_points"] += budget_cost
            per_project[project_key]["tokens_used"] += tokens_used

    for step in db.query(WorkflowStepRow).all():
        requirement = requirements.get(int(step.requirement_id or 0))
        if requirement is None:
            continue
        profile = _json_loads(getattr(step, "execution_profile_json", None), {})
        tier = str(profile.get("complexity_tier") or "standard").strip().lower() or "standard"
        if tier not in {"mini", "standard", "max"}:
            tier = "standard"
        overall["tier_mix"][tier] += 1
        for project_key in _requirement_project_keys(requirement, project_catalog):
            per_project[project_key]["tier_mix"][tier] += 1

    for artifact in db.query(ArtifactRow).filter(ArtifactRow.artifact_type == "prompt_cache_profile").all():
        requirement = requirements.get(int(artifact.requirement_id or 0))
        if requirement is None:
            continue
        payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
        saved_chars = int(payload.get("cached_chars_saved") or 0)
        deduped_bindings = int(payload.get("deduped_binding_count") or 0)
        overall["prompt_cache_saved_chars"] += saved_chars
        overall["deduped_bindings"] += deduped_bindings
        for project_key in _requirement_project_keys(requirement, project_catalog):
            per_project[project_key]["prompt_cache_saved_chars"] += saved_chars
            per_project[project_key]["deduped_bindings"] += deduped_bindings

    for artifact in db.query(ArtifactRow).filter(ArtifactRow.artifact_type == "runtime_adaptation").all():
        requirement = requirements.get(int(artifact.requirement_id or 0))
        if requirement is None:
            continue
        payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
        adaptation_type = str(payload.get("adaptation_type") or "").strip().lower()
        if adaptation_type == "escalation":
            overall["escalations"] += 1
        elif adaptation_type == "downgrade":
            overall["downgrades"] += 1
        else:
            continue
        for project_key in _requirement_project_keys(requirement, project_catalog):
            if adaptation_type == "escalation":
                per_project[project_key]["escalations"] += 1
            elif adaptation_type == "downgrade":
                per_project[project_key]["downgrades"] += 1

    return overall, dict(per_project)


def _project_display_for_keys(project_keys: list[str], project_catalog: dict[str, dict[str, Any]]) -> tuple[str | None, str | None]:
    normalized = [str(item).strip() for item in project_keys if str(item).strip()]
    if not normalized:
        return None, None
    if len(normalized) > 1:
        return "multi-project", "Multiple Projects"
    project_key = normalized[0]
    for project in project_catalog.values():
        if str(project.get("project_key") or "") == project_key:
            return project_key, str(project.get("display_name") or project_key)
    return project_key, project_key


def _bug_backlog_summary(
    db: Session,
    *,
    project_catalog: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = db.query(BugRecordRow).all()
    open_rows = [row for row in rows if str(getattr(row, "status", "") or "") == "open"]
    converted_rows = [row for row in rows if str(getattr(row, "status", "") or "") == "converted"]

    per_project: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "open_bug_count": 0,
            "critical_bug_count": 0,
            "converted_bug_count": 0,
            "recurring_bug_count": 0,
        }
    )
    recurring_items: list[dict[str, Any]] = []

    for row in open_rows:
        scorecard = _json_loads(getattr(row, "scorecard_json", None), {})
        total = float(scorecard.get("total") or 0.0)
        project_key = str(getattr(row, "project_key", "") or "").strip()
        project_display_name = None
        if project_key:
            project_display_name = next(
                (
                    str(project.get("display_name") or project_key)
                    for project in project_catalog.values()
                    if str(project.get("project_key") or "") == project_key
                ),
                project_key,
            )
        severity = str(getattr(row, "severity", "") or "normal").strip().lower()
        occurrence_count = int(getattr(row, "occurrence_count", 0) or 0)
        if project_key:
            per_project[project_key]["open_bug_count"] += 1
            if severity == "critical":
                per_project[project_key]["critical_bug_count"] += 1
            if occurrence_count >= 2:
                per_project[project_key]["recurring_bug_count"] += 1
        recurring_items.append(
            {
                "bug_id": int(row.id),
                "bug_key": str(row.bug_key),
                "title": str(row.title),
                "severity": severity,
                "project_key": project_key or None,
                "project_display_name": project_display_name,
                "fingerprint": str(getattr(row, "fingerprint", "") or ""),
                "occurrence_count": occurrence_count,
                "score_total": round(total, 1),
                "source_key": str(getattr(row, "source_key", "") or ""),
                "converted_requirement_id": int(row.converted_requirement_id) if row.converted_requirement_id is not None else None,
                "last_seen_at": (
                    _ensure_utc(getattr(row, "last_seen_at", None)).isoformat()
                    if _ensure_utc(getattr(row, "last_seen_at", None))
                    else None
                ),
            }
        )

    for row in converted_rows:
        project_key = str(getattr(row, "project_key", "") or "").strip()
        if project_key:
            per_project[project_key]["converted_bug_count"] += 1

    recurring_items.sort(
        key=lambda item: (
            _SEVERITY_RANK.get(str(item.get("severity") or "medium"), 99),
            -int(item.get("occurrence_count") or 0),
            -float(item.get("score_total") or 0.0),
            str(item.get("title") or ""),
        )
    )
    summary = {
        "open_bug_pressure": len(open_rows),
        "unresolved_critical_bugs": sum(1 for row in open_rows if str(getattr(row, "severity", "") or "").strip().lower() == "critical"),
        "bug_requirements_created": len(converted_rows),
        "recurring_bug_fingerprint_count": sum(1 for row in open_rows if int(getattr(row, "occurrence_count", 0) or 0) >= 2),
    }
    return summary, recurring_items[:8], dict(per_project)


def _cross_project_bug_recoveries(
    db: Session,
    *,
    project_catalog: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in db.query(BugRecordRow).all():
        metadata = _json_loads(getattr(row, "metadata_json", None), {})
        project_keys: list[str] = []
        primary_key = str(getattr(row, "project_key", "") or "").strip()
        if primary_key:
            project_keys.append(primary_key)
        if isinstance(metadata, dict):
            for item in list(metadata.get("affected_project_keys") or []):
                value = str(item or "").strip()
                if value and value not in project_keys:
                    project_keys.append(value)
        if len(project_keys) <= 1:
            continue
        project_display_names: list[str] = []
        for key in project_keys:
            display = next(
                (
                    str(project.get("display_name") or key)
                    for project in project_catalog.values()
                    if str(project.get("project_key") or "") == key
                ),
                key,
            )
            project_display_names.append(display)
        scorecard = _json_loads(getattr(row, "scorecard_json", None), {})
        status = str(getattr(row, "status", "") or "open")
        recovery_status = "requirement_created" if status == "converted" and row.converted_requirement_id is not None else ("recovery_open" if status == "open" else status)
        items.append(
            {
                "item_key": f"cross-project-bug:{int(row.id)}",
                "title": str(getattr(row, "title", "") or ""),
                "severity": str(getattr(row, "severity", "") or "medium"),
                "summary": (
                    f"Bug affects {len(project_keys)} projects: {', '.join(project_display_names)}. "
                    f"Occurrences: {int(getattr(row, 'occurrence_count', 0) or 0)}."
                ),
                "project_key": "multi-project",
                "project_display_name": "Multiple Projects",
                "recommendation": "Coordinate a cross-project remediation and validate the recovery path across all affected repositories.",
                "incident_family": "cross_project_bug_recovery",
                "incident_code": str(getattr(row, "fingerprint", "") or ""),
                "recovery_status": recovery_status,
                "requirement_id": int(row.converted_requirement_id) if row.converted_requirement_id is not None else None,
                "source_ref": f"bug-intake:{int(row.id)}",
                "affected_project_keys": project_keys,
                "affected_project_display_names": project_display_names,
                "score_total": round(float(scorecard.get("total") or 0.0), 1),
            }
        )
    items.sort(
        key=lambda item: (
            _SEVERITY_RANK.get(str(item.get("severity") or "medium"), 99),
            0 if str(item.get("recovery_status") or "") == "recovery_open" else 1,
            -len(list(item.get("affected_project_keys") or [])),
            str(item.get("title") or ""),
        )
    )
    return items[:6]


def _gate_recommendation(approval_type: str, approval_scope: str, *, step_type: str) -> tuple[str, str]:
    if approval_scope == "publish" or approval_type == "publish_manual_gate":
        return "publish_automation", "Stabilize delivery checks so more review-ready work can auto-promote without operator intervention."
    if approval_scope == "incident_recovery":
        return "incident_recovery_automation", "Automate incident diagnostics, recovery narrative, and retry readiness before escalating to the operator."
    if approval_type == "budget_review":
        return "budget_guardrail_tuning", "Tune model routing or budget caps so repeated budget reviews are handled automatically earlier in the loop."
    if approval_type == "stale_memory_review":
        return "context_refresh_automation", "Improve compaction, refresh cadence, or stale-memory recovery so this branch stops requiring manual review."
    if approval_scope == "max_tier":
        return "max_tier_branch_reduction", "Split or reroute work earlier so fewer branches escalate into max-tier human-gated execution."
    return "generic_gate_automation", f"Reduce repeated {step_type or approval_type} manual gate triggers with better routing or stronger automatic verification."


def _human_gate_hotspots(
    db: Session,
    *,
    project_catalog: dict[str, dict[str, Any]],
    requirements: dict[int, RequirementRow],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gate_buckets: dict[str, dict[str, Any]] = {}

    def _upsert_gate(
        *,
        gate_key: str,
        title: str,
        approval_type: str,
        approval_scope: str | None,
        step_type: str | None,
        project_key: str | None,
        project_display_name: str | None,
        status: str,
        summary: str,
    ) -> None:
        bucket = gate_buckets.setdefault(
            gate_key,
            {
                "gate_key": gate_key,
                "title": title,
                "approval_type": approval_type,
                "approval_scope": approval_scope,
                "step_type": step_type,
                "project_key": project_key,
                "project_display_name": project_display_name,
                "occurrence_count": 0,
                "pending_count": 0,
                "latest_status": status,
                "summary": summary,
            },
        )
        bucket["occurrence_count"] += 1
        if status == "pending":
            bucket["pending_count"] += 1
        bucket["latest_status"] = status

    steps_by_id = {
        int(step.id): step
        for step in db.query(WorkflowStepRow).all()
        if step.id is not None
    }

    for approval in db.query(ApprovalRequestRow).all():
        requirement = requirements.get(int(approval.requirement_id or 0))
        if requirement is None:
            continue
        step = steps_by_id.get(int(approval.step_id or 0))
        approval_policy = _json_loads(getattr(step, "approval_policy_json", None), {}) if step is not None else {}
        approval_scope = str(approval_policy.get("approval_scope") or "").strip() or None
        step_type = str(getattr(step, "step_type", "") or "").strip() or None
        project_key, project_display_name = _project_display_for_keys(
            _requirement_project_keys(requirement, project_catalog),
            project_catalog,
        )
        gate_key = "::".join(
            [
                str(approval.approval_type or ""),
                str(approval_scope or "unspecified"),
                str(step_type or "requirement"),
                str(project_key or "org-ops"),
            ]
        )
        _upsert_gate(
            gate_key=gate_key,
            title=f"{project_display_name or 'Org Ops'} {approval_scope or approval.approval_type}",
            approval_type=str(approval.approval_type or ""),
            approval_scope=approval_scope,
            step_type=step_type,
            project_key=project_key,
            project_display_name=project_display_name,
            status=str(approval.status or "pending"),
            summary=(
                f"{project_display_name or 'Org Ops'} triggered `{approval.approval_type}`"
                f" on `{step_type or 'requirement'}` with scope `{approval_scope or 'unspecified'}`."
            ),
        )

    for requirement in requirements.values():
        latest_delivery_state = db.query(ArtifactRow).filter(
            ArtifactRow.requirement_id == requirement.id,
            ArtifactRow.artifact_type == "delivery_state",
        ).order_by(ArtifactRow.id.desc()).first()
        if latest_delivery_state is None:
            continue
        payload = _json_loads(getattr(latest_delivery_state, "machine_readable_payload", None), {})
        if not isinstance(payload, dict):
            continue
        if str(payload.get("publish_status") or "") != "review_ready":
            continue
        if not bool(payload.get("requires_manual_approval")):
            continue
        project_key, project_display_name = _project_display_for_keys(
            _requirement_project_keys(requirement, project_catalog),
            project_catalog,
        )
        gate_key = f"publish_manual_gate::publish::{project_key or 'org-ops'}"
        _upsert_gate(
            gate_key=gate_key,
            title=f"{project_display_name or 'Org Ops'} publish gate",
            approval_type="publish_manual_gate",
            approval_scope="publish",
            step_type="publish",
            project_key=project_key,
            project_display_name=project_display_name,
            status="pending",
            summary=f"{project_display_name or 'Org Ops'} has review-ready work waiting on manual publish approval.",
        )

    hotspots = sorted(
        gate_buckets.values(),
        key=lambda item: (-int(item.get("occurrence_count") or 0), -int(item.get("pending_count") or 0), str(item.get("title") or "")),
    )[:8]

    automation_candidates: list[dict[str, Any]] = []
    for item in hotspots:
        occurrence_count = int(item.get("occurrence_count") or 0)
        pending_count = int(item.get("pending_count") or 0)
        if occurrence_count < 1:
            continue
        automation_type, rationale = _gate_recommendation(
            str(item.get("approval_type") or ""),
            str(item.get("approval_scope") or ""),
            step_type=str(item.get("step_type") or ""),
        )
        priority = "high" if pending_count >= 2 or str(item.get("approval_scope") or "") in {"publish", "incident_recovery"} else "normal"
        automation_candidates.append(
            {
                "candidate_key": f"automation:{item['gate_key']}",
                "title": f"Automate gate: {item['title']}",
                "gate_key": str(item["gate_key"]),
                "project_key": item.get("project_key"),
                "project_display_name": item.get("project_display_name"),
                "automation_type": automation_type,
                "priority": priority,
                "rationale": rationale,
                "occurrence_count": occurrence_count,
            }
        )
    automation_candidates.sort(
        key=lambda item: (0 if str(item.get("priority") or "normal") == "high" else 1, -int(item.get("occurrence_count") or 0), str(item.get("title") or "")),
    )
    return hotspots, automation_candidates[:6]


def _project_highlights(project_catalog: dict[str, dict[str, Any]], scheduler_plan: dict[str, Any]) -> list[dict[str, Any]]:
    scheduler_by_key = {
        str(item.get("project_key") or ""): dict(item)
        for item in scheduler_plan.get("project_states") or []
    }
    highlights: list[dict[str, Any]] = []
    for project in project_catalog.values():
        state = scheduler_by_key.get(str(project.get("project_key") or ""), {})
        runtime_metrics = dict(project.get("runtime_metrics") or {})
        highlights.append({
            "project_key": str(project.get("project_key") or ""),
            "display_name": str(project.get("display_name") or ""),
            "readiness_status": str(project.get("readiness_status") or "unknown"),
            "readiness_score": int(project.get("readiness_score") or 0),
            "active_count": int(state.get("active_count") or 0),
            "queued_count": int(state.get("queued_count") or 0),
            "bug_report_count": int(project.get("bug_report_count") or 0),
            "blocked_publish_count": int(project.get("blocked_publish_count") or 0),
            "scheduler_weight": float(state.get("scheduler_weight") or 1.0),
            "autonomy_mode": str(state.get("autonomy_mode") or "recommend"),
            "budget_used": int(state.get("budget_used") or 0),
            "budget_remaining": int(state.get("budget_remaining") or 0),
            "completed_requirements": int(runtime_metrics.get("completed_requirements") or 0),
            "budget_spent_points": int(runtime_metrics.get("budget_spent_points") or 0),
            "prompt_cache_saved_chars": int(runtime_metrics.get("prompt_cache_saved_chars") or 0),
            "escalations": int(runtime_metrics.get("escalations") or 0),
            "downgrades": int(runtime_metrics.get("downgrades") or 0),
            "tier_mix": dict(runtime_metrics.get("tier_mix") or {"mini": 0, "standard": 0, "max": 0}),
            "open_bug_count": int(project.get("open_bug_count") or 0),
            "critical_bug_count": int(project.get("critical_bug_count") or 0),
            "converted_bug_count": int(project.get("converted_bug_count") or 0),
            "recurring_bug_count": int(project.get("recurring_bug_count") or 0),
        })
    highlights.sort(
        key=lambda item: (
            -item["queued_count"],
            -item["bug_report_count"],
            item["readiness_score"],
            item["budget_remaining"],
        )
    )
    return highlights[:6]


def _bottlenecks(project_catalog: dict[str, dict[str, Any]], scheduler_plan: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for project in scheduler_plan.get("project_states") or []:
        project_key = str(project.get("project_key") or "")
        display_name = str(project.get("display_name") or project_key)
        catalog = next(
            (
                value
                for value in project_catalog.values()
                if str(value.get("project_key") or "") == project_key
            ),
            {},
        )
        if int(catalog.get("blocked_publish_count") or 0) > 0:
            items.append({
                "item_key": f"blocked-publish:{project_key}",
                "title": f"{display_name} publish gate is blocked",
                "severity": "high",
                "summary": f"{display_name} has {int(catalog.get('blocked_publish_count') or 0)} blocked publish requirements.",
                "project_key": project_key,
                "recommendation": "Prioritize delivery blocker or release gate cleanup before adding more work.",
            })
        if int(catalog.get("bug_report_count") or 0) > 0:
            items.append({
                "item_key": f"bug-pressure:{project_key}",
                "title": f"{display_name} has open defect pressure",
                "severity": "medium",
                "summary": f"{display_name} carries {int(catalog.get('bug_report_count') or 0)} bug-heavy requirements.",
                "project_key": project_key,
                "recommendation": "Feed defect-reduction requirements before expanding scope.",
            })
        if int(project.get("budget_remaining") or 0) <= 20 and int(project.get("queued_count") or 0) > 0:
            items.append({
                "item_key": f"budget:{project_key}",
                "title": f"{display_name} budget is nearly exhausted",
                "severity": "high",
                "summary": f"Budget remaining is {int(project.get('budget_remaining') or 0)} with {int(project.get('queued_count') or 0)} queued candidates.",
                "project_key": project_key,
                "recommendation": "Rebalance toward higher-leverage projects or raise the project budget deliberately.",
            })
        if (
            str(project.get("readiness_status") or "unknown") not in {"ready", "policy_only"}
            and int(project.get("queued_count") or 0) > 0
        ):
            items.append({
                "item_key": f"readiness:{project_key}",
                "title": f"{display_name} is queued but not automation-ready",
                "severity": "medium",
                "summary": f"Readiness is {project.get('readiness_status')} while work is already waiting in the queue.",
                "project_key": project_key,
                "recommendation": "Run onboarding hardening or policy setup before more autonomous execution.",
            })
    approval_required = [
        decision for decision in scheduler_plan.get("decisions") or []
        if bool(decision.get("approval_required"))
    ]
    if approval_required:
        top = approval_required[0]
        items.append({
            "item_key": "approval-backlog",
            "title": "Portfolio has approval-gated high-value work",
            "severity": "high",
            "summary": f"{len(approval_required)} scheduler decisions need operator approval. Top item: {top.get('title')}.",
            "project_key": str(top.get("project_key") or ""),
            "recommendation": "Review the approval queue so the scheduler can continue compounding value.",
        })
    items.sort(key=lambda item: (_SEVERITY_RANK.get(item["severity"], 99), item["title"]))
    return items[:8]


def _match_incident_project(
    incident: dict[str, Any],
    project_catalog: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    incident_project_key = str(incident.get("project_key") or "").strip()
    incident_root = str(incident.get("project_root_path") or "").strip()
    if incident_project_key:
        for project in project_catalog.values():
            if str(project.get("project_key") or "") == incident_project_key:
                return dict(project)
    if incident_root:
        for project in project_catalog.values():
            if str(project.get("root_path") or "") == incident_root:
                return dict(project)
    if incident_project_key:
        return {
            "project_key": incident_project_key,
            "display_name": str(incident.get("project_display_name") or incident_project_key),
            "root_path": incident_root or None,
        }
    return {
        "project_key": "org-ops",
        "display_name": str(incident.get("project_display_name") or "Org Ops"),
        "root_path": None,
    }


def _incidents(db: Session, project_catalog: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    incidents: list[dict[str, Any]] = []
    for incident in list_open_incidents(db):
        project = _match_incident_project(incident, project_catalog)
        severity = str(incident.get("severity") or "medium")
        incidents.append({
            "item_key": str(incident.get("incident_key") or ""),
            "title": str(incident.get("title") or ""),
            "severity": severity,
            "summary": str(incident.get("summary") or ""),
            "project_key": str(project.get("project_key") or "org-ops"),
            "project_display_name": str(project.get("display_name") or incident.get("project_display_name") or "Org Ops"),
            "recommendation": str(incident.get("recommended_action") or ""),
            "incident_family": str(incident.get("incident_family") or ""),
            "incident_code": str(incident.get("incident_code") or ""),
            "recovery_status": str(incident.get("recovery_status") or ""),
            "requirement_id": int(incident.get("requirement_id") or 0) or None,
            "source_ref": f"incident:{incident.get('incident_key')}",
        })
    incidents.sort(
        key=lambda item: (
            _SEVERITY_RANK.get(str(item.get("severity") or "medium"), 99),
            str(item.get("incident_code") or ""),
            str(item.get("title") or ""),
        )
    )
    return incidents[:8]


def _recommendations(scheduler_plan: dict[str, Any], incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions = []
    for decision in scheduler_plan.get("decisions") or []:
        action = str(decision.get("action") or "")
        if action not in {"start", "intake", "rebalance_start", "preempt_candidate", "approval_required"}:
            continue
        reason = str(decision.get("reason") or "")
        reasons = [str(item) for item in decision.get("reasons") or [] if str(item).strip()]
        decisions.append({
            "candidate_type": str(decision.get("candidate_type") or "requirement"),
            "title": str(decision.get("title") or ""),
            "project_key": str(decision.get("project_key") or "org-ops"),
            "project_display_name": str(decision.get("project_display_name") or "Org Ops"),
            "action": action,
            "score": float(decision.get("score") or 0.0),
            "budget_cost": int(decision.get("budget_cost") or 0),
            "source_ref": (
                f"requirement:{int(decision['requirement_id'])}"
                if decision.get("requirement_id") is not None
                else f"signal:{int(decision['signal_id'])}"
                if decision.get("signal_id") is not None
                else None
            ),
            "rationale": reason or ", ".join(reasons[:2]) or "Top-ranked portfolio candidate.",
            "approval_required": bool(decision.get("approval_required")),
            "requirement_id": int(decision["requirement_id"]) if decision.get("requirement_id") is not None else None,
            "signal_id": int(decision["signal_id"]) if decision.get("signal_id") is not None else None,
            "incident_family": None,
            "incident_code": None,
            "recovery_status": None,
        })
    for incident in incidents:
        severity = str(incident.get("severity") or "medium")
        base_score = 92.0 if severity in {"critical", "high"} else 68.0
        recovery_status = str(incident.get("recovery_status") or "")
        if recovery_status == "operator_review_required":
            action = "approval_required"
        elif recovery_status in {"replan_required", "runtime_recovery_required"}:
            action = "intake"
        else:
            action = "review"
        decisions.append({
            "candidate_type": "incident",
            "title": str(incident.get("title") or ""),
            "project_key": str(incident.get("project_key") or "org-ops"),
            "project_display_name": str(incident.get("project_display_name") or incident.get("project_key") or "Org Ops"),
            "action": action,
            "score": base_score,
            "budget_cost": 24 if severity in {"critical", "high"} else 16,
            "source_ref": str(incident.get("source_ref") or "") or None,
            "rationale": str(incident.get("recommendation") or "Resolve the active incident before expanding automation scope."),
            "approval_required": action == "approval_required",
            "requirement_id": int(incident.get("requirement_id") or 0) or None,
            "signal_id": None,
            "incident_family": str(incident.get("incident_family") or ""),
            "incident_code": str(incident.get("incident_code") or ""),
            "recovery_status": recovery_status or None,
        })
    decisions.sort(key=lambda item: (-item["score"], item["action"]))
    return decisions[:6]


def _signal_id_from_source_ref(source_ref: str | None) -> int | None:
    raw = str(source_ref or "").strip()
    if raw.startswith("signal:"):
        raw = raw.split(":", 1)[1]
    elif raw.startswith("optimization-signal:"):
        raw = raw.split(":", 1)[1]
    else:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _priority_from_score(score: float, *, action: str, severity: str | None = None) -> str:
    if str(severity or "medium") in {"critical", "high"}:
        return "high"
    if action in {"approval_required", "rebalance_start", "preempt_candidate"} or score >= 75:
        return "high"
    if score >= 40:
        return "normal"
    return "low"


def _template_key_for_item(*, recommendation: dict[str, Any] | None = None, item: dict[str, Any] | None = None, signal: Any | None = None) -> str:
    if signal is not None:
        return template_key_for_signal(str(signal.signal_type))
    if recommendation and str(recommendation.get("candidate_type") or "") == "incident":
        return "incident_recovery"
    source_title = f"{(item or {}).get('title', '')} {(item or {}).get('summary', '')}".lower()
    if "publish gate" in source_title or "release" in source_title or "blocker" in source_title:
        return "release_bottleneck"
    if "approval" in source_title:
        return "approval_automation"
    if "readiness" in source_title or "onboarding" in source_title:
        return "onboarding_friction"
    if "docs" in source_title or "documentation" in source_title:
        return "docs_drift"
    if "defect" in source_title or "bug" in source_title:
        return "defect_reduction"
    if recommendation and str(recommendation.get("candidate_type") or "") == "signal":
        return "defect_reduction"
    return "defect_reduction"


def _template_key_for_automation_candidate(candidate: dict[str, Any]) -> str:
    automation_type = str(candidate.get("automation_type") or "").strip().lower()
    if automation_type in {"incident_recovery_automation"}:
        return "incident_recovery"
    return "approval_automation"


def _target_project_path_for_automation_candidate(project: dict[str, Any], candidate: dict[str, Any]) -> str | None:
    template_key = _template_key_for_automation_candidate(candidate)
    automation_type = str(candidate.get("automation_type") or "").strip().lower()
    if template_key == "approval_automation" or automation_type in {
        "context_refresh_automation",
        "approval_automation",
        "manual_override_automation",
    }:
        return str(PROJECT_ROOT)
    return str(project.get("root_path") or "") or None


def _acceptance_checks_from_body(body: RequirementCreate) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for check in body.template_acceptance_checks or []:
        if isinstance(check, dict):
            checks.append(dict(check))
    return checks


def _build_bundle_item_from_requirement(
    recommendation: dict[str, Any],
    requirement: RequirementRow,
) -> dict[str, Any]:
    return {
        "bundle_item_key": f"requirement:{int(requirement.id)}",
        "title": str(requirement.title),
        "candidate_type": "requirement",
        "project_key": str(recommendation.get("project_key") or "org-ops"),
        "project_display_name": str(recommendation.get("project_display_name") or "Org Ops"),
        "action": str(recommendation.get("action") or "start"),
        "materialization_mode": "reuse_existing",
        "priority": str(requirement.priority or "normal"),
        "score": float(recommendation.get("score") or 0.0),
        "budget_cost": int(recommendation.get("budget_cost") or 0),
        "source_ref": f"requirement:{int(requirement.id)}",
        "target_project_path": str(requirement.target_project_path or "") or None,
        "requirement_id": int(requirement.id),
        "template_key": None,
        "rationale": str(recommendation.get("rationale") or "Existing ready requirement selected for the next cycle."),
        "description_markdown": str(requirement.description_markdown or ""),
        "acceptance_checks": [],
        "approval_required": bool(recommendation.get("approval_required")),
        "template_payload": {},
    }


def _build_bundle_item_from_template_body(
    *,
    bundle_item_key: str,
    recommendation: dict[str, Any] | None,
    title: str,
    project_key: str,
    project_display_name: str,
    materialization_source_ref: str | None,
    template_body: RequirementCreate,
    score: float,
    budget_cost: int,
    action: str,
    approval_required: bool,
    requirement_id: int | None = None,
) -> dict[str, Any]:
    return {
        "bundle_item_key": bundle_item_key,
        "title": str(template_body.title),
        "candidate_type": str((recommendation or {}).get("candidate_type") or "derived"),
        "project_key": project_key,
        "project_display_name": project_display_name,
        "action": action,
        "materialization_mode": "create_requirement",
        "priority": str(template_body.priority or "normal"),
        "score": round(score, 2),
        "budget_cost": int(budget_cost or 0),
        "source_ref": materialization_source_ref,
        "target_project_path": str(template_body.target_project_path or "") or None,
        "requirement_id": requirement_id,
        "template_key": str(template_body.template_key or ""),
        "rationale": str((recommendation or {}).get("rationale") or f"Bundle candidate generated from {title}."),
        "description_markdown": str(template_body.description_markdown),
        "acceptance_checks": _acceptance_checks_from_body(template_body),
        "approval_required": approval_required,
        "template_payload": dict(template_body.template_payload or {}),
    }


def _build_signal_bundle_item(
    *,
    recommendation: dict[str, Any],
    signal: Any,
    project_catalog: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    project = next(
        (
            item for item in project_catalog.values()
            if str(item.get("project_key") or "") == str(recommendation.get("project_key") or "")
        ),
        {},
    )
    template_key = _template_key_for_item(recommendation=recommendation, signal=signal)
    score = float(recommendation.get("score") or 0.0)
    action = str(recommendation.get("action") or "intake")
    body = build_template_instance(
        template_key=template_key,
        title=str(signal.title),
        context_summary=(
            f"{signal.summary}\n\n"
            f"Signal type: {signal.signal_type}\n"
            f"Severity: {signal.severity}\n"
            f"Confidence: {signal.confidence}\n"
            f"Occurrences: {signal.occurrence_count}\n"
            f"Scheduler rationale: {recommendation.get('rationale')}"
        ),
        target_project_path=str(signal.routing_target_path or project.get("root_path") or "") or None,
        priority=_priority_from_score(score, action=action, severity=str(signal.severity or "medium")),
        source="company_review_bundle",
        source_ref=(
            f"company-review-signal:{int(signal.id)}"
            if getattr(signal, "id", None) is not None else None
        ),
        evidence=_json_loads(getattr(signal, "evidence_json", None), []),
        score_breakdown={
            "score": score,
            "recommendation_action": action,
            "confidence": float(getattr(signal, "confidence", 0.0) or 0.0),
        },
        template_payload_extra={
            "signal_id": int(signal.id),
            "signal_type": str(signal.signal_type),
            "project_key": str(recommendation.get("project_key") or ""),
            "project_display_name": str(recommendation.get("project_display_name") or "Org Ops"),
            "source_review_action": action,
        },
    )
    return _build_bundle_item_from_template_body(
        bundle_item_key=f"signal:{int(signal.id)}",
        recommendation=recommendation,
        title=str(signal.title),
        project_key=str(recommendation.get("project_key") or "org-ops"),
        project_display_name=str(recommendation.get("project_display_name") or "Org Ops"),
        materialization_source_ref=f"signal:{int(signal.id)}",
        template_body=body,
        score=score,
        budget_cost=int(recommendation.get("budget_cost") or 0),
        action=action,
        approval_required=bool(recommendation.get("approval_required")),
    )


def _build_incident_bundle_item(
    *,
    recommendation: dict[str, Any],
    incident: dict[str, Any],
    project_catalog: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    project_key = str(recommendation.get("project_key") or "org-ops")
    project = next(
        (
            item for item in project_catalog.values()
            if str(item.get("project_key") or "") == project_key
        ),
        {},
    )
    score = float(recommendation.get("score") or 0.0)
    action = str(recommendation.get("action") or "intake")
    body = build_template_instance(
        template_key="incident_recovery",
        title=str(incident.get("title") or "Incident recovery"),
        context_summary=(
            f"{incident.get('summary')}\n\n"
            f"Incident family: {incident.get('incident_family')}\n"
            f"Incident code: {incident.get('incident_code')}\n"
            f"Recovery status: {incident.get('recovery_status')}\n"
            f"Company review rationale: {recommendation.get('rationale')}"
        ),
        target_project_path=str(project.get("root_path") or "") or None,
        priority=_priority_from_score(score, action=action, severity=str(incident.get("severity") or "medium")),
        source="company_review_bundle",
        source_ref=str(incident.get("source_ref") or "") or None,
        evidence=[{
            "incident_key": str(incident.get("item_key") or ""),
            "incident_family": str(incident.get("incident_family") or ""),
            "incident_code": str(incident.get("incident_code") or ""),
            "recovery_status": str(incident.get("recovery_status") or ""),
            "summary": str(incident.get("summary") or ""),
        }],
        score_breakdown={
            "score": score,
            "recommendation_action": action,
            "incident_recovery": True,
        },
        template_payload_extra={
            "project_key": project_key,
            "project_display_name": str(recommendation.get("project_display_name") or project.get("display_name") or "Org Ops"),
            "incident_family": str(incident.get("incident_family") or ""),
            "incident_code": str(incident.get("incident_code") or ""),
            "recovery_status": str(incident.get("recovery_status") or ""),
        },
    )
    return _build_bundle_item_from_template_body(
        bundle_item_key=str(incident.get("item_key") or ""),
        recommendation=recommendation,
        title=str(incident.get("title") or "Incident recovery"),
        project_key=project_key,
        project_display_name=str(recommendation.get("project_display_name") or project.get("display_name") or "Org Ops"),
        materialization_source_ref=str(incident.get("source_ref") or "") or None,
        template_body=body,
        score=score,
        budget_cost=int(recommendation.get("budget_cost") or 0),
        action=action,
        approval_required=bool(recommendation.get("approval_required")),
        requirement_id=int(recommendation.get("requirement_id") or 0) or None,
    )


def _build_derived_bundle_item(
    *,
    item: dict[str, Any],
    project_catalog: dict[str, dict[str, Any]],
    candidate_type: str,
) -> dict[str, Any]:
    project_key = str(item.get("project_key") or "org-ops")
    project = next(
        (
            value for value in project_catalog.values()
            if str(value.get("project_key") or "") == project_key
        ),
        {},
    )
    score = 72.0 if str(item.get("severity") or "medium") in {"high", "critical"} else 56.0
    template_key = _template_key_for_item(item=item)
    body = build_template_instance(
        template_key=template_key,
        title=str(item.get("title") or "Portfolio follow-up"),
        context_summary=(
            f"{item.get('summary')}\n\n"
            f"Recommendation: {item.get('recommendation') or 'Convert into an improvement requirement.'}\n"
            f"Generated from company operating review."
        ),
        target_project_path=str(project.get("root_path") or "") or None,
        priority=_priority_from_score(score, action="intake", severity=str(item.get("severity") or "medium")),
        source="company_review_bundle",
        source_ref=f"company-review-derived:{candidate_type}:{item.get('item_key')}",
        evidence=[{
            "item_key": str(item.get("item_key") or ""),
            "summary": str(item.get("summary") or ""),
            "severity": str(item.get("severity") or "medium"),
        }],
        score_breakdown={
            "review_generated": True,
            "severity": str(item.get("severity") or "medium"),
            "baseline_score": score,
        },
        template_payload_extra={
            "project_key": project_key,
            "project_display_name": str(project.get("display_name") or project_key or "Org Ops"),
            "derived_from": candidate_type,
            "derived_item_key": str(item.get("item_key") or ""),
        },
    )
    return _build_bundle_item_from_template_body(
        bundle_item_key=f"{candidate_type}:{item.get('item_key')}",
        recommendation=None,
        title=str(item.get("title") or "Portfolio follow-up"),
        project_key=project_key,
        project_display_name=str(project.get("display_name") or project_key or "Org Ops"),
        materialization_source_ref=f"{candidate_type}:{item.get('item_key')}",
        template_body=body,
        score=score,
        budget_cost=18 if candidate_type == "bottleneck" else 22,
        action="intake",
        approval_required=str(item.get("severity") or "medium") in {"high", "critical"},
    )


def _next_cycle_requirement_bundle(
    *,
    project_catalog: dict[str, dict[str, Any]],
    recommendations: list[dict[str, Any]],
    bottlenecks: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
    signals: list[Any],
    requirements: dict[int, RequirementRow],
) -> list[dict[str, Any]]:
    bundle: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    seen_titles: set[tuple[str, str]] = set()
    signals_by_id = {
        int(signal.id): signal
        for signal in signals
        if getattr(signal, "id", None) is not None
    }
    incidents_by_key = {
        str(item.get("item_key") or ""): item
        for item in incidents
        if str(item.get("item_key") or "").strip()
    }

    def _push(item: dict[str, Any]) -> None:
        key = str(item.get("bundle_item_key") or "")
        title_key = (str(item.get("project_key") or ""), str(item.get("title") or ""))
        if not key or key in seen_keys or title_key in seen_titles:
            return
        seen_keys.add(key)
        seen_titles.add(title_key)
        bundle.append(item)

    for recommendation in recommendations:
        requirement_id = recommendation.get("requirement_id")
        signal_id = recommendation.get("signal_id") or _signal_id_from_source_ref(recommendation.get("source_ref"))
        if requirement_id is not None and int(requirement_id) in requirements:
            _push(_build_bundle_item_from_requirement(recommendation, requirements[int(requirement_id)]))
            continue
        if signal_id is not None and int(signal_id) in signals_by_id:
            _push(_build_signal_bundle_item(
                recommendation=recommendation,
                signal=signals_by_id[int(signal_id)],
                project_catalog=project_catalog,
            ))
            continue
        source_ref = str(recommendation.get("source_ref") or "")
        if source_ref.startswith("incident:"):
            incident_key = source_ref.split(":", 1)[1]
            if incident_key in incidents_by_key:
                _push(_build_incident_bundle_item(
                    recommendation=recommendation,
                    incident=incidents_by_key[incident_key],
                    project_catalog=project_catalog,
                ))

    for incident in incidents:
        if len(bundle) >= 6:
            break
        _push(_build_derived_bundle_item(item=incident, project_catalog=project_catalog, candidate_type="incident"))

    for bottleneck in bottlenecks:
        if len(bundle) >= 6:
            break
        _push(_build_derived_bundle_item(item=bottleneck, project_catalog=project_catalog, candidate_type="bottleneck"))

    bundle.sort(
        key=lambda item: (
            0 if bool(item.get("approval_required")) else 1,
            _PRIORITY_RANK.get(str(item.get("priority") or "normal"), 9),
            -(float(item.get("score") or 0.0)),
            str(item.get("title") or ""),
        )
    )
    return bundle[:6]


def _operator_review_package(
    *,
    cycle_label: str,
    bundle: list[dict[str, Any]],
    bottlenecks: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
    portfolio_summary: dict[str, Any],
    project_highlights: list[dict[str, Any]],
    workflow_rituals: dict[str, Any],
) -> dict[str, Any]:
    all_decisions: list[dict[str, Any]] = []
    for item in bundle:
        if bool(item.get("approval_required")):
            all_decisions.append({
                "decision_key": f"bundle-approval:{item['bundle_item_key']}",
                "title": f"Approve next-cycle bundle item: {item['title']}",
                "decision_type": "bundle_approval",
                "severity": "high" if str(item.get("priority") or "normal") == "high" else "medium",
                "summary": f"{item['project_display_name']} / {item['action']} / score {item['score']}",
                "owner_hint": "operator",
                "related_bundle_item_key": item["bundle_item_key"],
            })
    for project in project_highlights:
        if int(project.get("budget_remaining") or 0) <= 20 and int(project.get("queued_count") or 0) > 0:
            all_decisions.append({
                "decision_key": f"budget:{project['project_key']}",
                "title": f"Confirm budget posture for {project['display_name']}",
                "decision_type": "budget_review",
                "severity": "high",
                "summary": f"Budget remaining {project['budget_remaining']} with {project['queued_count']} queued bundle candidates.",
                "owner_hint": "cto",
                "related_bundle_item_key": None,
            })
    for item in bottlenecks[:2]:
        if str(item.get("severity") or "medium") in {"high", "critical"}:
            all_decisions.append({
                "decision_key": f"risk:{item['item_key']}",
                "title": f"Review risk before autonomous promotion: {item['title']}",
                "decision_type": "risk_watch",
                "severity": str(item.get("severity") or "medium"),
                "summary": str(item.get("summary") or ""),
                "owner_hint": "reviewer",
                "related_bundle_item_key": None,
            })
    intake = dict(workflow_rituals.get("morning_intake_sweep") or {})
    dispatcher = dict(workflow_rituals.get("dispatcher_loop") or {})
    closeout = dict(workflow_rituals.get("closeout_and_compact_sweep") or {})
    approval = dict(workflow_rituals.get("approval_sweep") or {})
    if bool(intake.get("requires_operator_review")):
        all_decisions.append({
            "decision_key": "ritual:intake-triage",
            "title": "Review morning intake operator attention items",
            "decision_type": "intake_triage",
            "severity": "high",
            "summary": f"Morning intake flagged {int(intake.get('operator_attention_count') or 0)} operator attention items.",
            "owner_hint": "ops_intake_manager",
            "related_bundle_item_key": None,
        })
    if int(dispatcher.get("approval_reminder_count") or 0) > 0 or int(dispatcher.get("stuck_requirement_count") or 0) > 0:
        all_decisions.append({
            "decision_key": "ritual:dispatcher-follow-through",
            "title": "Review dispatcher follow-through backlog",
            "decision_type": "dispatcher_followthrough",
            "severity": "high" if int(dispatcher.get("stuck_requirement_count") or 0) > 0 else "medium",
            "summary": (
                f"Dispatcher reports {int(dispatcher.get('stuck_requirement_count') or 0)} stuck requirements and "
                f"{int(dispatcher.get('approval_reminder_count') or 0)} approval reminders."
            ),
            "owner_hint": "portfolio_operator",
            "related_bundle_item_key": None,
        })
    if int(closeout.get("stale_requirement_count") or 0) > 0:
        all_decisions.append({
            "decision_key": "ritual:end-of-day-closeout",
            "title": "Review stale items carried into weekly ritual",
            "decision_type": "closeout_followthrough",
            "severity": "medium",
            "summary": (
                f"End-of-day sweep still sees {int(closeout.get('stale_requirement_count') or 0)} stale requirements "
                f"after {int(closeout.get('compacted_requirement_count') or 0)} compactions."
            ),
            "owner_hint": "tester",
            "related_bundle_item_key": None,
        })
    if int(approval.get("stale_approval_count") or 0) > 0:
        all_decisions.append({
            "decision_key": "ritual:approval-stale-backlog",
            "title": "Review stale high-risk approvals",
            "decision_type": "approval_stale_backlog",
            "severity": "high",
            "summary": (
                f"Approval sweep still sees {int(approval.get('stale_approval_count') or 0)} stale approval requests "
                f"and {int(approval.get('pending_human_gate_count') or 0)} human-gated requirements."
            ),
            "owner_hint": "portfolio_operator",
            "related_bundle_item_key": None,
        })

    decisions = [
        item for item in all_decisions
        if str(item.get("severity") or "medium") in {"high", "critical"}
    ]
    checklist = [
        "Confirm the next-cycle bundle matches the current company goal and operator bandwidth.",
        "Approve or defer every high-value item that still requires human judgment.",
        "Verify blocked publish and budget pressure projects have a named owner before autonomous execution.",
        "Promote only the bundle items whose validation and delivery contracts can be completed this cycle.",
    ]
    top_risk = incidents[0]["title"] if incidents else bottlenecks[0]["title"] if bottlenecks else "No major blockers"
    summary_markdown = (
        f"Cycle `{cycle_label}` operator package.\n\n"
        f"- Bundle candidates: {len(bundle)}\n"
        f"- Decisions requiring operator review: {len(decisions)}\n"
        f"- Lower-risk decisions handled autonomously: {max(0, len(all_decisions) - len(decisions))}\n"
        f"- Open portfolio risk: {top_risk}\n"
        f"- Approval-required scheduler items: {portfolio_summary['approval_required_decisions']}\n"
        f"- Morning intake attention items: {int(intake.get('operator_attention_count') or 0)}\n"
        f"- Dispatcher approval reminders: {int(dispatcher.get('approval_reminder_count') or 0)}\n"
        f"- End-of-day stale carryover: {int(closeout.get('stale_requirement_count') or 0)}"
    )
    return {
        "title": "Operator Review Package",
        "summary_markdown": summary_markdown,
        "checklist": checklist,
        "decisions": decisions[:8],
        "autonomous_decision_count": max(0, len(all_decisions) - len(decisions)),
        "recommended_bundle_item_keys": [str(item["bundle_item_key"]) for item in bundle[:3]],
    }


def _autonomous_coo_posture(
    *,
    portfolio_summary: dict[str, Any],
    workflow_rituals: dict[str, Any],
    operator_review_package: dict[str, Any],
    incidents: list[dict[str, Any]],
) -> dict[str, Any]:
    intake = dict(workflow_rituals.get("morning_intake_sweep") or {})
    dispatcher = dict(workflow_rituals.get("dispatcher_loop") or {})
    closeout = dict(workflow_rituals.get("closeout_and_compact_sweep") or {})
    approval = dict(workflow_rituals.get("approval_sweep") or {})

    high_risk_decision_count = len(list(operator_review_package.get("decisions") or []))
    autonomous_decision_count = int(operator_review_package.get("autonomous_decision_count") or 0)
    autonomous_workflow_keys = [
        key for key in [
            "bug_log_sweep",
            "morning_intake_sweep",
            "dispatcher_loop",
            "closeout_and_compact_sweep",
            "approval_sweep",
        ]
        if workflow_rituals.get(key) is not None
    ]
    human_gate_required_count = int(approval.get("pending_human_gate_count") or 0)
    operator_queue_count = high_risk_decision_count + human_gate_required_count
    critical_incident_count = sum(
        1 for item in incidents if str(item.get("severity") or "medium") in {"critical", "high"}
    )
    autonomous_execution_rate = 0.0
    denom = operator_queue_count + int(portfolio_summary.get("active_requirements") or 0)
    if denom > 0:
        autonomous_execution_rate = round(
            (int(portfolio_summary.get("active_requirements") or 0) / denom) * 100,
            1,
        )
    summary_markdown = (
        f"Autonomous COO mode keeps `{len(autonomous_workflow_keys)}` daily loops self-running, "
        f"while only `{operator_queue_count}` high-risk items remain in the operator queue. "
        f"Approval sweep auto-managed `{int(approval.get('auto_approved_count') or 0)}` requirements; "
        f"stale human approvals: `{int(approval.get('stale_approval_count') or 0)}`."
    )
    return {
        "mode": "autonomous_coo",
        "operator_only_high_risk": True,
        "autonomous_workflow_keys": autonomous_workflow_keys,
        "high_risk_decision_count": high_risk_decision_count,
        "autonomous_decision_count": autonomous_decision_count,
        "operator_queue_count": operator_queue_count,
        "pending_human_gate_count": human_gate_required_count,
        "auto_approved_requirement_count": int(approval.get("auto_approved_count") or 0),
        "stale_approval_count": int(approval.get("stale_approval_count") or 0),
        "stuck_requirement_count": int(dispatcher.get("stuck_requirement_count") or 0),
        "critical_incident_count": critical_incident_count,
        "requires_operator_attention": operator_queue_count > 0 or critical_incident_count > 0,
        "autonomous_execution_rate": autonomous_execution_rate,
        "summary_markdown": summary_markdown,
    }


def _workflow_rituals_summary(db: Session) -> dict[str, Any]:
    rows = {
        str(row.workflow_key): row
        for row in db.query(RecurringWorkflowRow).filter(
            RecurringWorkflowRow.workflow_key.in_(
                ["morning_intake_sweep", "dispatcher_loop", "closeout_and_compact_sweep", "approval_sweep"]
            )
        ).all()
    }
    intake_payload = _json_loads(getattr(rows.get("morning_intake_sweep"), "last_result_json", None), {})
    dispatcher_payload = _json_loads(getattr(rows.get("dispatcher_loop"), "last_result_json", None), {})
    closeout_payload = _json_loads(getattr(rows.get("closeout_and_compact_sweep"), "last_result_json", None), {})
    approval_payload = _json_loads(getattr(rows.get("approval_sweep"), "last_result_json", None), {})

    return {
        "morning_intake_sweep": {
            "last_run_at": getattr(rows.get("morning_intake_sweep"), "last_run_at", None),
            "created_requirement_count": len(list(intake_payload.get("created_requirement_ids") or [])),
            "operator_attention_count": len(list(intake_payload.get("operator_attention_items") or [])),
            "requires_operator_review": bool(intake_payload.get("requires_operator_review")),
        },
        "dispatcher_loop": {
            "last_run_at": getattr(rows.get("dispatcher_loop"), "last_run_at", None),
            "started_count": len(list(dispatcher_payload.get("started_ids") or [])),
            "stuck_requirement_count": len(list(dispatcher_payload.get("stuck_requirement_ids") or [])),
            "approval_reminder_count": len(list(dispatcher_payload.get("approval_reminders") or [])),
            "follow_up_action_count": len(list(dispatcher_payload.get("follow_up_actions") or [])),
        },
        "closeout_and_compact_sweep": {
            "last_run_at": getattr(rows.get("closeout_and_compact_sweep"), "last_run_at", None),
            "acceptance_candidate_count": int(closeout_payload.get("acceptance_candidates") or 0),
            "stale_requirement_count": len(list(closeout_payload.get("stale_requirement_ids") or [])),
            "compacted_requirement_count": len(list(closeout_payload.get("compacted_requirement_ids") or [])),
            "review_snapshot_count": len(list(closeout_payload.get("review_snapshot_requirement_ids") or [])),
        },
        "approval_sweep": {
            "last_run_at": getattr(rows.get("approval_sweep"), "last_run_at", None),
            "auto_approved_count": len(list(approval_payload.get("auto_approved_requirement_ids") or [])),
            "pending_count": int(approval_payload.get("pending_count") or 0),
            "stale_approval_count": len(list(approval_payload.get("stale_approval_request_ids") or [])),
            "pending_human_gate_count": sum(
                1
                for item in list(approval_payload.get("pending_items") or [])
                if bool((item or {}).get("needs_human_gate"))
            ),
            "approval_source_counts": dict(approval_payload.get("approval_source_counts") or {}),
        },
    }


def build_operating_review_payload(db: Session) -> dict[str, Any]:
    project_catalog = build_project_catalog(db)
    refresh_optimization_signals(db)
    signals = list_optimization_signals(db, status="open")
    scheduler_plan = build_portfolio_schedule(
        db,
        refresh_signals=False,
        signal_rows=signals,
        project_catalog=project_catalog,
    )
    requirements = {
        int(row.id): row
        for row in db.query(RequirementRow).all()
        if row.id is not None
    }
    runtime_metrics, per_project_runtime_metrics = _aggregate_runtime_metrics(
        db,
        project_catalog=project_catalog,
        requirements=requirements,
    )
    bug_summary, recurring_bug_fingerprints, per_project_bug_metrics = _bug_backlog_summary(
        db,
        project_catalog=project_catalog,
    )
    cross_project_bug_recoveries = _cross_project_bug_recoveries(
        db,
        project_catalog=project_catalog,
    )
    for project in project_catalog.values():
        project_key = str(project.get("project_key") or "")
        project["runtime_metrics"] = per_project_runtime_metrics.get(project_key, _empty_runtime_metric_bucket())
        bug_metrics = per_project_bug_metrics.get(project_key, {})
        project["open_bug_count"] = int(bug_metrics.get("open_bug_count") or 0)
        project["critical_bug_count"] = int(bug_metrics.get("critical_bug_count") or 0)
        project["converted_bug_count"] = int(bug_metrics.get("converted_bug_count") or 0)
        project["recurring_bug_count"] = int(bug_metrics.get("recurring_bug_count") or 0)
    requirement_total = sum(1 for row in requirements.values() if str(row.status or "") != "deleted")
    completion_rate = round(
        (int(runtime_metrics.get("completed_requirements") or 0) / requirement_total) * 100,
        1,
    ) if requirement_total else 0.0
    human_gate_hotspots, automation_candidates = _human_gate_hotspots(
        db,
        project_catalog=project_catalog,
        requirements=requirements,
    )

    portfolio_summary = {
        "active_requirements": int(scheduler_plan.get("active_count") or 0),
        "completed_requirements": int(runtime_metrics.get("completed_requirements") or 0),
        "completion_rate": completion_rate,
        "open_signals": len(signals),
        "approval_required_decisions": sum(
            1 for item in scheduler_plan.get("decisions") or [] if bool(item.get("approval_required"))
        ),
        "rebalance_opportunities": sum(
            1 for item in scheduler_plan.get("decisions") or []
            if str(item.get("action") or "") in {"preempt_candidate", "rebalance_start"}
        ),
        "projects_over_budget": sum(
            1 for item in scheduler_plan.get("project_states") or []
            if int(item.get("budget_remaining") or 0) <= 20
        ),
        "blocked_publish_projects": sum(
            1 for item in project_catalog.values()
            if int(item.get("blocked_publish_count") or 0) > 0
        ),
        "budget_spent_points": int(runtime_metrics.get("budget_spent_points") or 0),
        "tokens_used": int(runtime_metrics.get("tokens_used") or 0),
        "prompt_cache_saved_chars": int(runtime_metrics.get("prompt_cache_saved_chars") or 0),
        "deduped_bindings": int(runtime_metrics.get("deduped_bindings") or 0),
        "escalations": int(runtime_metrics.get("escalations") or 0),
        "downgrades": int(runtime_metrics.get("downgrades") or 0),
        "tier_mix": dict(runtime_metrics.get("tier_mix") or {"mini": 0, "standard": 0, "max": 0}),
        "human_gate_hotspots": len(human_gate_hotspots),
        "open_bug_pressure": int(bug_summary.get("open_bug_pressure") or 0),
        "unresolved_critical_bugs": int(bug_summary.get("unresolved_critical_bugs") or 0),
        "bug_requirements_created": int(bug_summary.get("bug_requirements_created") or 0),
        "recurring_bug_fingerprint_count": int(bug_summary.get("recurring_bug_fingerprint_count") or 0),
        "cross_project_bug_recoveries": len(cross_project_bug_recoveries),
    }
    project_highlights = _project_highlights(project_catalog, scheduler_plan)
    bottlenecks = _bottlenecks(project_catalog, scheduler_plan)
    incidents = _incidents(db, project_catalog)
    if not incidents:
        incidents = [
            {
                "item_key": f"derived-{item['item_key']}",
                "title": item["title"],
                "severity": item["severity"],
                "summary": item["summary"],
                "project_key": item.get("project_key"),
                "project_display_name": next(
                    (
                        str(project.get("display_name") or item.get("project_key") or "Org Ops")
                        for project in project_catalog.values()
                        if str(project.get("project_key") or "") == str(item.get("project_key") or "")
                    ),
                    str(item.get("project_key") or "Org Ops"),
                ),
                "recommendation": item.get("recommendation"),
            }
            for item in bottlenecks
            if str(item.get("severity") or "medium") in {"high", "critical"}
        ][:4]
    next_cycle_recommendations = _recommendations(scheduler_plan, incidents)
    next_cycle_requirement_bundle = _next_cycle_requirement_bundle(
        project_catalog=project_catalog,
        recommendations=next_cycle_recommendations,
        bottlenecks=bottlenecks,
        incidents=incidents,
        signals=signals,
        requirements=requirements,
    )
    workflow_rituals = _workflow_rituals_summary(db)
    operator_review_package = _operator_review_package(
        cycle_label=_cycle_label(),
        bundle=next_cycle_requirement_bundle,
        bottlenecks=bottlenecks,
        incidents=incidents,
        portfolio_summary=portfolio_summary,
        project_highlights=project_highlights,
        workflow_rituals=workflow_rituals,
    )
    autonomous_coo_posture = _autonomous_coo_posture(
        portfolio_summary=portfolio_summary,
        workflow_rituals=workflow_rituals,
        operator_review_package=operator_review_package,
        incidents=incidents,
    )

    return {
        "cycle_label": _cycle_label(),
        "title": "Company Operating Review",
        "summary_markdown": _cycle_summary_markdown(portfolio_summary, bottlenecks, next_cycle_recommendations),
        "portfolio_summary": portfolio_summary,
        "project_highlights": project_highlights,
        "bottlenecks": bottlenecks,
        "incidents": incidents,
        "recurring_bug_fingerprints": recurring_bug_fingerprints,
        "cross_project_bug_recoveries": cross_project_bug_recoveries,
        "human_gate_hotspots": human_gate_hotspots,
        "automation_candidates": automation_candidates,
        "next_cycle_recommendations": next_cycle_recommendations,
        "next_cycle_requirement_bundle": next_cycle_requirement_bundle,
        "operator_review_package": operator_review_package,
        "autonomous_coo_posture": autonomous_coo_posture,
        "source_snapshot": {
            "scheduler_generated_at": scheduler_plan.get("generated_at").isoformat()
            if getattr(scheduler_plan.get("generated_at"), "isoformat", None)
            else scheduler_plan.get("generated_at"),
            "open_signal_ids": [int(signal.id) for signal in signals[:12]],
            "started_ids": list(scheduler_plan.get("started_ids") or []),
            "rebalanced_ids": list(scheduler_plan.get("rebalanced_ids") or []),
            "runtime_metrics": runtime_metrics,
            "workflow_rituals": workflow_rituals,
            "bug_backlog_summary": bug_summary,
        },
    }


def _review_payload(row: CompanyOperatingReviewRow) -> dict[str, Any]:
    payload = _json_loads(row.payload_json, {})
    return payload if isinstance(payload, dict) else {}


def company_review_to_dict(row: CompanyOperatingReviewRow) -> dict[str, Any]:
    payload = _review_payload(row)
    return {
        "id": int(row.id),
        "cycle_label": str(row.cycle_label),
        "title": str(row.title),
        "summary_markdown": str(row.summary_markdown or ""),
        "portfolio_summary": dict(payload.get("portfolio_summary") or {}),
        "project_highlights": list(payload.get("project_highlights") or []),
        "bottlenecks": list(payload.get("bottlenecks") or []),
        "incidents": list(payload.get("incidents") or []),
        "recurring_bug_fingerprints": list(payload.get("recurring_bug_fingerprints") or []),
        "cross_project_bug_recoveries": list(payload.get("cross_project_bug_recoveries") or []),
        "human_gate_hotspots": list(payload.get("human_gate_hotspots") or []),
        "automation_candidates": list(payload.get("automation_candidates") or []),
        "next_cycle_recommendations": list(payload.get("next_cycle_recommendations") or []),
        "next_cycle_requirement_bundle": list(payload.get("next_cycle_requirement_bundle") or []),
        "operator_review_package": dict(payload.get("operator_review_package") or {
            "title": "Operator Review Package",
            "summary_markdown": "No operator package generated yet.",
            "checklist": [],
            "decisions": [],
            "autonomous_decision_count": 0,
            "recommended_bundle_item_keys": [],
        }),
        "autonomous_coo_posture": dict(payload.get("autonomous_coo_posture") or {
            "mode": "autonomous_coo",
            "operator_only_high_risk": True,
            "autonomous_workflow_keys": [],
            "high_risk_decision_count": 0,
            "autonomous_decision_count": 0,
            "operator_queue_count": 0,
            "pending_human_gate_count": 0,
            "auto_approved_requirement_count": 0,
            "stale_approval_count": 0,
            "stuck_requirement_count": 0,
            "critical_incident_count": 0,
            "requires_operator_attention": False,
            "autonomous_execution_rate": 0.0,
            "summary_markdown": "Autonomous COO posture has not been computed yet.",
        }),
        "source_snapshot": dict(payload.get("source_snapshot") or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def refresh_company_operating_review(db: Session) -> CompanyOperatingReviewRow:
    payload = build_operating_review_payload(db)
    row = CompanyOperatingReviewRow(
        cycle_label=str(payload["cycle_label"]),
        title=str(payload["title"]),
        summary_markdown=str(payload["summary_markdown"]),
        payload_json=_json_dumps(
            {
                "portfolio_summary": payload["portfolio_summary"],
                "project_highlights": payload["project_highlights"],
                "bottlenecks": payload["bottlenecks"],
                "incidents": payload["incidents"],
                "recurring_bug_fingerprints": payload["recurring_bug_fingerprints"],
                "cross_project_bug_recoveries": payload["cross_project_bug_recoveries"],
                "human_gate_hotspots": payload["human_gate_hotspots"],
                "automation_candidates": payload["automation_candidates"],
                "next_cycle_recommendations": payload["next_cycle_recommendations"],
                "next_cycle_requirement_bundle": payload["next_cycle_requirement_bundle"],
                "operator_review_package": payload["operator_review_package"],
                "autonomous_coo_posture": payload["autonomous_coo_posture"],
                "source_snapshot": payload["source_snapshot"],
            },
        ),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "event=company_review_refreshed review_id=%s cycle=%s bundle_items=%s recommendations=%s incidents=%s",
        row.id,
        row.cycle_label,
        len(payload.get("next_cycle_requirement_bundle") or []),
        len(payload.get("next_cycle_recommendations") or []),
        len(payload.get("incidents") or []),
    )
    return row


def latest_company_operating_review(db: Session) -> CompanyOperatingReviewRow:
    row = db.query(CompanyOperatingReviewRow).order_by(
        CompanyOperatingReviewRow.created_at.desc(),
        CompanyOperatingReviewRow.id.desc(),
    ).first()
    if row is None:
        row = refresh_company_operating_review(db)
    return row


def materialize_company_review_bundle(
    db: Session,
    *,
    review_id: int,
    bundle_item_keys: list[str] | None = None,
    auto_start: bool = False,
) -> CompanyReviewBundleMaterializeResultOut:
    row = db.query(CompanyOperatingReviewRow).filter(CompanyOperatingReviewRow.id == review_id).first()
    if row is None:
        raise ValueError("Company operating review not found")
    payload = _review_payload(row)
    bundle = list(payload.get("next_cycle_requirement_bundle") or [])
    selected_keys = {str(key) for key in bundle_item_keys or [] if str(key).strip()}

    created_requirement_ids: list[int] = []
    reused_requirement_ids: list[int] = []
    skipped_bundle_item_keys: list[str] = []
    items: list[dict[str, Any]] = []

    for item in bundle:
        bundle_item_key = str(item.get("bundle_item_key") or "")
        if not bundle_item_key:
            continue
        if selected_keys and bundle_item_key not in selected_keys:
            continue

        if str(item.get("materialization_mode") or "") == "reuse_existing":
            requirement_id = item.get("requirement_id")
            if requirement_id is None:
                skipped_bundle_item_keys.append(bundle_item_key)
                items.append({
                    "bundle_item_key": bundle_item_key,
                    "status": "skipped",
                    "title": str(item.get("title") or ""),
                    "action": "reuse_existing",
                    "requirement_id": None,
                    "source_ref": str(item.get("source_ref") or "") or None,
                })
                continue
            reused_requirement_ids.append(int(requirement_id))
            items.append({
                "bundle_item_key": bundle_item_key,
                "status": "linked_existing",
                "title": str(item.get("title") or ""),
                "action": "reuse_existing",
                "requirement_id": int(requirement_id),
                "source_ref": str(item.get("source_ref") or "") or None,
            })
            continue

        review_source_ref = f"company-review-bundle:{review_id}:{bundle_item_key}"
        existing = db.query(RequirementRow).filter(RequirementRow.source_ref == review_source_ref).first()
        if existing is not None:
            reused_requirement_ids.append(int(existing.id))
            items.append({
                "bundle_item_key": bundle_item_key,
                "status": "already_exists",
                "title": str(existing.title),
                "action": "create_requirement",
                "requirement_id": int(existing.id),
                "source_ref": review_source_ref,
            })
            continue

        body = RequirementCreate(
            title=str(item.get("title") or "Company Review Bundle Item"),
            description_markdown=str(item.get("description_markdown") or ""),
            priority=str(item.get("priority") or "normal"),
            source="company_review_bundle",
            source_ref=review_source_ref,
            intake_metadata=normalize_requirement_intake_metadata(
                "company_review_bundle",
                review_source_ref,
                {
                    "intake_reason": "company_review_bundle_materialization",
                    "confidence": 0.75,
                    "review_id": int(review_id),
                    "bundle_item_key": bundle_item_key,
                    "registry_hint": "company_review_bundle",
                    "trigger": "company_review_materialize_bundle",
                },
            ),
            target_project_path=str(item.get("target_project_path") or "") or None,
            auto_start=auto_start,
            template_key=str(item.get("template_key") or "") or None,
            template_payload={
                **dict(item.get("template_payload") or {}),
                "company_review_id": int(review_id),
                "bundle_item_key": bundle_item_key,
                "bundle_generated_from": str(item.get("source_ref") or "") or None,
                "operator_review_package_title": str((payload.get("operator_review_package") or {}).get("title") or ""),
            } if item.get("template_key") else None,
            template_acceptance_checks=list(item.get("acceptance_checks") or []),
        )
        detail = create_requirement(db, body)
        created_requirement_ids.append(int(detail.requirement.id))
        items.append({
            "bundle_item_key": bundle_item_key,
            "status": "created",
            "title": str(detail.requirement.title),
            "action": "create_requirement",
            "requirement_id": int(detail.requirement.id),
            "source_ref": review_source_ref,
        })

    logger.info(
        "event=company_review_bundle_materialized review_id=%s created=%s reused=%s skipped=%s auto_start=%s",
        review_id,
        len(created_requirement_ids),
        len(reused_requirement_ids),
        len(skipped_bundle_item_keys),
        auto_start,
    )

    return CompanyReviewBundleMaterializeResultOut(
        review_id=int(review_id),
        created_requirement_ids=created_requirement_ids,
        reused_requirement_ids=sorted(set(reused_requirement_ids)),
        skipped_bundle_item_keys=skipped_bundle_item_keys,
        items=items,
    )


def materialize_company_review_automation_candidates(
    db: Session,
    *,
    review_id: int,
    candidate_keys: list[str] | None = None,
    auto_start: bool = False,
) -> CompanyReviewBundleMaterializeResultOut:
    row = db.query(CompanyOperatingReviewRow).filter(CompanyOperatingReviewRow.id == review_id).first()
    if row is None:
        raise ValueError("Company operating review not found")
    payload = _review_payload(row)
    candidates = list(payload.get("automation_candidates") or [])
    selected_keys = {str(key) for key in candidate_keys or [] if str(key).strip()}
    project_catalog = build_project_catalog(db)

    created_requirement_ids: list[int] = []
    reused_requirement_ids: list[int] = []
    skipped_candidate_keys: list[str] = []
    items: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate_key = str(candidate.get("candidate_key") or "")
        if not candidate_key:
            continue
        if selected_keys and candidate_key not in selected_keys:
            continue

        review_source_ref = f"company-review-automation:{review_id}:{candidate_key}"
        existing = db.query(RequirementRow).filter(RequirementRow.source_ref == review_source_ref).first()
        if existing is not None:
            reused_requirement_ids.append(int(existing.id))
            items.append(
                {
                    "bundle_item_key": candidate_key,
                    "status": "already_exists",
                    "title": str(existing.title),
                    "action": "create_requirement",
                    "requirement_id": int(existing.id),
                    "source_ref": review_source_ref,
                }
            )
            continue

        project_key = str(candidate.get("project_key") or "")
        project = next(
            (item for item in project_catalog.values() if str(item.get("project_key") or "") == project_key),
            {},
        )
        project_display_name = str(candidate.get("project_display_name") or project.get("display_name") or project_key or "Org Ops")
        template_key = _template_key_for_automation_candidate(candidate)
        occurrence_count = int(candidate.get("occurrence_count") or 0)
        body = build_template_instance(
            template_key=template_key,
            title=str(candidate.get("title") or "Automation Candidate"),
            context_summary=(
                f"Automation opportunity detected in `{project_display_name}`.\n\n"
                f"Automation type: {candidate.get('automation_type')}\n"
                f"Occurrences: {occurrence_count}\n"
                f"Rationale: {candidate.get('rationale')}"
            ),
            target_project_path=_target_project_path_for_automation_candidate(project, candidate),
            priority=str(candidate.get("priority") or "normal"),
            source="automation_candidate",
            source_ref=review_source_ref,
            evidence=[
                {
                    "candidate_key": candidate_key,
                    "automation_type": str(candidate.get("automation_type") or ""),
                    "occurrence_count": occurrence_count,
                    "gate_key": str(candidate.get("gate_key") or ""),
                }
            ],
            score_breakdown={
                "occurrence_count": occurrence_count,
                "priority": str(candidate.get("priority") or "normal"),
                "automation_type": str(candidate.get("automation_type") or ""),
            },
            template_payload_extra={
                "project_key": project_key or None,
                "project_display_name": project_display_name,
                "company_review_id": int(review_id),
                "candidate_key": candidate_key,
                "automation_type": str(candidate.get("automation_type") or ""),
                "gate_key": str(candidate.get("gate_key") or ""),
                "managed_project_key": project_key or None,
                "managed_project_display_name": project_display_name,
                "managed_project_root_path": str(project.get("root_path") or "") or None,
                "operator_review_package_title": str((payload.get("operator_review_package") or {}).get("title") or ""),
            },
            auto_start=auto_start,
        )
        body.intake_metadata = normalize_requirement_intake_metadata(
            "automation_candidate",
            review_source_ref,
            {
                "intake_reason": "company_review_automation_candidate_materialization",
                "confidence": 0.8,
                "review_id": int(review_id),
                "registry_hint": "automation_candidate",
                "trigger": "company_review_materialize_automation_candidate",
            },
        )
        detail = create_requirement(db, body)
        created_requirement_ids.append(int(detail.requirement.id))
        items.append(
            {
                "bundle_item_key": candidate_key,
                "status": "created",
                "title": str(detail.requirement.title),
                "action": "create_requirement",
                "requirement_id": int(detail.requirement.id),
                "source_ref": review_source_ref,
            }
        )

    logger.info(
        "event=company_review_automation_materialized review_id=%s created=%s reused=%s skipped=%s auto_start=%s",
        review_id,
        len(created_requirement_ids),
        len(reused_requirement_ids),
        len(skipped_candidate_keys),
        auto_start,
    )

    return CompanyReviewBundleMaterializeResultOut(
        review_id=int(review_id),
        created_requirement_ids=created_requirement_ids,
        reused_requirement_ids=sorted(set(reused_requirement_ids)),
        skipped_bundle_item_keys=skipped_candidate_keys,
        items=items,
    )
