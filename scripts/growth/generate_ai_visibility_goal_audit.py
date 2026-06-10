#!/usr/bin/env python3
"""Export the fail-closed AI visibility goal completion audit."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("APP_ENV", "test")

from server.database import SessionLocal, init_db  # noqa: E402
from server.services.growth.ai_visibility_goal_audit import (  # noqa: E402
    ai_visibility_goal_audit,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export AI visibility objective completion audit evidence."
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional JSON output path. Prints JSON to stdout when omitted.",
    )
    parser.add_argument(
        "--live-readiness-json",
        default="",
        help="Optional live-readiness JSON evidence to bind into the audit.",
    )
    parser.add_argument(
        "--external-gate-json",
        default="",
        help="Optional external-probe gate JSON evidence to bind into the audit.",
    )
    args = parser.parse_args()
    live_readiness = _read_optional_json(args.live_readiness_json)
    external_gate = _read_optional_json(args.external_gate_json)

    init_db()
    db = SessionLocal()
    try:
        payload = ai_visibility_goal_audit(
            db,
            live_readiness=live_readiness,
            external_gate=external_gate,
        ).model_dump(mode="json")
    finally:
        db.close()

    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(body, encoding="utf-8")
    print(body, end="")
    return 0


def _read_optional_json(path: str) -> dict[str, Any] | None:
    safe_path = path.strip()
    if not safe_path:
        return None
    payload = json.loads(Path(safe_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{safe_path} must contain a JSON object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
