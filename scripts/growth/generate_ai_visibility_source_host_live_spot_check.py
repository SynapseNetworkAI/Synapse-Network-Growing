#!/usr/bin/env python3
"""Export source-host live listing spot-check evidence."""

from __future__ import annotations

import argparse
import runpy
from pathlib import Path

ensure_project_root = runpy.run_path(
    str(Path(__file__).with_name("ai_visibility_cli_bootstrap.py"))
)["ensure_project_root"]
ensure_project_root(__file__)

from scripts.growth.ai_visibility_cli import (  # noqa: E402
    pydantic_payload,
    write_json_payload,
)
from scripts.growth.ai_visibility_db_cli import run_with_db  # noqa: E402

DEFAULT_FEED_KEY = "mcp_paid_api_discovery"


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export source-host live listing spot-check evidence."
    )
    parser.add_argument("--feed-key", default=DEFAULT_FEED_KEY)
    parser.add_argument("--run-group", default="")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Fetch public search URLs and check for Synapse listing candidates.",
    )
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")
    args = parser.parse_args()

    spot_check = run_with_db(
        lambda db: _build_spot_check(
            db,
            feed_key=args.feed_key,
            run_group=args.run_group or None,
            execute=args.execute,
        )
    )
    write_json_payload(pydantic_payload(spot_check), args.output)
    return 0


def _build_spot_check(
    db,
    *,
    feed_key: str,
    run_group: str | None,
    execute: bool,
):
    from server.services.growth.ai_visibility_source_host_live_spot_check import (
        ai_visibility_source_host_live_spot_check,
    )

    return ai_visibility_source_host_live_spot_check(
        db,
        feed_key=feed_key,
        run_group=run_group,
        execute=execute,
    )


if __name__ == "__main__":  # pragma: no cover - direct script entrypoint
    raise SystemExit(main())
