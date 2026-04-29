"""Social/Growth lane projections for Mission Workbench."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database import (
    SocialPostDraftRow,
    SocialPostMetricRow,
    SocialReplyItemRow,
    SocialRepostCandidateRow,
    utcnow,
)
from server.services.planning.mission_board_helpers import (
    mission_item,
    sort_mission_items,
)
from server.services.result_objects import ServiceListResult, service_list_result

ACTIVE_SOCIAL_DRAFT_STATUSES = {
    "draft",
    "generating",
    "needs_review",
    "approved",
}
ACTIVE_REPOST_STATUSES = {"candidate", "failed"}
SOCIAL_DAILY_DRAFT_TARGET_COUNT = 3
RECENT_PUBLISHED_SOCIAL_DRAFT_DAYS = 7


@service_list_result
def growth_items(db: Session) -> ServiceListResult:
    """Return Growth Lead summary items plus active/recent published drafts."""

    return sort_mission_items([*social_summary_items(db), *social_draft_items(db)])


@service_list_result
def social_summary_items(db: Session) -> ServiceListResult:
    active_drafts = _count_active_drafts(db)
    failed_drafts = _count_failed_drafts(db)
    pending_replies = _count_pending_replies(db)
    pending_reposts = _count_pending_reposts(db)
    latest_metric = (
        db.query(SocialPostMetricRow)
        .order_by(SocialPostMetricRow.observed_at.desc())
        .first()
    )
    latest_draft = (
        db.query(SocialPostDraftRow)
        .order_by(SocialPostDraftRow.updated_at.desc())
        .first()
    )
    return [
        _daily_inventory_item(active_drafts, failed_drafts, latest_draft),
        _review_queue_item(pending_replies, pending_reposts, latest_draft),
        _metrics_loop_item(latest_metric),
    ]


def _count_active_drafts(db: Session) -> int:
    return (
        db.query(SocialPostDraftRow)
        .filter(
            SocialPostDraftRow.status.in_(("generating", "needs_review", "approved"))
        )
        .count()
    )


def _count_failed_drafts(db: Session) -> int:
    return (
        db.query(SocialPostDraftRow)
        .filter(SocialPostDraftRow.status == "failed")
        .count()
    )


def _count_pending_replies(db: Session) -> int:
    return (
        db.query(SocialReplyItemRow)
        .filter(SocialReplyItemRow.status == "needs_review")
        .count()
    )


def _count_pending_reposts(db: Session) -> int:
    return (
        db.query(SocialRepostCandidateRow)
        .filter(SocialRepostCandidateRow.status == "candidate")
        .count()
    )


def _daily_inventory_status(active_drafts: int, failed_drafts: int) -> str:
    if active_drafts >= SOCIAL_DAILY_DRAFT_TARGET_COUNT:
        return "needs_review"
    if failed_drafts:
        return "blocked"
    if active_drafts:
        return "needs_review"
    return "pending"


def _daily_inventory_item(
    active_drafts: int,
    failed_drafts: int,
    latest_draft: SocialPostDraftRow | None,
) -> dict[str, Any]:
    return mission_item(
        item_id="social_summary:daily_draft_inventory",
        item_type="social_daily_inventory",
        title="Daily X draft inventory",
        status=_daily_inventory_status(active_drafts, failed_drafts),
        risk_level="normal",
        next_action="Open Publishing 今日队列 to review drafts or regenerate failed planner output.",
        deep_link="/publishing?tab=drafts",
        evidence_label=f"{active_drafts}/{SOCIAL_DAILY_DRAFT_TARGET_COUNT} active drafts · {failed_drafts} historical failures",
        updated_at=latest_draft.updated_at if latest_draft else None,
    )


def _review_queue_item(
    pending_replies: int,
    pending_reposts: int,
    latest_draft: SocialPostDraftRow | None,
) -> dict[str, Any]:
    return mission_item(
        item_id="social_summary:publishing_review_queue",
        item_type="social_review_queue",
        title="Publishing review queue",
        status="needs_review" if pending_replies or pending_reposts else "active",
        risk_level="normal",
        next_action="Review X drafts, replies, and repost candidates inside Publishing; public actions remain human-gated.",
        deep_link="/publishing",
        evidence_label=f"{pending_replies} replies · {pending_reposts} repost candidates",
        updated_at=latest_draft.updated_at if latest_draft else None,
    )


def _metrics_loop_item(latest_metric: SocialPostMetricRow | None) -> dict[str, Any]:
    return mission_item(
        item_id="social_summary:published_metrics_loop",
        item_type="social_metrics_loop",
        title="Published-effect metrics loop",
        status="completed" if latest_metric else "pending",
        risk_level="normal",
        next_action="Open Publishing 已发布效果 to inspect observed X metrics and planner feedback.",
        deep_link="/publishing?tab=metrics",
        evidence_label=f"latest observed {latest_metric.observed_at.isoformat()}"
        if latest_metric
        else "metrics not observed yet",
        updated_at=latest_metric.observed_at if latest_metric else None,
    )


@service_list_result
def social_draft_items(db: Session) -> ServiceListResult:
    items: list[dict[str, Any]] = []
    published_cutoff = utcnow() - timedelta(days=RECENT_PUBLISHED_SOCIAL_DRAFT_DAYS)
    for row in (
        db.query(SocialPostDraftRow)
        .filter(
            or_(
                SocialPostDraftRow.status.in_(sorted(ACTIVE_SOCIAL_DRAFT_STATUSES)),
                (
                    (SocialPostDraftRow.status == "published")
                    & (SocialPostDraftRow.published_at >= published_cutoff)
                ),
            )
        )
        .order_by(SocialPostDraftRow.updated_at.desc(), SocialPostDraftRow.id.desc())
        .limit(20)
        .all()
    ):
        has_metrics = (
            db.query(SocialPostMetricRow.id)
            .filter(SocialPostMetricRow.post_id == row.id)
            .first()
            is not None
        )
        title = f"#{int(row.id)} · {row.title or row.body_text or 'X content draft'}"
        item = mission_item(
            item_id=f"social_draft:{row.id}",
            item_type="publishing_draft",
            title=title[:140],
            status=str(row.status or "needs_review"),
            risk_level="normal",
            next_action=_social_draft_next_action(row),
            deep_link="/publishing?tab=drafts",
            evidence_label=_social_draft_evidence_label(row),
            updated_at=row.updated_at,
        )
        item.root.update(
            {
                "process_stages": _social_draft_process_stages(row, has_metrics),
                "external_post_id": row.external_post_id,
                "external_url": _social_draft_external_url(row),
                "published_at": row.published_at.isoformat()
                if row.published_at
                else None,
            }
        )
        items.append(item)
    return items


def _social_draft_next_action(row: SocialPostDraftRow) -> str:
    status = str(row.status or "needs_review")
    if status == "published":
        return "Published to X. Open the post or inspect published-effect metrics."
    if status == "approved":
        return "Publish to X or make a final edit before publishing."
    return "Review, edit, publish, or reject the X draft."


def _social_draft_evidence_label(row: SocialPostDraftRow) -> str:
    if row.external_post_id:
        return f"X post {row.external_post_id}"
    return str(row.failure_summary or f"{len(str(row.body_text or ''))} chars")


def _social_draft_external_url(row: SocialPostDraftRow) -> str | None:
    account = getattr(row, "account", None)
    handle = getattr(account, "handle", None)
    if not handle or not row.external_post_id:
        return None
    return f"https://x.com/{handle}/status/{row.external_post_id}"


def _social_draft_process_stages(
    row: SocialPostDraftRow, has_metrics: bool
) -> list[dict[str, str]]:
    status = str(row.status or "needs_review")
    if status == "failed":
        states = ("blocked", "missing", "missing", "missing", "missing")
    elif status == "generating":
        states = ("running", "missing", "missing", "missing", "missing")
    elif status in {"draft", "needs_review"}:
        states = ("completed", "waiting", "missing", "missing", "missing")
    elif status == "approved":
        states = ("completed", "completed", "waiting", "missing", "missing")
    elif status == "published":
        states = (
            "completed",
            "completed",
            "completed",
            "completed",
            "completed" if has_metrics else "missing",
        )
    else:
        states = ("missing", "missing", "missing", "missing", "missing")
    labels = (
        ("generated", "Generated"),
        ("needs_review", "Needs Review"),
        ("approved", "Approved/Edited"),
        ("published", "Published"),
        ("metrics", "Metrics"),
    )
    return [
        {"key": key, "label": label, "status": state}
        for (key, label), state in zip(labels, states, strict=True)
    ]


@service_list_result
def repost_candidate_items(db: Session) -> ServiceListResult:
    """Return repost candidates for callers that need social detail outside Workbench."""

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
