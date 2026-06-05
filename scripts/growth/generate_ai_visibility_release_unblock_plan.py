#!/usr/bin/env python3
"""Export operator commands to unblock an AI visibility release train."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.ai_visibility_cli import write_json_payload  # noqa: E402
from server.services.growth.ai_visibility_release_unblock import (  # noqa: E402
    DEFAULT_ACTOR,
    DEFAULT_TARGET_COMMIT,
    build_release_unblock_plan,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description=(
            "Export a non-executing release unblock command package for the "
            "Synapse AI visibility docs/www publication."
        )
    )
    parser.add_argument("--target-commit", default=DEFAULT_TARGET_COMMIT)
    parser.add_argument("--actor", default=DEFAULT_ACTOR)
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")
    args = parser.parse_args()

    payload = build_release_unblock_plan(
        target_commit=args.target_commit,
        actor=args.actor,
    )
    write_json_payload(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
