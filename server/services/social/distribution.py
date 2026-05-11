"""Human-gated multi-channel content asset and distribution task management."""

from __future__ import annotations

import json
from sqlalchemy.orm import Session

from server import schemas_social_distribution as dist_schema
from server.database import utcnow
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionAccountRow,
    SocialDistributionTaskRow,
)
from server.services.social.distribution_core import (
    _clean_optional,
    _normalize_platform,
    _record_event,
    _validate_account_status,
    _validate_asset_status,
)
from server.services.social.distribution_content import DEFAULT_DISTRIBUTION_ACCOUNTS
from server.services.social.distribution_documents import ensure_platform_documents_for_asset
from server.services.social.distribution_projection import (
    account_out,
    _asset_detail_out,
    _asset_out,
    _task_out,
)


def ensure_default_distribution_accounts(
    db: Session,
) -> list[dist_schema.SocialDistributionAccountOut]:
    changed = False
    for seed in DEFAULT_DISTRIBUTION_ACCOUNTS:
        platform = _normalize_platform(seed.platform)
        existing = (
            db.query(SocialDistributionAccountRow)
            .filter(
                SocialDistributionAccountRow.platform == platform,
                SocialDistributionAccountRow.channel_key == seed.channel_key,
            )
            .one_or_none()
        )
        if existing:
            if existing.publish_mode in {"", None}:
                existing.publish_mode = seed.publish_mode
                changed = True
            if existing.api_capability in {"", None}:
                existing.api_capability = seed.api_capability
                changed = True
            continue
        db.add(
            SocialDistributionAccountRow(
                platform=platform,
                channel_key=seed.channel_key,
                display_name=seed.display_name,
                signup_url=seed.signup_url,
                account_type=seed.account_type,
                priority=seed.priority,
                status="planned",
                read_automation_mode="manual_only",
                human_publish_required=True,
                publish_mode=seed.publish_mode,
                api_capability=seed.api_capability,
                notes=seed.notes,
            )
        )
        changed = True
    if changed:
        db.commit()
    return list_distribution_accounts(db)


def list_distribution_accounts(
    db: Session,
) -> list[dist_schema.SocialDistributionAccountOut]:
    if db.query(SocialDistributionAccountRow).count() == 0:
        ensure_default_distribution_accounts(db)
    rows = (
        db.query(SocialDistributionAccountRow)
        .order_by(
            SocialDistributionAccountRow.priority.asc(),
            SocialDistributionAccountRow.platform.asc(),
            SocialDistributionAccountRow.id.asc(),
        )
        .all()
    )
    return [account_out(row) for row in rows]


