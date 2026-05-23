#!/usr/bin/env python3
"""One-shot migration from legacy X social tables to distribution v2 tables.

This script is intentionally not run by application startup. It migrates legacy
rows into `social_content_assets` / `social_distribution_tasks` and then drops
the old X main-flow tables when explicitly confirmed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.database import SessionLocal, engine
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionAccountRow,
    SocialDistributionEventRow,
    SocialDistributionTaskRow,
)

CONFIRMATION = "MIGRATE_SOCIAL_DISTRIBUTION_V2_DROP_LEGACY"
LEGACY_TABLES = (
    "social_post_media_assets",
    "social_publish_events",
    "social_reply_items",
    "social_repost_candidates",
    "social_post_drafts",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--drop-legacy", action="store_true")
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"Refusing to run. Pass --confirm {CONFIRMATION}")

    migrated = _migrate_rows()
    if args.drop_legacy:
        _drop_legacy_tables()
    print(
        json.dumps(
            {"migrated": migrated, "dropped": args.drop_legacy},
            indent=2,
        )
    )
    return 0


def _migrate_rows() -> dict[str, int]:
    db = SessionLocal()
    try:
        x_account = _ensure_x_distribution_account(db)
        counts = {
            "drafts": _migrate_post_drafts(db, int(x_account.id)),
            "replies": _migrate_replies(db, int(x_account.id)),
            "reposts": _migrate_reposts(db, int(x_account.id)),
        }
        db.commit()
        return counts
    finally:
        db.close()


def _ensure_x_distribution_account(db) -> SocialDistributionAccountRow:
    row = (
        db.query(SocialDistributionAccountRow)
        .filter(
            SocialDistributionAccountRow.platform == "x",
            SocialDistributionAccountRow.channel_key == "official",
        )
        .one_or_none()
    )
    if row:
        return row
    row = SocialDistributionAccountRow(
        platform="x",
        channel_key="official",
        display_name="X Official Account",
        signup_url="https://x.com/",
        account_type="official",
        priority="P0",
        status="active",
        read_automation_mode="api_read_limited",
        human_publish_required=True,
        notes="Migrated X official account distribution channel.",
    )
    db.add(row)
    db.flush()
    return row


def _migrate_post_drafts(db, account_id: int) -> int:
    rows = (
        db.execute(text("SELECT * FROM social_post_drafts")).mappings().all()
        if _table_exists("social_post_drafts")
        else []
    )
    count = 0
    for row in rows:
        asset = _asset_for_legacy(
            db,
            f"legacy:x-post:{row['id']}",
            row["title"] or f"Legacy X post #{row['id']}",
            row["body_text"],
            row["status"],
        )
        _task_for_legacy(
            db,
            asset,
            account_id,
            f"legacy:x-post-task:{row['id']}",
            "post",
            row["status"],
            row["title"],
            row["body_text"],
            row.get("external_url"),
            row.get("external_post_id"),
            row.get("failure_summary"),
        )
        count += 1
    return count


def _migrate_replies(db, account_id: int) -> int:
    rows = (
        db.execute(text("SELECT * FROM social_reply_items")).mappings().all()
        if _table_exists("social_reply_items")
        else []
    )
    count = 0
    for row in rows:
        asset = _asset_for_legacy(
            db,
            f"legacy:x-reply:{row['id']}",
            f"Reply to @{row['source_author_handle'] or 'unknown'}",
            row["suggested_reply"],
            row["status"],
        )
        _task_for_legacy(
            db,
            asset,
            account_id,
            f"legacy:x-reply-task:{row['id']}",
            "reply",
            row["status"],
            asset.title,
            row["suggested_reply"],
            row.get("source_url"),
            row.get("published_external_post_id"),
            row.get("failure_summary"),
        )
        count += 1
    return count


def _migrate_reposts(db, account_id: int) -> int:
    rows = (
        db.execute(text("SELECT * FROM social_repost_candidates")).mappings().all()
        if _table_exists("social_repost_candidates")
        else []
    )
    count = 0
    for row in rows:
        asset = _asset_for_legacy(
            db,
            f"legacy:x-repost:{row['id']}",
            f"Quote/repost candidate from @{row['author_handle'] or 'unknown'}",
            row["source_text"],
            row["status"],
        )
        _task_for_legacy(
            db,
            asset,
            account_id,
            f"legacy:x-repost-task:{row['id']}",
            "quote",
            row["status"],
            asset.title,
            row["suggested_quote"],
            row.get("source_url"),
            row.get("published_external_post_id"),
            row.get("failure_summary"),
        )
        count += 1
    return count


def _asset_for_legacy(
    db, legacy_key: str, title: str, body: str | None, status: str
) -> SocialContentAssetRow:
    existing = (
        db.query(SocialContentAssetRow)
        .filter(SocialContentAssetRow.agent_metadata_json.like(f'%"{legacy_key}"%'))
        .one_or_none()
    )
    if existing:
        return existing
    asset = SocialContentAssetRow(
        asset_type="x_legacy",
        source_type="legacy_migration",
        title=title,
        body=body,
        summary=(body or "")[:500],
        status="ready"
        if status in {"published", "approved", "needs_review"}
        else "failed"
        if status == "failed"
        else "draft",
        created_by="migration",
        agent_metadata_json=json.dumps(
            {"legacy_key": legacy_key, "migrated_by": "social_distribution_v2"},
            sort_keys=True,
        ),
    )
    db.add(asset)
    db.flush()
    db.add(
        SocialDistributionEventRow(
            asset_id=int(asset.id),
            event_type="asset_migrated",
            actor="migration",
            summary=f"Migrated {legacy_key}.",
        )
    )
    return asset


def _task_for_legacy(
    db,
    asset,
    account_id: int,
    legacy_key: str,
    action: str,
    status: str,
    title: str | None,
    body: str | None,
    published_url: str | None,
    external_post_id: str | None,
    failure_summary: str | None,
) -> None:
    existing = (
        db.query(SocialDistributionTaskRow)
        .filter(SocialDistributionTaskRow.metadata_json.like(f'%"{legacy_key}"%'))
        .one_or_none()
    )
    if existing:
        return
    task = SocialDistributionTaskRow(
        asset_id=int(asset.id),
        account_id=account_id,
        platform="x",
        channel_key="official",
        action=action,
        status=_legacy_status(status),
        platform_title=title,
        platform_body=body,
        published_url=published_url,
        external_post_id=external_post_id,
        failure_summary=failure_summary,
        metadata_json=json.dumps(
            {"legacy_key": legacy_key, "migrated_by": "social_distribution_v2"},
            sort_keys=True,
        ),
    )
    db.add(task)
    db.flush()
    db.add(
        SocialDistributionEventRow(
            asset_id=int(asset.id),
            task_id=int(task.id),
            event_type="task_migrated",
            actor="migration",
            summary=f"Migrated {legacy_key}.",
        )
    )


def _legacy_status(status: str) -> str:
    return {
        "published": "live",
        "approved": "approved",
        "needs_review": "needs_review",
        "failed": "failed",
        "rejected": "rejected",
    }.get(status, "draft_ready")


def _drop_legacy_tables() -> None:
    with engine.begin() as conn:
        for table in LEGACY_TABLES:
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))


def _table_exists(table: str) -> bool:
    return table in inspect(engine).get_table_names()


if __name__ == "__main__":
    raise SystemExit(main())
