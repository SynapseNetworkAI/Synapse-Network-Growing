from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from server.database_growth import (
    GrowthAIVisibilityCheckRow,
    GrowthDiscoveryListingRow,
    GrowthLeadRow,
    GrowthOutreachMessageRow,
)
from server.schemas_growth import (
    GrowthAIVisibilityCheckCreate,
    GrowthAIVisibilityCheckListOut,
    GrowthAIVisibilityCheckOut,
    GrowthAIVisibilityComparisonListOut,
    GrowthAIVisibilityComparisonOut,
    GrowthDiscoveryListingCreate,
    GrowthDiscoveryListingListOut,
    GrowthDiscoveryListingOut,
    GrowthDiscoveryListingPatch,
    GrowthOverviewOut,
)
from server.services.growth.serializer import ai_check_out, json_dumps, listing_out

LISTING_STATUSES = {
    "candidate",
    "package_ready",
    "registry_submitted",
    "listed",
    "verified",
    "needs_fix",
}


def overview(db: Session) -> GrowthOverviewOut:
    return GrowthOverviewOut(
        lead_counts=_count_by(db, GrowthLeadRow, GrowthLeadRow.lead_type),
        message_counts=_count_by(
            db, GrowthOutreachMessageRow, GrowthOutreachMessageRow.status
        ),
        ai_visibility={
            "checks": int(
                db.query(func.count(GrowthAIVisibilityCheckRow.id)).scalar() or 0
            ),
            "cited": int(
                db.query(func.count(GrowthAIVisibilityCheckRow.id))
                .filter(GrowthAIVisibilityCheckRow.synapse_cited == 1)
                .scalar()
                or 0
            ),
        },
        discovery_counts=_count_by(
            db, GrowthDiscoveryListingRow, GrowthDiscoveryListingRow.status
        ),
    )


def create_ai_check(
    db: Session, body: GrowthAIVisibilityCheckCreate
) -> GrowthAIVisibilityCheckOut:
    if not body.query.strip() or not body.platform.strip():
        raise ValueError("query and platform are required")
    row = GrowthAIVisibilityCheckRow(
        query=body.query.strip(),
        platform=body.platform.strip(),
        answer_summary=body.answer_summary.strip(),
        synapse_mentioned=1 if body.synapse_mentioned else 0,
        synapse_cited=1 if body.synapse_cited else 0,
        cited_urls_json=json_dumps(body.cited_urls),
        competitor_mentions_json=json_dumps(body.competitor_mentions),
        missing_facts_json=json_dumps(body.missing_facts),
        next_action=body.next_action.strip(),
        feed_key=body.feed_key.strip(),
        run_group=body.run_group.strip(),
        result_rank=max(int(body.result_rank or 0), 0),
        evidence_url=body.evidence_url.strip(),
        metadata_json=json_dumps(body.metadata),
    )
    db.add(row)
    db.commit()
    return ai_check_out(row)


def list_ai_checks(
    db: Session,
    *,
    q: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> GrowthAIVisibilityCheckListOut:
    query = db.query(GrowthAIVisibilityCheckRow)
    if platform:
        query = query.filter(GrowthAIVisibilityCheckRow.platform == platform)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                GrowthAIVisibilityCheckRow.query.ilike(pattern),
                GrowthAIVisibilityCheckRow.answer_summary.ilike(pattern),
            )
        )
    total = int(query.count())
    items = (
        query.order_by(
            GrowthAIVisibilityCheckRow.run_at.desc(),
            GrowthAIVisibilityCheckRow.id.desc(),
        )
        .offset(max(offset, 0))
        .limit(_limit(limit))
        .all()
    )
    return GrowthAIVisibilityCheckListOut(
        items=[ai_check_out(item) for item in items],
        total=total,
        limit=_limit(limit),
        offset=max(offset, 0),
    )


def list_ai_comparisons(
    db: Session,
    *,
    feed_key: str | None = None,
    run_group: str | None = None,
    limit: int = 20,
) -> GrowthAIVisibilityComparisonListOut:
    query = db.query(GrowthAIVisibilityCheckRow)
    if feed_key:
        query = query.filter(GrowthAIVisibilityCheckRow.feed_key == feed_key.strip())
    if run_group:
        query = query.filter(GrowthAIVisibilityCheckRow.run_group == run_group.strip())
    rows = (
        query.order_by(
            GrowthAIVisibilityCheckRow.run_at.desc(),
            GrowthAIVisibilityCheckRow.id.desc(),
        )
        .limit(_limit(limit) * 6)
        .all()
    )
    grouped: dict[tuple[str, str], list[GrowthAIVisibilityCheckRow]] = {}
    for row in rows:
        key = (row.feed_key or "unassigned", row.run_group or "manual")
        grouped.setdefault(key, []).append(row)
    comparisons = [_comparison_out(key, value) for key, value in grouped.items()]
    comparisons.sort(key=lambda item: item.latest_run_at or datetime.min, reverse=True)
    return GrowthAIVisibilityComparisonListOut(
        items=comparisons[: _limit(limit)],
        total=len(comparisons),
    )


