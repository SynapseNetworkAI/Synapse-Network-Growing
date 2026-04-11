"""Portfolio-level scheduling across projects."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import ArtifactRow, RequirementRow
from server.services.optimization_signals import (
    build_optimization_signal_score_breakdown,
    list_optimization_signals,
    refresh_optimization_signals,
)
from server.services.optimization_templates import template_key_for_signal
from server.services.project_intelligence import build_project_catalog, build_requirement_score_breakdown
from server.services.project_policy import list_project_policies, project_policy_to_dict

DEFAULT_GLOBAL_CAPACITY = 2
MAX_GLOBAL_CAPACITY = 3
PREEMPT_THRESHOLD = 18.0

_TEMPLATE_BONUS = {
    "release_bottleneck": 8.0,
    "approval_automation": 6.0,
    "defect_reduction": 5.0,
    "onboarding_friction": 4.0,
    "docs_drift": 3.0,
}


def _latest_template_key(db: Session, requirement_id: int) -> str | None:
    artifact = db.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == "requirement_template",
    ).order_by(ArtifactRow.id.desc()).first()
    if artifact is None or not artifact.machine_readable_payload:
        return None
    import json

    try:
        payload = json.loads(artifact.machine_readable_payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    template_key = str(payload.get("template_key") or "").strip()
    return template_key or None


def _project_policy_maps(db: Session) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    policies = [project_policy_to_dict(row) for row in list_project_policies(db)]
    by_root = {str(policy["root_path"]): policy for policy in policies}
    by_key = {str(policy["project_key"]): policy for policy in policies}
    return by_root, by_key


def _global_capacity(policy_by_root: dict[str, dict[str, Any]]) -> int:
    active_slots = sum(
        int(policy.get("max_parallel_requirements") or 1)
        for policy in policy_by_root.values()
        if str(policy.get("status") or "active") == "active"
    )
    return max(1, min(MAX_GLOBAL_CAPACITY, active_slots or DEFAULT_GLOBAL_CAPACITY))


def _project_context_for_requirement(
    requirement: RequirementRow,
    score: dict[str, Any],
    policy_by_root: dict[str, dict[str, Any]],
    project_catalog: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    routing = dict(score.get("routing_context") or {})
    scorecards = list(routing.get("project_scorecards") or [])
    if scorecards:
        project = dict(scorecards[0])
        root = str(project.get("root_path") or "")
        policy = dict(policy_by_root.get(root) or {})
        return {
            "project_key": str(project.get("project_key") or "org-ops"),
            "display_name": str(project.get("display_name") or root.rsplit("/", 1)[-1] or "Org Ops"),
            "root_path": root,
            "scheduler_weight": float(policy.get("scheduler_weight") or 1.0),
            "max_parallel_requirements": int(policy.get("max_parallel_requirements") or 1),
            "readiness_status": str(project.get("readiness_status") or "unknown"),
            "readiness_score": int(project.get("readiness_score") or 0),
        }
    target_paths = [
        item.strip()
        for item in str(getattr(requirement, "target_project_path", "") or "").splitlines()
        if item.strip()
    ]
    target_root = target_paths[0] if target_paths else ""
    project = dict(project_catalog.get(target_root) or {})
    policy = dict(policy_by_root.get(target_root) or {})
    return {
        "project_key": str(project.get("project_key") or policy.get("project_key") or "org-ops"),
        "display_name": str(project.get("display_name") or policy.get("display_name") or (target_root.rsplit("/", 1)[-1] if target_root else "Org Ops")),
        "root_path": target_root,
        "scheduler_weight": float(policy.get("scheduler_weight") or 1.0),
        "max_parallel_requirements": int(policy.get("max_parallel_requirements") or 1),
        "readiness_status": str(project.get("readiness_status") or "unknown"),
        "readiness_score": int(project.get("readiness_score") or 0),
    }


def _weighted_scheduler_score(base_score: float, *, scheduler_weight: float, template_key: str | None, active_count: int, quota: int) -> float:
    weight_bonus = (float(scheduler_weight or 1.0) - 1.0) * 12.0
    template_bonus = _TEMPLATE_BONUS.get(str(template_key or ""), 0.0)
    headroom_bonus = 4.0 if active_count < max(1, quota) else -10.0
    return round(base_score + weight_bonus + template_bonus + headroom_bonus, 2)


def _running_requirement_decision(
    db: Session,
    requirement: RequirementRow,
    policy_by_root: dict[str, dict[str, Any]],
    project_catalog: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    score = build_requirement_score_breakdown(db, requirement)
    context = _project_context_for_requirement(requirement, score, policy_by_root, project_catalog)
    template_key = _latest_template_key(db, int(requirement.id))
    weighted = _weighted_scheduler_score(
        float(score.get("total") or 0.0),
        scheduler_weight=float(context["scheduler_weight"]),
        template_key=template_key,
        active_count=1,
        quota=int(context["max_parallel_requirements"]),
    )
    return {
        "candidate_type": "requirement",
        "action": "running",
        "requirement_id": int(requirement.id),
        "signal_id": None,
        "title": str(requirement.title),
        "project_key": context["project_key"],
        "project_display_name": context["display_name"],
        "score": weighted,
        "base_score": float(score.get("total") or 0.0),
        "scheduler_weight": float(context["scheduler_weight"]),
        "project_slot_available": False,
        "reason": "currently running",
        "reasons": ["currently running"],
        "template_key": template_key,
        "source": str(requirement.source),
        "preempt_requirement_id": None,
    }


def build_portfolio_schedule(db: Session) -> dict[str, Any]:
    policy_by_root, _policy_by_key = _project_policy_maps(db)
    project_catalog = build_project_catalog(db)
    global_capacity = _global_capacity(policy_by_root)
    refresh_optimization_signals(db)

    running_requirements = db.query(RequirementRow).filter(RequirementRow.status == "in_progress").all()
    paused_requirements = db.query(RequirementRow).filter(RequirementRow.status == "paused").all()
    ready_requirements = db.query(RequirementRow).filter(
        RequirementRow.status == "ready",
        RequirementRow.blocked_by_count == 0,
    ).all()

    project_active_counts: dict[str, int] = {}
    project_queue_counts: dict[str, int] = {}
    decisions: list[dict[str, Any]] = []

    for req in running_requirements:
        decision = _running_requirement_decision(db, req, policy_by_root, project_catalog)
        decisions.append(decision)
        key = str(decision["project_key"])
        project_active_counts[key] = project_active_counts.get(key, 0) + 1

    for req in paused_requirements:
        score = build_requirement_score_breakdown(db, req)
        context = _project_context_for_requirement(req, score, policy_by_root, project_catalog)
        key = str(context["project_key"])
        project_active_counts[key] = project_active_counts.get(key, 0) + 1

    requirement_candidates: list[dict[str, Any]] = []
    for requirement in ready_requirements:
        score = build_requirement_score_breakdown(db, requirement)
        routing = dict(score.get("routing_context") or {})
        context = _project_context_for_requirement(requirement, score, policy_by_root, project_catalog)
        key = str(context["project_key"])
        project_queue_counts[key] = project_queue_counts.get(key, 0) + 1
        template_key = _latest_template_key(db, int(requirement.id))
        active_count = project_active_counts.get(key, 0)
        quota = int(context["max_parallel_requirements"])
        scheduler_score = _weighted_scheduler_score(
            float(score.get("total") or 0.0),
            scheduler_weight=float(context["scheduler_weight"]),
            template_key=template_key,
            active_count=active_count,
            quota=quota,
        )
        reasons = [
            f"base score {round(float(score.get('total') or 0.0), 2)}",
            f"project weight {round(float(context['scheduler_weight']), 2)}",
        ]
        if template_key:
            reasons.append(f"template bonus for {template_key}")
        if requirement.target_project_path and not bool(routing.get("automation_ready")):
            requirement_candidates.append({
                "candidate_type": "requirement",
                "action": "delay",
                "requirement_id": int(requirement.id),
                "signal_id": None,
                "title": str(requirement.title),
                "project_key": context["project_key"],
                "project_display_name": context["display_name"],
                "score": scheduler_score,
                "base_score": float(score.get("total") or 0.0),
                "scheduler_weight": float(context["scheduler_weight"]),
                "project_slot_available": False,
                "reason": f"automation not ready ({routing.get('readiness_status') or 'unknown'})",
                "reasons": reasons + [f"automation not ready ({routing.get('readiness_status') or 'unknown'})"],
                "template_key": template_key,
                "source": str(requirement.source),
                "preempt_requirement_id": None,
            })
            continue
        requirement_candidates.append({
            "candidate_type": "requirement",
            "action": "pending",
            "requirement_id": int(requirement.id),
            "signal_id": None,
            "title": str(requirement.title),
            "project_key": context["project_key"],
            "project_display_name": context["display_name"],
            "score": scheduler_score,
            "base_score": float(score.get("total") or 0.0),
            "scheduler_weight": float(context["scheduler_weight"]),
            "project_slot_available": active_count < quota,
            "reason": "",
            "reasons": reasons,
            "template_key": template_key,
            "source": str(requirement.source),
            "preempt_requirement_id": None,
        })

    signal_candidates: list[dict[str, Any]] = []
    for signal in list_optimization_signals(db, status="open"):
        breakdown = build_optimization_signal_score_breakdown(signal, project_map=project_catalog)
        project_key = str(signal.project_key or "org-ops")
        project = next((item for item in project_catalog.values() if str(item.get("project_key")) == project_key), None) or {}
        display_name = str(project.get("display_name") or project_key or "Org Ops")
        root_path = str(project.get("root_path") or signal.routing_target_path or signal.project_root_path or "")
        policy = dict(policy_by_root.get(root_path) or {})
        quota = int(policy.get("max_parallel_requirements") or 1)
        active_count = project_active_counts.get(project_key, 0)
        template_key = template_key_for_signal(str(signal.signal_type))
        scheduler_score = _weighted_scheduler_score(
            float(breakdown.get("total") or 0.0),
            scheduler_weight=float(policy.get("scheduler_weight") or 1.0),
            template_key=template_key,
            active_count=active_count,
            quota=quota,
        )
        signal_candidates.append({
            "candidate_type": "signal",
            "action": "pending",
            "requirement_id": None,
            "signal_id": int(signal.id),
            "title": str(signal.title),
            "project_key": project_key,
            "project_display_name": display_name,
            "score": scheduler_score,
            "base_score": float(breakdown.get("total") or 0.0),
            "scheduler_weight": float(policy.get("scheduler_weight") or 1.0),
            "project_slot_available": active_count < quota,
            "reason": "",
            "reasons": [
                f"signal score {round(float(breakdown.get('total') or 0.0), 2)}",
                f"intake recommendation {breakdown.get('intake_recommendation')}",
            ],
            "template_key": template_key,
            "source": "optimization_signal",
            "preempt_requirement_id": None,
            "auto_intake_eligible": bool(breakdown.get("auto_intake_eligible")),
        })

    available_slots = max(global_capacity - len(running_requirements), 0)
    project_allocations = dict(project_active_counts)
    pending = sorted(requirement_candidates + signal_candidates, key=lambda item: float(item.get("score") or 0.0), reverse=True)

    weakest_running = min(
        (item for item in decisions if item["action"] == "running"),
        key=lambda item: float(item.get("score") or 0.0),
        default=None,
    )

    for candidate in pending:
        if candidate.get("action") == "delay":
            decisions.append(candidate)
            continue
        project_key = str(candidate["project_key"])
        quota = int(
            next(
                (
                    policy.get("max_parallel_requirements")
                    for policy in policy_by_root.values()
                    if str(policy.get("project_key")) == project_key
                ),
                1,
            )
            or 1
        )
        if project_allocations.get(project_key, 0) >= quota:
            candidate["action"] = "delay"
            candidate["reason"] = "project quota full"
            candidate["reasons"] = list(candidate["reasons"]) + ["project quota full"]
            decisions.append(candidate)
            continue
        if available_slots > 0:
            candidate["action"] = "intake" if candidate["candidate_type"] == "signal" else "start"
            candidate["reason"] = "scheduled in current capacity window"
            candidate["reasons"] = list(candidate["reasons"]) + ["scheduled in current capacity window"]
            available_slots -= 1
            project_allocations[project_key] = project_allocations.get(project_key, 0) + 1
            decisions.append(candidate)
            continue
        if weakest_running and float(candidate.get("score") or 0.0) >= float(weakest_running.get("score") or 0.0) + PREEMPT_THRESHOLD:
            candidate["action"] = "preempt_candidate"
            candidate["preempt_requirement_id"] = weakest_running.get("requirement_id")
            candidate["reason"] = f"higher-value than running requirement #{weakest_running.get('requirement_id')}"
            candidate["reasons"] = list(candidate["reasons"]) + [candidate["reason"]]
        else:
            candidate["action"] = "delay"
            candidate["reason"] = "global capacity full"
            candidate["reasons"] = list(candidate["reasons"]) + ["global capacity full"]
        decisions.append(candidate)

    project_states = []
    for project in sorted(project_catalog.values(), key=lambda item: str(item.get("display_name") or "")):
        project_key = str(project.get("project_key") or "")
        policy = next((item for item in policy_by_root.values() if str(item.get("project_key")) == project_key), {})
        project_states.append({
            "project_key": project_key,
            "display_name": str(project.get("display_name") or project_key),
            "root_path": str(project.get("root_path") or ""),
            "active_count": int(project_active_counts.get(project_key, 0)),
            "queued_count": int(project_queue_counts.get(project_key, 0)),
            "max_parallel_requirements": int(policy.get("max_parallel_requirements") or 1),
            "scheduler_weight": float(policy.get("scheduler_weight") or 1.0),
            "readiness_status": str(project.get("readiness_status") or "unknown"),
            "readiness_score": int(project.get("readiness_score") or 0),
        })

    return {
        "global_capacity": global_capacity,
        "active_count": len(running_requirements),
        "available_slots": max(global_capacity - len(running_requirements), 0),
        "generated_at": datetime.now(timezone.utc),
        "project_states": project_states,
        "decisions": decisions,
        "started_ids": [],
        "created_requirement_ids": [],
        "skipped": [],
    }


def validate_requirement_start_capacity(db: Session, requirement: RequirementRow) -> str | None:
    plan = build_portfolio_schedule(db)
    global_capacity = int(plan["global_capacity"])
    running_count = int(plan["active_count"])
    if str(requirement.status) == "in_progress":
        running_count = max(0, running_count - 1)
    if running_count >= global_capacity:
        return f"全局调度容量已满（{running_count}/{global_capacity}），请等待空闲槽位。"
    score = build_requirement_score_breakdown(db, requirement)
    policy_by_root, _ = _project_policy_maps(db)
    project_catalog = build_project_catalog(db)
    context = _project_context_for_requirement(requirement, score, policy_by_root, project_catalog)
    project_key = str(context["project_key"])
    active_count = next((int(item["active_count"]) for item in plan["project_states"] if str(item["project_key"]) == project_key), 0)
    if str(requirement.status) in {"paused", "in_progress"}:
        active_count = max(0, active_count - 1)
    quota = int(context["max_parallel_requirements"])
    if active_count >= quota:
        return f"项目调度槽位已满（{project_key}: {active_count}/{quota}），请等待当前项目工作完成。"
    return None


def execute_portfolio_schedule(db: Session) -> dict[str, Any]:
    plan = build_portfolio_schedule(db)
    started_ids: list[int] = []
    created_requirement_ids: list[int] = []
    skipped: list[str] = []

    from server.services.optimization_signals import create_requirement_from_signal
    from server.services.workflow_orchestrator import plan_requirement, start_requirement

    for decision in plan["decisions"]:
        action = str(decision.get("action") or "")
        if action not in {"start", "intake"}:
            continue
        try:
            if action == "intake":
                signal_id = int(decision["signal_id"])
                _signal, detail = create_requirement_from_signal(db, signal_id=signal_id, auto_start=False)
                requirement_id = int(detail.requirement.id)
                created_requirement_ids.append(requirement_id)
            else:
                requirement_id = int(decision["requirement_id"])
            requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
            if requirement is None:
                raise ValueError(f"requirement #{requirement_id} not found")
            if int(requirement.current_plan_version or 0) == 0 or requirement.active_workflow_run_id is None:
                plan_requirement(db, requirement_id)
            start_requirement(db, requirement_id)
            started_ids.append(requirement_id)
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{decision.get('title')}: {exc}")

    plan["started_ids"] = started_ids
    plan["created_requirement_ids"] = created_requirement_ids
    plan["skipped"] = skipped
    return plan
