"""Nested mission board projection for Goal Mission Lanes.

This module intentionally returns a tree-shaped projection.  The frontend can
render it with simple cards instead of introducing graph/canvas dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database import (
    ReleaseTaskRow,
    RequirementCandidateRow,
    RequirementRow,
    SocialPostDraftRow,
    SocialReplyItemRow,
    SocialRepostCandidateRow,
    WorkflowRunRow,
)
from server.services.planning.lifecycle import ensure_active_manifest, goal_to_dict
from server.services.planning.product_opportunities import (
    ProductOpportunityRow,
    ensure_product_opportunity_table,
    product_opportunity_to_dict,
)

LANE_KEYS = ("product_planner", "growth_lead", "software_engineer")
TERMINAL_CANDIDATE_STATUSES = {"materialized", "rejected", "suppressed", "validation_failed"}
ACTIVE_CANDIDATE_STATUSES = {"pending", "approved"}
TERMINAL_REQUIREMENT_STATUSES = {"completed", "succeeded", "done", "cancelled", "deleted", "superseded"}
ACTIVE_REQUIREMENT_STATUSES = {
    "draft",
    "planning",
    "ready",
    "executing",
    "running",
    "awaiting_operator",
    "delivery_ready",
    "ready_for_merge",
    "failed",
    "blocked",
    "needs_revision",
}
TERMINAL_WORKFLOW_STATUSES = {"succeeded", "completed", "done", "cancelled", "archived"}
ACTIVE_WORKFLOW_STATUSES = {"pending", "queued", "running", "awaiting_operator", "failed", "blocked"}
TERMINAL_RELEASE_TASK_STATUSES = {"completed", "failed", "cancelled"}
ACTIVE_SOCIAL_DRAFT_STATUSES = {"draft", "generating", "needs_review", "approved", "failed"}
ACTIVE_REPLY_STATUSES = {"needs_review", "failed"}
ACTIVE_REPOST_STATUSES = {"candidate", "failed"}


def _iso(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _item(
    *,
    item_id: str,
    item_type: str,
    title: str,
    status: str,
    risk_level: str = "normal",
    next_action: str = "",
    deep_link: str | None = None,
    evidence_label: str = "",
    updated_at: Any = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": item_type,
        "title": title,
        "status": status,
        "risk_level": risk_level,
        "next_action": next_action,
        "deep_link": deep_link,
        "evidence_label": evidence_label,
        "updated_at": _iso(updated_at),
    }


def _priority(item: dict[str, Any]) -> tuple[int, str]:
    status = str(item.get("status") or "")
    item_type = str(item.get("type") or "")
    severity = {
        "failed": 0,
        "blocked": 0,
        "awaiting_operator": 1,
        "needs_review": 1,
        "pending": 2,
        "approved": 2,
        "running": 2,
        "requested": 3,
    }.get(status, 4)
    type_boost = 0 if item_type in {"product_opportunity", "workflow", "requirement_candidate"} else 1
    return (severity + type_boost, str(item.get("updated_at") or ""))


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=_priority)[:50]


def _candidate_next_action(row: RequirementCandidateRow) -> str:
    status = str(row.status or "pending")
    if status == "pending":
        return "Review candidate and approve, defer, or reject."
    if status == "approved":
        return "Materialize into a requirement or approve-and-run."
    if status == "validation_failed":
        return "Inspect Fail-Closed reason before retrying Planner."
    return "Inspect candidate lineage."


def _requirement_next_action(row: RequirementRow) -> str:
    status = str(row.status or "draft")
    if status in {"draft", "planning", "ready"}:
        return "Submit or start the declarative workflow."
    if status in {"executing", "running"}:
        return "Watch workflow evidence and blockers."
    if status in {"awaiting_operator", "failed", "blocked", "needs_revision"}:
        return "Open requirement/workflow and resolve blocker."
    return "Inspect requirement outcome."


def _workflow_next_action(row: WorkflowRunRow) -> str:
    status = str(row.status or "pending")
    current_state = str(row.current_state or "")
    if current_state == "awaiting_operator" or status == "awaiting_operator":
        return "Review the human gate decision summary."
    if status in {"failed", "blocked"}:
        return "Inspect root cause and decide retry, repair, or stop."
    if status in {"running", "pending", "queued"}:
        return "Monitor state timeline and evidence."
    return "Open workflow evidence."


def _release_next_action(row: ReleaseTaskRow) -> str:
    status = str(row.status or "requested")
    if status == "requested":
        return "Check PR gate and deploy staging when eligible."
    if status == "failed":
        return "Open release task detail and inspect deploy failure."
    return "Inspect deployment evidence."


def _proof_item(
    *,
    key: str,
    label: str,
    status: str,
    evidence_label: str,
    next_action: str,
    deep_link: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "evidence_label": evidence_label,
        "next_action": next_action,
        "deep_link": deep_link,
    }


def _goal_rows(db: Session, manifest_id: int):
    from server.database import PlanningGoalRow

    return (
        db.query(PlanningGoalRow)
        .filter(PlanningGoalRow.manifest_id == manifest_id)
        .order_by(PlanningGoalRow.status.asc(), PlanningGoalRow.id.asc())
        .all()
    )


def _active_goal(db: Session, manifest_id: int) -> dict[str, Any] | None:
    for row in _goal_rows(db, manifest_id):
        if str(row.status or "active") == "active":
            return goal_to_dict(row, include_intent=False)
    return None


def _product_planner_items(db: Session, manifest_id: int) -> list[dict[str, Any]]:
    ensure_product_opportunity_table(db)
    rows = (
        db.query(ProductOpportunityRow)
        .filter(
            ProductOpportunityRow.manifest_id == manifest_id,
            ProductOpportunityRow.status == "proposed",
        )
        .order_by(ProductOpportunityRow.updated_at.desc(), ProductOpportunityRow.id.desc())
        .limit(20)
        .all()
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = product_opportunity_to_dict(row)
        items.append(
            _item(
                item_id=f"product_opportunity:{row.id}",
                item_type="product_opportunity",
                title=str(row.title or "Product Opportunity"),
                status=str(row.status or "proposed"),
                risk_level=str(row.risk_level or "normal"),
                next_action=str(row.next_action or "Review opportunity and create, defer, or reject the goal proposal."),
                deep_link="/planning?tab=opportunities",
                evidence_label=str(payload.get("success_metric") or ""),
                updated_at=row.updated_at,
            )
        )
    return items


def _growth_items(db: Session) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in (
        db.query(SocialPostDraftRow)
        .filter(SocialPostDraftRow.status.in_(sorted(ACTIVE_SOCIAL_DRAFT_STATUSES)))
        .order_by(SocialPostDraftRow.updated_at.desc(), SocialPostDraftRow.id.desc())
        .limit(20)
        .all()
    ):
        items.append(
            _item(
                item_id=f"social_draft:{row.id}",
                item_type="publishing_draft",
                title=str(row.title or row.body_text or "X content draft")[:120],
                status=str(row.status or "needs_review"),
                risk_level="normal",
                next_action="Review, edit, publish, or reject the X draft.",
                deep_link="/publishing",
                evidence_label=f"{len(str(row.body_text or ''))} chars",
                updated_at=row.updated_at,
            )
        )
    for row in (
        db.query(SocialReplyItemRow)
        .filter(SocialReplyItemRow.status.in_(sorted(ACTIVE_REPLY_STATUSES)))
        .order_by(SocialReplyItemRow.updated_at.desc(), SocialReplyItemRow.id.desc())
        .limit(20)
        .all()
    ):
        items.append(
            _item(
                item_id=f"social_reply:{row.id}",
                item_type="reply_draft",
                title=f"Reply to @{row.source_author_handle or row.author_handle or 'unknown'}",
                status=str(row.status or "needs_review"),
                risk_level=str(row.risk_level or "normal"),
                next_action="Review reply draft before any public X reply.",
                deep_link="/publishing?tab=replies",
                evidence_label=str(row.source_url or ""),
                updated_at=row.updated_at,
            )
        )
    for row in (
        db.query(SocialRepostCandidateRow)
        .filter(SocialRepostCandidateRow.status.in_(sorted(ACTIVE_REPOST_STATUSES)))
        .order_by(SocialRepostCandidateRow.updated_at.desc(), SocialRepostCandidateRow.id.desc())
        .limit(20)
        .all()
    ):
        items.append(
            _item(
                item_id=f"social_repost:{row.id}",
                item_type="repost_candidate",
                title=f"Quote/repost candidate from @{row.author_handle or 'unknown'}",
                status=str(row.status or "candidate"),
                risk_level="normal",
                next_action="Open repost candidate and decide whether to quote or ignore.",
                deep_link="/publishing?tab=reposts",
                evidence_label=f"fit {int(row.relevance_score or 0)}",
                updated_at=row.updated_at,
            )
        )
    return _sort_items(items)


def _software_items(db: Session, manifest_id: int, goal_key: str | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if goal_key:
        candidates = (
            db.query(RequirementCandidateRow)
            .filter(
                RequirementCandidateRow.manifest_id == manifest_id,
                RequirementCandidateRow.goal_key == goal_key,
                RequirementCandidateRow.status.in_(("pending", "approved", "validation_failed")),
            )
            .order_by(RequirementCandidateRow.updated_at.desc(), RequirementCandidateRow.id.desc())
            .limit(20)
            .all()
        )
        for row in candidates:
            items.append(
                _item(
                    item_id=f"candidate:{row.id}",
                    item_type="requirement_candidate",
                    title=str(row.title or f"Candidate #{row.id}"),
                    status=str(row.status or "pending"),
                    risk_level=str(row.risk_level or "normal"),
                    next_action=_candidate_next_action(row),
                    deep_link=f"/planning?tab=engineering&candidate={row.id}",
                    evidence_label=str(row.workflow_key or ""),
                    updated_at=row.updated_at,
                )
            )
        requirements = (
            db.query(RequirementRow)
            .filter(
                RequirementRow.operating_manifest_id == manifest_id,
                RequirementRow.goal_key == goal_key,
                RequirementRow.status.in_(sorted(ACTIVE_REQUIREMENT_STATUSES)),
            )
            .order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc())
            .limit(20)
            .all()
        )
        for row in requirements:
            items.append(
                _item(
                    item_id=f"requirement:{row.id}",
                    item_type="requirement",
                    title=str(row.title or f"Requirement #{row.id}"),
                    status=str(row.status or "draft"),
                    risk_level=str(row.priority or "normal"),
                    next_action=_requirement_next_action(row),
                    deep_link=f"/requirements/{row.id}",
                    evidence_label=str(row.project_key or ""),
                    updated_at=row.updated_at,
                )
            )
        workflows = (
            db.query(WorkflowRunRow)
            .filter(
                WorkflowRunRow.operating_manifest_id == manifest_id,
                WorkflowRunRow.goal_key == goal_key,
                WorkflowRunRow.status.in_(sorted(ACTIVE_WORKFLOW_STATUSES)),
            )
            .order_by(WorkflowRunRow.updated_at.desc(), WorkflowRunRow.id.desc())
            .limit(20)
            .all()
        )
        for row in workflows:
            items.append(
                _item(
                    item_id=f"workflow:{row.id}",
                    item_type="workflow",
                    title=f"Workflow #{row.id}: {row.workflow_key}",
                    status=str(row.current_state or row.status or "pending"),
                    risk_level=str(row.risk_level or "normal"),
                    next_action=_workflow_next_action(row),
                    deep_link=f"/workflows/{row.id}",
                    evidence_label=str(row.resolution or ""),
                    updated_at=row.updated_at,
                )
            )
        release_tasks = (
            db.query(ReleaseTaskRow)
            .join(RequirementRow, ReleaseTaskRow.requirement_id == RequirementRow.id)
            .filter(
                RequirementRow.operating_manifest_id == manifest_id,
                RequirementRow.goal_key == goal_key,
                ReleaseTaskRow.status.notin_(sorted(TERMINAL_RELEASE_TASK_STATUSES)),
            )
            .order_by(ReleaseTaskRow.updated_at.desc(), ReleaseTaskRow.id.desc())
            .limit(20)
            .all()
        )
        for row in release_tasks:
            items.append(
                _item(
                    item_id=f"release_task:{row.id}",
                    item_type="release_task",
                    title=f"{row.project_display_name or row.project_key} · {row.environment}",
                    status=str(row.status or "requested"),
                    risk_level="normal",
                    next_action=_release_next_action(row),
                    deep_link="/releases",
                    evidence_label=str(row.branch_name or ""),
                    updated_at=row.updated_at,
                )
            )
    return _sort_items(items)


def _active_goal_traction_proof(
    db: Session,
    *,
    manifest_id: int,
    goal_key: str | None,
    lanes: dict[str, list[dict[str, Any]]],
    unassigned_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Project public-preview traction proof without inventing green states."""

    published_x_count = (
        db.query(SocialPostDraftRow)
        .filter(SocialPostDraftRow.status == "published")
        .count()
    )
    successful_release_count = (
        db.query(ReleaseTaskRow)
        .filter(ReleaseTaskRow.status == "completed")
        .count()
    )
    provider_release_count = (
        db.query(ReleaseTaskRow)
        .filter(
            ReleaseTaskRow.status == "completed",
            ReleaseTaskRow.project_key == "synapse-network-provider",
        )
        .count()
    )
    active_sdk_work_count = 0
    if goal_key:
        active_sdk_work_count = (
            db.query(RequirementRow)
            .filter(
                RequirementRow.operating_manifest_id == manifest_id,
                RequirementRow.goal_key == goal_key,
                RequirementRow.project_key.in_(["synapse-network-sdk", "synapse-network"]),
                RequirementRow.status.in_(sorted(ACTIVE_REQUIREMENT_STATUSES | TERMINAL_REQUIREMENT_STATUSES)),
            )
            .count()
        )

    items = [
        _proof_item(
            key="docs_staging_visits",
            label="Docs / staging visits",
            status="missing",
            evidence_label="analytics_unavailable",
            next_action="Connect docs/staging analytics or add an evidence source before claiming traffic proof.",
            deep_link="/planning?tab=opportunities",
        ),
        _proof_item(
            key="provider_onboarding",
            label="Provider onboarding proof",
            status="present" if provider_release_count else "missing",
            evidence_label=f"{provider_release_count} provider release(s)",
            next_action="Ship or verify Provider self-serve onboarding evidence.",
            deep_link="/releases",
        ),
        _proof_item(
            key="sdk_demo_completion",
            label="SDK demo completion",
            status="present" if active_sdk_work_count else "missing",
            evidence_label=f"{active_sdk_work_count} SDK-related work item(s)",
            next_action="Create or complete the SDK quickstart / agent demo requirement.",
            deep_link="/planning?tab=engineering",
        ),
        _proof_item(
            key="x_engagement",
            label="X engagement proof",
            status="present" if published_x_count else "missing",
            evidence_label=f"{published_x_count} published X post(s)",
            next_action="Review Social Ops drafts, replies, reposts, and published effects.",
            deep_link="/publishing",
        ),
        _proof_item(
            key="staging_release",
            label="Staging release proof",
            status="present" if successful_release_count else "missing",
            evidence_label=f"{successful_release_count} completed release task(s)",
            next_action="Publish eligible staging tasks and verify online records.",
            deep_link="/releases",
        ),
        _proof_item(
            key="ops_lane_health",
            label="Ops lane health",
            status="blocked" if unassigned_items else "present",
            evidence_label=(
                f"{len(unassigned_items)} unassigned item(s)"
                if unassigned_items
                else ", ".join(f"{key}:{len(value)}" for key, value in lanes.items())
            ),
            next_action="Repair unassigned lineage before trusting the mission board.",
            deep_link="/planning?tab=unassigned" if unassigned_items else "/command-center",
        ),
    ]
    statuses = {str(item["status"]) for item in items}
    if "blocked" in statuses:
        overall = "blocked"
    elif "missing" in statuses:
        overall = "incomplete"
    else:
        overall = "present"
    return {
        "status": overall,
        "items": items,
    }


