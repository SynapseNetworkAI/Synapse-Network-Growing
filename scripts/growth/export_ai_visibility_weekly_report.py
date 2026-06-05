#!/usr/bin/env python3
"""Export the AI visibility weekly optimization report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.ai_visibility_cli import (  # noqa: E402
    pydantic_payload,
    write_json_payload,
)
from server.database import SessionLocal, init_db  # noqa: E402
from server.services.growth.ai_visibility_discovery import (  # noqa: E402
    ai_visibility_weekly_report,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export the derived AI visibility weekly report as JSON."
    )
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        report = ai_visibility_weekly_report(db)
    finally:
        db.close()
    write_json_payload(pydantic_payload(report), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
