#!/usr/bin/env python3
"""Archive duplicate social content tasks without deleting evidence rows."""

from __future__ import annotations

import argparse
import json

from server.database import SessionLocal, init_db
from server.services.social.distribution_dedupe import (
    DuplicateArchiveOptions,
    archive_duplicate_content_tasks,
)


def main() -> int:
    args = _parse_args()
    if args.apply and args.confirm != "ARCHIVE_DUPLICATE_CONTENT_TASKS":
        raise SystemExit("--apply requires --confirm ARCHIVE_DUPLICATE_CONTENT_TASKS")
    init_db()
    db = SessionLocal()
    try:
        result = archive_duplicate_content_tasks(
            db,
            DuplicateArchiveOptions(
                dry_run=not args.apply,
                title=args.title,
                task_type=args.task_type,
                actor=args.actor,
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
        help="Print duplicate groups and archive candidates without changing DB.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Archive duplicate candidates and write audit events.",
    )
    parser.add_argument(
        "--title",
        default="",
        help="Optional exact normalized title filter.",
    )
    parser.add_argument(
        "--task-type",
        default="",
        help="Optional task type filter, for example x_article_pack.",
    )
    parser.add_argument(
        "--actor",
        default="operator",
        help="Actor recorded in duplicate archive events.",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help="Required confirmation phrase for --apply.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
