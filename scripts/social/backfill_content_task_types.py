#!/usr/bin/env python3
"""Backfill explicit task_type metadata for active social content assets."""

from __future__ import annotations

import argparse
import json

from server.database import SessionLocal, init_db
from server.services.social.distribution_task_type_backfill import (
    TaskTypeBackfillOptions,
    backfill_content_asset_task_types,
)


def main() -> int:
    args = _parse_args()
    if args.apply and args.confirm != "BACKFILL_CONTENT_TASK_TYPES":
        raise SystemExit("--apply requires --confirm BACKFILL_CONTENT_TASK_TYPES")
    init_db()
    db = SessionLocal()
    try:
        result = backfill_content_asset_task_types(
            db,
            TaskTypeBackfillOptions(
                dry_run=not args.apply,
                actor=args.actor,
                include_archived=args.include_archived,
            ),
        )
    finally:
        db.close()
    print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print inferred task types without changing DB.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write inferred task_type metadata and audit events.",
    )
    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Also inspect archived/removed/rejected assets.",
    )
    parser.add_argument(
        "--actor",
        default="operator",
        help="Actor recorded in backfill events.",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help="Required confirmation phrase for --apply.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
