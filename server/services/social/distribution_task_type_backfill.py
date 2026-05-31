"""Backfill and infer stable social distribution task types."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from server.database import utcnow
from server.database_social_distribution import SocialContentAssetRow
from server.services.social.distribution_core import _record_event
from server.services.social.distribution_document_content import parse_json_object
from server.services.social.distribution_task_types import (
    CONTENT_DISTRIBUTION,
    LEGACY_UNCLASSIFIED,
    MANUAL_PLATFORM_POST,
    MULTI_PLATFORM_CAMPAIGN,
    X_ARTICLE_PACK,
    X_MEDIA_POST,
    X_REPLY_BLOCK,
    channel_selection_mode,
    generator_key_for_task_type,
    task_type_label,
)


TERMINAL_STATUSES = {"archived", "removed", "rejected"}


@dataclass(frozen=True)
class TaskTypeBackfillOptions:
    dry_run: bool = True
    actor: str = "operator"
    include_archived: bool = False


@dataclass(frozen=True)
class TaskTypeInferenceContext:
    actions: set[str]
    asset_type: str
    doc_kinds: set[str]
    post_intent: str
    source_type: str
    target_platforms: list[str]
    task_platforms: set[str]


class TaskTypeBackfillItem(BaseModel):
    asset_id: int
    title: str
    previous_task_type: str | None = None
    inferred_task_type: str
    reason: str
    changed: bool


class TaskTypeBackfillResult(BaseModel):
    dry_run: bool
    scanned_count: int
    changed_count: int
    items: list[TaskTypeBackfillItem]


def infer_task_type_for_asset(asset: SocialContentAssetRow) -> tuple[str, str]:
    metadata = parse_json_object(asset.agent_metadata_json)
    existing = str(metadata.get("task_type") or "").strip().lower()
    if existing:
        return existing, "explicit_metadata"

    context = _inference_context(asset, metadata)
    if _has_article_pack_evidence(context):
        return X_ARTICLE_PACK, "x_article_pack_evidence"
    if _has_x_media_evidence(context):
        return X_MEDIA_POST, "x_media_task_evidence"
    if _has_reply_evidence(context):
        return X_REPLY_BLOCK, "reply_intent"
    if _has_multi_platform_evidence(context):
        return MULTI_PLATFORM_CAMPAIGN, "multi_platform_evidence"
    if _is_legacy_content_distribution(context):
        return CONTENT_DISTRIBUTION, "legacy_content_distribution"
    if _is_single_manual_platform(context):
        return MANUAL_PLATFORM_POST, "single_manual_platform"
    return LEGACY_UNCLASSIFIED, "unclassified_legacy_asset"


def backfill_content_asset_task_types(
    db: Session,
    options: TaskTypeBackfillOptions | None = None,
) -> TaskTypeBackfillResult:
    opts = options or TaskTypeBackfillOptions()
    query = db.query(SocialContentAssetRow).order_by(SocialContentAssetRow.id.asc())
    if not opts.include_archived:
        query = query.filter(~SocialContentAssetRow.status.in_(TERMINAL_STATUSES))
    rows = query.all()
    items: list[TaskTypeBackfillItem] = []
    changed_count = 0
    for asset in rows:
        metadata = parse_json_object(asset.agent_metadata_json)
        previous = _string_or_none(metadata.get("task_type"))
        inferred, reason = infer_task_type_for_asset(asset)
        changed = previous != inferred
        items.append(
            TaskTypeBackfillItem(
                asset_id=int(asset.id),
                title=asset.title,
                previous_task_type=previous,
                inferred_task_type=inferred,
                reason=reason,
                changed=changed,
            )
        )
        if changed:
            changed_count += 1
            if not opts.dry_run:
                _write_task_type_metadata(
                    db,
                    asset,
                    metadata=metadata,
                    task_type=inferred,
                    reason=reason,
                    actor=opts.actor,
                )
    if not opts.dry_run:
        db.commit()
    return TaskTypeBackfillResult(
        dry_run=opts.dry_run,
        scanned_count=len(rows),
        changed_count=changed_count,
        items=items,
    )


def _write_task_type_metadata(
    db: Session,
    asset: SocialContentAssetRow,
    *,
    metadata: dict[str, Any],
    task_type: str,
    reason: str,
    actor: str,
) -> None:
    metadata.update(
        {
            "task_type": task_type,
            "task_type_label": task_type_label(task_type),
            "generator_key": generator_key_for_task_type(task_type),
            "channel_selection_mode": channel_selection_mode(task_type),
            "task_type_backfilled_at": utcnow().isoformat(),
            "task_type_backfill_reason": reason,
        }
    )
    asset.agent_metadata_json = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
    )
    asset.updated_at = utcnow()
    _record_event(
        db,
        asset,
        None,
        "content_task_type_backfilled",
        actor,
        "Backfilled stable content task type.",
        {
            "task_type": task_type,
            "reason": reason,
        },
    )


def _target_platforms(metadata: dict[str, Any]) -> list[str]:
    raw = metadata.get("target_platforms")
    if not isinstance(raw, list):
        return []
    return [str(item).strip().lower() for item in raw if str(item).strip()]


def _inference_context(
    asset: SocialContentAssetRow,
    metadata: dict[str, Any],
) -> TaskTypeInferenceContext:
    return TaskTypeInferenceContext(
        actions=_task_actions(asset),
        asset_type=str(getattr(asset, "asset_type", "") or "").strip().lower(),
        doc_kinds=_document_kinds(asset),
        post_intent=str(metadata.get("post_intent") or "").strip().lower(),
        source_type=str(getattr(asset, "source_type", "") or "").strip().lower(),
        target_platforms=_target_platforms(metadata),
        task_platforms=_task_platforms(asset),
    )


def _task_actions(asset: SocialContentAssetRow) -> set[str]:
    return {str(task.action or "").strip().lower() for task in list(asset.tasks or [])}


def _document_kinds(asset: SocialContentAssetRow) -> set[str]:
    return {
        str(document.document_kind or "").strip().lower()
        for document in list(asset.documents or [])
    }


def _task_platforms(asset: SocialContentAssetRow) -> set[str]:
    return {
        str(task.platform or "").strip().lower()
        for task in list(asset.tasks or [])
        if str(task.platform or "").strip()
    }


def _has_article_pack_evidence(context: TaskTypeInferenceContext) -> bool:
    return "x_article_pack" in context.doc_kinds or bool(
        context.actions.intersection({"x_article_manual_publish", "x_article_teaser"})
    )


def _has_x_media_evidence(context: TaskTypeInferenceContext) -> bool:
    return bool(context.actions.intersection({"x_media_post", "x_media_teaser"}))


def _has_reply_evidence(context: TaskTypeInferenceContext) -> bool:
    if context.post_intent == "engagement_reply":
        return True
    if context.asset_type in {"reply", "engagement_reply"}:
        return True
    return context.post_intent == "reply" and context.target_platforms == ["x"]


def _has_multi_platform_evidence(context: TaskTypeInferenceContext) -> bool:
    return len(context.target_platforms) > 1 or len(context.task_platforms) > 1


def _is_legacy_content_distribution(context: TaskTypeInferenceContext) -> bool:
    return context.source_type in {
        "manual_task",
        "manual",
        "asset_planner",
        "daily_planner",
    } and context.asset_type in {"article", "shipping_proof", "content"}


def _is_single_manual_platform(context: TaskTypeInferenceContext) -> bool:
    return len(context.target_platforms) == 1 and context.target_platforms[0] != "x"


def _string_or_none(value: object) -> str | None:
    text = str(value or "").strip().lower()
    return text or None