def create_listing(
    db: Session, body: GrowthDiscoveryListingCreate
) -> GrowthDiscoveryListingOut:
    _validate_listing_status(body.status)
    row = GrowthDiscoveryListingRow(
        surface=body.surface.strip(),
        target_repo=body.target_repo.strip(),
        package_name=body.package_name.strip(),
        listing_url=body.listing_url.strip(),
        status=body.status,
        submission_evidence_json=json_dumps(body.submission_evidence),
        verification_evidence_json=json_dumps(body.verification_evidence),
        failure_reason=body.failure_reason.strip(),
        last_checked_at=_utcnow(),
    )
    if not row.surface:
        raise ValueError("surface is required")
    db.add(row)
    db.commit()
    return listing_out(row)


def list_listings(
    db: Session,
    *,
    surface: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> GrowthDiscoveryListingListOut:
    query = db.query(GrowthDiscoveryListingRow)
    if surface:
        query = query.filter(GrowthDiscoveryListingRow.surface == surface)
    if status:
        query = query.filter(GrowthDiscoveryListingRow.status == status)
    total = int(query.count())
    items = (
        query.order_by(
            GrowthDiscoveryListingRow.updated_at.desc(),
            GrowthDiscoveryListingRow.id.desc(),
        )
        .offset(max(offset, 0))
        .limit(_limit(limit))
        .all()
    )
    return GrowthDiscoveryListingListOut(
        items=[listing_out(item) for item in items],
        total=total,
        limit=_limit(limit),
        offset=max(offset, 0),
    )


def patch_listing(
    db: Session, listing_id: int, body: GrowthDiscoveryListingPatch
) -> GrowthDiscoveryListingOut:
    row = (
        db.query(GrowthDiscoveryListingRow)
        .filter(GrowthDiscoveryListingRow.id == int(listing_id))
        .first()
    )
    if row is None:
        raise ValueError("discovery listing not found")
    if body.status is not None:
        _validate_listing_status(body.status)
        row.status = body.status
    if body.listing_url is not None:
        row.listing_url = body.listing_url.strip()
    if body.submission_evidence is not None:
        row.submission_evidence_json = json_dumps(body.submission_evidence)
    if body.verification_evidence is not None:
        row.verification_evidence_json = json_dumps(body.verification_evidence)
    if body.failure_reason is not None:
        row.failure_reason = body.failure_reason.strip()
    row.last_checked_at = _utcnow()
    db.commit()
    return listing_out(row)


def _count_by(db: Session, model, column) -> dict[str, int]:
    rows = db.query(column, func.count(model.id)).group_by(column).all()
    return {str(key or ""): int(count or 0) for key, count in rows if key}


def _validate_listing_status(status: str) -> None:
    if status not in LISTING_STATUSES:
        raise ValueError("invalid discovery listing status")


def _limit(value: int) -> int:
    return min(max(int(value or 50), 1), 100)


def _comparison_out(
    key: tuple[str, str],
    rows: list[GrowthAIVisibilityCheckRow],
) -> GrowthAIVisibilityComparisonOut:
    platforms = sorted({row.platform for row in rows if row.platform})
    external_rows = [row for row in rows if _is_external_visibility_platform(row.platform)]
    external_platforms = sorted({row.platform for row in external_rows if row.platform})
    competitors: Counter[str] = Counter()
    next_actions: list[str] = []
    evidence_urls: list[str] = []
    latest_run_at = None
    for row in rows:
        competitors.update(_json_list(row.competitor_mentions_json))
        if row.next_action and row.next_action not in next_actions:
            next_actions.append(row.next_action)
        if row.evidence_url and row.evidence_url not in evidence_urls:
            evidence_urls.append(row.evidence_url)
        if latest_run_at is None or row.run_at > latest_run_at:
            latest_run_at = row.run_at
    target_platforms = ["chatgpt", "claude", "grok"]
    return GrowthAIVisibilityComparisonOut(
        feed_key=key[0],
        run_group=key[1],
        platforms=platforms,
        external_platforms=external_platforms,
        total_checks=len(rows),
        external_checks_count=len(external_rows),
        local_validation_count=len(rows) - len(external_rows),
        mentioned_count=sum(1 for row in external_rows if row.synapse_mentioned),
        cited_count=sum(1 for row in external_rows if row.synapse_cited),
        missing_platforms=[
            platform for platform in target_platforms if platform not in external_platforms
        ],
        top_competitors=[item for item, _count in competitors.most_common(5)],
        next_actions=next_actions[:5],
        evidence_urls=evidence_urls[:5],
        latest_run_at=latest_run_at,
    )


def _is_external_visibility_platform(platform: str | None) -> bool:
    normalized = (platform or "").strip().lower()
    if not normalized:
        return False
    if normalized.endswith("_validation"):
        return False
    if normalized in {"local", "docs_local", "www_local", "staging_validation"}:
        return False
    return True


def _json_list(value: str) -> list[str]:
    import json

    try:
        loaded = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded if str(item).strip()]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
