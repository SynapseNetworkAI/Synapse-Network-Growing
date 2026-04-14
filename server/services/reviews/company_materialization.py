"""Company review refresh and latest-row helpers."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from server.database import CompanyOperatingReviewRow

logger = logging.getLogger("ops-dashboard.company_review")


def _persistable_review_payload(payload: dict[str, object]) -> dict[str, object]:
    """Project the full review payload into the persisted JSON shape."""

    return {
        "portfolio_summary": payload["portfolio_summary"],
        "project_highlights": payload["project_highlights"],
        "bottlenecks": payload["bottlenecks"],
        "incidents": payload["incidents"],
        "recurring_bug_fingerprints": payload["recurring_bug_fingerprints"],
        "cross_project_bug_recoveries": payload["cross_project_bug_recoveries"],
        "human_gate_hotspots": payload["human_gate_hotspots"],
        "automation_candidates": payload["automation_candidates"],
        "next_cycle_recommendations": payload["next_cycle_recommendations"],
        "next_cycle_requirement_bundle": payload["next_cycle_requirement_bundle"],
        "operator_review_package": payload["operator_review_package"],
        "autonomous_coo_posture": payload["autonomous_coo_posture"],
        "source_snapshot": payload["source_snapshot"],
    }


def refresh_company_operating_review(db: Session) -> CompanyOperatingReviewRow:
    """Recompute and persist the latest company operating review snapshot."""

    from server.services.reviews.company_review import _json_dumps, build_operating_review_payload

    payload = build_operating_review_payload(db)
    row = CompanyOperatingReviewRow(
        cycle_label=str(payload["cycle_label"]),
        title=str(payload["title"]),
        summary_markdown=str(payload["summary_markdown"]),
        payload_json=_json_dumps(_persistable_review_payload(payload)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "event=company_review_refreshed review_id=%s cycle=%s bundle_items=%s recommendations=%s incidents=%s",
        row.id,
        row.cycle_label,
        len(payload.get("next_cycle_requirement_bundle") or []),
        len(payload.get("next_cycle_recommendations") or []),
        len(payload.get("incidents") or []),
    )
    return row


def latest_company_operating_review(db: Session) -> CompanyOperatingReviewRow:
    """Return the latest persisted company review, refreshing when none exists."""

    row = db.query(CompanyOperatingReviewRow).order_by(
        CompanyOperatingReviewRow.created_at.desc(),
        CompanyOperatingReviewRow.id.desc(),
    ).first()
    if row is None:
        row = refresh_company_operating_review(db)
    return row


__all__ = [
    "_persistable_review_payload",
    "refresh_company_operating_review",
    "latest_company_operating_review",
]
