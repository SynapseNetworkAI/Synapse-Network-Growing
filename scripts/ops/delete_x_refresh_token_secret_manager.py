#!/usr/bin/env python
"""Delete migrated X refresh-token Secret Manager resources."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from server.database import init_db  # noqa: E402
from server.services.social.publishing import SocialPublishError  # noqa: E402
from server.services.x_refresh_secret_cleanup import (  # noqa: E402
    DELETE_CONFIRMATION,
    delete_x_refresh_token_secret_manager,
    dump_delete_result,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete the X refresh-token Secret Manager resource after local DB OAuth verification."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run", action="store_true", help="Verify and show what would be deleted."
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Delete the selected Secret Manager resources.",
    )
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="GCP project id. Defaults to staging and production.",
    )
    parser.add_argument(
        "--confirmation",
        default="",
        help=f"Required for --apply: {DELETE_CONFIRMATION}",
    )
    args = parser.parse_args()

    init_db()
    try:
        payload = delete_x_refresh_token_secret_manager(
            projects=args.project or None,
            confirmation=args.confirmation,
            dry_run=not args.apply,
        )
    except SocialPublishError as exc:
        payload = {
            "status": "blocked",
            "reason": "local_x_refresh_verification_failed",
            "failure_kind": exc.kind,
            "failure_summary": exc.summary,
            "deleted_count": 0,
            "error_count": 1,
        }
    print(dump_delete_result(payload))
    return 0 if int(payload.get("error_count") or 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