def _unassigned_items(db: Session, manifest_id: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in (
        db.query(RequirementCandidateRow)
        .filter(
            RequirementCandidateRow.manifest_id == manifest_id,
            RequirementCandidateRow.goal_key == "",
            RequirementCandidateRow.status.in_(sorted(ACTIVE_CANDIDATE_STATUSES)),
        )
        .order_by(RequirementCandidateRow.updated_at.desc(), RequirementCandidateRow.id.desc())
        .limit(50)
        .all()
    ):
        items.append(
            _item(
                item_id=f"candidate:{row.id}",
                item_type="requirement_candidate",
                title=str(row.title or f"Candidate #{row.id}"),
                status=str(row.status or "pending"),
                risk_level=str(row.risk_level or "normal"),
                next_action="Fix goal lineage or archive this orphaned candidate.",
                deep_link="/planning?tab=unassigned",
                evidence_label=str(row.project_key or ""),
                updated_at=row.updated_at,
            )
        )
    for row in (
        db.query(RequirementRow)
        .filter(
            RequirementRow.operating_manifest_id == manifest_id,
            or_(RequirementRow.goal_key.is_(None), RequirementRow.goal_key == ""),
            RequirementRow.status.in_(sorted(ACTIVE_REQUIREMENT_STATUSES)),
        )
        .order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc())
        .limit(50)
        .all()
    ):
        items.append(
            _item(
                item_id=f"requirement:{row.id}",
                item_type="requirement",
                title=str(row.title or f"Requirement #{row.id}"),
                status=str(row.status or "active"),
                risk_level=str(row.priority or "normal"),
                next_action="Attach to a goal lineage or cancel/archive if stale.",
                deep_link=f"/requirements/{row.id}",
                evidence_label=str(row.project_key or ""),
                updated_at=row.updated_at,
            )
        )
    for row in (
        db.query(WorkflowRunRow)
        .filter(
            WorkflowRunRow.operating_manifest_id == manifest_id,
            or_(WorkflowRunRow.goal_key.is_(None), WorkflowRunRow.goal_key == ""),
            WorkflowRunRow.status.in_(sorted(ACTIVE_WORKFLOW_STATUSES)),
        )
        .order_by(WorkflowRunRow.updated_at.desc(), WorkflowRunRow.id.desc())
        .limit(50)
        .all()
    ):
        items.append(
            _item(
                item_id=f"workflow:{row.id}",
                item_type="workflow",
                title=f"Workflow #{row.id}: {row.workflow_key}",
                status=str(row.current_state or row.status or "running"),
                risk_level=str(row.risk_level or "normal"),
                next_action="Repair missing goal_key lineage before this run disappears from mission context.",
                deep_link=f"/workflows/{row.id}",
                evidence_label=str(row.resolution or ""),
                updated_at=row.updated_at,
            )
        )
    return _sort_items(items)


