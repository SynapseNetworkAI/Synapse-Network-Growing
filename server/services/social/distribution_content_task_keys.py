"""Content task identity helpers for social distribution assets."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from server.database_social_distribution import SocialContentAssetRow
from server.services.social.distribution_document_content import parse_json_object
from server.services.social.distribution_task_type_backfill import infer_task_type_for_asset


CONTENT_TASK_TERMINAL_STATUSES = {"removed", "archived", "rejected"}


def content_task_key(
    *,
    task_type: str,
    title: str,
    campaign_key: str | None,
    goal_key: str | None,
) -> str:
    normalized_title = re.sub(r"\s+", " ", title.strip().lower())
    campaign = str(campaign_key or "").strip().lower()
    goal = str(goal_key or "").strip().lower()
    return "|".join([task_type.strip().lower(), normalized_title, campaign, goal])


def existing_content_task(
    db: Session,
    key: str,
) -> SocialContentAssetRow | None:
    candidates = (
        db.query(SocialContentAssetRow)
        .filter(SocialContentAssetRow.source_type.in_(("manual_task", "manual")))
        .order_by(
            SocialContentAssetRow.updated_at.desc(), SocialContentAssetRow.id.desc()
        )
        .limit(500)
        .all()
    )
    for candidate in candidates:
        if (
            str(candidate.status or "").strip().lower()
            in CONTENT_TASK_TERMINAL_STATUSES
        ):
            continue
        metadata = parse_json_object(candidate.agent_metadata_json)
        if str(
            candidate.source_type or ""
        ) != "manual_task" and not legacy_content_task_candidate(
            candidate,
            metadata,
        ):
            continue
        candidate_key = metadata.get("content_task_key") or candidate_content_task_key(
            candidate,
            metadata,
        )
        if candidate_key == key:
            return candidate
    return None


def legacy_content_task_candidate(
    candidate: SocialContentAssetRow,
    metadata: dict[str, object],
) -> bool:
    if str(metadata.get("source_of_truth") or "") == "e2e_x_article_pack":
        return True
    return any(
        str(task.action or "") == "x_article_manual_publish"
        for task in list(candidate.tasks or [])
    ) or any(
        str(document.document_kind or "") == "x_article_pack"
        for document in list(candidate.documents or [])
    )


def candidate_content_task_key(
    candidate: SocialContentAssetRow,
    metadata: dict[str, object],
) -> str:
    task_type = str(metadata.get("task_type") or "").strip().lower()
    if not task_type:
        task_type, _ = infer_task_type_for_asset(candidate)
    return content_task_key(
        task_type=task_type,
        title=candidate.title,
        campaign_key=str(metadata.get("campaign_key") or ""),
        goal_key=candidate.goal_key,
    )
