"""Deduplicate operator-created social content tasks."""

from __future__ import annotations

from dataclasses import dataclass
import json

from pydantic import BaseModel
from sqlalchemy.orm import Session

from server.database import utcnow
from server.database_social_distribution import SocialContentAssetRow
from server.services.social.distribution_content_task_keys import (
    CONTENT_TASK_TERMINAL_STATUSES,
    candidate_content_task_key,
)
from server.services.social.distribution_core import _record_event
from server.services.social.distribution_document_content import parse_json_object


PUBLISH_EVIDENCE_STATUSES = {"live", "article_live", "teaser_live"}


@dataclass(frozen=True)
class DuplicateArchiveOptions:
    dry_run: bool = True
    title: str | None = None
    task_type: str | None = None
    actor: str = "operator"


class DuplicateArchiveSkipped(BaseModel):
    asset_id: int
    reason: str


class DuplicateArchiveGroup(BaseModel):
    content_task_key: str
    keeper_id: int
    duplicate_ids: list[int]
    skipped: list[DuplicateArchiveSkipped]
    active_ids_before: list[int]


class DuplicateArchiveResult(BaseModel):
    dry_run: bool
    group_count: int
    archived_count: int
    groups: list[DuplicateArchiveGroup]


def archive_duplicate_content_tasks(
    db: Session,
    options: DuplicateArchiveOptions | None = None,
) -> DuplicateArchiveResult:
    opts = options or DuplicateArchiveOptions()
    groups = _duplicate_groups(
        _candidate_rows(db),
        title=opts.title,
        task_type=opts.task_type,
    )
    results: list[DuplicateArchiveGroup] = []
    archived_count = 0
    for content_task_key, rows in groups.items():
        if len(rows) < 2:
            continue
        keeper = _select_keeper(rows)
        duplicates: list[int] = []
        skipped: list[DuplicateArchiveSkipped] = []
        for row in rows:
            if int(row.id) == int(keeper.id):
                continue
            if _has_publish_evidence(row):
                skipped.append(
                    DuplicateArchiveSkipped(
                        asset_id=int(row.id),
                        reason="has_publish_evidence",
                    )
                )
                continue
            duplicates.append(int(row.id))
            if not opts.dry_run:
                _archive_duplicate(
                    db,
                    row,
                    duplicate_of_asset_id=int(keeper.id),
                    actor=opts.actor,
                )
        archived_count += len(duplicates)
        results.append(
            DuplicateArchiveGroup(
                content_task_key=content_task_key,
                keeper_id=int(keeper.id),
                duplicate_ids=duplicates,
                skipped=skipped,
                active_ids_before=[int(row.id) for row in rows],
            )
        )
    if not opts.dry_run:
        db.commit()
    return DuplicateArchiveResult(
        dry_run=opts.dry_run,
        group_count=len(results),
        archived_count=archived_count,
        groups=results,
    )


def _candidate_rows(db: Session) -> list[SocialContentAssetRow]:
    rows = (
        db.query(SocialContentAssetRow)
        .filter(SocialContentAssetRow.source_type.in_(("manual_task", "manual")))
        .order_by(
            SocialContentAssetRow.updated_at.desc(),
            SocialContentAssetRow.id.desc(),
        )
        .all()
    )
    return [row for row in rows if _is_supported_candidate(row)]


def _is_supported_candidate(row: SocialContentAssetRow) -> bool:
    if str(row.source_type or "") == "manual_task":
        return True
    metadata = parse_json_object(row.agent_metadata_json)
    if str(metadata.get("source_of_truth") or "") == "e2e_x_article_pack":
        return True
    return _has_complete_x_article_pack(row)


def _duplicate_groups(
    rows: list[SocialContentAssetRow],
    *,
    title: str | None,
    task_type: str | None,
) -> dict[str, list[SocialContentAssetRow]]:
    groups: dict[str, list[SocialContentAssetRow]] = {}
    title_filter = _normal_title(title)
    task_type_filter = str(task_type or "").strip().lower()
    for row in rows:
        if not _matches_duplicate_filter(row, title_filter):
            continue
        key = _content_task_key_for_row(row)
        if not _matches_task_type_filter(key, task_type_filter):
            continue
        groups.setdefault(key, []).append(row)
    return groups


def _matches_duplicate_filter(row: SocialContentAssetRow, title_filter: str) -> bool:
    status = str(row.status or "").strip().lower()
    if status in CONTENT_TASK_TERMINAL_STATUSES:
        return False
    return not title_filter or _normal_title(row.title) == title_filter


def _content_task_key_for_row(row: SocialContentAssetRow) -> str:
    metadata = parse_json_object(row.agent_metadata_json)
    key = str(metadata.get("content_task_key") or "").strip()
    return key or candidate_content_task_key(row, metadata)


def _matches_task_type_filter(key: str, task_type_filter: str) -> bool:
    return not task_type_filter or key.startswith(f"{task_type_filter}|")


def _select_keeper(rows: list[SocialContentAssetRow]) -> SocialContentAssetRow:
    return sorted(rows, key=_keeper_score, reverse=True)[0]


def _keeper_score(row: SocialContentAssetRow) -> tuple[int, int, str, int]:
    updated = row.updated_at or row.created_at
    return (
        1 if _has_publish_evidence(row) else 0,
        1 if _has_complete_x_article_pack(row) else 0,
        updated.isoformat() if updated else "",
        int(row.id),
    )


def _has_publish_evidence(row: SocialContentAssetRow) -> bool:
    for task in list(row.tasks or []):
        if str(task.status or "") in PUBLISH_EVIDENCE_STATUSES:
            return True
        if str(task.published_url or "").strip():
            return True
        if str(task.external_post_id or "").strip():
            return True
    return False


def _has_complete_x_article_pack(row: SocialContentAssetRow) -> bool:
    has_pack = any(
        str(document.document_kind or "") == "x_article_pack"
        for document in list(row.documents or [])
    )
    actions = {str(task.action or "") for task in list(row.tasks or [])}
    return has_pack and {"x_article_manual_publish", "x_article_teaser"}.issubset(
        actions
    )


def _archive_duplicate(
    db: Session,
    row: SocialContentAssetRow,
    *,
    duplicate_of_asset_id: int,
    actor: str,
) -> None:
    archived_at = utcnow().isoformat()
    metadata = parse_json_object(row.agent_metadata_json)
    metadata.update(
        {
            "archive_reason": "archived_duplicate",
            "duplicate_of_asset_id": duplicate_of_asset_id,
            "archived_by": actor.strip() or "operator",
            "archived_at": archived_at,
        }
    )
    row.status = "archived"
    row.agent_metadata_json = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
    )
    row.updated_at = utcnow()
    _record_event(
        db,
        row,
        None,
        "content_task_archived_duplicate",
        actor,
        "Archived duplicate content task.",
        {
            "duplicate_of_asset_id": duplicate_of_asset_id,
            "archive_reason": "archived_duplicate",
            "archived_at": archived_at,
        },
    )


def _normal_title(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())
