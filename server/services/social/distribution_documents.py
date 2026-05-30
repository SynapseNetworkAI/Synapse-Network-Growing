"""Content-task documents for the Social Distribution board."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from server import config
from server import schemas_social_distribution as dist_schema
from server.database import utcnow
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionDocumentRow,
    SocialDistributionTaskRow,
)
from server.services.social.distribution_board_contract import document_status_for_task
from server.services.social.distribution_core import (
    _normalize_platform,
    _record_event,
    _validate_document_kind,
    _validate_document_status,
)
from server.services.social.distribution_document_content import (
    build_source_plan_payload,
    list_from_metadata,
    parse_json_object,
    platform_document_markdown,
    source_plan_markdown,
    validate_source_plan_payload,
)
from server.services.social.agent_content_pack import generate_canonical_article_expansion


CANONICAL_ARTICLE_SKILL_PATHS: tuple[tuple[str, str], ...] = (
    ("product-marketing-context", ".agents/product-marketing-context.md"),
    ("social-content", ".agents/skills/social-content/SKILL.md"),
    ("build-in-public", ".agents/skills/build-in-public/SKILL.md"),
    ("solo-founder-narrative", ".agents/skills/solo-founder-narrative/SKILL.md"),
)


def ensure_platform_documents_for_asset(
    db: Session,
    asset: SocialContentAssetRow,
    *,
    actor: str = "system",
) -> bool:
    existing_task_ids = {
        int(document.task_id)
        for document in list(asset.documents or [])
        if document.document_kind == "platform_draft" and document.task_id is not None
    }
    changed = False
    for task in list(asset.tasks or []):
        if int(task.id) in existing_task_ids:
            continue
        if not str(task.platform_title or "").strip() and not str(
            task.platform_body or ""
        ).strip():
            continue
        create_platform_draft_document(
            db,
            asset=asset,
            task=task,
            metadata={"backfilled": True},
        )
        _record_event(
            db,
            asset,
            task,
            "document_backfilled",
            actor,
            "Backfilled platform_draft document from existing distribution task.",
            {"platform": task.platform, "channel_key": task.channel_key},
        )
        changed = True
    if changed:
        asset.updated_at = utcnow()
        db.commit()
        db.refresh(asset)
    return changed


def generate_content_plan(
    db: Session,
    asset_id: int,
    body: dist_schema.SocialDistributionGenerateContentPlanRequest,
) -> dist_schema.SocialContentAssetDetailOut:
    from server.services.social.distribution import get_content_asset

    asset = db.get(SocialContentAssetRow, asset_id)
    if asset is None:
        raise ValueError("Content asset not found.")
    metadata = parse_json_object(asset.agent_metadata_json)
    plan = build_source_plan_payload(
        title=asset.title,
        source_material=asset.body or asset.summary,
        target_audience=str(metadata.get("target_audience") or ""),
        target_platforms=list_from_metadata(metadata.get("target_platforms")),
        canonical_url=asset.canonical_url,
        source_doc_path=str(metadata.get("source_doc_path") or ""),
    )
    validate_source_plan_payload(plan)
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
    if asset.status == "draft":
        asset.status = "active"
    asset.updated_at = utcnow()
    _record_event(
        db,
        asset,
        None,
        "content_plan_generated",
        body.actor,
        "Generated structured content implementation plan.",
        {"document_kind": "source_plan"},
    )
    db.commit()
    db.refresh(asset)
    return get_content_asset(db, int(asset.id))


def expand_canonical_article(
    db: Session,
    asset_id: int,
    body: dist_schema.SocialDistributionExpandCanonicalArticleRequest,
) -> dist_schema.SocialContentAssetDetailOut:
    from server.services.social.distribution import get_content_asset

    asset = db.get(SocialContentAssetRow, asset_id)
    if asset is None:
        raise ValueError("Content asset not found.")
    source_plan = _latest_document(asset, "source_plan")
    article = generate_canonical_article_expansion(
        asset_title=asset.title,
        asset_summary=asset.summary,
        source_material=asset.body,
        source_plan=source_plan.body_markdown if source_plan else None,
        canonical_url=asset.canonical_url,
        skill_context=_canonical_article_skill_context(),
    )
    document = _upsert_document(
        db,
        asset=asset,
        task=None,
        document_kind="canonical_article",
        platform=None,
        channel_key=None,
        title=article.title,
        body_markdown=article.body_markdown,
        status="needs_review",
        metadata={
            **article.metadata,
            "summary": article.summary,
            "key_facts": article.key_facts,
            "generation_reason": article.generation_reason,
            "source_document_id": int(source_plan.id) if source_plan else None,
        },
    )
    asset.status = "needs_review"
    asset.updated_at = utcnow()
    _record_event(
        db,
        asset,
        None,
        "canonical_article_generated",
        body.actor,
        "Expanded source outline into canonical_article for human review.",
        {
            "document_id": int(document.id),
            "generated_by": "asset_expansion_agent_v1",
        },
    )
    db.commit()
    db.refresh(asset)
    return get_content_asset(db, int(asset.id))


def approve_canonical_article(
    db: Session,
    asset_id: int,
    body: dist_schema.SocialDistributionApproveCanonicalArticleRequest,
) -> dist_schema.SocialContentAssetDetailOut:
    from server.services.social.distribution import get_content_asset

    asset = db.get(SocialContentAssetRow, asset_id)
    if asset is None:
        raise ValueError("Content asset not found.")
    document = (
        db.get(SocialDistributionDocumentRow, int(body.document_id))
        if body.document_id
        else _latest_document(asset, "canonical_article")
    )
    if document is None or int(document.asset_id) != int(asset.id):
        raise ValueError("canonical_article not found.")
    if document.document_kind != "canonical_article":
        raise ValueError("document is not a canonical_article.")
    document.status = "approved"
    document.updated_at = utcnow()
    asset.status = "approved"
    asset.updated_at = utcnow()
    _record_event(
        db,
        asset,
        None,
        "canonical_article_approved",
        body.actor,
        "Operator approved canonical_article for platform adaptation.",
        {"document_id": int(document.id), "document_version": int(document.version or 1)},
    )
    db.commit()
    db.refresh(asset)
    return get_content_asset(db, int(asset.id))


def create_platform_draft_document(
    db: Session,
    *,
    asset: SocialContentAssetRow,
    task: SocialDistributionTaskRow,
    metadata: dict[str, object] | None = None,
) -> SocialDistributionDocumentRow:
    title = task.platform_title or f"{task.platform} draft for {asset.title}"
    body = platform_document_markdown(asset, task)
    task_metadata = parse_json_object(task.metadata_json)
    return _upsert_document(
        db,
        asset=asset,
        task=task,
        document_kind="platform_draft",
        platform=task.platform,
        channel_key=task.channel_key,
        title=title,
        body_markdown=body,
        status=document_status_for_task(task.status),
        metadata={
            "generated_by": "distribution_task_generation_v1",
            "task_status": task.status,
            "source_document_id": task_metadata.get("source_document_id"),
            "source_document_version": task_metadata.get("source_document_version"),
            **task_metadata,
            **(metadata or {}),
        },
    )


def approved_canonical_article_document(
    db: Session,
    asset: SocialContentAssetRow,
) -> SocialDistributionDocumentRow | None:
    return (
        db.query(SocialDistributionDocumentRow)
        .filter(
            SocialDistributionDocumentRow.asset_id == int(asset.id),
            SocialDistributionDocumentRow.document_kind == "canonical_article",
            SocialDistributionDocumentRow.status == "approved",
        )
        .order_by(
            SocialDistributionDocumentRow.version.desc(),
            SocialDistributionDocumentRow.updated_at.desc(),
            SocialDistributionDocumentRow.id.desc(),
        )
        .first()
    )


def _latest_document(
    asset: SocialContentAssetRow,
    document_kind: str,
) -> SocialDistributionDocumentRow | None:
    return max(
        (
            document
            for document in list(asset.documents or [])
            if document.document_kind == document_kind
        ),
        key=lambda document: (
            int(document.version or 1),
            document.updated_at or document.created_at or utcnow(),
            int(document.id),
        ),
        default=None,
    )


def _canonical_article_skill_context() -> dict[str, str]:
    context: dict[str, str] = {}
    for name, relative_path in CANONICAL_ARTICLE_SKILL_PATHS:
        path = Path(config.PROJECT_ROOT) / relative_path
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            content = ""
        if content.strip():
            context[name] = content
    return context


def update_task_document_status(
    db: Session,
    *,
    task: SocialDistributionTaskRow,
    status: str,
    metadata: dict[str, object] | None = None,
) -> None:
    _validate_document_status(status)
    rows = (
        db.query(SocialDistributionDocumentRow)
        .filter(
            SocialDistributionDocumentRow.task_id == int(task.id),
            SocialDistributionDocumentRow.document_kind == "platform_draft",
        )
        .all()
    )
    for row in rows:
        current = parse_json_object(row.metadata_json)
        row.status = status
        row.metadata_json = json.dumps(
            {**current, **(metadata or {}), "task_status": task.status},
            ensure_ascii=False,
            sort_keys=True,
        )
        row.updated_at = utcnow()


def sync_task_document_from_task(
    db: Session,
    *,
    task: SocialDistributionTaskRow,
    metadata: dict[str, object] | None = None,
) -> None:
    if task.asset is not None:
        create_platform_draft_document(
            db,
            asset=task.asset,
            task=task,
            metadata=metadata,
        )
    update_task_document_status(
        db,
        task=task,
        status=document_status_for_task(task.status),
        metadata=metadata,
    )


def _source_plan_metadata(asset: SocialContentAssetRow) -> dict[str, object]:
    for document in asset.documents or []:
        if document.document_kind != "source_plan":
            continue
        metadata = parse_json_object(document.metadata_json)
        structured = metadata.get("structured_plan")
        return structured if isinstance(structured, dict) else {}
    return {}


def _upsert_document(
    db: Session,
    *,
    asset: SocialContentAssetRow,
    task: SocialDistributionTaskRow | None,
    document_kind: str,
    platform: str | None,
    channel_key: str | None,
    title: str,
    body_markdown: str,
    status: str,
    metadata: dict[str, object],
) -> SocialDistributionDocumentRow:
    _validate_document_kind(document_kind)
    _validate_document_status(status)
    normalized_platform = _normalize_platform(platform or "") if platform else None
    existing = (
        db.query(SocialDistributionDocumentRow)
        .filter(
            SocialDistributionDocumentRow.asset_id == int(asset.id),
            SocialDistributionDocumentRow.task_id == (int(task.id) if task else None),
            SocialDistributionDocumentRow.document_kind == document_kind,
            SocialDistributionDocumentRow.platform == normalized_platform,
            SocialDistributionDocumentRow.channel_key == channel_key,
        )
        .one_or_none()
    )
    if existing:
        existing.version = int(existing.version or 1) + 1
        existing.title = title.strip() or existing.title
        existing.body_markdown = body_markdown.strip()
        existing.status = status
        existing.metadata_json = json.dumps(
            metadata, ensure_ascii=False, sort_keys=True
        )
        existing.updated_at = utcnow()
        return existing
    row = SocialDistributionDocumentRow(
        asset_id=int(asset.id),
        task_id=int(task.id) if task else None,
        document_kind=document_kind,
        platform=normalized_platform,
        channel_key=channel_key,
        title=title.strip(),
        body_markdown=body_markdown.strip(),
        status=status,
        version=1,
        metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    )
    db.add(row)
    db.flush()
    return row
