#!/usr/bin/env python3
"""Dev-only reset for generated social distribution assets/tasks/events."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from server import config
from server.database import SessionLocal
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionEventRow,
    SocialDistributionTaskRow,
)

REQUIRED_CONFIRM = "RESET_SOCIAL_DISTRIBUTION_ASSET_HISTORY"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    if args.confirm != REQUIRED_CONFIRM:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "confirmation_required",
                    "required_confirm": REQUIRED_CONFIRM,
                },
                indent=2,
            )
        )
        return 2

    backup_path = _backup_db()
    db = SessionLocal()
    try:
        counts = {
            "events": db.query(SocialDistributionEventRow).count(),
            "tasks": db.query(SocialDistributionTaskRow).count(),
            "assets": db.query(SocialContentAssetRow).count(),
        }
        db.query(SocialDistributionEventRow).delete()
        db.query(SocialDistributionTaskRow).delete()
        db.query(SocialContentAssetRow).delete()
        db.commit()
    finally:
        db.close()
    print(
        json.dumps(
            {
                "ok": True,
                "backup_path": str(backup_path) if backup_path else None,
                "deleted": counts,
                "preserved": [
                    "social_distribution_accounts",
                    "social_accounts",
                    "oauth secrets",
                    "watchlist",
                    "trend items",
                    "post metrics",
                    "project policies",
                ],
            },
            indent=2,
        )
    )
    return 0


def _backup_db() -> Path | None:
    db_path = Path(config.DATABASE_URL.replace("sqlite:///", ""))
    if not db_path.exists():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = config.PROJECT_ROOT / "runtime" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"ops-social-distribution-reset-{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    return backup_path


if __name__ == "__main__":
    raise SystemExit(main())
