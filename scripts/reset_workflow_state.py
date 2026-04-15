#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.config import DB_PATH
from server.database import SessionLocal, init_db
from server.services.workflows.agent_first import reset_workflow_state_data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset workflow requirements, approvals, executions, validations, releases, and runtime history for the canonical v2 state machine."
    )
    parser.add_argument("--yes", action="store_true", help="Apply the workflow reset immediately.")
    parser.add_argument("--skip-backup", action="store_true", help="Skip creating a SQLite file backup before reset.")
    args = parser.parse_args()

    if not args.yes:
        parser.error("Pass --yes to confirm workflow reset.")

    db_path = Path(DB_PATH)
    if db_path.exists() and not args.skip_backup:
        backup_path = db_path.with_name(f"{db_path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(db_path, backup_path)
        print(json.dumps({"backup": str(backup_path)}, ensure_ascii=False))

    init_db()
    with SessionLocal() as db:
        summary = reset_workflow_state_data(db)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
