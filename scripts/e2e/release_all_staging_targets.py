#!/usr/bin/env python3
"""Create and directly publish every canonical staging release target."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Any

import requests


CONFIRM_PHRASE = "RELEASE_ALL_STAGING_TARGETS"


@dataclass(frozen=True)
class ReleaseTarget:
    project_key: str
    project_display_name: str
    service_key: str


@dataclass(frozen=True)
class ScheduledJobTarget:
    job_name: str
    run_smoke_jobs: bool = False
    run_migrations: bool = False


TARGETS = [
    ReleaseTarget("synapse-network", "Synapse-Network", "gateway"),
    ReleaseTarget("synapse-network", "Synapse-Network", "gateway-admin"),
    ReleaseTarget("synapse-network", "Synapse-Network", "admin-front"),
    ReleaseTarget("synapse-network", "Synapse-Network", "user-front"),
    ReleaseTarget("synapse-network", "Synapse-Network", "docs-front"),
    ReleaseTarget(
        "synapse-network-provider", "Synapse-Network-Provider", "provider-service"
    ),
]

SCHEDULED_JOB_TARGET = ScheduledJobTarget(
    "synapse-staging-deposit-indexer", run_smoke_jobs=True
)


def _request(method: str, base_url: str, path: str, **kwargs: Any) -> Any:
    response = requests.request(
        method, f"{base_url.rstrip('/')}{path}", timeout=30, **kwargs
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"{method} {path} failed: {response.status_code} {response.text[:1000]}"
        )
    return response.json()


def _create_task(base_url: str, target: ReleaseTarget, branch: str) -> int:
    payload = {
        "project_key": target.project_key,
        "project_display_name": target.project_display_name,
        "service_key": target.service_key,
        "branch_name": branch,
        "environment": "staging",
        "actor": "operator",
        "note": "Postgres migration all-service staging E2E direct publish.",
    }
    task = _request("POST", base_url, "/api/releases/tasks", json=payload)
    return int(task["id"])


def _deploy_task(base_url: str, task_id: int) -> None:
    _request(
        "POST",
        base_url,
        f"/api/releases/tasks/{task_id}/deploy-staging",
        json={"actor": "operator"},
    )


def _sync(base_url: str) -> None:
    _request(
        "POST", base_url, "/api/releases/tasks/sync-deployment-statuses?max_records=50"
    )


def _sync_scheduled_jobs(base_url: str) -> None:
    _request("POST", base_url, "/api/releases/scheduled-jobs/sync?max_records=50")


def _task(base_url: str, task_id: int) -> Any:
    tasks = _request("GET", base_url, "/api/releases/tasks")
    for item in tasks:
        if int(item["id"]) == task_id:
            return item
    raise RuntimeError(f"Release task #{task_id} not found after sync")


def _wait_for_task(
    base_url: str, task_id: int, timeout_seconds: int, poll_seconds: int
) -> Any:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        _sync(base_url)
        task = _task(base_url, task_id)
        if task["status"] in {"completed", "failed", "cancelled"}:
            return task
        print(
            f"[release-e2e] task #{task_id}: {task['status']} / deploy={task.get('deployment_status')}"
        )
        time.sleep(poll_seconds)
    raise TimeoutError(
        f"Release task #{task_id} did not finish within {timeout_seconds}s"
    )


def _create_scheduled_job_task(
    base_url: str, target: ScheduledJobTarget, branch: str
) -> int:
    payload = {
        "job_name": target.job_name,
        "environment": "staging",
        "source_ref_type": "branch",
        "source_ref": branch,
        "actor": "operator",
        "note": "Postgres migration scheduled-job staging E2E direct publish.",
        "run_smoke_jobs": target.run_smoke_jobs,
        "run_migrations": target.run_migrations,
    }
    task = _request(
        "POST", base_url, "/api/releases/scheduled-jobs/tasks", json=payload
    )
    return int(task["id"])


def _publish_scheduled_job_task(base_url: str, task_id: int) -> None:
    _request(
        "POST",
        base_url,
        f"/api/releases/scheduled-jobs/tasks/{task_id}/publish",
        json={"actor": "operator"},
    )


def _scheduled_job_task(base_url: str, task_id: int) -> Any:
    return _request("GET", base_url, f"/api/releases/scheduled-jobs/tasks/{task_id}")


def _wait_for_scheduled_job_task(
    base_url: str, task_id: int, timeout_seconds: int, poll_seconds: int
) -> Any:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        _sync_scheduled_jobs(base_url)
        task = _scheduled_job_task(base_url, task_id)
        if task["status"] in {"completed", "failed", "cancelled"}:
            return task
        print(
            f"[release-e2e] scheduled job task #{task_id}: {task['status']} / health={task.get('health_status')}"
        )
        time.sleep(poll_seconds)
    raise TimeoutError(
        f"Scheduled job release task #{task_id} did not finish within {timeout_seconds}s"
    )


def release_scheduled_job(
    base_url: str, branch: str, timeout_seconds: int, poll_seconds: int
) -> None:
    print(
        f"[release-e2e] create scheduled job release {SCHEDULED_JOB_TARGET.job_name}@{branch}"
    )
    task_id = _create_scheduled_job_task(base_url, SCHEDULED_JOB_TARGET, branch)
    print(f"[release-e2e] publish scheduled job task #{task_id}")
    _publish_scheduled_job_task(base_url, task_id)
    final = _wait_for_scheduled_job_task(
        base_url, task_id, timeout_seconds, poll_seconds
    )
    ok = (
        final.get("status") == "completed"
        and final.get("health_status") in {"passed", "healthy", "manual_verified"}
        and final.get("external_url")
    )
    if not ok:
        raise SystemExit(
            "scheduled job release failed: "
            f"{final.get('failure_summary') or final.get('notes') or final.get('status')}"
        )
    print(
        f"[release-e2e] ok scheduled job {SCHEDULED_JOB_TARGET.job_name}: {final.get('external_url')}"
    )


def release_all(
    base_url: str, branch: str, timeout_seconds: int, poll_seconds: int
) -> None:
    failures = []
    for target in TARGETS:
        print(
            f"[release-e2e] create {target.project_key}/{target.service_key}@{branch}"
        )
        task_id = _create_task(base_url, target, branch)
        print(f"[release-e2e] deploy task #{task_id}")
        _deploy_task(base_url, task_id)
        final = _wait_for_task(base_url, task_id, timeout_seconds, poll_seconds)
        ok = (
            final.get("status") == "completed"
            and final.get("deployment_status") == "succeeded"
            and final.get("deployment_health_status")
            in {"passed", "healthy", "manual_verified"}
            and final.get("deployment_external_url")
        )
        if not ok:
            failures.append((target, final))
            print(
                f"[release-e2e] FAILED {target.service_key}: {final.get('note') or final.get('deployment_failure_summary')}"
            )
            continue
        print(
            f"[release-e2e] ok {target.service_key}: {final.get('deployment_external_url')}"
        )
    if failures:
        raise SystemExit(f"{len(failures)} staging release target(s) failed")
    release_scheduled_job(base_url, branch, timeout_seconds, poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:9700")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--timeout-seconds", type=int, default=2400)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    if args.confirm != CONFIRM_PHRASE:
        raise SystemExit(
            f"Refusing to publish staging services without --confirm {CONFIRM_PHRASE}"
        )
    release_all(args.base_url, args.branch, args.timeout_seconds, args.poll_seconds)


if __name__ == "__main__":
    main()
