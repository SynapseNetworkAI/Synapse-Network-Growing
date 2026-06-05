#!/usr/bin/env python3
"""Export the fail-closed AI visibility goal completion audit."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("APP_ENV", "test")

from server.database import SessionLocal, init_db  # noqa: E402
from server.services.growth.ai_visibility_goal_audit import (  # noqa: E402
    ai_visibility_goal_audit,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export AI visibility objective completion audit evidence."
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional JSON output path. Prints JSON to stdout when omitted.",
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        payload = ai_visibility_goal_audit(db).model_dump(mode="json")
    finally:
        db.close()

    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(body, encoding="utf-8")
    print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
