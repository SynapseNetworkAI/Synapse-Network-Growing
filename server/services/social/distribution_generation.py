"""Platform task generation for social distribution assets."""

from __future__ import annotations

import json
import time

from sqlalchemy.orm import Session

from server import schemas_social_distribution as dist_schema
from server.database import utcnow
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionAccountRow,
    SocialDistributionTaskRow,
)
from server.services.social.distribution import get_content_asset
from server.services.social.distribution_core import (
    PLATFORM_ORDER,
    _normalize_platform,
    _record_event,
)
from server.services.social.distribution_documents import (
    approved_canonical_article_document,
    create_platform_draft_document,
)
from server.services.social.distribution_publish_lint import (
    BLOCKED,
    PublishLintResult,
    lint_distribution_task,
    lint_summary,
)
from server.services.social.distribution_task_types import (
    MULTI_PLATFORM_CAMPAIGN,
    X_ARTICLE_PACK,
    X_MEDIA_POST,
)
from server.services.social.agent_content_pack import generate_platform_task_draft


def generate_distribution_tasks(
    db: Session,
    asset_id: int,
    body: dist_schema.SocialDistributionGenerateTasksRequest,
) -> dist_schema.SocialDistributionGenerateTasksOut:
    asset = db.get(SocialContentAssetRow, asset_id)
    if asset is None:
        raise ValueError("Content asset not found.")
    asset_metadata = _asset_metadata(asset)
    task_type = str(asset_metadata.get("task_type") or "").strip()
    if task_type == X_ARTICLE_PACK:
        raise ValueError(
            "x_article_pack uses generate_x_article_pack; X Article publishing is manual."
        )
    if not body.account_ids:
        raise ValueError("select at least one distribution channel.")
    accounts = _ordered_accounts(db, body.account_ids)
    if len(accounts) != len(set(body.account_ids)):
        raise ValueError("one or more distribution accounts were not found.")
    if task_type == X_MEDIA_POST and any(account.platform != "x" for account in accounts):
        raise ValueError("x_media_post is X-only; choose multi_platform_campaign for other channels.")
    if task_type == MULTI_PLATFORM_CAMPAIGN and len(accounts) < 2:
        raise ValueError("multi_platform_campaign requires at least two selected channels.")
    canonical_article = approved_canonical_article_document(db, asset)
    if canonical_article is None:
        raise ValueError(
            "canonical_article_required: expand and approve canonical article "
            "before generating platform tasks."
        )
    canonical_metadata = _document_metadata(canonical_article)
    canonical_body = canonical_article.body_markdown

    results: list[dist_schema.SocialDistributionPlatformGenerationOut] = []
    generated_ids: list[int] = []
    failed_ids: list[int] = []
    for index, account in enumerate(accounts):
        if index:
            jitter_seconds = 0.1 + (time.monotonic_ns() % 151) / 1000
            time.sleep(jitter_seconds)
        try:
            task = _generate_and_apply_task(
                db=db,
                asset=asset,
                account=account,
                action=body.action,
                generation_order=index + 1,
                canonical_article=canonical_article,
                canonical_metadata=canonical_metadata,
                canonical_body=canonical_body,
            )
            generated_ids.append(int(task.id))
            results.append(_generation_result(account, "generated", int(task.id), None))
            _record_event(
                db,
                asset,
                task,
                "task_generated",
                body.actor,
                f"Generated {account.display_name} distribution task.",
                {"platform": account.platform, "channel_key": account.channel_key},
            )
        except Exception as exc:  # pragma: no cover - exercised by monkeypatch tests.
            task = _find_or_create_task(db, asset, account, body.action)
            task.status = "failed"
            task.failure_summary = f"task_generation_failed: {str(exc)[:240]}"
            task.updated_at = utcnow()
            failed_ids.append(int(task.id))
            results.append(
                _generation_result(
                    account, "failed", int(task.id), task.failure_summary
                )
            )
            _record_event(
                db,
                asset,
                task,
                "task_failed",
                body.actor,
                task.failure_summary,
                {"platform": account.platform},
            )
        db.commit()
        db.refresh(asset)
    asset.status = "ready"
    asset.updated_at = utcnow()
    db.commit()
    return dist_schema.SocialDistributionGenerateTasksOut(
        asset=get_content_asset(db, int(asset.id)),
        results=results,
        generated_task_ids=generated_ids,
        failed_task_ids=failed_ids,
    )


