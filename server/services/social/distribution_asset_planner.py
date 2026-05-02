"""Low-context asset planner for the multi-channel distribution center."""

from __future__ import annotations

import json
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from server import config, schemas_social_distribution as dist_schema
from server.database import (
    DeploymentRecordRow,
    PlanningGoalRow,
    ReleaseTaskRow,
    RequirementRow,
    SocialPostMetricRow,
    SocialTrendItemRow,
    utcnow,
)
from server.database_social_distribution import SocialContentAssetRow
from server.services.planning.product_opportunities import ProductOpportunityRow
from server.services.social.distribution import get_content_asset
from server.services.social.agent_content_pack import (
    AgentContentGenerationError,
    generate_canonical_asset_pack,
)
from server.services.social.distribution_asset_signals import (
    AssetSignal,
    _dedupe_signals,
    _public_safe,
    _signal_out,
)
from server.services.social.distribution_core import _record_event

ASSET_PLANNER_TARGET_COUNT = 3
ACTIVE_ASSET_STATUSES = {"proposed", "approved", "ready"}
ASSET_TYPE_ORDER = (
    "shipping_proof",
    "developer_education",
    "market_commentary",
    "launch_asset",
)
SOURCE_SIGNAL_LIMIT = 5


def run_social_asset_planner_sweep(
    db: Session,
    *,
    now: datetime | None = None,
    target_count: int = ASSET_PLANNER_TARGET_COUNT,
) -> dist_schema.SocialAssetPlannerRunOut:
    current = now or utcnow()
    local_date = _operator_local_date(current)
    start_utc, end_utc = _local_day_bounds_utc(local_date)
    active_rows = _active_asset_rows_for_day(db, start_utc=start_utc, end_utc=end_utc)
    if len(active_rows) >= int(target_count):
        return dist_schema.SocialAssetPlannerRunOut(
            local_date=local_date,
            target_count=int(target_count),
            active_count=len(active_rows),
            no_asset_created=True,
            already_satisfied=True,
            reason="daily_asset_inventory_satisfied",
        )

    chosen_type, signals = _sample_signals_for_next_asset(db, active_rows=active_rows)
    if not chosen_type or not signals:
        return dist_schema.SocialAssetPlannerRunOut(
            local_date=local_date,
            target_count=int(target_count),
            active_count=len(active_rows),
            no_asset_created=True,
            reason="no_qualified_signal",
            signals=[],
        )

    try:
        row = _create_asset_from_signals(
            db,
            local_date=local_date,
            asset_type=chosen_type,
            signals=signals,
        )
    except (AgentContentGenerationError, RuntimeError) as exc:
        db.rollback()
        return dist_schema.SocialAssetPlannerRunOut(
            local_date=local_date,
            target_count=int(target_count),
            active_count=len(active_rows),
            no_asset_created=True,
            selected_asset_type=chosen_type,
            selected_signal_count=len(signals),
            reason=_bounded_generation_failure(exc),
            signals=[_signal_out(signal) for signal in signals],
        )
    db.commit()
    db.refresh(row)
    return dist_schema.SocialAssetPlannerRunOut(
        local_date=local_date,
        target_count=int(target_count),
        active_count=len(active_rows) + 1,
        selected_asset_type=chosen_type,
        selected_signal_count=len(signals),
        created_asset_id=int(row.id),
        asset=get_content_asset(db, int(row.id)),
        signals=[_signal_out(signal) for signal in signals],
    )


def _bounded_generation_failure(exc: Exception) -> str:
    detail = str(exc or "asset generation failed").strip()
    detail = detail.replace("\n", " ")
    if not detail:
        detail = exc.__class__.__name__
    return f"asset_generation_failed: {detail[:500]}"


def _operator_zone() -> ZoneInfo:
    try:
        return ZoneInfo(config.OPERATOR_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _operator_local_date(value: datetime) -> str:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(_operator_zone()).date().isoformat()


def _local_day_bounds_utc(local_date: str) -> tuple[datetime, datetime]:
    zone = _operator_zone()
    day = datetime.strptime(local_date, "%Y-%m-%d").date()
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day, time.max, tzinfo=zone)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _active_asset_rows_for_day(
    db: Session, *, start_utc: datetime, end_utc: datetime
) -> list[SocialContentAssetRow]:
    return (
        db.query(SocialContentAssetRow)
        .filter(
            SocialContentAssetRow.status.in_(sorted(ACTIVE_ASSET_STATUSES)),
            SocialContentAssetRow.created_at >= start_utc,
            SocialContentAssetRow.created_at <= end_utc,
        )
        .order_by(
            SocialContentAssetRow.created_at.desc(), SocialContentAssetRow.id.desc()
        )
        .all()
    )


