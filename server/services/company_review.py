"""Company-level operating review aggregation and persistence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import CompanyOperatingReviewRow, RequirementRow
from server.schemas import CompanyReviewBundleMaterializeResultOut, RequirementCreate
from server.services.optimization_signals import list_optimization_signals, refresh_optimization_signals
from server.services.optimization_templates import build_template_instance, template_key_for_signal
from server.services.portfolio_scheduler import build_portfolio_schedule
from server.services.project_intelligence import build_project_catalog
from server.services.workflow_orchestrator import create_requirement


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _cycle_label(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    iso = moment.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


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
        f"Recommended next move: {lead_recommendation}."
    )


def _project_highlights(project_catalog: dict[str, dict[str, Any]], scheduler_plan: dict[str, Any]) -> list[dict[str, Any]]:
    scheduler_by_key = {
        str(item.get("project_key") or ""): dict(item)
        for item in scheduler_plan.get("project_states") or []
    }
    highlights: list[dict[str, Any]] = []
    for project in project_catalog.values():
        state = scheduler_by_key.get(str(project.get("project_key") or ""), {})
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


def _incidents(signals: list[Any]) -> list[dict[str, Any]]:
    incidents: list[dict[str, Any]] = []
    for signal in signals:
        severity = str(signal.severity or "medium")
        if severity not in {"critical", "high"} and str(signal.signal_type) not in {"delivery_blocker", "bug_report"}:
            continue
        incidents.append({
            "item_key": f"signal:{int(signal.id)}",
            "title": str(signal.title),
            "severity": severity,
            "summary": str(signal.summary),
            "project_key": str(signal.project_key or ""),
            "recommendation": "Convert this incident into a prioritized optimization requirement if it remains open.",
        })
    incidents.sort(key=lambda item: (_SEVERITY_RANK.get(item["severity"], 99), item["title"]))
    return incidents[:6]


def _recommendations(scheduler_plan: dict[str, Any]) -> list[dict[str, Any]]:
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
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    for item in bundle:
        if bool(item.get("approval_required")):
            decisions.append({
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
            decisions.append({
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
            decisions.append({
                "decision_key": f"risk:{item['item_key']}",
                "title": f"Review risk before autonomous promotion: {item['title']}",
                "decision_type": "risk_watch",
                "severity": str(item.get("severity") or "medium"),
                "summary": str(item.get("summary") or ""),
                "owner_hint": "reviewer",
                "related_bundle_item_key": None,
            })
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
        f"- Open portfolio risk: {top_risk}\n"
        f"- Approval-required scheduler items: {portfolio_summary['approval_required_decisions']}"
    )
    return {
        "title": "Operator Review Package",
        "summary_markdown": summary_markdown,
        "checklist": checklist,
        "decisions": decisions[:8],
        "recommended_bundle_item_keys": [str(item["bundle_item_key"]) for item in bundle[:3]],
    }


def build_operating_review_payload(db: Session) -> dict[str, Any]:
    refresh_optimization_signals(db)
    scheduler_plan = build_portfolio_schedule(db)
    project_catalog = build_project_catalog(db)
    signals = list_optimization_signals(db, status="open")
    requirements = {
        int(row.id): row
        for row in db.query(RequirementRow).all()
        if row.id is not None
    }

    portfolio_summary = {
        "active_requirements": int(scheduler_plan.get("active_count") or 0),
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
    }
    project_highlights = _project_highlights(project_catalog, scheduler_plan)
    bottlenecks = _bottlenecks(project_catalog, scheduler_plan)
    incidents = _incidents(signals)
    if not incidents:
        incidents = [
            {
                "item_key": f"derived-{item['item_key']}",
                "title": item["title"],
                "severity": item["severity"],
                "summary": item["summary"],
                "project_key": item.get("project_key"),
                "recommendation": item.get("recommendation"),
            }
            for item in bottlenecks
            if str(item.get("severity") or "medium") in {"high", "critical"}
        ][:4]
    next_cycle_recommendations = _recommendations(scheduler_plan)
    next_cycle_requirement_bundle = _next_cycle_requirement_bundle(
        project_catalog=project_catalog,
        recommendations=next_cycle_recommendations,
        bottlenecks=bottlenecks,
        incidents=incidents,
        signals=signals,
        requirements=requirements,
    )
    operator_review_package = _operator_review_package(
        cycle_label=_cycle_label(),
        bundle=next_cycle_requirement_bundle,
        bottlenecks=bottlenecks,
        incidents=incidents,
        portfolio_summary=portfolio_summary,
        project_highlights=project_highlights,
    )

    return {
        "cycle_label": _cycle_label(),
        "title": "Company Operating Review",
        "summary_markdown": _cycle_summary_markdown(portfolio_summary, bottlenecks, next_cycle_recommendations),
        "portfolio_summary": portfolio_summary,
        "project_highlights": project_highlights,
        "bottlenecks": bottlenecks,
        "incidents": incidents,
        "next_cycle_recommendations": next_cycle_recommendations,
        "next_cycle_requirement_bundle": next_cycle_requirement_bundle,
        "operator_review_package": operator_review_package,
        "source_snapshot": {
            "scheduler_generated_at": scheduler_plan.get("generated_at").isoformat()
            if getattr(scheduler_plan.get("generated_at"), "isoformat", None)
            else scheduler_plan.get("generated_at"),
            "open_signal_ids": [int(signal.id) for signal in signals[:12]],
            "started_ids": list(scheduler_plan.get("started_ids") or []),
            "rebalanced_ids": list(scheduler_plan.get("rebalanced_ids") or []),
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
        "next_cycle_recommendations": list(payload.get("next_cycle_recommendations") or []),
        "next_cycle_requirement_bundle": list(payload.get("next_cycle_requirement_bundle") or []),
        "operator_review_package": dict(payload.get("operator_review_package") or {
            "title": "Operator Review Package",
            "summary_markdown": "No operator package generated yet.",
            "checklist": [],
            "decisions": [],
            "recommended_bundle_item_keys": [],
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
        payload_json=json.dumps(
            {
                "portfolio_summary": payload["portfolio_summary"],
                "project_highlights": payload["project_highlights"],
                "bottlenecks": payload["bottlenecks"],
                "incidents": payload["incidents"],
                "next_cycle_recommendations": payload["next_cycle_recommendations"],
                "next_cycle_requirement_bundle": payload["next_cycle_requirement_bundle"],
                "operator_review_package": payload["operator_review_package"],
                "source_snapshot": payload["source_snapshot"],
            },
            ensure_ascii=False,
        ),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
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

    return CompanyReviewBundleMaterializeResultOut(
        review_id=int(review_id),
        created_requirement_ids=created_requirement_ids,
        reused_requirement_ids=sorted(set(reused_requirement_ids)),
        skipped_bundle_item_keys=skipped_bundle_item_keys,
        items=items,
    )
