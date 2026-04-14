"""Composition helpers for company review payload assembly."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


def _build_portfolio_summary(
    *,
    scheduler_plan: dict[str, Any],
    project_catalog: dict[str, dict[str, Any]],
    signals: list[Any],
    runtime_metrics: dict[str, Any],
    bug_summary: dict[str, Any],
    human_gate_hotspots: list[dict[str, Any]],
    cross_project_bug_recoveries: list[dict[str, Any]],
    requirement_total: int,
) -> dict[str, Any]:
    """Assemble the portfolio summary section for the company review payload."""

    completion_rate = round(
        (int(runtime_metrics.get("completed_requirements") or 0) / requirement_total) * 100,
        1,
    ) if requirement_total else 0.0
    return {
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


def build_operating_review_payload(db: Session) -> dict[str, Any]:
    """Build the full company operating review payload using legacy helper chains."""

    from server.services.reviews.company_review import (
        _aggregate_runtime_metrics,
        _autonomous_coo_posture,
        _bug_backlog_summary,
        _bottlenecks,
        _cross_project_bug_recoveries,
        _cycle_label,
        _cycle_summary_markdown,
        _empty_runtime_metric_bucket,
        _human_gate_hotspots,
        _incidents,
        _next_cycle_requirement_bundle,
        _operator_review_package,
        _project_highlights,
        _recommendations,
        _workflow_rituals_summary,
    )
    from server.database import RequirementRow
    from server.services.signals.optimization_signals import list_optimization_signals, refresh_optimization_signals
    from server.services.scheduling.portfolio_scheduler import build_portfolio_schedule
    from server.services.projects.intelligence import build_project_catalog

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
    human_gate_hotspots, automation_candidates = _human_gate_hotspots(
        db,
        project_catalog=project_catalog,
        requirements=requirements,
    )
    portfolio_summary = _build_portfolio_summary(
        scheduler_plan=scheduler_plan,
        project_catalog=project_catalog,
        signals=signals,
        runtime_metrics=runtime_metrics,
        bug_summary=bug_summary,
        human_gate_hotspots=human_gate_hotspots,
        cross_project_bug_recoveries=cross_project_bug_recoveries,
        requirement_total=requirement_total,
    )
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


__all__ = [
    "_build_portfolio_summary",
    "build_operating_review_payload",
]
