#!/usr/bin/env python3
"""Export a bounded AI visibility release blocker snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.services.growth.ai_visibility_release_snapshot import (  # noqa: E402
    build_snapshot,
)
from server.services.growth.ai_visibility_release_unblock import (  # noqa: E402
    DEFAULT_ACTOR,
    DEFAULT_TARGET_COMMIT,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export current AI visibility release blockers as JSON evidence."
    )
    parser.add_argument("--target-commit", default=DEFAULT_TARGET_COMMIT)
    parser.add_argument("--actor", default=DEFAULT_ACTOR)
    parser.add_argument("--feed-key", default="mcp_paid_api_discovery")
    parser.add_argument("--run-group", default="")
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")
    args = parser.parse_args()

    payload = build_snapshot(
        target_commit=args.target_commit,
        actor=args.actor,
        feed_key=args.feed_key,
        run_group=args.run_group,
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
