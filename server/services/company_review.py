"""Company-level operating review aggregation and persistence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import CompanyOperatingReviewRow
from server.services.optimization_signals import list_optimization_signals, refresh_optimization_signals
from server.services.portfolio_scheduler import build_portfolio_schedule
from server.services.project_intelligence import build_project_catalog


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _cycle_label(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    iso = moment.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _summary_markdown(
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
        if str(project.get("readiness_status") or "unknown") not in {"ready", "policy_only"} and int(project.get("queued_count") or 0) > 0:
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
        })
    decisions.sort(key=lambda item: (-item["score"], item["action"]))
    return decisions[:6]


def build_operating_review_payload(db: Session) -> dict[str, Any]:
    refresh_optimization_signals(db)
    scheduler_plan = build_portfolio_schedule(db)
    project_catalog = build_project_catalog(db)
    signals = list_optimization_signals(db, status="open")

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

    return {
        "cycle_label": _cycle_label(),
        "title": "Company Operating Review",
        "summary_markdown": _summary_markdown(portfolio_summary, bottlenecks, next_cycle_recommendations),
        "portfolio_summary": portfolio_summary,
        "project_highlights": project_highlights,
        "bottlenecks": bottlenecks,
        "incidents": incidents,
        "next_cycle_recommendations": next_cycle_recommendations,
        "source_snapshot": {
            "scheduler_generated_at": scheduler_plan.get("generated_at").isoformat()
            if getattr(scheduler_plan.get("generated_at"), "isoformat", None)
            else scheduler_plan.get("generated_at"),
            "open_signal_ids": [int(signal.id) for signal in signals[:12]],
            "started_ids": list(scheduler_plan.get("started_ids") or []),
            "rebalanced_ids": list(scheduler_plan.get("rebalanced_ids") or []),
        },
    }


def company_review_to_dict(row: CompanyOperatingReviewRow) -> dict[str, Any]:
    payload = json.loads(row.payload_json or "{}")
    if not isinstance(payload, dict):
        payload = {}
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
