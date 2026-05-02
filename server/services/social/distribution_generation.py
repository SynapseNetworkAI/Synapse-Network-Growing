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
from server.services.social.agent_content_pack import generate_platform_task_draft


def generate_distribution_tasks(
    db: Session,
    asset_id: int,
    body: dist_schema.SocialDistributionGenerateTasksRequest,
) -> dist_schema.SocialDistributionGenerateTasksOut:
    asset = db.get(SocialContentAssetRow, asset_id)
    if asset is None:
        raise ValueError("Content asset not found.")
    if not body.account_ids:
        raise ValueError("select at least one distribution channel.")
    accounts = _ordered_accounts(db, body.account_ids)
    if len(accounts) != len(set(body.account_ids)):
        raise ValueError("one or more distribution accounts were not found.")

    results: list[dist_schema.SocialDistributionPlatformGenerationOut] = []
    generated_ids: list[int] = []
    failed_ids: list[int] = []
    for index, account in enumerate(accounts):
        if index:
            jitter_seconds = 0.1 + (time.monotonic_ns() % 151) / 1000
            time.sleep(jitter_seconds)
        task = _find_or_create_task(db, asset, account, body.action)
        try:
            draft = generate_platform_task_draft(
                asset_title=asset.title,
                asset_summary=asset.summary,
                asset_body=asset.body,
                asset_metadata=_asset_metadata(asset),
                canonical_url=asset.canonical_url,
                platform=account.platform,
                channel_key=account.channel_key,
                display_name=account.display_name,
            )
            task.status = "needs_review" if account.platform == "x" else "draft_ready"
            task.platform_title = draft.title
            task.platform_body = draft.body
            task.operator_checklist = draft.checklist
            task.submission_url = account.signup_url
            task.failure_summary = None
            task.metadata_json = json.dumps(
                {
                    **draft.metadata,
                    "generation_order": index + 1,
                    "serial_generation": True,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            task.updated_at = utcnow()
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
        db.flush()
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
    db.flush()
    return generate_distribution_tasks(
        db,
        asset_id,
        dist_schema.SocialDistributionGenerateTasksRequest(
            account_ids=account_ids,
            action=body.action,
            actor=body.actor,
        ),
    )


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
    if not recommended:
        return {"x", "hacker_news", "reddit", "v2ex", "devto", "hashnode"}
    return recommended


def _asset_metadata(asset: SocialContentAssetRow) -> dict[str, object]:
    try:
        payload = json.loads(asset.agent_metadata_json or "{}")
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
