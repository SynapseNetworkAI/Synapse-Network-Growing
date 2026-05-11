"""Content-task documents for the Social Distribution board."""

from __future__ import annotations

import json
from collections import Counter

from sqlalchemy.orm import Session

from server import schemas_social_distribution as dist_schema
from server.database import utcnow
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionDocumentRow,
    SocialDistributionTaskRow,
)
from server.services.social.distribution_core import (
    _clean_optional,
    _normalize_platform,
    _record_event,
    _validate_document_kind,
    _validate_document_status,
)
from server.services.social.distribution_document_content import (
    build_source_plan_payload,
    clean_platform_list,
    list_from_metadata,
    parse_json_object,
    platform_document_markdown,
    source_plan_markdown,
    summary_from_text,
    validate_source_plan_payload,
)
from server.services.social.distribution_projection import _asset_out

BOARD_COLUMNS = (
    (
        "backlog",
        "Backlog",
        "Content tasks that still need a plan or channel selection.",
    ),
    (
        "plan_ready",
        "Plan Ready",
        "A source plan exists and platform drafts can be generated.",
    ),
    ("drafting", "Drafting", "Platform documents or tasks are being prepared."),
    (
        "human_review",
        "Human Review",
        "Drafts need operator review before public action.",
    ),
    (
        "ready_to_publish",
        "Ready to Publish",
        "Platform drafts are ready for human-gated publish or manual posting.",
    ),
    ("live", "Live", "Content has at least one live distribution record."),
    (
        "blocked",
        "Blocked",
        "Generation, policy, or publishing failure needs attention.",
    ),
)


