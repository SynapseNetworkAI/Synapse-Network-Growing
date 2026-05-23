"""X post metrics observation and summaries."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.database import SocialPostDraftRow, SocialPostMetricRow, utcnow
from server.schemas_social_metrics import (
    SocialPostMetricOut,
    SocialPostMetricSummaryOut,
    SocialPostMetricTopPostOut,
)
from server.services.result_objects import ServiceObjectResult, service_object_result
from server.services.social.publishing import (
    DEFAULT_X_SECRET_REF,
    SocialPublishError,
    _bounded_excerpt,
    _record_x_read_budget_event,
    _x_read_budget_local_date,
    _x_read_budget_remaining,
    ensure_default_social_account,
    x_oauth_token_provider,
)
from server.services.social.post_metric_projection import (
    metric_base_out,
    metric_engagement,
    metric_post_index,
    metric_top_post_out,
)
from server.services.social.x_client import (
    XApiAuthError,
    XApiClient,
    XApiRateLimitError,
    XApiTransientError,
)


def list_social_post_metrics(db: Session) -> list[SocialPostMetricOut]:
    rows = (
        db.query(SocialPostMetricRow)
        .order_by(SocialPostMetricRow.observed_at.desc(), SocialPostMetricRow.id.desc())
        .limit(100)
        .all()
    )
    return [metric_base_out(row) for row in rows]


def _latest_social_metric_rows(
    db: Session, *, limit: int = 100
) -> list[SocialPostMetricRow]:
    rows = (
        db.query(SocialPostMetricRow)
        .order_by(SocialPostMetricRow.observed_at.desc(), SocialPostMetricRow.id.desc())
        .limit(max(1, int(limit)))
        .all()
    )
    latest: dict[str, SocialPostMetricRow] = {}
    for row in rows:
        key = str(row.external_post_id or row.post_id or row.id)
        if key not in latest:
            latest[key] = row
    return list(latest.values())


def _metric_summary_counts(
    rows: list[SocialPostMetricRow],
) -> tuple[int, int, int, int]:
    return (
        sum(int(row.likes or 0) for row in rows),
        sum(int(row.replies or 0) for row in rows),
        sum(int(row.reposts or 0) for row in rows),
        sum(int(row.link_clicks or 0) for row in rows),
    )


def _metric_summary_top_posts(
    rows: list[SocialPostMetricRow], posts_by_id: dict[int, SocialPostDraftRow]
) -> list[SocialPostMetricTopPostOut]:
    top_rows = sorted(rows, key=metric_engagement, reverse=True)[:3]
    return [
        metric_top_post_out(
            row, posts_by_id.get(int(row.post_id)) if row.post_id is not None else None
        )
        for row in top_rows
    ]


def social_post_metrics_summary(db: Session) -> SocialPostMetricSummaryOut:
    rows = _latest_social_metric_rows(db)
    if not rows:
        return SocialPostMetricSummaryOut(
            diagnostic="No X post metrics recorded yet. Run x_social_post_observer_sweep after at least one published post has an external X post id."
        )
    posts_by_id = metric_post_index(db, rows).posts_by_id
    total_likes, total_replies, total_reposts, total_link_clicks = (
        _metric_summary_counts(rows)
    )
    engagement_total = total_likes + total_replies + total_reposts + total_link_clicks
    return SocialPostMetricSummaryOut(
        observed_post_count=len(rows),
        metric_row_count=db.query(SocialPostMetricRow).count(),
        total_impressions=sum(int(row.impressions or 0) for row in rows),
        total_likes=total_likes,
        total_replies=total_replies,
        total_reposts=total_reposts,
        total_link_clicks=total_link_clicks,
        average_engagement=round(engagement_total / max(1, len(rows)), 2),
        top_posts=_metric_summary_top_posts(rows, posts_by_id),
        last_observed_at=max(
            (row.observed_at for row in rows if row.observed_at), default=None
        ),
        diagnostic=None,
    )


def _metric_value(*maps: dict[str, Any] | None, keys: tuple[str, ...]) -> int:
    for payload in maps:
        if not isinstance(payload, dict):
            continue
        for key in keys:
            try:
                return int(payload.get(key) or 0)
            except (TypeError, ValueError):
                continue
    return 0


def _published_posts_for_metrics(
    db: Session, *, max_records: int
) -> list[SocialPostDraftRow]:
    return (
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


def _lookup_x_metric_posts(
    external_ids: list[str],
    *,
    db: Session | None = None,
    local_date: str | None = None,
    allow_owner_metrics: bool = True,
) -> tuple[list[Any], str | None, bool]:
    token_result = x_oauth_token_provider.get_access_token(DEFAULT_X_SECRET_REF)
    client = XApiClient(token_result.access_token)
    budget_date = local_date or _x_read_budget_local_date()
    if not allow_owner_metrics:
        try:
            return (
                client.get_posts_by_ids(external_ids, include_owner_metrics=False),
                "Owner metrics skipped because the daily X read budget has only one request left.",
                False,
            )
        finally:
            if db is not None:
                _record_x_read_budget_event(
                    db,
                    workflow_key="x_social_post_observer_sweep",
                    local_date=budget_date,
                    request_count=1,
                    detail="tweet_lookup public metrics",
                )
                db.commit()
    try:
        try:
            posts = client.get_posts_by_ids(external_ids, include_owner_metrics=True)
        finally:
            if db is not None:
                _record_x_read_budget_event(
                    db,
                    workflow_key="x_social_post_observer_sweep",
                    local_date=budget_date,
                    request_count=1,
                    detail="tweet_lookup owner metrics",
                )
                db.commit()
        return (posts, None, True)
    except XApiAuthError as exc:
        diagnostic = f"Owner metrics unavailable; falling back to public metrics only: {_bounded_excerpt(str(exc), max_chars=240)}"
        try:
            posts = client.get_posts_by_ids(external_ids, include_owner_metrics=False)
        finally:
            if db is not None:
                _record_x_read_budget_event(
                    db,
                    workflow_key="x_social_post_observer_sweep",
                    local_date=budget_date,
                    request_count=1,
                    detail="tweet_lookup public metrics fallback",
                )
                db.commit()
        return (posts, diagnostic, False)


def _metric_row_from_x_post(
    row: SocialPostDraftRow,
    x_post: Any,
    *,
    observed_at: Any,
    private_metrics_available: bool,
) -> SocialPostMetricRow:
    public = x_post.public_metrics or {}
    owner = x_post.non_public_metrics or {}
    organic = x_post.organic_metrics or {}
    summary = "X metrics observed from public metrics"
    summary += (
        " and owner metrics."
        if private_metrics_available and (owner or organic)
        else "."
    )
    return SocialPostMetricRow(
        post_id=int(row.id),
        external_post_id=str(row.external_post_id),
        impressions=_metric_value(
            owner, organic, public, keys=("impression_count", "view_count")
        ),
        likes=_metric_value(public, keys=("like_count",)),
        replies=_metric_value(public, keys=("reply_count",)),
        reposts=_metric_value(public, keys=("retweet_count", "repost_count")),
        follows=_metric_value(owner, organic, keys=("user_profile_clicks", "follows")),
        link_clicks=_metric_value(
            owner, organic, keys=("url_link_clicks", "link_clicks")
        ),
        summary=summary,
        observed_at=observed_at,
    )


@service_object_result
def run_x_social_post_observer_sweep(
    db: Session, *, max_records: int = 20
) -> ServiceObjectResult:
    """Read X metrics for published posts and write local observation rows."""

    ensure_default_social_account(db)
    rows = _published_posts_for_metrics(db, max_records=max_records)
    if not rows:
        return {
            "read_only": True,
            "workflow_key": "x_social_post_observer_sweep",
            "observed_count": 0,
            "created_metric_ids": [],
            "diagnostic": "No published X posts with external_post_id are available for metrics observation.",
        }
    local_date = _x_read_budget_local_date()
    remaining = _x_read_budget_remaining(db, local_date=local_date)
    if remaining["request_count"] <= 0:
        return {
            "read_only": True,
            "workflow_key": "x_social_post_observer_sweep",
            "observed_count": 0,
            "created_metric_ids": [],
            "budget_exhausted": True,
            "budget_local_date": local_date,
            "budget_remaining_requests": 0,
            "diagnostic": "Daily X read budget exhausted; metrics observer skipped external lookup.",
        }
    external_ids = [str(row.external_post_id) for row in rows if row.external_post_id]
    try:
        x_posts, diagnostic, private_metrics_available = _lookup_x_metric_posts(
            external_ids,
            db=db,
            local_date=local_date,
            allow_owner_metrics=remaining["request_count"] >= 2,
        )
    except XApiRateLimitError as exc:
        return {
            "read_only": True,
            "workflow_key": "x_social_post_observer_sweep",
            "observed_count": 0,
            "created_metric_ids": [],
            "rate_limited": True,
            "diagnostic": _bounded_excerpt(str(exc), max_chars=500),
        }
    except (SocialPublishError, XApiAuthError, XApiTransientError) as exc:
        return {
            "read_only": True,
            "workflow_key": "x_social_post_observer_sweep",
            "observed_count": 0,
            "created_metric_ids": [],
            "diagnostic": f"X metrics observer unavailable: {_bounded_excerpt(str(exc), max_chars=500)}",
        }

    posts_by_external_id = {post.id: post for post in x_posts}
    created_ids: list[int] = []
    missing_external_ids: list[str] = []
    observed_at = utcnow()
    for row in rows:
        x_post = posts_by_external_id.get(str(row.external_post_id))
        if x_post is None:
            missing_external_ids.append(str(row.external_post_id))
            continue
        metric = _metric_row_from_x_post(
            row,
            x_post,
            observed_at=observed_at,
            private_metrics_available=private_metrics_available,
        )
        db.add(metric)
        db.flush()
        created_ids.append(int(metric.id))
    db.commit()
    return {
        "read_only": True,
        "workflow_key": "x_social_post_observer_sweep",
        "observed_count": len(created_ids),
        "created_metric_ids": created_ids,
        "post_ids": [int(row.id) for row in rows],
        "external_post_ids": external_ids,
        "missing_external_ids": missing_external_ids,
        "private_metrics_available": private_metrics_available,
        "budget_local_date": local_date,
        "budget_remaining_requests": _x_read_budget_remaining(
            db, local_date=local_date
        )["request_count"],
        "diagnostic": diagnostic,
    }
