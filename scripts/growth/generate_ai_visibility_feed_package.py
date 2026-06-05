#!/usr/bin/env python3
"""Export AI visibility feed packages for operator execution."""

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
from server.services.growth.ai_visibility_plan import (  # noqa: E402
    ai_visibility_feed_packages,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export Synapse AI visibility feed packages as JSON."
    )
    parser.add_argument("--feed-key", help="Optional single feed key.")
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")
    args = parser.parse_args()

    feed_packages = ai_visibility_feed_packages(feed_key=args.feed_key)
    write_json_payload(pydantic_payload(feed_packages), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
