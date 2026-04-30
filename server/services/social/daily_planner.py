"""Daily X content planner inventory top-up."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server.database import (
    SocialCampaignGoalRow,
    SocialPostDraftRow,
    SocialPostMetricRow,
)
from server.services.result_objects import ServiceObjectResult, service_object_result
from server.services.social import publishing
from server.services.social.daily_planner_inventory import (
    DAILY_PLANNER_ACTIVE_STATUSES,
    daily_planner_inventory,
    _daily_planner_raw_metadata,
    _expire_stale_daily_planner_generating_posts,
    _next_daily_planner_slot,
)
from server.services.social.product_change_signals import (
    planner_product_change_lines as _planner_product_change_lines,
    recent_product_change_signals as _recent_product_change_signals,
)

logger = logging.getLogger("ops-dashboard.social-daily-planner")

DAILY_PLANNER_TARGET_COUNT = 3


def _daily_planner_angle(slot: int) -> str:
    angles = (
        "Product education: explain Synapse Network's agent-payment primitive clearly.",
        "Shipping proof: connect recent staging / release progress to public trust.",
        "Developer use case: show how agent builders and API providers benefit in practice.",
    )
    return angles[(max(1, int(slot)) - 1) % len(angles)]


def _recent_social_metric_rows(
    db: Session, *, limit: int = 3
) -> list[SocialPostMetricRow]:
    return (
        db.query(SocialPostMetricRow)
        .order_by(SocialPostMetricRow.observed_at.desc(), SocialPostMetricRow.id.desc())
        .limit(max(1, int(limit)))
        .all()
    )


def _active_campaign_goal(db: Session) -> SocialCampaignGoalRow | None:
    return (
        db.query(SocialCampaignGoalRow)
        .filter(
            SocialCampaignGoalRow.platform == "x",
            SocialCampaignGoalRow.status == "active",
        )
        .order_by(
            SocialCampaignGoalRow.updated_at.desc(), SocialCampaignGoalRow.id.desc()
        )
        .first()
    )


def _campaign_goal_summary(
    goal: SocialCampaignGoalRow | None,
) -> tuple[str, str, str, str]:
    if goal is None:
        return (
            "Build trust for Synapse Network official X",
            "Explain Synapse Network to AI agent builders and API providers.",
            "Product education, shipping proof, agent economy commentary, developer use cases, trust and governance",
            "published posts/week, engagement rate, profile visits, docs clicks",
        )
    content_pillars = publishing._json_loads(goal.content_pillars_json, [])
    success_metrics = publishing._json_loads(goal.success_metrics_json, [])
    return (
        str(goal.title),
        str(goal.objective),
        ", ".join(str(item) for item in content_pillars)
        or "Product education, shipping proof, agent economy commentary, developer use cases, trust and governance",
        ", ".join(str(item) for item in success_metrics)
        or "published posts/week, engagement rate, profile visits, docs clicks",
    )


def _planner_variable_factor(
    local_date: str, planner_slot: int, trends: list[Any], watchlist: list[Any]
) -> str:
    candidates = [f"Trend: {trend.topic} - {trend.summary}" for trend in trends]
    candidates.extend(
        f"Watchlist: @{row.handle} - {row.rationale or row.latest_summary or row.display_name or row.handle}"
        for row in watchlist
    )
    if not candidates:
        return "Fresh angle: explain why autonomous agents need governed API access and payment rails."
    seed = sum(int(part) for part in local_date.split("-") if part.isdigit()) + int(
        planner_slot
    )
    return candidates[seed % len(candidates)]


def _planner_trend_lines(trends: list[Any]) -> str:
    return (
        "\n".join(
            f"- {trend.topic}: {trend.summary} (score={trend.relevance_score:.2f})"
            for trend in trends
        )
        or "- metrics_unavailable: no high-quality trend radar item yet."
    )


def _planner_watchlist_lines(watchlist: list[Any]) -> str:
    return (
        "\n".join(
            f"- @{row.handle} ({row.category}): {row.rationale or row.latest_summary or row.display_name or row.handle}"
            for row in watchlist
        )
        or "- no watchlist highlights available."
    )


def _planner_metric_lines(metrics: list[SocialPostMetricRow]) -> str:
    return (
        "\n".join(
            f"- post_metric_id={row.id}: impressions={row.impressions}, likes={row.likes}, replies={row.replies}, reposts={row.reposts}, link_clicks={row.link_clicks}, summary={row.summary or 'no summary'}"
            for row in metrics
        )
        or "- metrics_unavailable: no recent post metrics yet."
    )


def _build_daily_planner_prompt(
    db: Session,
    *,
    local_date: str,
    planner_slot: int,
    planner_angle: str,
) -> tuple[str, dict[str, Any]]:
    goal = _active_campaign_goal(db)
    trends = publishing._top_social_trends(db)
    watchlist = publishing._watchlist_highlights(db)
    metrics = _recent_social_metric_rows(db)
    goal_title, goal_objective, content_pillars, success_metrics = (
        _campaign_goal_summary(goal)
    )
    variable_factor = _planner_variable_factor(
        local_date, planner_slot, trends, watchlist
    )
    trend_lines = _planner_trend_lines(trends)
    watchlist_lines = _planner_watchlist_lines(watchlist)
    metric_lines = _planner_metric_lines(metrics)
    product_change_signals = _recent_product_change_signals(db)
    product_change_lines = _planner_product_change_lines(product_change_signals)
    prompt = "\n".join(
        [
            f"Create today's human-reviewed X official account draft for Synapse Network. Local date: {local_date}.",
            f"This is daily planner slot {planner_slot} of {DAILY_PLANNER_TARGET_COUNT}. Make it distinct from the other daily drafts.",
            "This is a scheduled daily planner draft. Do not publish, reply, repost, follow, delete, or claim an external action happened.",
            "",
            "# Active campaign goal",
            f"Title: {goal_title}",
            f"Objective: {goal_objective}",
            f"Content pillars: {content_pillars}",
            f"Success metrics: {success_metrics}",
            "",
            "# Variable factor for freshness",
            variable_factor,
            "",
            "# Required draft angle",
            planner_angle,
            "",
            "# Top trend radar items",
            trend_lines,
            "",
            "# Watchlist highlights",
            watchlist_lines,
            "",
            "# Recent 3 published post performance",
            metric_lines,
            "",
            "# Verified product change signals",
            product_change_lines,
            "",
            "Write a substantial, high-trust X post with a strong hook, concrete product value, and relevant hashtags. Keep it public-facing and useful to AI agent builders, API providers, and developer operators.",
        ]
    )
    return prompt, {
        "planner_local_date": local_date,
        "planner_slot": int(planner_slot),
        "planner_angle": planner_angle,
        "trend_item_ids": [int(row.id) for row in trends],
        "watchlist_handles": [str(row.handle) for row in watchlist],
        "recent_metric_post_ids": [
            int(row.post_id) for row in metrics if row.post_id is not None
        ],
        "product_change_signals": product_change_signals,
        "variable_factor": variable_factor,
        "metrics_available": bool(metrics),
    }


def _generate_daily_planner_slot(
    db: Session,
    *,
    account_id: int,
    local_date: str,
    daily_rows: list[SocialPostDraftRow],
) -> tuple[SocialPostDraftRow, str, bool]:
    planner_slot = _next_daily_planner_slot(
        daily_rows, target_count=DAILY_PLANNER_TARGET_COUNT
    )
    planner_run_key = f"x_daily:{account_id}:{local_date}:slot-{planner_slot}"
    prompt, metadata = _build_daily_planner_prompt(
        db,
        local_date=local_date,
        planner_slot=planner_slot,
        planner_angle=_daily_planner_angle(planner_slot),
    )
    metadata = {
        **metadata,
        "planner_run_key": planner_run_key,
        "source_type": "daily_planner",
    }
    row = SocialPostDraftRow(
        platform="x",
        account_id=account_id,
        source_type="daily_planner",
        title=f"X daily planner draft slot {planner_slot} is generating",
        body_text="",
        status="generating",
        generated_by="x_social_daily_content_planner",
        policy_check_json=publishing._json_dumps(
            publishing._generation_running_policy()
        ),
        raw_agent_output_json=publishing._json_dumps(
            {
                "source": "x_social_daily_content_planner",
                "status": "generating",
                "provider": config.SOCIAL_CONTENT_LLM_PROVIDER,
                "requested_model": config.SOCIAL_CONTENT_LLM_MODEL,
                "media_mode": "text_only",
                "prompt_excerpt": publishing._bounded_excerpt(prompt, max_chars=240),
                **metadata,
            }
        ),
    )
    db.add(row)
    db.flush()
    publishing._record_event(
        db,
        row,
        "daily_planner_generation_started",
        actor="x_social_daily_content_planner",
        summary="Hourly X social planner created a draft shell to maintain today's 3-draft inventory; no external publish attempted.",
        payload={
            "planner_local_date": local_date,
            "planner_run_key": planner_run_key,
            "planner_slot": planner_slot,
        },
    )
    db.commit()
    try:
        publishing._finalize_generated_social_post(
            db,
            int(row.id),
            prompt=prompt,
            actor="x_social_daily_content_planner",
            style_type="marketing",
            media_mode="text_only",
        )
    except Exception:
        logger.exception(
            "daily planner draft generation failed",
            extra={"post_id": int(row.id), "planner_slot": planner_slot},
        )

    row = publishing._get_post(db, int(row.id))
    raw = _daily_planner_raw_metadata(row)
    raw.update(metadata)
    raw["source"] = "x_social_daily_content_planner"
    row.raw_agent_output_json = publishing._json_dumps(raw)
    if row.status == "approved":
        row.status = "needs_review"
        row.reviewed_by = None
        publishing._record_event(
            db,
            row,
            "daily_planner_requires_human_review",
            actor="x_social_daily_content_planner",
            summary="Policy passed, but scheduled X drafts remain in needs_review until an operator approves publishing.",
            payload={
                "planner_local_date": local_date,
                "planner_run_key": planner_run_key,
                "planner_slot": planner_slot,
            },
        )
    db.commit()
    return row, planner_run_key, row.status in DAILY_PLANNER_ACTIVE_STATUSES


def _daily_planner_satisfied_result(
    *, account_id: int, local_date: str, active_rows: list[SocialPostDraftRow]
) -> dict[str, Any]:
    return {
        "already_created": True,
        "already_satisfied": True,
        "target_count": DAILY_PLANNER_TARGET_COUNT,
        "active_count": len(active_rows),
        "created_post_ids": [],
        "existing_post_ids": [int(row.id) for row in active_rows],
        "created_post_id": None,
        "existing_post_id": int(active_rows[0].id) if active_rows else None,
        "planner_local_date": local_date,
        "planner_run_key": f"x_daily:{account_id}:{local_date}",
        "status": "satisfied",
    }


def _top_up_daily_planner_slots(
    db: Session,
    *,
    account_id: int,
    local_date: str,
    daily_rows: list[SocialPostDraftRow],
    active_rows: list[SocialPostDraftRow],
) -> tuple[list[int], list[int], list[str]]:
    created_ids: list[int] = []
    failed_ids: list[int] = []
    created_run_keys: list[str] = []
    missing_count = DAILY_PLANNER_TARGET_COUNT - len(active_rows)
    create_count = min(
        max(0, missing_count), int(config.X_DAILY_PLANNER_MAX_CREATED_PER_TICK)
    )
    for _index in range(create_count):
        row, planner_run_key, is_active = _generate_daily_planner_slot(
            db, account_id=account_id, local_date=local_date, daily_rows=daily_rows
        )
        daily_rows.append(row)
        if is_active:
            active_rows.append(row)
            created_ids.append(int(row.id))
            created_run_keys.append(planner_run_key)
        else:
            failed_ids.append(int(row.id))
            break
    return created_ids, failed_ids, created_run_keys


def _daily_planner_top_up_result(
    *,
    account_id: int,
    local_date: str,
    active_rows: list[SocialPostDraftRow],
    created_ids: list[int],
    failed_ids: list[int],
    created_run_keys: list[str],
    expired_post_ids: list[int] | None = None,
) -> dict[str, Any]:
    created_id_set = set(created_ids)
    return {
        "already_created": False,
        "already_satisfied": len(active_rows) >= DAILY_PLANNER_TARGET_COUNT,
        "target_count": DAILY_PLANNER_TARGET_COUNT,
        "active_count": len(active_rows),
        "created_post_ids": created_ids,
        "existing_post_ids": [
            int(row.id) for row in active_rows if int(row.id) not in created_id_set
        ],
        "failed_post_ids": failed_ids,
        "expired_generating_post_ids": expired_post_ids or [],
        "max_created_per_tick": int(config.X_DAILY_PLANNER_MAX_CREATED_PER_TICK),
        "created_post_id": created_ids[0] if created_ids else None,
        "existing_post_id": int(active_rows[0].id) if active_rows else None,
        "planner_local_date": local_date,
        "planner_run_key": created_run_keys[0]
        if created_run_keys
        else f"x_daily:{account_id}:{local_date}",
        "planner_run_keys": created_run_keys,
        "status": "created" if created_ids else "generation_failed",
    }


@service_object_result
def run_x_social_daily_content_planner(
    db: Session, *, now: datetime | None = None
) -> ServiceObjectResult:
    """Top up each operator-local day to three human-reviewed X draft slots."""

    publishing.ensure_default_social_ops_seed(db)
    account = publishing.ensure_default_social_account(db)
    local_date = publishing._operator_local_date(now)
    daily_rows, active_rows = daily_planner_inventory(
        db, account_id=int(account.id), local_date=local_date
    )
    expired_post_ids = _expire_stale_daily_planner_generating_posts(
        db, daily_rows, now=now
    )
    if expired_post_ids:
        daily_rows, active_rows = daily_planner_inventory(
            db, account_id=int(account.id), local_date=local_date
        )
    if len(active_rows) >= DAILY_PLANNER_TARGET_COUNT:
        result = _daily_planner_satisfied_result(
            account_id=int(account.id), local_date=local_date, active_rows=active_rows
        )
        result["expired_generating_post_ids"] = expired_post_ids
        result["max_created_per_tick"] = int(
            config.X_DAILY_PLANNER_MAX_CREATED_PER_TICK
        )
        return result

    created_ids, failed_ids, created_run_keys = _top_up_daily_planner_slots(
        db,
        account_id=int(account.id),
        local_date=local_date,
        daily_rows=daily_rows,
        active_rows=active_rows,
    )

    _, active_rows = daily_planner_inventory(
        db, account_id=int(account.id), local_date=local_date
    )
    return _daily_planner_top_up_result(
        account_id=int(account.id),
        local_date=local_date,
        active_rows=active_rows,
        created_ids=created_ids,
        failed_ids=failed_ids,
        created_run_keys=created_run_keys,
        expired_post_ids=expired_post_ids,
    )
