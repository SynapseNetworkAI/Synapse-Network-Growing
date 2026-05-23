#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.database import SessionLocal, init_db
from server.services.workflows.reset import reset_company_ops_state_data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset workflow requirements, approvals, executions, validations, releases, and runtime history for the canonical v2 state machine."
    )
    parser.add_argument("--yes", action="store_true", help="Apply the workflow reset immediately.")
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Deprecated no-op retained for old operator commands; PostgreSQL is the only runtime database.",
    )
    args = parser.parse_args()

    if not args.yes:
        parser.error("Pass --yes to confirm workflow reset.")

    init_db()
    with SessionLocal() as db:
        summary = reset_company_ops_state_data(db)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
