"""Manual distribution task state updates."""

from __future__ import annotations

import json

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
from server.services.social.distribution_content_strategy import (
    X_WEIGHTED_CHAR_LIMIT,
    x_format_from_metadata,
    x_tweets_from_metadata,
    x_weighted_character_count,
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
    metadata = _task_metadata(row)
    tweets = x_tweets_from_metadata(metadata, row.platform_body)
    x_format = x_format_from_metadata(metadata, tweets)
    _validate_x_publish_payload(x_format, tweets)
    policy_text = "\n\n".join(tweets)
    policy = run_content_policy_check(policy_text)
    if policy.get("status") == "blocked":
        return _mark_x_policy_blocked(db, row, actor, policy)

    social_account = ensure_default_social_account(db)
    row.status = "submitted"
    row.updated_at = utcnow()
    db.flush()
    try:
        if x_format == "thread":
            result = _publish_x_thread(db, row, social_account, tweets)
        else:
            result = x_publisher.publish_text(social_account, tweets[0])
    except SocialPublishError as exc:
        return _mark_x_publish_failed(db, row, actor, exc)

    return _mark_x_publish_success(db, row, actor, metadata, x_format, result)


def _mark_x_policy_blocked(
    db: Session,
    row: SocialDistributionTaskRow,
    actor: str,
    policy: dict[str, object],
) -> dist_schema.SocialDistributionTaskOut:
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


def _mark_x_publish_failed(
    db: Session,
    row: SocialDistributionTaskRow,
    actor: str,
    exc: SocialPublishError,
) -> dist_schema.SocialDistributionTaskOut:
    row.status = "failed"
    row.failure_summary = exc.summary
    row.updated_at = utcnow()
    sync_task_document_from_task(
        db,
        task=row,
        metadata={
            "failure_summary": row.failure_summary,
            **_task_metadata(row),
        },
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


def _mark_x_publish_success(
    db: Session,
    row: SocialDistributionTaskRow,
    actor: str,
    metadata: dict[str, object],
    x_format: str,
    result,
) -> dist_schema.SocialDistributionTaskOut:
    published_ids = _published_tweet_ids(row, x_format, result.post_id)
    row.status = "live"
    row.external_post_id = result.post_id
    row.published_url = f"https://x.com/SynapseNetworkA/status/{result.post_id}"
    row.failure_summary = None
    row.metadata_json = json.dumps(
        {
            **metadata,
            "x_format": x_format,
            "published_tweet_ids": published_ids,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    row.updated_at = utcnow()
    sync_task_document_from_task(
        db,
        task=row,
        metadata={
            "external_post_id": result.post_id,
            "published_url": row.published_url,
            "published_tweet_ids": published_ids,
        },
    )
    _record_event(
        db,
        row.asset,
        row,
        "task_published_x_thread" if x_format == "thread" else "task_published_x",
        actor,
        _x_publish_success_message(x_format),
        {
            "external_post_id": result.post_id,
            "published_tweet_ids": published_ids,
            "response": result.response_summary,
        },
    )
    db.commit()
    db.refresh(row)
    return _task_out(row)


def _publish_x_thread(
    db: Session,
    row: SocialDistributionTaskRow,
    social_account,
    tweets: list[str],
):
    published_ids: list[str] = []
    first = x_publisher.publish_text(social_account, tweets[0])
    published_ids.append(first.post_id)
    _persist_x_thread_progress(db, row, published_ids)
    previous_id = first.post_id
    for index, tweet in enumerate(tweets[1:], start=2):
        try:
            reply = x_publisher.publish_reply(
                social_account,
                tweet,
                in_reply_to_tweet_id=previous_id,
            )
        except SocialPublishError as exc:
            _mark_x_thread_partial_failure(db, row, published_ids, index, exc.summary)
            raise
        published_ids.append(reply.post_id)
        previous_id = reply.post_id
        _persist_x_thread_progress(db, row, published_ids)
    return first


def _published_tweet_ids(
    row: SocialDistributionTaskRow, x_format: str, root_post_id: str
) -> list[str]:
    published_ids = (
        _task_metadata(row).get("published_tweet_ids")
        if x_format == "thread"
        else [root_post_id]
    )
    if not isinstance(published_ids, list):
        published_ids = [root_post_id]
    return [str(item) for item in published_ids]


def _x_publish_success_message(x_format: str) -> str:
    if x_format == "thread":
        return "Distribution task published to X thread after Human Gate."
    return "Distribution task published to X after Human Gate."


def _persist_x_thread_progress(
    db: Session, row: SocialDistributionTaskRow, published_ids: list[str]
) -> None:
    metadata = {
        **_task_metadata(row),
        "published_tweet_ids": list(published_ids),
    }
    row.metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    db.flush()


def _mark_x_thread_partial_failure(
    db: Session,
    row: SocialDistributionTaskRow,
    published_ids: list[str],
    failure_index: int,
    summary: str,
) -> None:
    metadata = {
        **_task_metadata(row),
        "published_tweet_ids": list(published_ids),
        "partial_publish_failure_index": failure_index,
    }
    row.status = "failed"
    row.failure_summary = summary
    row.metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    row.updated_at = utcnow()
    sync_task_document_from_task(
        db,
        task=row,
        metadata={
            "failure_summary": summary,
            "published_tweet_ids": list(published_ids),
            "partial_publish_failure_index": failure_index,
        },
    )


def _validate_x_publish_payload(x_format: str, tweets: list[str]) -> None:
    if not tweets:
        raise ValueError("X publish payload is empty.")
    if x_format == "single" and len(tweets) != 1:
        raise ValueError("X single publish requires exactly one tweet.")
    if x_format == "thread" and len(tweets) < 2:
        raise ValueError("X thread publish requires at least two tweets.")
    for index, tweet in enumerate(tweets):
        count = x_weighted_character_count(tweet)
        if count > X_WEIGHTED_CHAR_LIMIT:
            raise ValueError(
                f"X tweet {index + 1} exceeds {X_WEIGHTED_CHAR_LIMIT} weighted chars."
            )


def _task_metadata(row: SocialDistributionTaskRow) -> dict[str, object]:
    try:
        payload = json.loads(row.metadata_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
