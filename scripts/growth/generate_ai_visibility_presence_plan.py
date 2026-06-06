#!/usr/bin/env python3
"""Export the AI visibility source-host presence plan as JSON."""

from __future__ import annotations

import argparse
import runpy
from pathlib import Path

_bootstrap = runpy.run_path(
    str(Path(__file__).with_name("ai_visibility_cli_bootstrap.py"))
)
_bootstrap["ensure_project_root"](__file__)

from scripts.growth.ai_visibility_cli import (  # noqa: E402
    pydantic_payload,
    write_json_payload,
)
from scripts.growth.ai_visibility_db_cli import run_with_db  # noqa: E402

DEFAULT_FEED_KEY = "mcp_paid_api_discovery"


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export source-host presence actions for AI visibility."
    )
    parser.add_argument("--feed-key", default=DEFAULT_FEED_KEY)
    parser.add_argument("--run-group", default="")
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")
    args = parser.parse_args()

    plan = run_with_db(
        lambda db: _build_presence_plan(
            db,
            feed_key=args.feed_key,
            run_group=args.run_group or None,
        )
    )
    write_json_payload(pydantic_payload(plan), args.output)
    return 0


def _build_presence_plan(db, *, feed_key: str, run_group: str | None):
    from server.services.growth.ai_visibility_presence_plan import (
        ai_visibility_presence_plan,
    )

    return ai_visibility_presence_plan(db, feed_key=feed_key, run_group=run_group)


if __name__ == "__main__":
    raise SystemExit(main())
