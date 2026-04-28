"""Lane item projections for the nested Mission Board."""

from __future__ import annotations

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
from server.services.planning.mission_board_helpers import (
    ACTIVE_REQUIREMENT_STATUSES,
    mission_item,
    sort_mission_items,
)
from server.services.planning.product_opportunities import (
    ProductOpportunityRow,
    ensure_product_opportunity_table,
    product_opportunity_to_dict,
)

ACTIVE_CANDIDATE_STATUSES = {"pending", "approved"}
ACTIVE_WORKFLOW_STATUSES = {
    "pending",
    "queued",
    "running",
    "awaiting_operator",
    "failed",
    "blocked",
}
TERMINAL_RELEASE_TASK_STATUSES = {"completed", "failed", "cancelled"}
ACTIVE_SOCIAL_DRAFT_STATUSES = {
    "draft",
    "generating",
    "needs_review",
    "approved",
    "failed",
}
ACTIVE_REPLY_STATUSES = {"needs_review", "failed"}
ACTIVE_REPOST_STATUSES = {"candidate", "failed"}


def candidate_next_action(row: RequirementCandidateRow) -> str:
    status = str(row.status or "pending")
    if status == "pending":
        return "Review candidate and approve, defer, or reject."
    if status == "approved":
        return "Materialize into a requirement or approve-and-run."
    if status == "validation_failed":
        return "Inspect Fail-Closed reason before retrying Planner."
    return "Inspect candidate lineage."


def requirement_next_action(row: RequirementRow) -> str:
    status = str(row.status or "draft")
    if status in {"draft", "planning", "ready"}:
        return "Submit or start the declarative workflow."
    if status in {"executing", "running"}:
        return "Watch workflow evidence and blockers."
    if status in {"awaiting_operator", "failed", "blocked", "needs_revision"}:
        return "Open requirement/workflow and resolve blocker."
    return "Inspect requirement outcome."


def workflow_next_action(row: WorkflowRunRow) -> str:
    status = str(row.status or "pending")
    current_state = str(row.current_state or "")
    if current_state == "awaiting_operator" or status == "awaiting_operator":
        return "Review the human gate decision summary."
    if status in {"failed", "blocked"}:
        return "Inspect root cause and decide retry, repair, or stop."
    if status in {"running", "pending", "queued"}:
        return "Monitor state timeline and evidence."
    return "Open workflow evidence."


def release_next_action(row: ReleaseTaskRow) -> str:
    status = str(row.status or "requested")
    if status == "requested":
        return "Check PR gate and deploy staging when eligible."
    if status == "failed":
        return "Open release task detail and inspect deploy failure."
    return "Inspect deployment evidence."


