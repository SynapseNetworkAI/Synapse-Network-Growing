#!/usr/bin/env python3
"""Export a complete AI visibility operator handoff bundle."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.database import SessionLocal, init_db  # noqa: E402
from server.services.growth.ai_visibility_handoff_bundle import (  # noqa: E402
    DEFAULT_FEED_KEY,
    build_handoff_payloads,
)
from server.services.growth.ai_visibility_release_unblock import (  # noqa: E402
    DEFAULT_ACTOR,
    DEFAULT_TARGET_COMMIT,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export AI visibility release/probe handoff evidence files."
    )
    parser.add_argument("--feed-key", default=DEFAULT_FEED_KEY)
    parser.add_argument("--run-group", default="")
    parser.add_argument("--target-commit", default=DEFAULT_TARGET_COMMIT)
    parser.add_argument("--actor", default=DEFAULT_ACTOR)
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory for manifest/evidence files. Defaults to docs/archive/evidence/growth/ai-visibility/<run-group>-handoff.",
    )
    args = parser.parse_args()

    os.environ.setdefault("APP_ENV", "test")
    generated_at = datetime.now(UTC)
    safe_run_group = args.run_group or (
        f"{generated_at.date().isoformat()}-{args.feed_key}-operator-handoff"
    )
    output_dir = Path(
        args.output_dir
        or f"docs/archive/evidence/growth/ai-visibility/{safe_run_group}-handoff"
    )
    init_db()
    db = SessionLocal()
    try:
        payloads = build_handoff_payloads(
            output_dir=output_dir,
            feed_key=args.feed_key,
            run_group=safe_run_group,
            target_commit=args.target_commit,
            actor=args.actor,
            db=db,
            generated_at=generated_at,
        )
    finally:
        db.close()
    manifest = write_handoff_payloads(payloads)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def write_handoff_payloads(payloads: dict) -> Any:
    files = payloads["files"]
    files["manifest"].parent.mkdir(parents=True, exist_ok=True)
    _write_json(files["release_snapshot"], payloads["release_snapshot"])
    _write_json(files["live_readiness"], payloads["live_readiness"])
    _write_json(files["external_probe_gate"], payloads["external_probe_gate"])
    _write_json(files["next_cycle"], payloads["next_cycle"])
    _write_json(files["goal_audit"], payloads["goal_audit"])
    files["operator_brief"].write_text(
        payloads["operator_brief"],
        encoding="utf-8",
    )
    manifest = payloads["manifest"]
    _write_json(files["manifest"], manifest)
    return manifest


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
