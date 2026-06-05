#!/usr/bin/env python3
"""Export the AI visibility optimization brief as Markdown."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.database import SessionLocal, init_db  # noqa: E402
from server.services.growth.ai_visibility_brief import (  # noqa: E402
    ai_visibility_optimization_brief,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export a Markdown operator brief for the AI visibility loop."
    )
    parser.add_argument("--run-group", default="")
    parser.add_argument(
        "--output", help="Write Markdown to this path instead of stdout."
    )
    args = parser.parse_args()

    os.environ.setdefault("APP_ENV", "test")
    init_db()
    db = SessionLocal()
    try:
        brief = ai_visibility_optimization_brief(
            db,
            run_group=args.run_group or None,
        )
    finally:
        db.close()

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(brief.markdown, encoding="utf-8")
    else:
        print(brief.markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
