"""Shared projections for social post metric rows."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from server.database import SocialPostDraftRow, SocialPostMetricRow
from server.schemas_social_metrics import (
    SocialPostMetricOut,
    SocialPostMetricTopPostOut,
)


@dataclass(frozen=True)
class MetricPostIndex:
    posts_by_id: dict[int, SocialPostDraftRow]


def metric_post_id(row: SocialPostMetricRow) -> int | None:
    return int(row.post_id) if row.post_id is not None else None


def metric_engagement(row: SocialPostMetricRow) -> int:
    return (
        int(row.likes or 0)
        + int(row.replies or 0)
        + int(row.reposts or 0)
        + int(row.link_clicks or 0)
    )


def metric_base_out(row: SocialPostMetricRow) -> SocialPostMetricOut:
    return SocialPostMetricOut(
        id=int(row.id),
        post_id=metric_post_id(row),
        external_post_id=row.external_post_id,
        impressions=int(row.impressions or 0),
        likes=int(row.likes or 0),
        replies=int(row.replies or 0),
        reposts=int(row.reposts or 0),
        follows=int(row.follows or 0),
        link_clicks=int(row.link_clicks or 0),
        summary=row.summary,
        observed_at=row.observed_at,
    )


def metric_post_index(db: Session, rows: list[SocialPostMetricRow]) -> MetricPostIndex:
    post_ids = [int(row.post_id) for row in rows if row.post_id is not None]
    if not post_ids:
        return MetricPostIndex(posts_by_id={})
    rows_by_id = db.query(SocialPostDraftRow).filter(
        SocialPostDraftRow.id.in_(post_ids)
    )
    return MetricPostIndex(posts_by_id={int(row.id): row for row in rows_by_id.all()})


def metric_top_post_out(
    row: SocialPostMetricRow, post: SocialPostDraftRow | None
) -> SocialPostMetricTopPostOut:
    return SocialPostMetricTopPostOut(
        post_id=metric_post_id(row),
        external_post_id=row.external_post_id,
        title=getattr(post, "title", None),
        impressions=int(row.impressions or 0),
        likes=int(row.likes or 0),
        replies=int(row.replies or 0),
        reposts=int(row.reposts or 0),
        link_clicks=int(row.link_clicks or 0),
        engagement_total=metric_engagement(row),
        observed_at=row.observed_at,
    )