def _sample_signals_for_next_asset(
    db: Session, *, active_rows: list[SocialContentAssetRow]
) -> tuple[str | None, list[AssetSignal]]:
    existing_types = {str(row.asset_type or "") for row in active_rows}
    for asset_type in ASSET_TYPE_ORDER:
        if asset_type in existing_types:
            continue
        signals = _signals_for_type(db, asset_type)[:SOURCE_SIGNAL_LIMIT]
        if signals:
            return asset_type, signals
    for asset_type in ASSET_TYPE_ORDER:
        signals = _signals_for_type(db, asset_type)[:SOURCE_SIGNAL_LIMIT]
        if signals:
            return asset_type, signals
    return None, []


def _signals_for_type(db: Session, asset_type: str) -> list[AssetSignal]:
    if asset_type == "shipping_proof":
        return _shipping_proof_signals(db)
    if asset_type == "developer_education":
        return _developer_education_signals(db)
    if asset_type == "market_commentary":
        return _market_commentary_signals(db)
    return _launch_asset_signals(db)


def _shipping_proof_signals(db: Session) -> list[AssetSignal]:
    signals: list[AssetSignal] = []
    releases = (
        db.query(ReleaseTaskRow)
        .filter(ReleaseTaskRow.status == "completed")
        .order_by(ReleaseTaskRow.updated_at.desc(), ReleaseTaskRow.id.desc())
        .limit(3)
        .all()
    )
    for row in releases:
        signals.append(
            AssetSignal(
                signal_type="shipping_proof",
                source_ref=f"release_task:{int(row.id)}",
                title=f"{row.project_display_name or row.project_key} shipped to {row.environment}",
                summary=f"{row.service_key or 'service'} deployed from {row.branch_name}; status={row.status}.",
                score=0.95,
            )
        )
    requirements = (
        db.query(RequirementRow)
        .filter(RequirementRow.status.in_(("completed", "done")))
        .order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc())
        .limit(3)
        .all()
    )
    for row in requirements:
        signals.append(
            AssetSignal(
                signal_type="shipping_proof",
                source_ref=f"requirement:{int(row.id)}",
                title=row.title,
                summary=f"Completed product work for {row.project_display_name or row.project_key or 'Synapse Network'}.",
                score=0.85,
            )
        )
    deployments = (
        db.query(DeploymentRecordRow)
        .filter(DeploymentRecordRow.status.in_(("completed", "succeeded")))
        .order_by(DeploymentRecordRow.updated_at.desc(), DeploymentRecordRow.id.desc())
        .limit(3)
        .all()
    )
    for row in deployments:
        signals.append(
            AssetSignal(
                signal_type="shipping_proof",
                source_ref=f"deployment:{int(row.id)}",
                title=f"{row.project_key} {row.environment} deployment succeeded",
                summary=f"Cloud/deploy evidence is available with health={row.health_status or 'recorded'}.",
                score=0.80,
            )
        )
    return _dedupe_signals(signals)


def _developer_education_signals(db: Session) -> list[AssetSignal]:
    signals: list[AssetSignal] = []
    opportunities = (
        db.query(ProductOpportunityRow)
        .filter(
            ProductOpportunityRow.status.in_(("proposed", "approved", "converted")),
            ProductOpportunityRow.recommended_lane.in_(
                ("software_engineer", "both", "growth_lead")
            ),
        )
        .order_by(
            ProductOpportunityRow.updated_at.desc(), ProductOpportunityRow.id.desc()
        )
        .limit(5)
        .all()
    )
    for row in opportunities:
        signals.append(
            AssetSignal(
                signal_type="developer_education",
                source_ref=f"product_opportunity:{int(row.id)}",
                title=row.title,
                summary=f"{row.problem} Why now: {row.why_now or row.next_action}",
                score=0.82,
            )
        )
    goals = (
        db.query(PlanningGoalRow)
        .filter(PlanningGoalRow.status == "active")
        .order_by(PlanningGoalRow.updated_at.desc(), PlanningGoalRow.id.desc())
        .limit(3)
        .all()
    )
    for row in goals:
        signals.append(
            AssetSignal(
                signal_type="developer_education",
                source_ref=f"planning_goal:{int(row.id)}",
                title=row.title,
                summary=row.intent_markdown or row.success_metric or row.goal_key,
                score=0.70,
            )
        )
    return _dedupe_signals(signals)


