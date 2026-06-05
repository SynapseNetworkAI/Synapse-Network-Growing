#!/usr/bin/env python3
"""Validate recorded AI visibility probes against the planned probe matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.record_ai_visibility_probe import (  # noqa: E402
    ProbeRecord,
    parse_probe_file,
    validate_records,
)
from server.database import SessionLocal  # noqa: E402
from server.services.growth.ai_visibility_probe_matrix import (  # noqa: E402
    ai_visibility_probe_matrix,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Validate probe JSON/JSONL rows against the AI visibility probe matrix."
    )
    parser.add_argument("probe_file", help="JSON array/object or JSONL probe result file.")
    parser.add_argument("--matrix-file", help="Optional matrix JSON. Defaults to current DB-derived matrix.")
    parser.add_argument("--feed-key", default="", help="Validate only one feed.")
    parser.add_argument("--run-group", default="", help="Validate only one run group.")
    parser.add_argument(
        "--allow-missing-evidence",
        action="store_true",
        help="Do not require evidence_url on each external probe row.",
    )
    args = parser.parse_args()

    try:
        records = parse_probe_file(Path(args.probe_file))
        matrix_rows = _load_matrix_rows(args.matrix_file)
        report = validate_probe_matrix(
            records=records,
            matrix_rows=matrix_rows,
            feed_key=args.feed_key,
            run_group=args.run_group,
            require_evidence=not args.allow_missing_evidence,
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report["status"] == "succeeded" else 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


def validate_probe_matrix(
    *,
    records: list[ProbeRecord],
    matrix_rows: list[dict[str, Any]],
    feed_key: str = "",
    run_group: str = "",
    require_evidence: bool = True,
) -> dict[str, Any]:
    scoped_matrix = _scoped_matrix_rows(
        matrix_rows=matrix_rows,
        records=records,
        feed_key=feed_key,
        run_group=run_group,
    )
    expected = _expected_keys(scoped_matrix)
    actual = _actual_keys(records)
    errors = validate_records(records)
    if require_evidence:
        errors.extend(_missing_evidence_errors(records))
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    errors.extend(
        [
            f"missing matrix probe: feed={feed} run_group={run} platform={platform} query={query}"
            for feed, run, platform, query in missing
        ]
    )
    errors.extend(
        [
            f"unexpected probe row: feed={feed} run_group={run} platform={platform} query={query}"
            for feed, run, platform, query in unexpected
        ]
    )
    warnings = _blocked_matrix_warnings(scoped_matrix)
    platforms = sorted({platform for _, _, platform, _ in actual})
    feeds = sorted({feed for feed, _, _, _ in actual})
    run_groups = sorted({run for _, run, _, _ in actual})
    return {
        "status": "failed" if errors else "succeeded",
        "record_count": len(records),
        "expected_count": len(expected),
        "matched_count": len(expected & actual),
        "missing_count": len(missing),
        "unexpected_count": len(unexpected),
        "platforms": platforms,
        "feed_keys": feeds,
        "run_groups": run_groups,
        "errors": errors,
        "warnings": warnings,
    }


def _load_matrix_rows(matrix_file: str | None) -> list[dict[str, Any]]:
    if matrix_file:
        payload = json.loads(Path(matrix_file).read_text(encoding="utf-8"))
    else:
        db = SessionLocal()
        try:
            payload = ai_visibility_probe_matrix(db).model_dump(mode="json")
        finally:
            db.close()
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        raise ValueError("probe matrix JSON must contain a rows array")
    return rows


def _scoped_matrix_rows(
    *,
    matrix_rows: list[dict[str, Any]],
    records: list[ProbeRecord],
    feed_key: str,
    run_group: str,
) -> list[dict[str, Any]]:
    safe_feed_key = feed_key.strip()
    safe_run_group = run_group.strip()
    if not safe_feed_key:
        feed_keys = {record.feed_key for record in records if record.feed_key}
        if len(feed_keys) == 1:
            safe_feed_key = next(iter(feed_keys))
    if not safe_run_group:
        run_groups = {record.run_group for record in records if record.run_group}
        if len(run_groups) == 1:
            safe_run_group = next(iter(run_groups))
    rows = [
        row
        for row in matrix_rows
        if (not safe_feed_key or str(row.get("feed_key", "")) == safe_feed_key)
        and (not safe_run_group or str(row.get("run_group", "")) == safe_run_group)
    ]
    if not rows:
        raise ValueError("no probe matrix rows matched the requested scope")
    return rows


def _expected_keys(matrix_rows: list[dict[str, Any]]) -> set[tuple[str, str, str, str]]:
    expected: set[tuple[str, str, str, str]] = set()
    for row in matrix_rows:
        feed_key = str(row.get("feed_key", "")).strip()
        run_group = str(row.get("run_group", "")).strip()
        platform = str(row.get("platform", "")).strip().lower()
        queries = row.get("queries") or []
        if not isinstance(queries, list):
            continue
        for query in queries:
            expected.add((feed_key, run_group, platform, str(query).strip()))
    return {item for item in expected if all(item)}


def _actual_keys(records: list[ProbeRecord]) -> set[tuple[str, str, str, str]]:
    return {
        (record.feed_key, record.run_group, record.platform, record.query)
        for record in records
    }


def _missing_evidence_errors(records: list[ProbeRecord]) -> list[str]:
    return [
        f"record {index}: evidence_url is required for matrix validation"
        for index, record in enumerate(records)
        if not record.evidence_url
    ]


def _blocked_matrix_warnings(matrix_rows: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for row in matrix_rows:
        status = str(row.get("status", ""))
        if not status.startswith("blocked"):
            continue
        blockers = row.get("blockers") or []
        blocker_text = "; ".join(str(item) for item in blockers if str(item).strip())
        warnings.append(
            "matrix row is blocked before probing: "
            f"feed={row.get('feed_key')} platform={row.get('platform')} {blocker_text}".strip()
        )
    return warnings


if __name__ == "__main__":
    raise SystemExit(main())
