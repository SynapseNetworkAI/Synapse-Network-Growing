#!/usr/bin/env python3
"""Export source-host feed execution checklist for operator tracking."""

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
        description="Export source-host execution checklist for AI visibility feeds."
    )
    parser.add_argument("--feed-key", default=DEFAULT_FEED_KEY)
    parser.add_argument("--run-group", default="")
    parser.add_argument(
        "--diagnosis-file",
        help="Optional feed diagnosis JSON to build an offline checklist without the Ops API ledger.",
    )
    parser.add_argument(
        "--skip-source-host-audit",
        action="store_true",
        help="Do not annotate offline diagnosis items with existing source-host evidence.",
    )
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")
    args = parser.parse_args()

    if args.diagnosis_file:
        checklist = _build_execution_checklist_from_diagnosis(
            args.diagnosis_file,
            feed_key=args.feed_key,
            run_group=args.run_group or None,
            use_source_host_audit=not args.skip_source_host_audit,
        )
    else:
        checklist = run_with_db(
            lambda db: _build_execution_checklist(
                db,
                feed_key=args.feed_key,
                run_group=args.run_group or None,
            )
        )
    write_json_payload(pydantic_payload(checklist), args.output)
    return 0


def _build_execution_checklist(db, *, feed_key: str, run_group: str | None):
    from server.services.growth.ai_visibility_source_host_feed import (
        ai_visibility_source_host_execution_checklist,
    )

    return ai_visibility_source_host_execution_checklist(
        db,
        feed_key=feed_key,
        run_group=run_group,
    )


def _build_execution_checklist_from_diagnosis(
    diagnosis_file: str,
    *,
    feed_key: str,
    run_group: str | None,
    use_source_host_audit: bool = True,
):
    from server.services.growth.ai_visibility_source_host_offline import (
        source_host_execution_checklist_from_diagnosis,
    )
    from scripts.growth.ai_visibility_source_host_audit_cli import (
        maybe_offline_source_host_audit_facts,
    )

    return source_host_execution_checklist_from_diagnosis(
        diagnosis_file,
        feed_key=feed_key,
        run_group=run_group,
        audit_facts=maybe_offline_source_host_audit_facts(use_source_host_audit),
    )


if __name__ == "__main__":
    raise SystemExit(main())