def approve_and_generate_distribution_tasks(
    db: Session,
    asset_id: int,
    body: dist_schema.SocialDistributionApproveGenerateRequest,
) -> dist_schema.SocialDistributionGenerateTasksOut:
    asset = db.get(SocialContentAssetRow, asset_id)
    if asset is None:
        raise ValueError("Content asset not found.")
    account_ids = body.account_ids or _default_account_ids_for_asset(db, asset)
    if not account_ids:
        raise ValueError("no distribution channels are configured for this asset.")
    asset.status = "approved"
    asset.updated_at = utcnow()
    _record_event(
        db,
        asset,
        None,
        "asset_approved",
        body.actor,
        "Operator approved asset and requested serial task generation.",
        {"account_ids": account_ids},
    )
    db.commit()
    return generate_distribution_tasks(
        db,
        asset_id,
        dist_schema.SocialDistributionGenerateTasksRequest(
            account_ids=account_ids,
            action=body.action,
            actor=body.actor,
        ),
    )


def _generate_and_apply_task(
    *,
    db: Session,
    asset: SocialContentAssetRow,
    account: SocialDistributionAccountRow,
    action: str,
    generation_order: int,
    canonical_article,
    canonical_metadata: dict[str, object],
    canonical_body: str,
) -> SocialDistributionTaskRow:
    draft = generate_platform_task_draft(
        asset_title=canonical_article.title or asset.title,
        asset_summary=str(canonical_metadata.get("summary") or asset.summary or ""),
        asset_body=canonical_body,
        asset_metadata=_platform_asset_metadata(asset, canonical_article, canonical_metadata),
        canonical_url=asset.canonical_url,
        platform=account.platform,
        channel_key=account.channel_key,
        display_name=account.display_name,
    )
    task = _find_or_create_task(db, asset, account, action)
    metadata = _generated_task_metadata(draft.metadata, canonical_article, generation_order)
    publish_lint = lint_distribution_task(
        platform=account.platform,
        channel_key=account.channel_key,
        title=draft.title,
        body=draft.body,
        metadata=metadata,
    )
    task.status = "needs_review" if account.platform == "x" or publish_lint.status == BLOCKED else "draft_ready"
    task.platform_title = draft.title
    task.platform_body = draft.body
    task.operator_checklist = _checklist_with_lint(draft.checklist, publish_lint)
    task.submission_url = account.signup_url
    task.failure_summary = None
    task.metadata_json = json.dumps(
        {**metadata, "platform_publish_lint": publish_lint.model_dump()},
        ensure_ascii=False,
        sort_keys=True,
    )
    create_platform_draft_document(
        db,
        asset=asset,
        task=task,
        metadata={"generation_order": generation_order},
    )
    task.updated_at = utcnow()
    return task


def _platform_asset_metadata(
    asset: SocialContentAssetRow,
    canonical_article,
    canonical_metadata: dict[str, object],
) -> dict[str, object]:
    return {
        **_asset_metadata(asset),
        "canonical_article_id": int(canonical_article.id),
        "canonical_article_version": int(canonical_article.version or 1),
        "canonical_article_status": canonical_article.status,
        "canonical_article_generated_by": canonical_metadata.get("generated_by"),
        "key_facts": canonical_metadata.get("key_facts", []),
        "density_driven_adaptation": True,
    }


def _generated_task_metadata(
    draft_metadata: dict[str, object],
    canonical_article,
    generation_order: int,
) -> dict[str, object]:
    return {
        **draft_metadata,
        "source_document_id": int(canonical_article.id),
        "source_document_version": int(canonical_article.version or 1),
        "generation_order": generation_order,
        "serial_generation": True,
    }


