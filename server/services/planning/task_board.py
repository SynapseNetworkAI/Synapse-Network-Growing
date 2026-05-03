"""Requirement-first Planning Task Board projection.

The board is intentionally a lightweight projection. Requirements are the
source of truth for delivery cards; workflow runs, PRs, and releases are only
linked evidence shown from detail surfaces.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database import RequirementCandidateRow, RequirementRow, utcnow
from server.services.planning.product_opportunities import (
    ProductOpportunityRow,
    ensure_product_opportunity_table,
)
from server.services.result_objects import ServiceObjectResult, service_object_result

BOARD_COLUMNS = (
    ("backlog", "Backlog", "Ideas and early planning items."),
    ("todo", "Todo", "Validated work ready for operator or runner action."),
    ("in_progress", "In Progress", "Agent or deterministic workflow is running."),
    ("human_review", "Human Review", "Human Gate or operator judgment required."),
    ("rework", "Rework", "Failed, blocked, or needs repair."),
    ("delivery", "Delivery", "PR, release, deploy, or publish handoff."),
    ("done", "Done", "Recently completed outcomes."),
    ("canceled", "Canceled", "Closed, rejected, or superseded work."),
)
VISIBLE_COLUMNS = {key for key, _, _ in BOARD_COLUMNS if key != "canceled"}

REQUIREMENT_STATUS_COLUMNS = {
    "draft": "backlog",
    "proposed": "backlog",
    "planning": "backlog",
    "ready": "todo",
    "approved": "todo",
    "delivery_ready": "todo",
    "in_progress": "in_progress",
    "running": "in_progress",
    "executing": "in_progress",
    "awaiting_operator": "human_review",
    "needs_review": "human_review",
    "failed": "rework",
    "blocked": "rework",
    "validation_failed": "rework",
    "needs_revision": "rework",
    "pr_opened": "delivery",
    "pr_created": "delivery",
    "releasing": "delivery",
    "deploy_requested": "delivery",
    "publishing": "delivery",
    "completed": "done",
    "done": "done",
    "published": "done",
    "online": "done",
    "succeeded": "done",
    "cancelled": "canceled",
    "canceled": "canceled",
    "deleted": "canceled",
    "rejected": "canceled",
    "dropped": "canceled",
    "superseded": "canceled",
}
CANDIDATE_STATUS_COLUMNS = {
    "pending": "backlog",
    "approved": "todo",
    "validation_failed": "rework",
}


def _iso(value: Any) -> str | None:
    if not value:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _requirement_column(row: RequirementRow) -> str:
    for value in (row.status, row.workflow_state, row.phase):
        key = REQUIREMENT_STATUS_COLUMNS.get(_normalize_status(value))
        if key:
            return key
    return "backlog"


def _candidate_column(row: RequirementCandidateRow) -> str:
    return CANDIDATE_STATUS_COLUMNS.get(_normalize_status(row.status), "backlog")


def _requirement_next_action(row: RequirementRow, column_key: str) -> str:
    if column_key == "backlog":
        return "Clarify scope, acceptance, and readiness before execution."
    if column_key == "todo":
        return "Start or resume the declarative workflow when policy allows."
    if column_key == "in_progress":
        return "Monitor workflow heartbeat and evidence from the detail page."
    if column_key == "human_review":
        return "Open the human gate or workflow detail and make a decision."
    if column_key == "rework":
        return "Inspect root cause, repair context, then retry from a checkpoint."
    if column_key == "delivery":
        return "Review PR/release evidence and complete delivery handoff."
    if column_key == "done":
        return "Inspect delivered evidence or online record."
    return "Inspect task history."


def _delivery_label(row: RequirementRow) -> str:
    if row.active_workflow_run_id:
        return f"Workflow #{int(row.active_workflow_run_id)}"
    if row.completed_at:
        return "Completed"
    if row.failure_reason:
        return "Failure recorded"
    return str(row.project_key or row.workflow_family or "")


def _requirement_card(row: RequirementRow) -> dict[str, Any]:
    column_key = _requirement_column(row)
    return {
        "id": f"requirement:{int(row.id)}",
        "object_id": int(row.id),
        "card_kind": "requirement",
        "task_key": f"REQ-{int(row.id)}",
        "title": str(row.title or f"Requirement #{int(row.id)}"),
        "status": str(row.status or "draft"),
        "column_key": column_key,
        "goal_key": str(row.goal_key or ""),
        "project_key": str(row.project_key or ""),
        "lane": "software_engineer",
        "priority": str(row.priority or "normal"),
        "risk_level": str(row.priority or "normal"),
        "updated_at": _iso(row.updated_at),
        "next_action": _requirement_next_action(row, column_key),
        "deep_link": f"/requirements/{int(row.id)}",
        "detail_api": f"/api/requirements/{int(row.id)}",
        "latest_workflow_run_id": int(row.active_workflow_run_id)
        if row.active_workflow_run_id
        else None,
        "delivery_label": _delivery_label(row),
        "description": str(row.description_markdown or "")[:280],
    }


def _candidate_card(row: RequirementCandidateRow) -> dict[str, Any]:
    column_key = _candidate_column(row)
    return {
        "id": f"candidate:{int(row.id)}",
        "object_id": int(row.id),
        "card_kind": "intake",
        "intake_type": "requirement_candidate",
        "task_key": f"RC-{int(row.id)}",
        "title": str(row.title or f"Candidate #{int(row.id)}"),
        "status": str(row.status or "pending"),
        "column_key": column_key,
        "goal_key": str(row.goal_key or ""),
        "project_key": str(row.project_key or ""),
        "lane": "software_engineer",
        "priority": str(row.priority or "normal"),
        "risk_level": str(row.risk_level or "normal"),
        "updated_at": _iso(row.updated_at),
        "next_action": "Review, materialize, or repair this intake candidate.",
        "deep_link": f"/planning?tab=engineering&candidate={int(row.id)}",
        "detail_api": f"/api/planning/candidates/{int(row.id)}",
        "latest_workflow_run_id": None,
        "delivery_label": str(row.workflow_key or ""),
        "description": str(row.description_markdown or "")[:280],
    }


def _opportunity_card(row: ProductOpportunityRow) -> dict[str, Any]:
    return {
        "id": f"product_opportunity:{int(row.id)}",
        "object_id": int(row.id),
        "card_kind": "intake",
        "intake_type": "product_opportunity",
        "task_key": f"OPP-{int(row.id)}",
        "title": str(row.title or f"Product Opportunity #{int(row.id)}"),
        "status": str(row.status or "proposed"),
        "column_key": "backlog",
        "goal_key": str(row.suggested_goal_key or ""),
        "project_key": "",
        "lane": str(row.recommended_lane or "product_planner"),
        "priority": "normal",
        "risk_level": str(row.risk_level or "normal"),
        "updated_at": _iso(row.updated_at),
        "next_action": str(
            row.next_action or "Review opportunity and convert, defer, or reject."
        ),
        "deep_link": f"/planning?tab=opportunities&opportunity={int(row.id)}",
        "detail_api": f"/api/planning/product-opportunities/{int(row.id)}",
        "latest_workflow_run_id": None,
        "delivery_label": str(row.success_metric or ""),
        "description": str(row.problem or "")[:280],
    }


def _active_requirement_rows(
    db: Session, *, include_done_days: int
) -> list[RequirementRow]:
    cutoff = utcnow() - timedelta(days=max(1, include_done_days))
    return (
        db.query(RequirementRow)
        .filter(
            or_(
                RequirementRow.status.notin_(
                    ("completed", "done", "published", "online")
                ),
                RequirementRow.updated_at >= cutoff,
            )
        )
        .order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc())
        .limit(300)
        .all()
    )


def _candidate_rows(db: Session) -> list[RequirementCandidateRow]:
    return (
        db.query(RequirementCandidateRow)
        .filter(
            RequirementCandidateRow.materialized_requirement_id.is_(None),
            RequirementCandidateRow.status.in_(
                ("pending", "approved", "validation_failed")
            ),
        )
        .order_by(
            RequirementCandidateRow.updated_at.desc(), RequirementCandidateRow.id.desc()
        )
        .limit(100)
        .all()
    )


def _opportunity_rows(db: Session) -> list[ProductOpportunityRow]:
    ensure_product_opportunity_table(db)
    return (
        db.query(ProductOpportunityRow)
        .filter(ProductOpportunityRow.status == "proposed")
        .order_by(
            ProductOpportunityRow.updated_at.desc(), ProductOpportunityRow.id.desc()
        )
        .limit(100)
        .all()
    )


def _empty_columns() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key, _, _ in BOARD_COLUMNS}


def _sort_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        cards, key=lambda item: str(item.get("updated_at") or ""), reverse=True
    )


@service_object_result
def planning_task_board_snapshot(
    db: Session, *, include_done_days: int = 7
) -> ServiceObjectResult:
    done_days = max(1, min(int(include_done_days or 7), 90))
    grouped = _empty_columns()
    for row in _active_requirement_rows(db, include_done_days=done_days):
        card = _requirement_card(row)
        grouped.setdefault(str(card["column_key"]), []).append(card)
    for row in _opportunity_rows(db):
        card = _opportunity_card(row)
        grouped.setdefault(str(card["column_key"]), []).append(card)
    for row in _candidate_rows(db):
        card = _candidate_card(row)
        grouped.setdefault(str(card["column_key"]), []).append(card)

    columns = []
    for key, title, description in BOARD_COLUMNS:
        cards = _sort_cards(grouped.get(key, []))
        columns.append(
            {
                "key": key,
                "title": title,
                "description": description,
                "hidden": key not in VISIBLE_COLUMNS,
                "count": len(cards),
                "cards": cards,
            }
        )
    return {
        "columns": columns,
        "summary": {
            "total": sum(len(items) for items in grouped.values()),
            "visible_total": sum(
                len(items) for key, items in grouped.items() if key in VISIBLE_COLUMNS
            ),
            "include_done_days": done_days,
        },
        "generated_at": _iso(utcnow()),
    }