def _market_commentary_signals(db: Session) -> list[AssetSignal]:
    rows = (
        db.query(SocialTrendItemRow)
        .filter(SocialTrendItemRow.status != "archived")
        .order_by(
            SocialTrendItemRow.relevance_score.desc(),
            SocialTrendItemRow.collected_at.desc(),
        )
        .limit(8)
        .all()
    )
    return _dedupe_signals(
        [
            AssetSignal(
                signal_type="market_commentary",
                source_ref=f"social_trend:{int(row.id)}",
                title=row.topic,
                summary=f"{row.summary} Source: {row.author_handle or row.source_platform}.",
                score=float(row.relevance_score or 0.0),
            )
            for row in rows
            if float(row.relevance_score or 0.0) >= 0.7
        ]
    )


def _launch_asset_signals(db: Session) -> list[AssetSignal]:
    metrics = (
        db.query(SocialPostMetricRow)
        .order_by(SocialPostMetricRow.observed_at.desc(), SocialPostMetricRow.id.desc())
        .limit(3)
        .all()
    )
    signals = [
        AssetSignal(
            signal_type="launch_asset",
            source_ref=f"social_metric:{int(row.id)}",
            title="Published content performance signal",
            summary=(
                f"impressions={row.impressions}, likes={row.likes}, "
                f"replies={row.replies}, reposts={row.reposts}, "
                f"link_clicks={row.link_clicks}. {row.summary or ''}"
            ),
            score=0.65,
        )
        for row in metrics
    ]
    if signals:
        return signals
    goals = (
        db.query(PlanningGoalRow)
        .filter(PlanningGoalRow.status == "active")
        .order_by(PlanningGoalRow.weight.desc(), PlanningGoalRow.updated_at.desc())
        .limit(3)
        .all()
    )
    return [
        AssetSignal(
            signal_type="launch_asset",
            source_ref=f"planning_goal:{int(row.id)}",
            title=row.title,
            summary=(
                f"Launch narrative candidate for goal {row.goal_key}: "
                f"{row.success_metric or row.intent_markdown}"
            ),
            score=0.60,
        )
        for row in goals
    ]


def _create_asset_from_signals(
    db: Session,
    *,
    local_date: str,
    asset_type: str,
    signals: list[AssetSignal],
) -> SocialContentAssetRow:
    pack = generate_canonical_asset_pack(
        asset_type=asset_type,
        local_date=local_date,
        signals=signals,
    )
    channels = pack.recommended_channels or _recommended_channels(asset_type)
    metadata = {
        "generated_by": "agent_content_pack_v1",
        "planner_local_date": local_date,
        "selected_signal_type": asset_type,
        "recommended_channels": channels,
        "source_signal_refs": pack.source_signal_refs
        or [signal.source_ref for signal in signals],
        "generation_reason": pack.generation_reason
        or _generation_reason(asset_type, signals),
        "signal_sample_size": len(signals),
        "key_facts": pack.key_facts,
        "code_blocks": [block.model_dump() for block in pack.code_blocks],
        "context_refs": pack.context_refs,
        "context_sources": pack.context_sources,
        "agent": pack.generation_metadata,
    }
    row = SocialContentAssetRow(
        asset_type=pack.asset_type or asset_type,
        source_type="asset_planner",
        title=_public_safe(pack.title)[:240],
        summary=_public_safe(pack.summary)[:1200],
        body=_public_safe(pack.body),
        goal_key=pack.goal_key or _infer_goal_key(signals),
        status="proposed",
        created_by="social_asset_planner_sweep",
        policy_check_json=json.dumps({"status": "passed"}, sort_keys=True),
        agent_metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    )
    db.add(row)
    db.flush()
    _record_event(
        db,
        row,
        None,
        "asset_planner_created",
        "social_asset_planner_sweep",
        f"Generated {asset_type} content asset from {len(signals)} sampled signals.",
        {
            "local_date": local_date,
            "asset_type": asset_type,
            "source_signal_refs": [signal.source_ref for signal in signals],
            "recommended_channels": channels,
        },
    )
    return row


def _recommended_channels(asset_type: str) -> list[str]:
    if asset_type == "shipping_proof":
        return ["x", "hacker_news", "reddit", "v2ex"]
    if asset_type == "developer_education":
        return ["x", "devto", "hashnode", "reddit", "v2ex"]
    if asset_type == "market_commentary":
        return ["x", "reddit", "v2ex"]
    return ["x", "hacker_news", "devto", "hashnode"]


def _generation_reason(asset_type: str, signals: list[AssetSignal]) -> str:
    refs = ", ".join(signal.source_ref for signal in signals)
    return (
        f"Selected {asset_type} because today's asset inventory is below target "
        f"and sampled signals were available: {refs}."
    )


def _infer_goal_key(signals: list[AssetSignal]) -> str | None:
    for signal in signals:
        if "sdk" in signal.title.lower():
            return "sdk_developer_quickstart"
        if "growth" in signal.title.lower() or "social" in signal.title.lower():
            return "growth_social_conversion_loop"
    return "synapse_public_preview_traction"
