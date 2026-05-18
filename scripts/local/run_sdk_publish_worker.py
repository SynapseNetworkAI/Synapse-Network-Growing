#!/usr/bin/env python3
"""Run local SDK package publish checks and reconcile SDK package rows."""

from __future__ import annotations

import argparse
import subprocess  # nosec B404
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SDK_REPO = Path("/Users/cliff/workspace/agent/Synapse-Network-Sdk")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.database import SessionLocal  # noqa: E402
from server.services.releases.sdk_packages import sync_sdk_package_release_statuses  # noqa: E402


def run_once() -> int:
    if not SDK_REPO.exists():
        print(f"SDK repo path not found: {SDK_REPO}", file=sys.stderr)
        return 2
    result = subprocess.run(  # nosec B603
        ["/bin/bash", "scripts/ci/pr_checks.sh"],
        cwd=str(SDK_REPO),
        check=False,
    )
    if result.returncode != 0:
        return int(result.returncode)
    with SessionLocal() as db:
        sync_sdk_package_release_statuses(db, max_records=50)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once", action="store_true", help="Run one local SDK reconciliation."
    )
    parser.parse_args()
    return run_once()


if __name__ == "__main__":
    raise SystemExit(main())
