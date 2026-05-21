"""Campaign templates for human-gated social distribution tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from server import config
from server import schemas_social_distribution as dist_schema
from server.database_social_distribution import SocialContentAssetRow
from server.services.social.distribution import get_content_asset
from server.services.social.distribution_documents import create_content_task


X_BRAND_WEEK_CAMPAIGN_KEY = "x_brand_awareness_week_1"


@dataclass(frozen=True)
class CampaignTaskSpec:
    title: str
    target_audience: str
    source_material: str
    post_intent: str
    day_offset: int


X_BRAND_WEEK_TASKS: tuple[CampaignTaskSpec, ...] = (
    CampaignTaskSpec(
        title="X Week 1 Day 1 - Why agents need settlement rails, not SaaS subscriptions",
        target_audience="AI agent developers, devtools builders, fintech infra engineers",
        source_material=(
            "Explain Synapse as the settlement layer for AI agents. Contrast SaaS "
            "subscriptions, credit cards, API keys, and per-call USDC settlement. "
            "Hook: AI agents can think, but they still cannot pay."
        ),
        post_intent="brand_positioning",
        day_offset=0,
    ),
    CampaignTaskSpec(
        title="X Week 1 Day 2 - Give an AI agent a $5 budget, not your credit card",
        target_audience="Agent developers worried about runaway spend",
        source_material=(
            "Focus on budget isolation, micropayments, and why capped USDC balance "
            "is safer than unlimited API keys. Include one architecture diagram prompt."
        ),
        post_intent="technical_explainer",
        day_offset=1,
    ),
    CampaignTaskSpec(
        title="X Week 1 Day 3 - Replacing GitHub Actions with a local deploy runner",
        target_audience="Solo founders, infra engineers, indie hackers",
        source_material=(
            "Build-in-public story: why CI/CD cost got too high, why local runner "
            "+ Postgres events + digest deploy is more controllable, and what was "
            "deliberately not automated."
        ),
        post_intent="build_in_public",
        day_offset=2,
    ),
    CampaignTaskSpec(
        title="X Week 1 Day 4 - Lifecycle of a paid agent API call",
        target_audience="Technical developers evaluating Synapse architecture",
        source_material=(
            "Explain discover -> invoke -> meter -> settle -> receipt. Include a "
            "request for one architecture visual/image prompt and keep the copy "
            "concrete rather than promotional."
        ),
        post_intent="technical_explainer",
        day_offset=3,
    ),
    CampaignTaskSpec(
        title="X Week 1 Day 5 - Provider registry needs proofs, not profile pages",
        target_audience="API providers, marketplace builders, agent platform devs",
        source_material=(
            "Explain provider onboarding, service registry, health/readiness, "
            "receipts, and why agents need verifiable service metadata instead of "
            "trust-me marketplace profiles."
        ),
        post_intent="technical_explainer",
        day_offset=4,
    ),
    CampaignTaskSpec(
        title="X Week 1 Day 6 - Human Gate is blast-radius control",
        target_audience="Agent ops builders, automation engineers, safety-minded founders",
        source_material=(
            "Explain why Synapse avoids God Agent workflows and keeps high-risk "
            "actions behind deterministic gates. Hook: I do not want a God Agent; "
            "I want a system that knows when to stop."
        ),
        post_intent="build_in_public",
        day_offset=5,
    ),
    CampaignTaskSpec(
        title="X Week 1 Day 7 - Weekly build log: receipts over vibes",
        target_audience="Builders following public technical progress",
        source_material=(
            "Summarize what shipped this week and ask what developers want to "
            "inspect next: settlement, provider onboarding, local deploy, or SDK. "
            "Keep it as a weekly build log, not a launch announcement."
        ),
        post_intent="weekly_log",
        day_offset=6,
    ),
    *(
        CampaignTaskSpec(
            title=f"X Week 1 Reply Block Day {day}",
            target_audience="Agent infra, devtools, payments, solo-founder builders on X",
            source_material=(
                "Paste 5 real X URLs or watchlist posts for today's reply block. "
                "Generate value-add reply drafts only. No hard sell, no 'Great point', "
                "no link spam; each reply must add one concrete technical angle."
            ),
            post_intent="engagement_reply",
            day_offset=day - 1,
        )
        for day in range(1, 6)
    ),
)


def create_x_brand_week_template(
    db: Session, *, created_by: str = "operator"
) -> dist_schema.SocialDistributionCampaignTemplateOut:
    """Create the week-one X brand campaign tasks idempotently."""

    created_count = 0
    existing_count = 0
    assets: list[dist_schema.SocialContentAssetDetailOut] = []
    for spec in X_BRAND_WEEK_TASKS:
        existing = _existing_campaign_asset(db, spec.title)
        if existing is not None:
            existing_count += 1
            assets.append(get_content_asset(db, int(existing.id)))
            continue
        assets.append(
            create_content_task(
                db,
                dist_schema.SocialContentTaskCreateRequest(
                    title=spec.title,
                    source_material=spec.source_material,
                    target_audience=spec.target_audience,
                    target_platforms=["x"],
                    goal_key=X_BRAND_WEEK_CAMPAIGN_KEY,
                    campaign_key=X_BRAND_WEEK_CAMPAIGN_KEY,
                    post_intent=spec.post_intent,
                    planned_publish_at=_planned_publish_at(spec.day_offset),
                    created_by=created_by,
                ),
            )
        )
        created_count += 1
    return dist_schema.SocialDistributionCampaignTemplateOut(
        campaign_key=X_BRAND_WEEK_CAMPAIGN_KEY,
        created_count=created_count,
        existing_count=existing_count,
        assets=assets,
    )


def _existing_campaign_asset(db: Session, title: str) -> SocialContentAssetRow | None:
    return (
        db.query(SocialContentAssetRow)
        .filter(
            SocialContentAssetRow.goal_key == X_BRAND_WEEK_CAMPAIGN_KEY,
            SocialContentAssetRow.title == title,
        )
        .one_or_none()
    )


def _planned_publish_at(day_offset: int) -> datetime:
    try:
        zone = ZoneInfo(config.OPERATOR_TIMEZONE)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    local_today = datetime.now(zone).date()
    local_dt = datetime.combine(
        local_today + timedelta(days=day_offset),
        time(hour=21, minute=30),
        tzinfo=zone,
    )
    return local_dt.astimezone(timezone.utc)
