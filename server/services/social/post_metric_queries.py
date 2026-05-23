"""Read-only social post metric query projections."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from server import config
from server.database import SocialPostDraftRow, SocialPostMetricRow
from server.schemas_social_metrics import (
    SocialPostMetricDailyOut,
    SocialPostMetricDailyQueryOut,
    SocialPostMetricDetailOut,
    SocialPostMetricQueryOut,
    SocialPostMetricTopPostOut,
)
from server.services.social.publishing import DEFAULT_X_HANDLE
from server.services.social.post_metric_projection import (
    metric_base_out,
    metric_engagement,
    metric_post_index,
    metric_top_post_out,
)


def _operator_zone() -> ZoneInfo:
    try:
        return ZoneInfo(config.OPERATOR_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _local_day_bounds_utc(
    *, date_from: str | None = None, date_to: str | None = None
) -> tuple[datetime | None, datetime | None, str | None, str | None]:
    zone = _operator_zone()
    parsed_from = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else None
    parsed_to = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else None
    start = (
        datetime.combine(parsed_from, time.min, tzinfo=zone).astimezone(timezone.utc)
        if parsed_from
        else None
    )
    end = (
        datetime.combine(
            parsed_to + timedelta(days=1), time.min, tzinfo=zone
        ).astimezone(timezone.utc)
        if parsed_to
        else None
    )
    return (
        start,
        end,
        parsed_from.isoformat() if parsed_from else None,
        parsed_to.isoformat() if parsed_to else None,
    )


def _x_post_url(external_post_id: str | None) -> str | None:
    return (
        f"https://x.com/{DEFAULT_X_HANDLE}/status/{external_post_id}"
        if external_post_id
        else None
    )


def _body_excerpt(value: str | None, *, max_chars: int = 240) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    return text if len(text) <= max_chars else f"{text[: max_chars - 1]}…"


def _post_for_metric(
    row: SocialPostMetricRow, posts_by_id: dict[int, SocialPostDraftRow]
) -> SocialPostDraftRow | None:
    if row.post_id is None:
        return None
    return posts_by_id.get(int(row.post_id))


def _post_attr(post: SocialPostDraftRow | None, attr: str):
    return getattr(post, attr, None)


def _metric_detail_out(
    row: SocialPostMetricRow, posts_by_id: dict[int, SocialPostDraftRow]
) -> SocialPostMetricDetailOut:
    post = _post_for_metric(row, posts_by_id)
    return SocialPostMetricDetailOut(
        **metric_base_out(row).model_dump(),
        post_title=_post_attr(post, "title"),
        post_body_excerpt=_body_excerpt(_post_attr(post, "body_text")),
        post_status=_post_attr(post, "status"),
        published_at=_post_attr(post, "published_at"),
        x_url=_x_post_url(row.external_post_id),
        created_at=row.created_at,
    )


def _metric_top_post_out(
    row: SocialPostMetricRow, posts_by_id: dict[int, SocialPostDraftRow]
) -> SocialPostMetricTopPostOut:
    return metric_top_post_out(row, _post_for_metric(row, posts_by_id))


def _query_metric_rows(
    db: Session,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    post_id: int | None = None,
    external_post_id: str | None = None,
):
    start, end, _from, _to = _local_day_bounds_utc(date_from=date_from, date_to=date_to)
    query = db.query(SocialPostMetricRow)
    if start is not None:
        query = query.filter(SocialPostMetricRow.observed_at >= start)
    if end is not None:
        query = query.filter(SocialPostMetricRow.observed_at < end)
    if post_id is not None:
        query = query.filter(SocialPostMetricRow.post_id == int(post_id))
    if external_post_id:
        query = query.filter(
            SocialPostMetricRow.external_post_id == str(external_post_id).strip()
        )
    return query


def query_social_post_metrics(
    db: Session,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    post_id: int | None = None,
    external_post_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> SocialPostMetricQueryOut:
    bounded_limit = max(1, min(100, int(limit or 20)))
    bounded_offset = max(0, int(offset or 0))
    query = _query_metric_rows(
        db,
        date_from=date_from,
        date_to=date_to,
        post_id=post_id,
        external_post_id=external_post_id,
    )
    rows = (
        query.order_by(
            SocialPostMetricRow.observed_at.desc(), SocialPostMetricRow.id.desc()
        )
        .limit(bounded_limit)
        .offset(bounded_offset)
        .all()
    )
    posts_by_id = metric_post_index(db, rows).posts_by_id
    return SocialPostMetricQueryOut(
        items=[_metric_detail_out(row, posts_by_id) for row in rows],
        total=int(query.count()),
        limit=bounded_limit,
        offset=bounded_offset,
    )


def get_social_post_metric(
    db: Session, metric_id: int
) -> SocialPostMetricDetailOut | None:
    row = (
        db.query(SocialPostMetricRow)
        .filter(SocialPostMetricRow.id == int(metric_id))
        .first()
    )
    if row is None:
        return None
    return _metric_detail_out(row, metric_post_index(db, [row]).posts_by_id)


def _default_daily_window(
    date_from: str | None, date_to: str | None
) -> tuple[str | None, str | None]:
    if date_from is not None or date_to is not None:
        return date_from, date_to
    today = datetime.now(timezone.utc).astimezone(_operator_zone()).date()
    return (today - timedelta(days=29)).isoformat(), today.isoformat()


def _metric_buckets(
    rows: list[SocialPostMetricRow], zone: ZoneInfo
) -> dict[str, list[SocialPostMetricRow]]:
    buckets: dict[str, list[SocialPostMetricRow]] = {}
    for row in rows:
        observed = _ensure_utc(row.observed_at) or datetime.now(timezone.utc)
        buckets.setdefault(observed.astimezone(zone).date().isoformat(), []).append(row)
    return buckets


def _sum_metric(rows: list[SocialPostMetricRow], attr: str) -> int:
    return sum(int(getattr(row, attr) or 0) for row in rows)


def _unique_metric_keys(rows: list[SocialPostMetricRow]) -> set[str]:
    return {str(row.external_post_id or row.post_id or row.id) for row in rows}


def _last_observed_at(rows: list[SocialPostMetricRow]):
    return max((row.observed_at for row in rows if row.observed_at), default=None)


def _top_post_or_none(
    rows: list[SocialPostMetricRow], posts_by_id: dict[int, SocialPostDraftRow]
) -> SocialPostMetricTopPostOut | None:
    top_row = max(rows, key=metric_engagement, default=None)
    if top_row is None:
        return None
    return _metric_top_post_out(top_row, posts_by_id)


def _daily_metric_out(
    db: Session, local_date: str, bucket_rows: list[SocialPostMetricRow]
) -> SocialPostMetricDailyOut:
    likes = _sum_metric(bucket_rows, "likes")
    replies = _sum_metric(bucket_rows, "replies")
    reposts = _sum_metric(bucket_rows, "reposts")
    clicks = _sum_metric(bucket_rows, "link_clicks")
    unique_posts = _unique_metric_keys(bucket_rows)
    posts_by_id = metric_post_index(db, bucket_rows).posts_by_id
    return SocialPostMetricDailyOut(
        local_date=local_date,
        observed_post_count=len(unique_posts),
        metric_row_count=len(bucket_rows),
        total_impressions=_sum_metric(bucket_rows, "impressions"),
        total_likes=likes,
        total_replies=replies,
        total_reposts=reposts,
        total_link_clicks=clicks,
        average_engagement=round(
            (likes + replies + reposts + clicks) / max(1, len(unique_posts)), 2
        ),
        top_post=_top_post_or_none(bucket_rows, posts_by_id),
        last_observed_at=_last_observed_at(bucket_rows),
    )


def query_social_post_metric_daily(
    db: Session,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> SocialPostMetricDailyQueryOut:
    zone = _operator_zone()
    date_from, date_to = _default_daily_window(date_from, date_to)
    _start, _end, normalized_from, normalized_to = _local_day_bounds_utc(
        date_from=date_from, date_to=date_to
    )
    rows = (
        _query_metric_rows(db, date_from=normalized_from, date_to=normalized_to)
        .order_by(SocialPostMetricRow.observed_at.desc(), SocialPostMetricRow.id.desc())
        .all()
    )
    daily_items = [
        _daily_metric_out(db, local_date, bucket_rows)
        for local_date, bucket_rows in sorted(
            _metric_buckets(rows, zone).items(), reverse=True
        )
    ]
    bounded_limit = max(1, min(100, int(limit or 30)))
    bounded_offset = max(0, int(offset or 0))
    return SocialPostMetricDailyQueryOut(
        items=daily_items[bounded_offset : bounded_offset + bounded_limit],
        total=len(daily_items),
        limit=bounded_limit,
        offset=bounded_offset,
        date_from=normalized_from,
        date_to=normalized_to,
    )
