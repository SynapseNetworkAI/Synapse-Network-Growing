#!/usr/bin/env python3
"""Run local SDK package dry-run/publish work."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SDK_REPO = Path("/Users/cliff/workspace/agent/Synapse-Network-Sdk")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.database import SessionLocal  # noqa: E402
from server.services.releases.sdk_package_runner import process_sdk_package_release  # noqa: E402


def run_once(release_id: int | None = None) -> int:
    if not SDK_REPO.exists():
        print(f"SDK repo path not found: {SDK_REPO}", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        processed = process_sdk_package_release(db, release_id=release_id)
    print(f"[sdk-publish-worker] processed={processed}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once", action="store_true", help="Run one local SDK reconciliation."
    )
    parser.add_argument("--release-id", type=int, default=None)
    args = parser.parse_args()
    return run_once(release_id=args.release_id)


if __name__ == "__main__":
    raise SystemExit(main())
