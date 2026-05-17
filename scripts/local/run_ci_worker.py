#!/usr/bin/env python3
"""Run requested local CI records with chunked append-only logs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.database import SessionLocal  # noqa: E402
from server.services.local_runner.ci_runs import (  # noqa: E402
    append_local_ci_event,
    claim_local_ci_run,
    finish_local_ci_run,
)
from server.services.local_runner.log_stream import run_command_with_chunked_logs  # noqa: E402
from server.services.local_runner.worker_loop import run_forever  # noqa: E402


def _append_event_factory(run_id: int):
    def append_event(event_type: str, message: str, step_key: str) -> None:
        with SessionLocal() as db:
            append_local_ci_event(
                db,
                ci_run_id=run_id,
                event_type=event_type,
                message=message,
                step_key=step_key,
            )
            db.commit()

    return append_event


def _command_for_scope(scope: str) -> list[str]:
    normalized = str(scope or "auto").strip().lower()
    selected = "full" if normalized == "full" else "auto"
    return ["bash", "scripts/ci/local_pr_checks.sh", "--scope", selected]


def _finish_run(run_id: int, exit_code: int, summary: str | None) -> None:
    with SessionLocal() as db:
        finish_local_ci_run(db, run_id, exit_code=exit_code, summary=summary)


def run_once(run_id: int | None = None) -> int:
    with SessionLocal() as db:
        run = claim_local_ci_run(db, run_id=run_id)
        if run is None:
            return 0
        claimed_id = int(run.id)
        repo_path = str(run.repo_path)
        scope = str(run.scope or "auto")
    command = _command_for_scope(scope)
    result = run_command_with_chunked_logs(
        command,
        cwd=repo_path,
        env=os.environ.copy(),
        step_key="local_ci",
        append_event=_append_event_factory(claimed_id),
        echo=True,
    )
    _finish_run(claimed_id, result.exit_code, result.failure_summary)
    return int(result.exit_code)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once", action="store_true", help="Run one CI record and exit."
    )
    parser.add_argument(
        "--loop", action="store_true", help="Continuously poll requested records."
    )
    parser.add_argument("--run-id", type=int, default=None)
    args = parser.parse_args()
    if args.loop:
        run_forever(lambda: run_once(run_id=args.run_id))
    return run_once(run_id=args.run_id)


if __name__ == "__main__":
    raise SystemExit(main())
