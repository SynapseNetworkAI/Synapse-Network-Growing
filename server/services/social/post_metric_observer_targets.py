"""Metric observation target selection and row construction."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from server.database import SocialPostDraftRow, SocialPostMetricRow, SocialReplyItemRow
from server.database_social_distribution import SocialDistributionTaskRow
from server.services.social.post_metric_features import (
    MetricTarget,
    json_dumps,
    json_object,
    metric_metadata_for_target,
    metric_value,
)

_X_STATUS_ID_PATTERN = re.compile(r"/status(?:es)?/([0-9]+)")


def published_targets_for_metrics(
    db: Session, *, max_records: int
) -> list[MetricTarget]:
    targets = [
        *_published_posts_for_metrics(db, max_records=max_records),
        *_published_distribution_tasks_for_metrics(db, max_records=max_records),
        *_published_replies_for_metrics(db, max_records=max_records),
    ]
    deduped: dict[str, MetricTarget] = {}
    for target in targets:
        deduped.setdefault(target.external_post_id, target)
    return list(deduped.values())[: max(1, min(100, int(max_records or 20)))]


def _published_posts_for_metrics(
    db: Session, *, max_records: int
) -> list[MetricTarget]:
    rows = (
        db.query(SocialPostDraftRow)
        .filter(
            SocialPostDraftRow.platform == "x",
            SocialPostDraftRow.status == "published",
            SocialPostDraftRow.external_post_id.isnot(None),
            SocialPostDraftRow.external_post_id != "",
        )
        .order_by(
            SocialPostDraftRow.published_at.desc().nullslast(),
            SocialPostDraftRow.updated_at.desc(),
            SocialPostDraftRow.id.desc(),
        )
        .limit(max(1, min(100, int(max_records or 20))))
        .all()
    )
    return [
        MetricTarget(
            "legacy_post",
            int(row.id),
            None,
            str(row.external_post_id),
            row.title,
            row.body_text or "",
            row.status,
            row.published_at,
            dict(json_object(row.raw_agent_output_json)),
        )
        for row in rows
    ]


def _published_distribution_tasks_for_metrics(
    db: Session, *, max_records: int
) -> list[MetricTarget]:
    rows = (
        db.query(SocialDistributionTaskRow)
        .filter(
            SocialDistributionTaskRow.platform == "x",
            SocialDistributionTaskRow.status == "live",
        )
        .order_by(
            SocialDistributionTaskRow.updated_at.desc(),
            SocialDistributionTaskRow.id.desc(),
        )
        .limit(max(1, min(100, int(max_records or 20))))
        .all()
    )
    return [
        MetricTarget(
            "distribution_task",
            None,
            int(row.id),
            external_id,
            row.platform_title,
            row.platform_body or "",
            row.status,
            row.updated_at,
            dict(json_object(row.metadata_json)),
        )
        for row in rows
        if (
            external_id := _observable_x_post_id(
                row.external_post_id, row.published_url
            )
        )
    ]


def _published_replies_for_metrics(
    db: Session, *, max_records: int
) -> list[MetricTarget]:
    rows = (
        db.query(SocialReplyItemRow)
        .filter(
            SocialReplyItemRow.platform == "x",
            SocialReplyItemRow.published_external_post_id.isnot(None),
            SocialReplyItemRow.published_external_post_id != "",
        )
        .order_by(SocialReplyItemRow.updated_at.desc(), SocialReplyItemRow.id.desc())
        .limit(max(1, min(100, int(max_records or 20))))
        .all()
    )
    return [
        MetricTarget(
            "reply",
            None,
            None,
            external_id,
            f"Reply to {row.source_author_handle or row.source_post_id or 'X post'}",
            row.suggested_reply or row.incoming_text or "",
            row.status,
            row.updated_at,
            {
                **dict(json_object(row.metadata_json)),
                "reply_item_id": int(row.id),
                "source_post_id": row.source_post_id,
                "source_url": row.source_url,
                "source_author_handle": row.source_author_handle,
            },
        )
        for row in rows
        if (external_id := _observable_x_post_id(row.published_external_post_id, None))
    ]


def _observable_x_post_id(*values: str | None) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if not text or text.startswith("manual:"):
            continue
        if text.isdigit():
            return text
        match = _X_STATUS_ID_PATTERN.search(text)
        if match:
            return match.group(1)
    return None


def metric_row_from_x_post(
    target: MetricTarget,
    x_post: Any,
    *,
    observed_at: Any,
    private_metrics_available: bool,
) -> SocialPostMetricRow:
    public = x_post.public_metrics or {}
    owner = x_post.non_public_metrics or {}
    organic = x_post.organic_metrics or {}
    summary = _metric_summary(private_metrics_available, owner, organic)
    metadata = metric_metadata_for_target(
        target,
        x_post=x_post,
        private_metrics_available=private_metrics_available,
        metric_source=_metric_source(private_metrics_available, owner, organic),
    )
    return SocialPostMetricRow(
        post_id=target.post_id,
        external_post_id=str(target.external_post_id),
        impressions=metric_value(
            owner, organic, public, keys=("impression_count", "view_count")
        ),
        likes=metric_value(public, keys=("like_count",)),
        replies=metric_value(public, keys=("reply_count",)),
        reposts=metric_value(public, keys=("retweet_count", "repost_count")),
        follows=metric_value(owner, organic, keys=("user_profile_clicks", "follows")),
        link_clicks=_link_clicks(metadata, owner, organic),
        profile_visits=metric_value(
            owner, organic, keys=("user_profile_clicks", "profile_visits")
        ),
        bookmarks=metric_value(
            public, owner, organic, keys=("bookmark_count", "bookmarks")
        ),
        format_kind=str(metadata.get("format_kind") or "") or None,
        posted_at=target.published_at,
        summary=summary,
        metadata_json=json_dumps(metadata),
        observed_at=observed_at,
    )


def _metric_source(
    private_metrics_available: bool, owner: dict[str, Any], organic: dict[str, Any]
) -> str:
    return (
        "x_api_owner"
        if private_metrics_available and (owner or organic)
        else "x_api_public"
    )


def _metric_summary(
    private_metrics_available: bool, owner: dict[str, Any], organic: dict[str, Any]
) -> str:
    summary = "X metrics observed from public metrics"
    return (
        f"{summary} and owner metrics."
        if private_metrics_available and (owner or organic)
        else f"{summary}."
    )


def _link_clicks(
    metadata: Mapping[str, Any], owner: dict[str, Any], organic: dict[str, Any]
) -> int:
    if not metadata.get("has_url"):
        return 0
    return metric_value(owner, organic, keys=("url_link_clicks", "link_clicks"))