def _ordered_accounts(
    db: Session, account_ids: list[int]
) -> list[SocialDistributionAccountRow]:
    wanted = {int(value) for value in account_ids}
    rows = (
        db.query(SocialDistributionAccountRow)
        .filter(SocialDistributionAccountRow.id.in_(wanted))
        .all()
    )
    return sorted(
        rows,
        key=lambda row: (_platform_rank(row.platform), row.channel_key, int(row.id)),
    )


def _default_account_ids_for_asset(
    db: Session, asset: SocialContentAssetRow
) -> list[int]:
    recommended = _recommended_channels_for_asset(asset)
    rows = _eligible_distribution_accounts(db)
    eligible = [
        row
        for row in rows
        if row.platform in recommended or row.channel_key in recommended
    ]
    return [int(row.id) for row in _ordered_account_rows(eligible)]


def _recommended_channels_for_asset(asset: SocialContentAssetRow) -> set[str]:
    try:
        metadata = json.loads(asset.agent_metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    requested = (
        metadata.get("recommended_channels") if isinstance(metadata, dict) else []
    )
    recommended = (
        {str(item) for item in requested} if isinstance(requested, list) else set()
    )
    if not recommended and isinstance(metadata.get("target_platforms"), list):
        recommended = {str(item) for item in metadata["target_platforms"]}
    if not recommended:
        return {"x", "hacker_news", "reddit", "v2ex", "devto", "hashnode"}
    return recommended


def _asset_metadata(asset: SocialContentAssetRow) -> dict[str, object]:
    try:
        payload = json.loads(asset.agent_metadata_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _document_metadata(document) -> dict[str, object]:
    try:
        payload = json.loads(document.metadata_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _eligible_distribution_accounts(db: Session) -> list[SocialDistributionAccountRow]:
    return (
        db.query(SocialDistributionAccountRow)
        .filter(
            SocialDistributionAccountRow.status.in_(("active", "registered", "planned"))
        )
        .all()
    )


def _platform_rank(platform: str) -> int:
    normalized = _normalize_platform(platform)
    return (
        PLATFORM_ORDER.index(normalized)
        if normalized in PLATFORM_ORDER
        else len(PLATFORM_ORDER)
    )


def _ordered_account_rows(
    rows: list[SocialDistributionAccountRow],
) -> list[SocialDistributionAccountRow]:
    return sorted(
        rows,
        key=lambda row: (_platform_rank(row.platform), row.channel_key, int(row.id)),
    )


def _find_or_create_task(
    db: Session,
    asset: SocialContentAssetRow,
    account: SocialDistributionAccountRow,
    action: str,
) -> SocialDistributionTaskRow:
    existing = (
        db.query(SocialDistributionTaskRow)
        .filter(
            SocialDistributionTaskRow.asset_id == int(asset.id),
            SocialDistributionTaskRow.account_id == int(account.id),
            SocialDistributionTaskRow.action == action,
        )
        .one_or_none()
    )
    if existing:
        return existing
    task = SocialDistributionTaskRow(
        asset_id=int(asset.id),
        account_id=int(account.id),
        platform=_normalize_platform(account.platform),
        channel_key=account.channel_key,
        action=action.strip() or "post",
        submission_url=account.signup_url,
    )
    db.add(task)
    db.flush()
    return task


def _generation_result(
    account: SocialDistributionAccountRow,
    status: str,
    task_id: int | None,
    error: str | None,
) -> dist_schema.SocialDistributionPlatformGenerationOut:
    return dist_schema.SocialDistributionPlatformGenerationOut(
        account_id=int(account.id),
        platform=account.platform,
        channel_key=account.channel_key,
        status=status,
        task_id=task_id,
        error=error,
    )


def _checklist_with_lint(checklist: str | None, lint: PublishLintResult) -> str:
    base = str(checklist or "").strip()
    if lint.status == "passed":
        return base
    lint_text = f"Platform publish lint: {lint.status} - {lint_summary(lint)}"
    return f"{base}\n{lint_text}".strip() if base else lint_text
