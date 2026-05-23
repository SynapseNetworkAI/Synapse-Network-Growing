#!/usr/bin/env python
"""Dry-run or apply Secret Manager active-version cleanup."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from server.services.secret_manager_cleanup import cleanup_secret_manager_versions  # noqa: E402
from server.services.result_objects import dump_service_result  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Keep only the latest active Secret Manager versions."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print cleanup candidates without destroying versions.",
    )
    mode.add_argument(
        "--apply", action="store_true", help="Destroy old active versions."
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=3,
        help="Number of newest active versions to keep per secret.",
    )
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="GCP project id. Repeat for multiple projects.",
    )
    args = parser.parse_args()

    result = cleanup_secret_manager_versions(
        projects=args.project or None,
        keep=args.keep,
        dry_run=not args.apply,
    )
    payload = dump_service_result(result)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if int(payload.get("error_count") or 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
