"""Content-task creation for the Social Distribution board."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from server import schemas_social_distribution as dist_schema
from server.database_social_distribution import SocialContentAssetRow
from server.services.social.distribution_core import _clean_optional, _record_event
from server.services.social.distribution_document_content import (
    build_source_plan_payload,
    clean_platform_list,
    source_plan_markdown,
    summary_from_text,
)
from server.services.social.distribution_content_task_keys import (
    content_task_key as make_content_task_key,
    existing_content_task,
)
from server.services.social.distribution_documents import _upsert_document
from server.services.social.distribution_task_types import (
    channel_selection_mode,
    generator_key_for_task_type,
    normalize_social_task_type,
    task_type_label,
    task_type_target_platforms,
)


def create_content_task(
    db: Session,
    body: dist_schema.SocialContentTaskCreateRequest,
) -> dist_schema.SocialContentAssetDetailOut:
    from server.services.social.distribution import get_content_asset

    if not body.title.strip():
        raise ValueError("content task title is required.")
    planned_publish_at = (
        body.planned_publish_at.isoformat() if body.planned_publish_at else None
    )
    requested_platforms = clean_platform_list(body.target_platforms)
    task_type = normalize_social_task_type(
        body.task_type,
        post_intent=body.post_intent,
        target_platforms=requested_platforms,
    )
    target_platforms = task_type_target_platforms(task_type, requested_platforms)
    content_task_key = make_content_task_key(
        task_type=task_type,
        title=body.title,
        campaign_key=body.campaign_key,
        goal_key=body.goal_key,
    )
    existing = existing_content_task(db, content_task_key)
    if existing is not None:
        detail = get_content_asset(db, int(existing.id))
        detail.agent_metadata["reused_existing"] = True
        detail.agent_metadata["content_task_key"] = content_task_key
        return detail
    asset = _create_asset(
        body, task_type, target_platforms, content_task_key, planned_publish_at
    )
    db.add(asset)
    db.flush()
    _create_source_plan_document(db, asset, body, target_platforms)
    _record_event(
        db,
        asset,
        None,
        "content_task_created",
        asset.created_by,
        "Content task created with source plan document.",
        {
            "target_platforms": target_platforms,
            "task_type": task_type,
            "content_task_key": content_task_key,
            "generator_key": generator_key_for_task_type(task_type),
        },
    )
    db.commit()
    db.refresh(asset)
    return get_content_asset(db, int(asset.id))


def _create_asset(
    body: dist_schema.SocialContentTaskCreateRequest,
    task_type: str,
    target_platforms: list[str],
    content_task_key: str,
    planned_publish_at: str | None,
) -> SocialContentAssetRow:
    return SocialContentAssetRow(
        asset_type="article",
        source_type="manual_task",
        title=body.title.strip(),
        body=_clean_optional(body.source_material),
        summary=summary_from_text(body.source_material) or body.title.strip(),
        canonical_url=_clean_optional(body.canonical_url),
        goal_key=_clean_optional(body.goal_key),
        status="draft",
        created_by=body.created_by.strip() or "operator",
        agent_metadata_json=json.dumps(
            {
                "source_of_truth": "social_content_assets",
                "task_shape": "symphony_style_distribution_board",
                "task_type": task_type,
                "task_type_label": task_type_label(task_type),
                "generator_key": generator_key_for_task_type(task_type),
                "channel_selection_mode": channel_selection_mode(task_type),
                "content_task_key": content_task_key,
                "reused_existing": False,
                "target_audience": _clean_optional(body.target_audience),
                "target_platforms": target_platforms,
                "source_doc_path": _clean_optional(body.source_doc_path),
                "campaign_key": _clean_optional(body.campaign_key),
                "post_intent": _clean_optional(body.post_intent),
                "planned_publish_at": planned_publish_at,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )


def _create_source_plan_document(
    db: Session,
    asset: SocialContentAssetRow,
    body: dist_schema.SocialContentTaskCreateRequest,
    target_platforms: list[str],
) -> None:
    plan = build_source_plan_payload(
        title=asset.title,
        source_material=asset.body,
        target_audience=body.target_audience,
        target_platforms=target_platforms,
        canonical_url=asset.canonical_url,
        source_doc_path=body.source_doc_path,
    )
    _upsert_document(
        db,
        asset=asset,
        task=None,
        document_kind="source_plan",
        platform=None,
        channel_key=None,
        title=f"Plan: {asset.title}",
        body_markdown=source_plan_markdown(plan),
        status="generated",
        metadata={
            "generated_by": "distribution_content_plan_v1",
            "structured_plan": plan,
        },
    )
