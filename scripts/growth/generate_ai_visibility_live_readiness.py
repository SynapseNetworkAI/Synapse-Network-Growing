#!/usr/bin/env python3
"""Export live AI visibility feed readiness as JSON evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.ai_visibility_cli import write_json_payload  # noqa: E402
from server.services.growth.ai_visibility_live_readiness import (  # noqa: E402
    ai_visibility_live_readiness,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export current public-feed readiness for AI visibility."
    )
    parser.add_argument(
        "--feed-key",
        action="append",
        dest="feed_keys",
        help="Feed key to check. Repeat for multiple. Defaults to all feeds.",
    )
    parser.add_argument("--run-group", default="")
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")
    args = parser.parse_args()

    payload = ai_visibility_live_readiness(
        feed_keys=args.feed_keys,
        run_group=args.run_group or None,
    ).model_dump(mode="json")
    write_json_payload(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
