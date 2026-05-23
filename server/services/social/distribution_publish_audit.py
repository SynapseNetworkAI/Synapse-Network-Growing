"""Manual live/removed state and published-page audit helpers."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from server import schemas_social_distribution as dist_schema
from server.database import utcnow
from server.database_social_distribution import SocialDistributionTaskRow
from server.services.social.distribution_core import _clean_optional, _record_event
from server.services.social.distribution_documents import sync_task_document_from_task
from server.services.social.distribution_projection import _task_out

VISIBILITY_STATUSES = {
    "unverified",
    "visible",
    "removed_by_filter",
    "flagged",
    "not_found",
    "blocked",
}
LAYOUT_STATUSES = {"unknown", "passed", "needs_fix"}


def mark_distribution_task_live(
    db: Session, task_id: int, body: dist_schema.SocialDistributionMarkLiveRequest
) -> dist_schema.SocialDistributionTaskOut:
    row = _task_or_error(db, task_id)
    if not body.published_url.strip():
        raise ValueError("published_url is required.")
    existing = _task_metadata(row)
    layout_status = str(existing.get("layout_status") or "unknown")
    row.status = "live"
    row.published_url = body.published_url.strip()
    row.manual_result_note = _clean_optional(body.manual_result_note)
    row.metadata_json = _json_dump(
        {
            **existing,
            "visibility_status": "unverified",
            "layout_status": layout_status,
            "last_publish_audit": {
                "visibility_status": "unverified",
                "layout_status": layout_status,
                "source": "mark_live",
            },
        }
    )
    row.updated_at = utcnow()
    sync_task_document_from_task(
        db, task=row, metadata={"published_url": row.published_url}
    )
    _record_event(
        db,
        row.asset,
        row,
        "task_marked_live",
        body.actor,
        "Operator marked task live.",
        {"published_url": row.published_url},
    )
    db.commit()
    db.refresh(row)
    return _task_out(row)


def mark_distribution_task_removed(
    db: Session, task_id: int, body: dist_schema.SocialDistributionMarkRemovedRequest
) -> dist_schema.SocialDistributionTaskOut:
    row = _task_or_error(db, task_id)
    if not body.manual_result_note.strip():
        raise ValueError("removed reason is required.")
    existing = _task_metadata(row)
    row.status = "removed"
    row.manual_result_note = body.manual_result_note.strip()
    row.metadata_json = _json_dump(
        {
            **existing,
            "visibility_status": "removed_by_filter",
            "last_publish_audit": {
                "visibility_status": "removed_by_filter",
                "layout_status": existing.get("layout_status") or "unknown",
                "source": "mark_removed",
                "note": row.manual_result_note,
            },
        }
    )
    row.updated_at = utcnow()
    sync_task_document_from_task(
        db, task=row, metadata={"removed_reason": row.manual_result_note}
    )
    _record_event(
        db,
        row.asset,
        row,
        "task_removed",
        body.actor,
        "Operator marked task removed.",
        {"reason": row.manual_result_note},
    )
    db.commit()
    db.refresh(row)
    return _task_out(row)


def audit_distribution_task_published_page(
    db: Session,
    task_id: int,
    body: dist_schema.SocialDistributionAuditPublishedPageRequest,
) -> dist_schema.SocialDistributionTaskOut:
    row = _task_or_error(db, task_id)
    visibility_status = body.visibility_status.strip()
    layout_status = body.layout_status.strip()
    if visibility_status not in VISIBILITY_STATUSES:
        raise ValueError(f"unknown visibility status: {visibility_status}")
    if layout_status not in LAYOUT_STATUSES:
        raise ValueError(f"unknown layout status: {layout_status}")
    if row.status == "live" and not str(row.published_url or "").strip():
        raise ValueError("published_url is required before auditing a live task.")
    row.metadata_json = _json_dump(
        {
            **_task_metadata(row),
            "visibility_status": visibility_status,
            "layout_status": layout_status,
            "last_publish_audit": {
                "visibility_status": visibility_status,
                "layout_status": layout_status,
                "note": _clean_optional(body.audit_note),
                "actor": body.actor.strip() or "operator",
                "source": "operator_audit",
            },
        }
    )
    row.updated_at = utcnow()
    _record_event(
        db,
        row.asset,
        row,
        "task_published_page_audited",
        body.actor,
        _audit_summary(visibility_status, layout_status, body.audit_note),
        {
            "visibility_status": visibility_status,
            "layout_status": layout_status,
            "published_url": row.published_url,
            "note": _clean_optional(body.audit_note),
        },
    )
    db.commit()
    db.refresh(row)
    return _task_out(row)


def _task_or_error(db: Session, task_id: int) -> SocialDistributionTaskRow:
    row = db.get(SocialDistributionTaskRow, task_id)
    if row is None:
        raise ValueError("Distribution task not found.")
    return row


def _task_metadata(row: SocialDistributionTaskRow) -> dict[str, object]:
    try:
        payload = json.loads(row.metadata_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_dump(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _audit_summary(
    visibility_status: str, layout_status: str, audit_note: str | None
) -> str:
    note = _clean_optional(audit_note)
    suffix = f": {note}" if note else ""
    return (
        f"Published page audited: visibility={visibility_status}, "
        f"layout={layout_status}{suffix}"
    )
