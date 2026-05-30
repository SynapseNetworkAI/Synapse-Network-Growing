#!/usr/bin/env python3
"""Real GCP E2E evidence for Schedule Cost Control workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from scripts.e2e.schedule_cost_control_helpers import (
    E2EFailure,
    WORKFLOW_KEYS,
    _artifact_snapshot,
    _artifact_targets,
    assert_artifact_apply,
    assert_dry_run_unchanged,
    assert_gate,
    assert_secret_apply,
    assert_staging_shutdown_apply,
    _db_rows,
    secret_projects,
    _secret_snapshot,
    _staging_shutdown_input,
    _staging_shutdown_snapshot,
    write_json,
)

CONFIRM_PHRASE = "APPLY_COST_CONTROL_E2E"


@dataclass(frozen=True)
class Args:
    base_url: str
    database_url: str | None
    output_dir: Path
    confirm: str | None
    apply_artifacts: bool
    apply_secrets: bool
    apply_staging_shutdown: bool
    skip_artifacts: bool
    skip_secrets: bool
    skip_staging_shutdown: bool


def _request(method: str, base_url: str, path: str, **kwargs: Any) -> Any:
    response = requests.request(
        method, f"{base_url.rstrip('/')}{path}", timeout=180, **kwargs
    )
    if response.status_code >= 400:
        raise E2EFailure(
            f"{method} {path} failed {response.status_code}: {response.text}"
        )
    return response.json()


def _workflow_map(base_url: str) -> dict[str, dict[str, Any]]:
    schedules = _request("GET", base_url, "/api/schedules")
    by_key = {str(item["workflow_key"]): item for item in schedules}
    missing = [key for key in WORKFLOW_KEYS if key not in by_key]
    assert_gate(not missing, f"missing schedules: {missing}")
    return by_key


def _run_workflow(base_url: str, workflow_key: str, *, dry_run: bool) -> dict[str, Any]:
    return _request(
        "POST",
        base_url,
        f"/api/schedules/{workflow_key}/run",
        json={"dry_run": bool(dry_run)},
    )


def _verify_db_runs(args: Args) -> None:
    if not args.database_url:
        return
    rows = _db_rows(
        args.database_url,
        """
        select workflow_key, status, dry_run, result_json, error_excerpt, started_at, completed_at
        from recurring_workflow_runs
        where workflow_key = any(%s)
        order by id desc
        limit 30
        """,
        (list(WORKFLOW_KEYS),),
    )
    write_json(args.output_dir / "db-run-history.json", rows)
    assert_gate(
        rows, "No recurring workflow run history found for cost-control workflows"
    )
    assert_gate(
        any(row["dry_run"] for row in rows), "Expected at least one dry-run row"
    )


def _require_confirm(args: Args) -> None:
    if args.apply_artifacts or args.apply_secrets or args.apply_staging_shutdown:
        assert_gate(
            args.confirm == CONFIRM_PHRASE,
            f"--confirm {CONFIRM_PHRASE} is required for apply",
        )


def _capture_all(
    args: Args, workflows: dict[str, dict[str, Any]], suffix: str
) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    if not args.skip_artifacts:
        snapshots["artifacts"] = _artifact_snapshot(
            _artifact_targets(workflows["artifact_registry_cleanup_sweep"])
        )
        write_json(args.output_dir / f"artifacts-{suffix}.json", snapshots["artifacts"])
    if not args.skip_secrets:
        snapshots["secrets"] = _secret_snapshot(
            secret_projects(workflows["secret_manager_version_cleanup_sweep"])
        )
        write_json(args.output_dir / f"secrets-{suffix}.json", snapshots["secrets"])
    if not args.skip_staging_shutdown:
        snapshots["staging_shutdown"] = _staging_shutdown_snapshot(
            _staging_shutdown_input(workflows["staging_environment_shutdown_sweep"])
        )
        write_json(
            args.output_dir / f"staging-shutdown-{suffix}.json",
            snapshots["staging_shutdown"],
        )
    return snapshots


def _run_dry_runs(args: Args) -> dict[str, Any]:
    dry_runs = {}
    if not args.skip_artifacts:
        dry_runs["artifacts"] = _run_workflow(
            args.base_url, "artifact_registry_cleanup_sweep", dry_run=True
        )
    if not args.skip_secrets:
        dry_runs["secrets"] = _run_workflow(
            args.base_url, "secret_manager_version_cleanup_sweep", dry_run=True
        )
    if not args.skip_staging_shutdown:
        dry_runs["staging_shutdown"] = _run_workflow(
            args.base_url, "staging_environment_shutdown_sweep", dry_run=True
        )
    return dry_runs


def _run_applies(args: Args) -> dict[str, Any]:
    apply_runs = {}
    if args.apply_artifacts:
        apply_runs["artifacts"] = _run_workflow(
            args.base_url, "artifact_registry_cleanup_sweep", dry_run=False
        )
    if args.apply_secrets:
        apply_runs["secrets"] = _run_workflow(
            args.base_url, "secret_manager_version_cleanup_sweep", dry_run=False
        )
    if args.apply_staging_shutdown:
        apply_runs["staging_shutdown"] = _run_workflow(
            args.base_url, "staging_environment_shutdown_sweep", dry_run=False
        )
    return apply_runs


def _run_e2e(args: Args) -> dict[str, Any]:
    _require_confirm(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    workflows = _workflow_map(args.base_url)
    write_json(
        args.output_dir / "schedule-workflows.json",
        {key: workflows[key] for key in WORKFLOW_KEYS},
    )

    before = _capture_all(args, workflows, "before")
    dry_runs = _run_dry_runs(args)
    write_json(args.output_dir / "dry-run-results.json", dry_runs)
    after_dry = _capture_all(args, workflows, "after-dry-run")
    for key, label in (
        ("artifacts", "Artifact Registry"),
        ("secrets", "Secret Manager"),
        ("staging_shutdown", "Staging shutdown targets"),
    ):
        if key in before:
            assert_dry_run_unchanged(before[key], after_dry[key], label)

    apply_runs = _run_applies(args)
    write_json(args.output_dir / "apply-results.json", apply_runs)
    after_apply = (
        _capture_all(args, workflows, "after-apply") if apply_runs else after_dry
    )
    if args.apply_artifacts:
        assert_artifact_apply(
            after_dry["artifacts"], after_apply["artifacts"], apply_runs["artifacts"]
        )
    if args.apply_secrets:
        assert_secret_apply(
            after_dry["secrets"], after_apply["secrets"], apply_runs["secrets"]
        )
    if args.apply_staging_shutdown:
        assert_staging_shutdown_apply(
            after_dry["staging_shutdown"],
            after_apply["staging_shutdown"],
            apply_runs["staging_shutdown"],
        )
    _verify_db_runs(args)
    return {
        "status": "passed",
        "output_dir": str(args.output_dir),
        "dry_run_workflows": sorted(dry_runs.keys()),
        "apply_workflows": sorted(apply_runs.keys()),
    }


def parse_args() -> Args:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:9700")
    parser.add_argument("--database-url", default=os.environ.get("OPS_DATABASE_URL"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/archive/evidence") / f"schedule-cost-control-{stamp}",
    )
    parser.add_argument("--confirm")
    parser.add_argument("--apply-artifacts", action="store_true")
    parser.add_argument("--apply-secrets", action="store_true")
    parser.add_argument("--apply-staging-shutdown", action="store_true")
    parser.add_argument("--skip-artifacts", action="store_true")
    parser.add_argument("--skip-secrets", action="store_true")
    parser.add_argument("--skip-staging-shutdown", action="store_true")
    return Args(**vars(parser.parse_args()))


def main() -> int:
    try:
        result = _run_e2e(parse_args())
    except E2EFailure as exc:
        print(f"[schedule-cost-control-e2e] FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