def update_distribution_account(
    db: Session,
    account_id: int,
    body: dist_schema.SocialDistributionAccountPatchRequest,
) -> dist_schema.SocialDistributionAccountOut:
    row = db.get(SocialDistributionAccountRow, account_id)
    if row is None:
        raise ValueError("Distribution account not found.")
    if body.status is not None:
        _validate_account_status(body.status)
        row.status = body.status.strip()
    for field in (
        "profile_url",
        "email_hint",
        "two_factor_status",
        "publish_mode",
        "credential_ref",
        "api_capability",
        "notes",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(row, field, value.strip() if isinstance(value, str) else value)
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return account_out(row)


def create_content_asset(
    db: Session, body: dist_schema.SocialContentAssetCreateRequest
) -> dist_schema.SocialContentAssetDetailOut:
    if not body.title.strip():
        raise ValueError("asset title is required.")
    _validate_asset_status(body.status)
    row = SocialContentAssetRow(
        asset_type=body.asset_type.strip() or "article",
        source_type=body.source_type.strip() or "manual",
        title=body.title.strip(),
        body=_clean_optional(body.body),
        summary=_clean_optional(body.summary),
        canonical_url=_clean_optional(body.canonical_url),
        source_signal_id=body.source_signal_id,
        goal_key=_clean_optional(body.goal_key),
        status=body.status.strip(),
        created_by=body.created_by.strip() or "operator",
        agent_metadata_json=json.dumps(
            {"source_of_truth": "social_content_assets"}, sort_keys=True
        ),
    )
    db.add(row)
    db.flush()
    _record_event(
        db,
        row,
        None,
        "asset_created",
        row.created_by,
        "Content asset created.",
        {"status": row.status},
    )
    db.commit()
    db.refresh(row)
    return get_content_asset(db, int(row.id))


def list_content_assets(db: Session) -> list[dist_schema.SocialContentAssetOut]:
    rows = (
        db.query(SocialContentAssetRow)
        .order_by(
            SocialContentAssetRow.updated_at.desc(), SocialContentAssetRow.id.desc()
        )
        .limit(100)
        .all()
    )
    return [_asset_out(row) for row in rows]


def get_content_asset(
    db: Session, asset_id: int
) -> dist_schema.SocialContentAssetDetailOut:
    row = db.get(SocialContentAssetRow, asset_id)
    if row is None:
        raise ValueError("Content asset not found.")
    ensure_platform_documents_for_asset(db, row)
    return _asset_detail_out(row)


def update_content_asset(
    db: Session,
    asset_id: int,
    body: dist_schema.SocialContentAssetPatchRequest,
) -> dist_schema.SocialContentAssetDetailOut:
    row = db.get(SocialContentAssetRow, asset_id)
    if row is None:
        raise ValueError("Content asset not found.")
    if body.status is not None:
        _validate_asset_status(body.status)
        row.status = body.status.strip()
    for field in ("title", "body", "summary", "canonical_url", "goal_key"):
        value = getattr(body, field)
        if value is not None:
            setattr(row, field, value.strip() if isinstance(value, str) else value)
    row.updated_at = utcnow()
    _record_event(
        db, row, None, "asset_updated", "operator", "Content asset updated.", {}
    )
    db.commit()
    db.refresh(row)
    return get_content_asset(db, int(row.id))


def list_distribution_tasks(
    db: Session,
    *,
    platform: str | None = None,
    channel_key: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dist_schema.SocialDistributionTaskListOut:
    bounded_limit = max(1, min(int(limit or 100), 100))
    bounded_offset = max(0, int(offset or 0))
    if platform or channel_key or status:
        groups = _filtered_distribution_task_groups(
            db,
            platform=platform,
            channel_key=channel_key,
            status=status,
            limit=bounded_limit,
            offset=bounded_offset,
        )
    else:
        groups = _asset_distribution_task_groups(
            db, limit=bounded_limit, offset=bounded_offset
        )
    flat = [task for group in groups for task in group.tasks]
    return dist_schema.SocialDistributionTaskListOut(
        groups=groups,
        flat=sorted(
            flat, key=lambda task: (str(task.updated_at), task.id), reverse=True
        ),
        total_assets=len(groups),
        total_tasks=len(flat),
        limit=bounded_limit,
        offset=bounded_offset,
    )


def _filtered_distribution_task_groups(
    db: Session,
    *,
    platform: str | None,
    channel_key: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> list[dist_schema.SocialDistributionTaskGroupOut]:
    task_rows = _filtered_distribution_task_rows(
        db,
        platform=platform,
        channel_key=channel_key,
        status=status,
        limit=limit,
        offset=offset,
    )
    asset_ids = list(dict.fromkeys(int(task.asset_id) for task in task_rows))
    asset_map = _asset_map_for_ids(db, asset_ids)
    return [
        dist_schema.SocialDistributionTaskGroupOut(
            asset=_asset_out(asset_map[int(asset_id)]),
            tasks=[
                _task_out(task)
                for task in task_rows
                if int(task.asset_id) == int(asset_id)
            ],
        )
        for asset_id in asset_ids
        if int(asset_id) in asset_map
    ]


def _filtered_distribution_task_rows(
    db: Session,
    *,
    platform: str | None,
    channel_key: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> list[SocialDistributionTaskRow]:
    query = db.query(SocialDistributionTaskRow)
    if platform:
        query = query.filter(
            SocialDistributionTaskRow.platform == _normalize_platform(platform)
        )
    if channel_key:
        query = query.filter(SocialDistributionTaskRow.channel_key == channel_key)
    if status and status != "all":
        query = query.filter(SocialDistributionTaskRow.status == status)
    return (
        query.order_by(
            SocialDistributionTaskRow.updated_at.desc(),
            SocialDistributionTaskRow.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )


def _asset_map_for_ids(
    db: Session, asset_ids: list[int]
) -> dict[int, SocialContentAssetRow]:
    assets = (
        db.query(SocialContentAssetRow)
        .filter(SocialContentAssetRow.id.in_(asset_ids))
        .all()
        if asset_ids
        else []
    )
    return {int(asset.id): asset for asset in assets}


def _asset_distribution_task_groups(
    db: Session, *, limit: int, offset: int
) -> list[dist_schema.SocialDistributionTaskGroupOut]:
    assets = (
        db.query(SocialContentAssetRow)
        .order_by(
            SocialContentAssetRow.updated_at.desc(), SocialContentAssetRow.id.desc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        dist_schema.SocialDistributionTaskGroupOut(
            asset=_asset_out(asset),
            tasks=[_task_out(task) for task in asset.tasks],
        )
        for asset in assets
    ]
