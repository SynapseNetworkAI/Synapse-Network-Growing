"""Account snapshots and weekly review generation for X metrics."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from server.database import SocialPostMetricRow, utcnow
from server.database_social_analytics import (
    SocialAccountSnapshotRow,
    SocialWeeklyReviewRow,
)
from server.schemas_social_metrics import (
    SocialAccountSnapshotOut,
    SocialWeeklyReviewOut,
)
from server.services.result_objects import ServiceObjectResult, service_object_result
from server.services.social.post_metric_features import (
    json_dumps,
    json_loads,
    metric_metadata,
    metric_value,
)
from server.services.social.publishing import (
    DEFAULT_X_SECRET_REF,
    SocialPublishError,
    _bounded_excerpt,
    ensure_default_social_account,
    x_oauth_token_provider,
)
from server.services.social.x_client import (
    XApiAuthError,
    XApiClient,
    XApiRateLimitError,
    XApiTransientError,
)


def _snapshot_out(
    row: SocialAccountSnapshotRow, previous: SocialAccountSnapshotRow | None
) -> SocialAccountSnapshotOut:
    return SocialAccountSnapshotOut(
        id=int(row.id),
        platform=row.platform,
        account_handle=row.account_handle,
        followers=int(row.followers or 0),
        following=int(row.following or 0),
        followers_delta=int(row.followers or 0) - int(previous.followers or 0)
        if previous
        else 0,
        profile_url=row.profile_url,
        summary=row.summary,
        observed_at=row.observed_at,
    )


def list_x_account_snapshots(db: Session, *, limit: int = 30, offset: int = 0):
    bounded_limit = max(1, min(100, int(limit or 30)))
    bounded_offset = max(0, int(offset or 0))
    query = db.query(SocialAccountSnapshotRow).filter(
        SocialAccountSnapshotRow.platform == "x"
    )
    rows = (
        query.order_by(
            SocialAccountSnapshotRow.observed_at.desc(),
            SocialAccountSnapshotRow.id.desc(),
        )
        .limit(bounded_limit)
        .offset(bounded_offset)
        .all()
    )
    previous_by_id = {
        int(row.id): rows[index + 1] if index + 1 < len(rows) else None
        for index, row in enumerate(rows)
    }
    return {
        "items": [_snapshot_out(row, previous_by_id[int(row.id)]) for row in rows],
        "total": int(query.count()),
        "limit": bounded_limit,
        "offset": bounded_offset,
    }


@service_object_result
def run_x_account_snapshot_sweep(db: Session) -> ServiceObjectResult:
    """Read official X account public metrics and write a daily snapshot."""

    account = ensure_default_social_account(db)
    try:
        token_result = x_oauth_token_provider.get_access_token(DEFAULT_X_SECRET_REF)
        client = XApiClient(token_result.access_token)
        user = client.get_user_by_username(account.handle)
    except (
        SocialPublishError,
        XApiAuthError,
        XApiRateLimitError,
        XApiTransientError,
    ) as exc:
        return {
            "read_only": True,
            "workflow_key": "x_account_snapshot_sweep",
            "created_snapshot_id": None,
            "diagnostic": f"X account snapshot unavailable: {_bounded_excerpt(str(exc), max_chars=500)}",
        }
    metrics = user.public_metrics or {}
    row = SocialAccountSnapshotRow(
        platform="x",
        account_handle=str(user.username or account.handle).lstrip("@"),
        followers=metric_value(metrics, keys=("followers_count",)),
        following=metric_value(metrics, keys=("following_count",)),
        profile_url=f"https://x.com/{str(user.username or account.handle).lstrip('@')}",
        summary="Official X account public metrics snapshot.",
        metadata_json=json_dumps({"x_user_id": user.id, "verified": user.verified}),
        observed_at=utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "read_only": True,
        "workflow_key": "x_account_snapshot_sweep",
        "created_snapshot_id": int(row.id),
        "followers": int(row.followers or 0),
        "following": int(row.following or 0),
    }


def _hook_pattern(hook: str | None) -> str:
    text = str(hook or "").strip().lower()
    if not text:
        return "unknown"
    if text.endswith("?") or text.startswith(("why ", "how ", "what ")):
        return "question"
    if any(token in text for token in ("not ", "instead", "stop ", "rather than")):
        return "contrarian"
    if any(token in text for token in ("shipped", "built", "changed", "replaced")):
        return "build_in_public"
    return "technical_claim"


def _rate(numerator: int, denominator: int) -> float:
    return round(float(numerator) / max(1, int(denominator or 0)), 4)


def _aggregate_topics(rows: list[SocialPostMetricRow]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        tags = list(metric_metadata(row).get("topic_tags") or ["untagged"])
        for tag in tags:
            bucket = buckets.setdefault(
                str(tag),
                {
                    "topic": str(tag),
                    "posts": 0,
                    "impressions": 0,
                    "bookmarks": 0,
                    "replies": 0,
                    "profile_visits": 0,
                },
            )
            bucket["posts"] += 1
            bucket["impressions"] += int(row.impressions or 0)
            bucket["bookmarks"] += int(row.bookmarks or 0)
            bucket["replies"] += int(row.replies or 0)
            bucket["profile_visits"] += int(row.profile_visits or 0)
    for bucket in buckets.values():
        bucket["bookmark_rate"] = _rate(bucket["bookmarks"], bucket["impressions"])
        bucket["reply_rate"] = _rate(bucket["replies"], bucket["impressions"])
    return sorted(
        buckets.values(),
        key=lambda item: (item["bookmarks"], item["replies"], item["impressions"]),
        reverse=True,
    )


def _aggregate_hooks(rows: list[SocialPostMetricRow]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        pattern = _hook_pattern(metric_metadata(row).get("hook_text"))
        bucket = buckets.setdefault(
            pattern,
            {
                "hook_pattern": pattern,
                "posts": 0,
                "impressions": 0,
                "bookmarks": 0,
                "replies": 0,
            },
        )
        bucket["posts"] += 1
        bucket["impressions"] += int(row.impressions or 0)
        bucket["bookmarks"] += int(row.bookmarks or 0)
        bucket["replies"] += int(row.replies or 0)
    for bucket in buckets.values():
        bucket["bookmark_rate"] = _rate(bucket["bookmarks"], bucket["impressions"])
        bucket["reply_rate"] = _rate(bucket["replies"], bucket["impressions"])
    return sorted(
        buckets.values(),
        key=lambda item: (
            item["bookmark_rate"],
            item["reply_rate"],
            item["impressions"],
        ),
        reverse=True,
    )


def _weekly_recommendations(
    best_topics: list[dict[str, Any]],
    best_hooks: list[dict[str, Any]],
    low_patterns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    if best_topics:
        topic = best_topics[0]["topic"]
        recommendations.append(
            {
                "action": "increase_topic",
                "topic": topic,
                "reason": "highest combined bookmark/reply/impression signal",
            }
        )
        if best_topics[0].get("bookmark_rate", 0) > best_topics[0].get("reply_rate", 0):
            recommendations.append(
                {
                    "action": "add_visual",
                    "topic": topic,
                    "reason": "bookmark-heavy technical topic may benefit from an architecture diagram",
                }
            )
    if best_hooks:
        recommendations.append(
            {
                "action": "reuse_hook_pattern",
                "hook_pattern": best_hooks[0]["hook_pattern"],
                "reason": "best observed bookmark/reply rate",
            }
        )
    for pattern in low_patterns[:2]:
        recommendations.append(
            {
                "action": "reduce_or_reframe",
                "pattern": pattern.get("hook_pattern") or pattern.get("topic"),
                "reason": "low interaction in current window",
            }
        )
    return recommendations


def _weekly_review_out(row: SocialWeeklyReviewRow) -> SocialWeeklyReviewOut:
    return SocialWeeklyReviewOut(
        id=int(row.id),
        platform=row.platform,
        week_start=row.week_start,
        week_end=row.week_end,
        status=row.status,
        summary=row.summary,
        best_topics=list(json_loads(row.best_topics_json, [])),
        best_hooks=list(json_loads(row.best_hooks_json, [])),
        low_performing_patterns=list(json_loads(row.low_performing_patterns_json, [])),
        recommendations=list(json_loads(row.recommendations_json, [])),
        content_generation_guidance=dict(
            json_loads(row.content_generation_guidance_json, {})
        ),
        source_metric_ids=[
            int(item) for item in json_loads(row.source_metric_ids_json, [])
        ],
        error_excerpt=row.error_excerpt,
        created_at=row.created_at,
    )


def list_social_weekly_reviews(db: Session, *, limit: int = 12, offset: int = 0):
    bounded_limit = max(1, min(52, int(limit or 12)))
    bounded_offset = max(0, int(offset or 0))
    query = db.query(SocialWeeklyReviewRow).filter(
        SocialWeeklyReviewRow.platform == "x"
    )
    rows = (
        query.order_by(
            SocialWeeklyReviewRow.week_start.desc(), SocialWeeklyReviewRow.id.desc()
        )
        .limit(bounded_limit)
        .offset(bounded_offset)
        .all()
    )
    return {
        "items": [_weekly_review_out(row) for row in rows],
        "total": int(query.count()),
        "limit": bounded_limit,
        "offset": bounded_offset,
    }


def _weekly_window(days: int):
    bounded_days = max(1, min(30, int(days or 7)))
    week_end = utcnow()
    return bounded_days, week_end - timedelta(days=bounded_days), week_end


def _weekly_metric_rows(
    db: Session, *, week_start, week_end
) -> list[SocialPostMetricRow]:
    return (
        db.query(SocialPostMetricRow)
        .filter(SocialPostMetricRow.observed_at >= week_start)
        .filter(SocialPostMetricRow.observed_at <= week_end)
        .order_by(SocialPostMetricRow.observed_at.desc(), SocialPostMetricRow.id.desc())
        .all()
    )


def _low_patterns(best_hooks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(
        best_hooks,
        key=lambda value: (
            value.get("impressions", 0),
            value.get("replies", 0),
            value.get("bookmarks", 0),
        ),
    )
    return [
        item
        for item in rows
        if int(item.get("impressions") or 0) <= 100
        or (int(item.get("replies") or 0) + int(item.get("bookmarks") or 0)) == 0
    ]


def _guidance(
    best_topics: list[dict[str, Any]],
    best_hooks: list[dict[str, Any]],
    low_patterns: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "best_topics": [item["topic"] for item in best_topics[:3]],
        "best_hooks": [item["hook_pattern"] for item in best_hooks[:3]],
        "low_performing_patterns": [
            item.get("hook_pattern") or item.get("topic") for item in low_patterns[:3]
        ],
        "recommended_format": "diagram_or_long_post"
        if any(item.get("action") == "add_visual" for item in recommendations)
        else "single_or_reply",
        "avoid_patterns": [
            item.get("hook_pattern") or item.get("topic") for item in low_patterns[:3]
        ],
    }


def _review_summary(
    rows: list[SocialPostMetricRow], days: int, best_topics, best_hooks
):
    return f"Reviewed {len(rows)} X metric rows from the last {days} days. Best topic: {best_topics[0]['topic'] if best_topics else 'none'}. Best hook: {best_hooks[0]['hook_pattern'] if best_hooks else 'none'}."


@service_object_result
def run_x_social_weekly_analytics_review(
    db: Session, *, days: int = 7, dry_run: bool = False
) -> ServiceObjectResult:
    """Create deterministic content guidance from local X metrics."""

    bounded_days, week_start, week_end = _weekly_window(days)
    rows = _weekly_metric_rows(db, week_start=week_start, week_end=week_end)
    best_topics = _aggregate_topics(rows)
    best_hooks = _aggregate_hooks(rows)
    low_patterns = _low_patterns(best_hooks)
    recommendations = _weekly_recommendations(best_topics, best_hooks, low_patterns)
    guidance = _guidance(best_topics, best_hooks, low_patterns, recommendations)
    summary = _review_summary(rows, bounded_days, best_topics, best_hooks)
    result = {
        "workflow_key": "x_social_weekly_analytics_review",
        "dry_run": bool(dry_run),
        "metric_count": len(rows),
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "best_topics": best_topics[:5],
        "best_hooks": best_hooks[:5],
        "low_performing_patterns": low_patterns[:5],
        "recommendations": recommendations,
        "content_generation_guidance": guidance,
        "summary": summary,
    }
    if dry_run:
        return result
    row = SocialWeeklyReviewRow(
        platform="x",
        week_start=week_start,
        week_end=week_end,
        status="succeeded",
        summary=summary,
        best_topics_json=json_dumps(best_topics[:5]),
        best_hooks_json=json_dumps(best_hooks[:5]),
        low_performing_patterns_json=json_dumps(low_patterns[:5]),
        recommendations_json=json_dumps(recommendations),
        content_generation_guidance_json=json_dumps(guidance),
        source_metric_ids_json=json_dumps([int(row.id) for row in rows]),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    result["review_id"] = int(row.id)
    return result
