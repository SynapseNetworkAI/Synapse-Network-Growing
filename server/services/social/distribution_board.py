"""Board projection for social distribution content assets."""

from __future__ import annotations

import json
from collections import Counter

from sqlalchemy.orm import Session, object_session

from server import schemas_social_distribution as dist_schema
from server.database import SocialReplyItemRow, utcnow
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionDocumentRow,
    SocialDistributionTaskRow,
)
from server.services.social.distribution_board_contract import (
    BOARD_COLUMNS,
    board_next_action,
)
from server.services.social.distribution_documents import (
    ensure_platform_documents_for_asset,
)
from server.services.social.distribution_projection import _asset_out
from server.services.social.distribution_reply_metadata import reply_ids_from_asset
from server.services.social.distribution_task_kinds import task_kind_for_asset

PUBLISHABLE_DOCUMENT_KINDS = {"platform_draft", "x_article_pack"}


def social_distribution_board(
    db: Session,
) -> dist_schema.SocialDistributionBoardOut:
    rows = (
        db.query(SocialContentAssetRow)
        .filter(SocialContentAssetRow.status != "archived")
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
        ensure_platform_documents_for_asset(db, asset)
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
    task_kind = task_kind_for_asset(asset)
    reply_status_counts = (
        _reply_status_counts(asset) if task_kind.code == "x_reply_block" else Counter()
    )
    if task_kind.code == "x_reply_block":
        status_counts.update(reply_status_counts)
    column_key = _asset_column(
        asset, status_counts, doc_status_counts, docs, task_kind_code=task_kind.code
    )
    return dist_schema.SocialDistributionBoardCardOut(
        id=f"asset:{int(asset.id)}",
        asset=_asset_out(asset),
        column_key=column_key,
        task_kind_code=task_kind.code,
        task_kind_label=task_kind.label,
        task_kind_action=task_kind.action,
        task_count=len(tasks),
        document_count=len(docs),
        platform_count=_platform_count(asset, tasks, task_kind_code=task_kind.code),
        failed_count=status_counts.get("failed", 0)
        + status_counts.get("rejected", 0)
        + doc_status_counts.get("failed", 0),
        ready_to_publish_count=_card_ready_to_publish_count(
            status_counts, docs, task_kind_code=task_kind.code
        ),
        live_count=status_counts.get("live", 0)
        + status_counts.get("published", 0)
        + status_counts.get("published_manual", 0),
        visibility_issue_count=_visibility_issue_count(tasks),
        status_counts=dict(status_counts),
        document_status_counts=dict(doc_status_counts),
        next_action=board_next_action(column_key, task_kind_code=task_kind.code),
        updated_at=asset.updated_at,
    )


def _asset_column(
    asset: SocialContentAssetRow,
    status_counts: Counter[str],
    doc_status_counts: Counter[str],
    docs: list[SocialDistributionDocumentRow],
    *,
    task_kind_code: str = "content_distribution",
) -> str:
    if task_kind_code == "x_reply_block":
        return _reply_asset_column(asset, status_counts, docs)
    column_checks = (
        ("blocked", _asset_is_blocked(asset, status_counts, doc_status_counts)),
        ("live", _asset_is_live(asset, status_counts)),
        ("ready_to_publish", _asset_is_ready_to_publish(status_counts)),
        ("needs_review", _asset_needs_review(asset, docs)),
    )
    for column_key, matched in column_checks:
        if matched:
            return column_key
    return "backlog"


def _reply_asset_column(
    asset: SocialContentAssetRow,
    status_counts: Counter[str],
    docs: list[SocialDistributionDocumentRow],
) -> str:
    if _asset_is_blocked(asset, status_counts, Counter()):
        return "blocked"
    if status_counts.get("published", 0) or status_counts.get("published_manual", 0):
        return "live"
    if (
        status_counts.get("agent_approved_needs_manual_publish", 0)
        or status_counts.get("approved", 0)
        or status_counts.get("needs_review", 0)
    ):
        return "ready_to_publish"
    if _has_document_kind(docs, "source_plan") or asset.status in {
        "draft",
        "active",
        "approved",
        "ready",
    }:
        return "needs_review"
    return "backlog"


def _asset_is_blocked(
    asset: SocialContentAssetRow,
    status_counts: Counter[str],
    doc_status_counts: Counter[str],
) -> bool:
    return (
        bool(status_counts.get("failed", 0))
        or bool(status_counts.get("removed", 0))
        or bool(status_counts.get("skipped", 0))
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
    return _ready_task_count(status_counts) > 0


def _asset_needs_review(
    asset: SocialContentAssetRow,
    docs: list[SocialDistributionDocumentRow],
) -> bool:
    return _has_document_kind(docs, "source_plan") or asset.status in {
        "draft",
        "active",
        "approved",
        "ready",
    }


def _ready_to_publish_count(
    status_counts: Counter[str],
    docs: list[SocialDistributionDocumentRow],
) -> int:
    return _ready_task_count(status_counts) + _ready_document_count(docs)


def _ready_task_count(status_counts: Counter[str]) -> int:
    return (
        status_counts.get("draft_ready", 0)
        + status_counts.get("approved", 0)
        + status_counts.get("submitted", 0)
        + status_counts.get("needs_manual_article_publish", 0)
    )


def _ready_document_count(docs: list[SocialDistributionDocumentRow]) -> int:
    return sum(
        1
        for doc in docs
        if doc.task_id is None
        and str(doc.document_kind or "") in PUBLISHABLE_DOCUMENT_KINDS
        and str(doc.status or "") in {"approved", "published"}
    )


def _card_ready_to_publish_count(
    status_counts: Counter[str],
    docs: list[SocialDistributionDocumentRow],
    *,
    task_kind_code: str,
) -> int:
    if task_kind_code == "x_reply_block":
        return (
            status_counts.get("agent_approved_needs_manual_publish", 0)
            + status_counts.get("approved", 0)
            + status_counts.get("needs_review", 0)
        )
    return _ready_to_publish_count(status_counts, docs)


def _has_document_kind(
    docs: list[SocialDistributionDocumentRow],
    document_kind: str,
) -> bool:
    return any(doc.document_kind == document_kind for doc in docs)


def _platform_count(
    asset: SocialContentAssetRow,
    tasks: list[SocialDistributionTaskRow],
    *,
    task_kind_code: str,
) -> int:
    if task_kind_code == "x_reply_block":
        return 1 if reply_ids_from_asset(asset) else 0
    return len({(task.platform, task.channel_key) for task in tasks})


def _reply_status_counts(asset: SocialContentAssetRow) -> Counter[str]:
    reply_ids = reply_ids_from_asset(asset)
    session = object_session(asset)
    if not reply_ids or session is None:
        return Counter()
    rows = (
        session.query(SocialReplyItemRow.status)
        .filter(SocialReplyItemRow.id.in_(reply_ids))
        .all()
    )
    return Counter(str(row[0] or "needs_review") for row in rows)


def _visibility_issue_count(tasks: list[SocialDistributionTaskRow]) -> int:
    issue_statuses = {"removed_by_filter", "flagged", "not_found", "blocked"}
    count = 0
    for task in tasks:
        try:
            metadata = json.loads(getattr(task, "metadata_json", None) or "{}")
        except json.JSONDecodeError:
            metadata = {}
        if not isinstance(metadata, dict):
            continue
        if metadata.get("visibility_status") in issue_statuses:
            count += 1
        elif metadata.get("layout_status") == "needs_fix":
            count += 1
    return count