def create_content_task(
    db: Session,
    body: dist_schema.SocialContentTaskCreateRequest,
) -> dist_schema.SocialContentAssetDetailOut:
    from server.services.social.distribution import get_content_asset

    if not body.title.strip():
        raise ValueError("content task title is required.")
    asset = SocialContentAssetRow(
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
                "target_audience": _clean_optional(body.target_audience),
                "target_platforms": clean_platform_list(body.target_platforms),
                "source_doc_path": _clean_optional(body.source_doc_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    db.add(asset)
    db.flush()
    plan = build_source_plan_payload(
        title=asset.title,
        source_material=asset.body,
        target_audience=body.target_audience,
        target_platforms=body.target_platforms,
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
    _record_event(
        db,
        asset,
        None,
        "content_task_created",
        asset.created_by,
        "Content task created with source plan document.",
        {"target_platforms": clean_platform_list(body.target_platforms)},
    )
    db.commit()
    db.refresh(asset)
    return get_content_asset(db, int(asset.id))


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


def create_platform_draft_document(
    db: Session,
    *,
    asset: SocialContentAssetRow,
    task: SocialDistributionTaskRow,
    metadata: dict[str, object] | None = None,
) -> SocialDistributionDocumentRow:
    title = task.platform_title or f"{task.platform} draft for {asset.title}"
    body = platform_document_markdown(asset, task)
    return _upsert_document(
        db,
        asset=asset,
        task=task,
        document_kind="platform_draft",
        platform=task.platform,
        channel_key=task.channel_key,
        title=title,
        body_markdown=body,
        status="needs_review" if task.status == "needs_review" else "generated",
        metadata={
            "generated_by": "distribution_task_generation_v1",
            "task_status": task.status,
            **(metadata or {}),
        },
    )


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


def social_distribution_board(
    db: Session,
) -> dist_schema.SocialDistributionBoardOut:
    rows = (
        db.query(SocialContentAssetRow)
        .order_by(
            SocialContentAssetRow.updated_at.desc(), SocialContentAssetRow.id.desc()
        )
        .limit(200)
        .all()
    )
    grouped: dict[str, list[dist_schema.SocialDistributionBoardCardOut]] = {
        key: [] for key, _, _ in BOARD_COLUMNS
    }
    for asset in rows:
        card = _board_card(asset)
        grouped.setdefault(card.column_key, []).append(card)
    columns = [
        dist_schema.SocialDistributionBoardColumnOut(
            key=key,
            title=title,
            description=description,
            count=len(grouped.get(key, [])),
            cards=grouped.get(key, []),
        )
        for key, title, description in BOARD_COLUMNS
    ]
    return dist_schema.SocialDistributionBoardOut(
        columns=columns,
        summary={
            "total_assets": len(rows),
            "total_tasks": sum(len(asset.tasks or []) for asset in rows),
            "total_documents": sum(len(asset.documents or []) for asset in rows),
        },
        generated_at=utcnow(),
    )


def _board_card(
    asset: SocialContentAssetRow,
) -> dist_schema.SocialDistributionBoardCardOut:
    tasks = list(asset.tasks or [])
    docs = list(asset.documents or [])
    status_counts = Counter(str(task.status or "planned") for task in tasks)
    doc_status_counts = Counter(str(doc.status or "generated") for doc in docs)
    column_key = _asset_column(asset, status_counts, doc_status_counts, docs)
    return dist_schema.SocialDistributionBoardCardOut(
        id=f"asset:{int(asset.id)}",
        asset=_asset_out(asset),
        column_key=column_key,
        task_count=len(tasks),
        document_count=len(docs),
        platform_count=len({(task.platform, task.channel_key) for task in tasks}),
        failed_count=status_counts.get("failed", 0)
        + doc_status_counts.get("failed", 0),
        ready_to_publish_count=status_counts.get("draft_ready", 0)
        + status_counts.get("approved", 0),
        live_count=status_counts.get("live", 0),
        status_counts=dict(status_counts),
        document_status_counts=dict(doc_status_counts),
        next_action=_next_action(column_key),
        updated_at=asset.updated_at,
    )


def _asset_column(
    asset: SocialContentAssetRow,
    status_counts: Counter[str],
    doc_status_counts: Counter[str],
    docs: list[SocialDistributionDocumentRow],
) -> str:
    column_checks = (
        ("blocked", _asset_is_blocked(asset, status_counts, doc_status_counts)),
        ("live", _asset_is_live(asset, status_counts)),
        ("ready_to_publish", _asset_is_ready_to_publish(status_counts)),
        ("human_review", bool(status_counts.get("needs_review", 0))),
        ("drafting", _asset_is_drafting(status_counts, docs)),
        ("plan_ready", _asset_has_plan(asset, docs)),
    )
    for column_key, matched in column_checks:
        if matched:
            return column_key
    return "backlog"


def _asset_is_blocked(
    asset: SocialContentAssetRow,
    status_counts: Counter[str],
    doc_status_counts: Counter[str],
) -> bool:
    return (
        bool(status_counts.get("failed", 0))
        or bool(doc_status_counts.get("failed", 0))
        or asset.status == "failed"
    )


def _asset_is_live(
    asset: SocialContentAssetRow,
    status_counts: Counter[str],
) -> bool:
    return bool(status_counts.get("live", 0)) or asset.status in {
        "distributed",
        "archived",
    }


def _asset_is_ready_to_publish(status_counts: Counter[str]) -> bool:
    return bool(status_counts.get("draft_ready", 0)) or bool(
        status_counts.get("approved", 0)
    )


def _asset_is_drafting(
    status_counts: Counter[str],
    docs: list[SocialDistributionDocumentRow],
) -> bool:
    return _has_document_kind(docs, "platform_draft") or _tasks_are_planned_only(
        status_counts
    )


def _asset_has_plan(
    asset: SocialContentAssetRow,
    docs: list[SocialDistributionDocumentRow],
) -> bool:
    return _has_document_kind(docs, "source_plan") or asset.status in {
        "active",
        "approved",
        "ready",
    }


def _has_document_kind(
    docs: list[SocialDistributionDocumentRow],
    document_kind: str,
) -> bool:
    return any(doc.document_kind == document_kind for doc in docs)


def _tasks_are_planned_only(status_counts: Counter[str]) -> bool:
    return bool(status_counts) and set(status_counts.keys()) <= {"planned", "submitted"}


def _next_action(column_key: str) -> str:
    return {
        "backlog": "Create or regenerate the content plan before channel drafting.",
        "plan_ready": "Select channels and generate platform documents.",
        "drafting": "Review generated platform documents and fix failed drafts.",
        "human_review": "Review X or sensitive drafts before public action.",
        "ready_to_publish": "Publish X through Human Gate or manually post non-X drafts.",
        "live": "Inspect links, events, and observed metrics.",
        "blocked": "Open the task detail and repair the failed generation or publish attempt.",
    }.get(column_key, "Inspect task history.")


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
