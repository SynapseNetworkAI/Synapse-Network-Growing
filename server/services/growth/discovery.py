from __future__ import annotations

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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