def mission_board_snapshot(db: Session) -> dict[str, Any]:
    ensure_product_opportunity_table(db)
    manifest = ensure_active_manifest(db)
    manifest_id = int(manifest.id)
    active_goal = _active_goal(db, manifest_id)
    active_goal_key = str(active_goal.get("goal_key") or "") if active_goal else None
    lanes = {
        "product_planner": _product_planner_items(db, manifest_id),
        "growth_lead": _growth_items(db),
        "software_engineer": _software_items(db, manifest_id, active_goal_key),
    }
    unassigned_items = _unassigned_items(db, manifest_id)
    traction_proof = _active_goal_traction_proof(
        db,
        manifest_id=manifest_id,
        goal_key=active_goal_key,
        lanes=lanes,
        unassigned_items=unassigned_items,
    )
    next_actions: list[dict[str, Any]] = []
    for lane_key in LANE_KEYS:
        if lanes[lane_key]:
            first = lanes[lane_key][0]
            next_actions.append(
                {
                    "lane": lane_key,
                    "title": first["title"],
                    "next_action": first["next_action"],
                    "deep_link": first["deep_link"],
                    "status": first["status"],
                }
            )
    if unassigned_items:
        next_actions.insert(
            0,
            {
                "lane": "unassigned",
                "title": f"{len(unassigned_items)} unassigned active item(s)",
                "next_action": "Open unassigned queue and repair lineage.",
                "deep_link": "/planning?tab=unassigned",
                "status": "blocked",
            },
        )
    return {
        "active_goal": active_goal,
        "lanes": lanes,
        "lane_summary": {key: {"count": len(value)} for key, value in lanes.items()},
        "unassigned": {
            "count": len(unassigned_items),
            "items": unassigned_items,
        },
        "traction_proof": traction_proof,
        "next_actions": next_actions,
        "manifest": {
            "id": manifest_id,
            "version_name": str(manifest.version_name or ""),
            "cycle_label": str(manifest.cycle_label or ""),
            "updated_at": _iso(manifest.updated_at),
        },
    }