def product_planner_items(db: Session, manifest_id: int) -> list[dict[str, Any]]:
    ensure_product_opportunity_table(db)
    rows = (
        db.query(ProductOpportunityRow)
        .filter(
            ProductOpportunityRow.manifest_id == manifest_id,
            ProductOpportunityRow.status == "proposed",
        )
        .order_by(
            ProductOpportunityRow.updated_at.desc(), ProductOpportunityRow.id.desc()
        )
        .limit(20)
        .all()
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = product_opportunity_to_dict(row)
        items.append(
            mission_item(
                item_id=f"product_opportunity:{row.id}",
                item_type="product_opportunity",
                title=str(row.title or "Product Opportunity"),
                status=str(row.status or "proposed"),
                risk_level=str(row.risk_level or "normal"),
                next_action=str(
                    row.next_action
                    or "Review opportunity and create, defer, or reject the goal proposal."
                ),
                deep_link="/planning?tab=opportunities",
                evidence_label=str(payload.get("success_metric") or ""),
                updated_at=row.updated_at,
            )
        )
    return items


def growth_items(db: Session) -> list[dict[str, Any]]:
    return sort_mission_items(
        [*social_draft_items(db), *reply_draft_items(db), *repost_candidate_items(db)]
    )


def social_draft_items(db: Session) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in (
        db.query(SocialPostDraftRow)
        .filter(SocialPostDraftRow.status.in_(sorted(ACTIVE_SOCIAL_DRAFT_STATUSES)))
        .order_by(SocialPostDraftRow.updated_at.desc(), SocialPostDraftRow.id.desc())
        .limit(20)
        .all()
    ):
        items.append(
            mission_item(
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
    return items


def reply_draft_items(db: Session) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in (
        db.query(SocialReplyItemRow)
        .filter(SocialReplyItemRow.status.in_(sorted(ACTIVE_REPLY_STATUSES)))
        .order_by(SocialReplyItemRow.updated_at.desc(), SocialReplyItemRow.id.desc())
        .limit(20)
        .all()
    ):
        items.append(
            mission_item(
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
    return items


def repost_candidate_items(db: Session) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in (
        db.query(SocialRepostCandidateRow)
        .filter(SocialRepostCandidateRow.status.in_(sorted(ACTIVE_REPOST_STATUSES)))
        .order_by(
            SocialRepostCandidateRow.updated_at.desc(),
            SocialRepostCandidateRow.id.desc(),
        )
        .limit(20)
        .all()
    ):
        items.append(
            mission_item(
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
    return items


def software_items(
    db: Session, manifest_id: int, goal_key: str | None
) -> list[dict[str, Any]]:
    if not goal_key:
        return []
    return sort_mission_items(
        [
            *candidate_items(db, manifest_id, goal_key),
            *requirement_items(db, manifest_id, goal_key),
            *workflow_items(db, manifest_id, goal_key),
            *release_task_items(db, manifest_id, goal_key),
        ]
    )


def candidate_items(
    db: Session, manifest_id: int, goal_key: str
) -> list[dict[str, Any]]:
    rows = (
        db.query(RequirementCandidateRow)
        .filter(
            RequirementCandidateRow.manifest_id == manifest_id,
            RequirementCandidateRow.goal_key == goal_key,
            RequirementCandidateRow.status.in_(
                ("pending", "approved", "validation_failed")
            ),
        )
        .order_by(
            RequirementCandidateRow.updated_at.desc(), RequirementCandidateRow.id.desc()
        )
        .limit(20)
        .all()
    )
    return [
        mission_item(
            item_id=f"candidate:{row.id}",
            item_type="requirement_candidate",
            title=str(row.title or f"Candidate #{row.id}"),
            status=str(row.status or "pending"),
            risk_level=str(row.risk_level or "normal"),
            next_action=candidate_next_action(row),
            deep_link=f"/planning?tab=engineering&candidate={row.id}",
            evidence_label=str(row.workflow_key or ""),
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def requirement_items(
    db: Session, manifest_id: int, goal_key: str
) -> list[dict[str, Any]]:
    rows = (
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
    return [
        mission_item(
            item_id=f"requirement:{row.id}",
            item_type="requirement",
            title=str(row.title or f"Requirement #{row.id}"),
            status=str(row.status or "draft"),
            risk_level=str(row.priority or "normal"),
            next_action=requirement_next_action(row),
            deep_link=f"/requirements/{row.id}",
            evidence_label=str(row.project_key or ""),
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def workflow_items(
    db: Session, manifest_id: int, goal_key: str
) -> list[dict[str, Any]]:
    rows = (
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
    return [
        mission_item(
            item_id=f"workflow:{row.id}",
            item_type="workflow",
            title=f"Workflow #{row.id}: {row.workflow_key}",
            status=str(row.current_state or row.status or "pending"),
            risk_level=str(row.risk_level or "normal"),
            next_action=workflow_next_action(row),
            deep_link=f"/workflows/{row.id}",
            evidence_label=str(row.resolution or ""),
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def release_task_items(
    db: Session, manifest_id: int, goal_key: str
) -> list[dict[str, Any]]:
    rows = (
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
    return [
        mission_item(
            item_id=f"release_task:{row.id}",
            item_type="release_task",
            title=f"{row.project_display_name or row.project_key} · {row.environment}",
            status=str(row.status or "requested"),
            risk_level="normal",
            next_action=release_next_action(row),
            deep_link="/releases",
            evidence_label=str(row.branch_name or ""),
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def unassigned_items(db: Session, manifest_id: int) -> list[dict[str, Any]]:
    return sort_mission_items(
        [
            *unassigned_candidate_items(db, manifest_id),
            *unassigned_requirement_items(db, manifest_id),
            *unassigned_workflow_items(db, manifest_id),
        ]
    )


def unassigned_candidate_items(db: Session, manifest_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(RequirementCandidateRow)
        .filter(
            RequirementCandidateRow.manifest_id == manifest_id,
            RequirementCandidateRow.goal_key == "",
            RequirementCandidateRow.status.in_(sorted(ACTIVE_CANDIDATE_STATUSES)),
        )
        .order_by(
            RequirementCandidateRow.updated_at.desc(), RequirementCandidateRow.id.desc()
        )
        .limit(50)
        .all()
    )
    return [
        mission_item(
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
        for row in rows
    ]


def unassigned_requirement_items(db: Session, manifest_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(RequirementRow)
        .filter(
            RequirementRow.operating_manifest_id == manifest_id,
            or_(RequirementRow.goal_key.is_(None), RequirementRow.goal_key == ""),
            RequirementRow.status.in_(sorted(ACTIVE_REQUIREMENT_STATUSES)),
        )
        .order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc())
        .limit(50)
        .all()
    )
    return [
        mission_item(
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
        for row in rows
    ]


def unassigned_workflow_items(db: Session, manifest_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(WorkflowRunRow)
        .filter(
            WorkflowRunRow.operating_manifest_id == manifest_id,
            or_(WorkflowRunRow.goal_key.is_(None), WorkflowRunRow.goal_key == ""),
            WorkflowRunRow.status.in_(sorted(ACTIVE_WORKFLOW_STATUSES)),
        )
        .order_by(WorkflowRunRow.updated_at.desc(), WorkflowRunRow.id.desc())
        .limit(50)
        .all()
    )
    return [
        mission_item(
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
        for row in rows
    ]
