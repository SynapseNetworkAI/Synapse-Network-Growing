"""Manual distribution task state updates."""

from __future__ import annotations

from sqlalchemy.orm import Session

from server import schemas_social_distribution as dist_schema
from server.database import utcnow
from server.database_social_distribution import SocialDistributionTaskRow
from server.services.social.publishing import (
    SocialPublishError,
    ensure_default_social_account,
    run_content_policy_check,
    x_publisher,
)
from server.services.social.distribution_core import (
    _clean_optional,
    _record_event,
    _validate_task_status,
)
from server.services.social.distribution_documents import (
    sync_task_document_from_task,
)
from server.services.social.distribution_projection import _task_out


def update_distribution_task(
    db: Session, task_id: int, body: dist_schema.SocialDistributionTaskPatchRequest
) -> dist_schema.SocialDistributionTaskOut:
    row = db.get(SocialDistributionTaskRow, task_id)
    if row is None:
        raise ValueError("Distribution task not found.")
    if body.status is not None:
        _validate_task_status(body.status)
        row.status = body.status.strip()
    for field in (
        "platform_title",
        "platform_body",
        "operator_checklist",
        "submission_url",
        "published_url",
        "external_post_id",
        "failure_summary",
        "manual_result_note",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(row, field, value.strip() if isinstance(value, str) else value)
    row.updated_at = utcnow()
    sync_task_document_from_task(
        db,
        task=row,
        metadata={"published_url": row.published_url},
    )
    _record_event(
        db,
        row.asset,
        row,
        "task_updated",
        "operator",
        "Distribution task updated.",
        {"status": row.status},
    )
    db.commit()
    db.refresh(row)
    return _task_out(row)


def mark_distribution_task_live(
    db: Session, task_id: int, body: dist_schema.SocialDistributionMarkLiveRequest
) -> dist_schema.SocialDistributionTaskOut:
    row = db.get(SocialDistributionTaskRow, task_id)
    if row is None:
        raise ValueError("Distribution task not found.")
    if not body.published_url.strip():
        raise ValueError("published_url is required.")
    row.status = "live"
    row.published_url = body.published_url.strip()
    row.manual_result_note = _clean_optional(body.manual_result_note)
    row.updated_at = utcnow()
    sync_task_document_from_task(
        db,
        task=row,
        metadata={"published_url": row.published_url},
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
    row = db.get(SocialDistributionTaskRow, task_id)
    if row is None:
        raise ValueError("Distribution task not found.")
    if not body.manual_result_note.strip():
        raise ValueError("removed reason is required.")
    row.status = "removed"
    row.manual_result_note = body.manual_result_note.strip()
    row.updated_at = utcnow()
    sync_task_document_from_task(
        db,
        task=row,
        metadata={"removed_reason": row.manual_result_note},
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


def publish_distribution_task_to_x(
    db: Session, task_id: int, actor: str = "operator"
) -> dist_schema.SocialDistributionTaskOut:
    row = db.get(SocialDistributionTaskRow, task_id)
    if row is None:
        raise ValueError("Distribution task not found.")
    if row.platform != "x":
        raise ValueError("only X distribution tasks can be published via API in v1.")
    if row.account and row.account.publish_mode != "api_human_gated":
        raise ValueError("this X channel is not configured for API publishing.")
    if row.status not in {"needs_review", "approved", "failed", "draft_ready"}:
        raise ValueError(f"task status {row.status} cannot be published to X.")
    text = str(row.platform_body or "").strip()
    policy = run_content_policy_check(text)
    if policy.get("status") == "blocked":
        row.status = "failed"
        row.failure_summary = "policy_blocked: " + ", ".join(
            str(item) for item in policy.get("blocked_reasons", [])
        )
        row.updated_at = utcnow()
        sync_task_document_from_task(
            db,
            task=row,
            metadata={"failure_summary": row.failure_summary},
        )
        _record_event(
            db,
            row.asset,
            row,
            "task_publish_blocked",
            actor,
            row.failure_summary,
            {"policy": policy},
        )
        db.commit()
        db.refresh(row)
        return _task_out(row)

    social_account = ensure_default_social_account(db)
    row.status = "submitted"
    row.updated_at = utcnow()
    db.flush()
    try:
        result = x_publisher.publish_text(social_account, text)
    except SocialPublishError as exc:
        row.status = "failed"
        row.failure_summary = exc.summary
        row.updated_at = utcnow()
        sync_task_document_from_task(
            db,
            task=row,
            metadata={"failure_summary": row.failure_summary},
        )
        _record_event(
            db,
            row.asset,
            row,
            "task_publish_failed",
            actor,
            exc.summary,
            {"kind": exc.kind},
        )
        db.commit()
        db.refresh(row)
        return _task_out(row)

    row.status = "live"
    row.external_post_id = result.post_id
    row.published_url = f"https://x.com/SynapseNetworkA/status/{result.post_id}"
    row.failure_summary = None
    row.updated_at = utcnow()
    sync_task_document_from_task(
        db,
        task=row,
        metadata={"external_post_id": result.post_id, "published_url": row.published_url},
    )
    _record_event(
        db,
        row.asset,
        row,
        "task_published_x",
        actor,
        "Distribution task published to X after Human Gate.",
        {"external_post_id": result.post_id, "response": result.response_summary},
    )
    db.commit()
    db.refresh(row)
    return _task_out(row)
