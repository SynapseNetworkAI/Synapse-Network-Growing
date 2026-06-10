#!/usr/bin/env python3
"""Validate live AI visibility feed assets and emit JSONL evidence rows.

This runner checks public crawl/readiness surfaces before an operator spends
time or API tokens on GPT/Claude/Grok/Gemini probes. It emits *_live_validation rows,
which are intentionally local/live readiness evidence, not answer-engine proof.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.ai_visibility_cli import emit_failure, write_text_or_stdout  # noqa: E402
from scripts.growth.record_ai_visibility_probe import validate_records  # noqa: E402
from server.services.growth.ai_visibility_feed_validation import (  # noqa: E402
    parse_feed_keys,
    validate_feed,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Run live readiness checks for AI visibility feed assets."
    )
    parser.add_argument(
        "--feed-key",
        action="append",
        dest="feed_keys",
        help="Feed key to validate. Repeat for multiple. Defaults to all feeds.",
    )
    parser.add_argument(
        "--run-group",
        default=f"{datetime.now(UTC).date().isoformat()}-feed-validation",
    )
    parser.add_argument("--output", help="Write JSONL rows to this path.")
    args = parser.parse_args()

    try:
        feed_keys, rows = _validated_rows(args.feed_keys, args.run_group)
        errors = validate_records(rows, allow_local_validation=True)
        if errors:
            emit({"status": "failed", "errors": errors}, stderr=True)
            return 2
        _write_rows(rows, output=args.output)
        _emit_success(
            rows,
            feed_keys=feed_keys,
            run_group=args.run_group,
            output=args.output,
        )
        return 0
    except Exception as exc:
        emit_failure(exc)
        return 1


def _validated_rows(raw_feed_keys: list[str] | None, run_group: str):
    feed_keys = parse_feed_keys(raw_feed_keys)
    rows = [
        row
        for feed_key in feed_keys
        for row in validate_feed(feed_key=feed_key, run_group=run_group)
    ]
    return feed_keys, rows


def _write_rows(rows, *, output: str | None) -> None:
    payload = "\n".join(
        json.dumps(row.api_payload(), ensure_ascii=False) for row in rows
    )
    write_text_or_stdout(payload, output=output)


def _emit_success(
    rows,
    *,
    feed_keys: list[str],
    run_group: str,
    output: str | None,
) -> None:
    emit(
        {
            "status": "succeeded",
            "record_count": len(rows),
            "feed_keys": feed_keys,
            "run_group": run_group,
            "output": output or "stdout",
            "passed": sum(1 for row in rows if row.synapse_mentioned),
            "failed": sum(1 for row in rows if not row.synapse_mentioned),
        },
        stderr=True,
    )


def emit(payload: dict[str, Any], *, stderr: bool = False) -> None:
    print(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        file=sys.stderr if stderr else sys.stdout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
