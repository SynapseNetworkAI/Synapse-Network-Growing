#!/usr/bin/env python3
"""Regenerate unpublished X reply drafts with the real social reply agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.database import SessionLocal  # noqa: E402
from server.services.social.publishing import (
    regenerate_unpublished_social_replies_with_agent,
)  # noqa: E402


SAFETY_PHRASE = "REGENERATE_SOCIAL_REPLIES_WITH_AGENT"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate unpublished social_reply_items with Codex/LLM. No template fallback is used."
    )
    parser.add_argument("--confirm", required=True, help=f"Must equal {SAFETY_PHRASE}")
    parser.add_argument(
        "--actor", default="operator", help="Audit actor written into reply metadata"
    )
    args = parser.parse_args()
    if args.confirm != SAFETY_PHRASE:
        print(f"Refusing to run. Pass --confirm {SAFETY_PHRASE}.", file=sys.stderr)
        return 2
    db = SessionLocal()
    try:
        result = regenerate_unpublished_social_replies_with_agent(db, actor=args.actor)
    finally:
        db.close()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
