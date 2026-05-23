#!/usr/bin/env python3
"""Run local deploy records with chunked append-only deployment logs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.database import SessionLocal  # noqa: E402
from server.services.local_runner.deploy_runs import (
    claim_local_deployment,
    finish_local_deployment,
)  # noqa: E402
from server.services.local_runner.json_utils import _json_load_dict  # noqa: E402
from server.services.local_runner.log_stream import run_command_with_chunked_logs  # noqa: E402
from server.services.local_runner.worker_loop import run_forever  # noqa: E402
from server.services.releases.deployment_events import append_deployment_event  # noqa: E402


def _append_event_factory(deployment_record_id: int):
    def append_event(event_type: str, message: str, step_key: str) -> None:
        with SessionLocal() as db:
            append_deployment_event(
                db,
                deployment_record_id=deployment_record_id,
                event_type=event_type,
                message=message,
                step_key=step_key,
            )
            db.commit()

    return append_event


def _command_from_metadata(metadata: dict[str, object]) -> list[str]:
    command = metadata.get("localRunnerCommand")
    if isinstance(command, list) and all(isinstance(item, str) for item in command):
        return list(command)
    if isinstance(command, str) and command.strip():
        return ["bash", "-lc", command]
    raise ValueError(
        "localRunnerCommand is required for local deploy runner v1. "
        "Create a new DeploymentRecord with an explicit command or attach a deploy recipe."
    )


def _env_for_deployment(metadata: dict[str, object]) -> dict[str, str]:
    env = os.environ.copy()
    impersonation = str(metadata.get("impersonateServiceAccount") or "").strip()
    if impersonation:
        env["LOCAL_DEPLOY_IMPERSONATE_SERVICE_ACCOUNT"] = impersonation
    manifest_path = str(metadata.get("localManifestPath") or "").strip()
    if manifest_path:
        path = Path(manifest_path)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        env["LOCAL_DEPLOY_MANIFEST_PATH"] = str(path)
    return env


def run_once(deployment_record_id: int | None = None) -> int:
    with SessionLocal() as db:
        record = claim_local_deployment(db, deployment_record_id=deployment_record_id)
        if record is None:
            return 0
        claimed_id = int(record.id)
        metadata = _json_load_dict(record.metadata_json)
    try:
        command = _command_from_metadata(metadata)
    except ValueError as exc:
        append_event = _append_event_factory(claimed_id)
        append_event("runner_status", f"{exc}\n", "preflight")
        with SessionLocal() as db:
            finish_local_deployment(db, claimed_id, exit_code=2, summary=str(exc))
        return 2
    result = run_command_with_chunked_logs(
        command,
        cwd=str(metadata.get("cwd") or ROOT),
        env=_env_for_deployment(metadata),
        step_key=str(metadata.get("stepKey") or "local_deploy"),
        append_event=_append_event_factory(claimed_id),
        echo=True,
    )
    with SessionLocal() as db:
        finish_local_deployment(
            db,
            claimed_id,
            exit_code=result.exit_code,
            summary=result.failure_summary,
        )
    return int(result.exit_code)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once", action="store_true", help="Run one deploy record and exit."
    )
    parser.add_argument(
        "--loop", action="store_true", help="Continuously poll requested records."
    )
    parser.add_argument("--deployment-record-id", type=int, default=None)
    args = parser.parse_args()
    if args.loop:
        run_forever(lambda: run_once(deployment_record_id=args.deployment_record_id))
    return run_once(deployment_record_id=args.deployment_record_id)


if __name__ == "__main__":
    raise SystemExit(main())
