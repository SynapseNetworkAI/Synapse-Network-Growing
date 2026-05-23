#!/usr/bin/env python3
"""Schedule Center E2E verifier.

Default mode is non-destructive: it checks API/UI-adjacent contracts, database
lineage, and real GCP dry-run evidence when requested. Destructive apply paths
require an explicit confirmation phrase and are scoped to test resources.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404 - fixed argv, no shell
import sys
import time
from dataclasses import dataclass
from typing import Any

import psycopg
import requests


CONFIRM_PHRASE = "APPLY_SCHEDULE_E2E"
STAGING_PROJECT = "fabled-archive-494108-k5"
PROD_PROJECT = "synapse-network-prod"
CLEANUP_FIXTURE_ID = "-".join(["schedule", "e2e", "cleanup", "test"])


@dataclass(frozen=True)
class Args:
    base_url: str
    database_url: str | None
    real_gcp_dry_run: bool
    apply_secret_test: bool
    cleanup_test_secret: bool
    artifact_apply_repository: str | None
    artifact_region: str
    artifact_keep: int
    confirm: str | None


class E2EFailure(RuntimeError):
    pass


def _request(method: str, base_url: str, path: str, **kwargs: Any) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    response = requests.request(method, url, timeout=120, **kwargs)
    if response.status_code >= 400:
        raise E2EFailure(
            f"{method} {path} failed {response.status_code}: {response.text}"
        )
    return response.json()


def _gcloud_json(cmd: list[str]) -> list[dict[str, Any]]:
    result = subprocess.run(  # noqa: S603 # nosec B603
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise E2EFailure(f"gcloud failed: {' '.join(cmd)}\n{detail}")
    data = json.loads(result.stdout or "[]")
    return data if isinstance(data, list) else []


def _gcloud(cmd: list[str], *, input_text: str | None = None) -> str:
    result = subprocess.run(  # noqa: S603 # nosec B603
        cmd,
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise E2EFailure(f"gcloud failed: {' '.join(cmd)}\n{detail}")
    return result.stdout


def _db_rows(
    database_url: str, sql: str, params: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    with psycopg.connect(database_url) as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise E2EFailure(message)


def verify_api_and_crud(args: Args) -> None:
    print("[schedule-e2e] verifying schedule list/templates")
    schedules = _request("GET", args.base_url, "/api/schedules")
    templates = _request("GET", args.base_url, "/api/schedules/templates")
    keys = {item["workflow_key"] for item in schedules}
    template_keys = {item["template_key"] for item in templates}
    _assert(
        "secret_manager_version_cleanup_sweep" in keys,
        "secret cleanup schedule missing",
    )
    _assert(
        "artifact_registry_cleanup_sweep" in keys, "artifact cleanup schedule missing"
    )
    _assert("artifact_registry_cleanup" in template_keys, "artifact template missing")
    _assert(
        "secret_manager_version_cleanup" in template_keys, "secret template missing"
    )

    print("[schedule-e2e] verifying custom artifact schedule CRUD")
    workflow_key = f"custom_artifact_cleanup_e2e_{int(time.time())}"
    created = _request(
        "POST",
        args.base_url,
        "/api/schedules",
        json={
            "template_key": "artifact_registry_cleanup",
            "workflow_key": workflow_key,
            "display_name": "Custom Artifact Cleanup E2E",
            "schedule": {"cadence": "daily", "suggested_local_time": "12:30"},
            "input_query": {
                "projects": [STAGING_PROJECT],
                "repository": args.artifact_apply_repository or "schedule-e2e",
                "keep": 3,
                "older_than_days": 7,
            },
        },
    )
    _assert(created["is_builtin"] is False, "custom schedule should not be builtin")
    patched = _request(
        "PATCH",
        args.base_url,
        f"/api/schedules/{workflow_key}",
        json={
            "status": "paused",
            "schedule": {"cadence": "daily", "suggested_local_time": "12:45"},
        },
    )
    _assert(patched["status"] == "paused", "custom schedule patch did not persist")
    deleted = _request("DELETE", args.base_url, f"/api/schedules/{workflow_key}")
    _assert(deleted["deleted"] is True, "custom schedule delete failed")
    builtin_delete = requests.delete(
        f"{args.base_url.rstrip('/')}/api/schedules/bug_log_sweep", timeout=60
    )
    _assert(builtin_delete.status_code == 400, "builtin delete must be rejected")


def verify_schedule_runs(args: Args) -> None:
    print("[schedule-e2e] running built-in dry-runs through Schedule API")
    secret_run = _request(
        "POST",
        args.base_url,
        "/api/schedules/secret_manager_version_cleanup_sweep/run",
        json={"dry_run": True},
    )
    artifact_run = _request(
        "POST",
        args.base_url,
        "/api/schedules/artifact_registry_cleanup_sweep/run",
        json={"dry_run": True},
    )
    _assert(secret_run["result"].get("dry_run") is True, "secret dry-run flag missing")
    _assert(
        artifact_run["result"].get("dry_run") is True, "artifact dry-run flag missing"
    )
    _assert(
        artifact_run["result"].get("deleted_count") == 0,
        "artifact dry-run deleted images",
    )

    secret_history = _request(
        "GET", args.base_url, "/api/schedules/secret_manager_version_cleanup_sweep/runs"
    )
    artifact_history = _request(
        "GET", args.base_url, "/api/schedules/artifact_registry_cleanup_sweep/runs"
    )
    _assert(
        secret_history and secret_history[0]["dry_run"] is True,
        "secret run history missing",
    )
    _assert(
        artifact_history and artifact_history[0]["dry_run"] is True,
        "artifact run history missing",
    )


def verify_database(args: Args) -> None:
    if not args.database_url:
        print("[schedule-e2e] OPS_DATABASE_URL not provided; skipping direct DB checks")
        return
    print("[schedule-e2e] verifying recurring_workflows and recurring_workflow_runs")
    workflows = _db_rows(
        args.database_url,
        """
        select workflow_key, status, is_builtin, output_action_json
        from recurring_workflows
        where workflow_key in (
          'secret_manager_version_cleanup_sweep',
          'artifact_registry_cleanup_sweep'
        )
        """,
    )
    _assert(len(workflows) == 2, "expected two cleanup workflows in DB")
    actions = {
        row["workflow_key"]: json.loads(row["output_action_json"])["kind"]
        for row in workflows
    }
    _assert(
        actions["secret_manager_version_cleanup_sweep"]
        == "destroy_old_secret_manager_versions",
        "secret output action mismatch",
    )
    _assert(
        actions["artifact_registry_cleanup_sweep"]
        == "cleanup_artifact_registry_versions",
        "artifact output action mismatch",
    )
    runs = _db_rows(
        args.database_url,
        """
        select workflow_key, status, dry_run, result_json, error_excerpt
        from recurring_workflow_runs
        where workflow_key in (
          'secret_manager_version_cleanup_sweep',
          'artifact_registry_cleanup_sweep'
        )
        order by id desc
        limit 10
        """,
    )
    _assert(any(row["dry_run"] for row in runs), "expected dry-run rows in DB")
    _assert(
        all(not row["error_excerpt"] for row in runs[:2]),
        "latest schedule runs have errors",
    )


def _version_state_counts(project: str, secret: str) -> dict[str, int]:
    rows = _gcloud_json(
        [
            "gcloud",
            "secrets",
            "versions",
            "list",
            secret,
            "--project",
            project,
            "--format=json",
        ]
    )
    counts: dict[str, int] = {}
    for row in rows:
        state = str(row.get("state") or "UNKNOWN")
        counts[state] = counts.get(state, 0) + 1
    return counts


def _artifact_digest_count(project: str, region: str, repository: str) -> int:
    rows = _gcloud_json(
        [
            "gcloud",
            "artifacts",
            "docker",
            "images",
            "list",
            f"{region}-docker.pkg.dev/{project}/{repository}",
            "--include-tags",
            "--format=json",
        ]
    )
    return len(rows)


def verify_real_gcp_dry_run(args: Args) -> None:
    if not args.real_gcp_dry_run:
        return
    print("[schedule-e2e] verifying remote state is unchanged by dry-runs")
    secret_rows = _gcloud_json(
        ["gcloud", "secrets", "list", "--project", STAGING_PROJECT, "--format=json"]
    )
    if secret_rows:
        secret = str(secret_rows[0]["name"]).rsplit("/", 1)[-1]
        before = _version_state_counts(STAGING_PROJECT, secret)
        _request(
            "POST",
            args.base_url,
            "/api/schedules/secret_manager_version_cleanup_sweep/run",
            json={"dry_run": True},
        )
        after = _version_state_counts(STAGING_PROJECT, secret)
        _assert(before == after, f"secret versions changed during dry-run: {secret}")
    if args.artifact_apply_repository:
        before = _artifact_digest_count(
            STAGING_PROJECT, args.artifact_region, args.artifact_apply_repository
        )
        _request(
            "POST",
            args.base_url,
            "/api/schedules/artifact_registry_cleanup_sweep/run",
            json={"dry_run": True},
        )
        after = _artifact_digest_count(
            STAGING_PROJECT, args.artifact_region, args.artifact_apply_repository
        )
        _assert(before == after, "artifact image count changed during dry-run")


def apply_secret_test(args: Args) -> None:
    if not args.apply_secret_test:
        return
    _assert(args.confirm == CONFIRM_PHRASE, f"--confirm {CONFIRM_PHRASE} required")
    print("[schedule-e2e] preparing Secret Manager test fixture")
    existing = _gcloud_json(
        ["gcloud", "secrets", "list", "--project", STAGING_PROJECT, "--format=json"]
    )
    if CLEANUP_FIXTURE_ID not in {
        str(row["name"]).rsplit("/", 1)[-1] for row in existing
    }:
        _gcloud(
            [
                "gcloud",
                "secrets",
                "create",
                CLEANUP_FIXTURE_ID,
                "--project",
                STAGING_PROJECT,
            ]
        )
    for index in range(5):
        _gcloud(
            [
                "gcloud",
                "secrets",
                "versions",
                "add",
                CLEANUP_FIXTURE_ID,
                "--project",
                STAGING_PROJECT,
                "--data-file=-",
            ],
            input_text=f"schedule-e2e-dummy-{index}",
        )

    workflow_key = f"custom_secret_cleanup_e2e_{int(time.time())}"
    _request(
        "POST",
        args.base_url,
        "/api/schedules",
        json={
            "template_key": "secret_manager_version_cleanup",
            "workflow_key": workflow_key,
            "display_name": "Custom Secret Cleanup E2E",
            "input_query": {
                "projects": [STAGING_PROJECT],
                "secret_ids": [CLEANUP_FIXTURE_ID],
                "keep": 3,
            },
        },
    )
    dry_run = _request(
        "POST",
        args.base_url,
        f"/api/schedules/{workflow_key}/run",
        json={"dry_run": True},
    )
    _assert(
        dry_run["result"]["candidate_count"] >= 2, "secret dry-run found no candidates"
    )
    apply = _request(
        "POST",
        args.base_url,
        f"/api/schedules/{workflow_key}/run",
        json={"dry_run": False},
    )
    _assert(
        apply["result"]["destroyed_count"] >= 2,
        "secret apply did not destroy old versions",
    )
    states = _version_state_counts(STAGING_PROJECT, CLEANUP_FIXTURE_ID)
    active = states.get("ENABLED", 0) + states.get("DISABLED", 0)
    _assert(active <= 3, f"expected <=3 active test secret versions, got {states}")
    _request("DELETE", args.base_url, f"/api/schedules/{workflow_key}")
    if args.cleanup_test_secret:
        _gcloud(
            [
                "gcloud",
                "secrets",
                "delete",
                CLEANUP_FIXTURE_ID,
                "--project",
                STAGING_PROJECT,
                "--quiet",
            ]
        )


def apply_artifact_test(args: Args) -> None:
    if not args.artifact_apply_repository:
        return
    if not args.confirm:
        return
    _assert(args.confirm == CONFIRM_PHRASE, f"--confirm {CONFIRM_PHRASE} required")
    print(
        "[schedule-e2e] applying Artifact Registry cleanup to explicit test repository"
    )
    workflow_key = f"custom_artifact_cleanup_e2e_{int(time.time())}"
    before = _artifact_digest_count(
        STAGING_PROJECT, args.artifact_region, args.artifact_apply_repository
    )
    _request(
        "POST",
        args.base_url,
        "/api/schedules",
        json={
            "template_key": "artifact_registry_cleanup",
            "workflow_key": workflow_key,
            "display_name": "Custom Artifact Cleanup E2E",
            "input_query": {
                "projects": [STAGING_PROJECT],
                "region": args.artifact_region,
                "repository": args.artifact_apply_repository,
                "keep": args.artifact_keep,
                "older_than_days": 0,
            },
        },
    )
    dry_run = _request(
        "POST",
        args.base_url,
        f"/api/schedules/{workflow_key}/run",
        json={"dry_run": True},
    )
    _assert(
        dry_run["result"]["project_count"] == 1, "artifact dry-run project mismatch"
    )
    apply = _request(
        "POST",
        args.base_url,
        f"/api/schedules/{workflow_key}/run",
        json={"dry_run": False},
    )
    after = _artifact_digest_count(
        STAGING_PROJECT, args.artifact_region, args.artifact_apply_repository
    )
    _assert(after <= before, "artifact apply increased digest count unexpectedly")
    _assert(
        apply["result"]["deleted_count"] == before - after,
        "artifact deleted_count mismatch",
    )
    _request("DELETE", args.base_url, f"/api/schedules/{workflow_key}")


def parse_args() -> Args:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:9700")
    parser.add_argument("--database-url", default=os.environ.get("OPS_DATABASE_URL"))
    parser.add_argument("--real-gcp-dry-run", action="store_true")
    parser.add_argument("--apply-secret-test", action="store_true")
    parser.add_argument("--cleanup-test-secret", action="store_true")
    parser.add_argument("--artifact-apply-repository")
    parser.add_argument("--artifact-region", default="us-central1")
    parser.add_argument("--artifact-keep", type=int, default=3)
    parser.add_argument("--confirm")
    ns = parser.parse_args()
    return Args(**vars(ns))


def main() -> int:
    args = parse_args()
    try:
        verify_api_and_crud(args)
        verify_schedule_runs(args)
        verify_database(args)
        verify_real_gcp_dry_run(args)
        apply_secret_test(args)
        apply_artifact_test(args)
    except E2EFailure as exc:
        print(f"[schedule-e2e] FAILED: {exc}", file=sys.stderr)
        return 1
    print("[schedule-e2e] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
