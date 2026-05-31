"""Helpers for Schedule Cost Control real-GCP E2E verification."""

from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed argv, no shell
from pathlib import Path
from typing import Any

import psycopg

from server.services.staging_environment_shutdown import (
    _cloud_run_services_list_command,
    _scheduler_jobs_list_command,
)

STAGING_PROJECT = "fabled-archive-494108-k5"
PROD_PROJECT = "synapse-network-prod"
WORKFLOW_KEYS = (
    "artifact_registry_cleanup_sweep",
    "secret_manager_version_cleanup_sweep",
    "staging_environment_shutdown_sweep",
)


class E2EFailure(RuntimeError):
    """Raised when a verification gate fails."""


def assert_gate(condition: bool, message: str) -> None:
    if not condition:
        raise E2EFailure(message)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _db_rows(
    database_url: str, sql: str, params: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    with psycopg.connect(_psycopg_dsn(database_url)) as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def _psycopg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def gcloud_json(command: list[str]) -> Any:
    result = subprocess.run(  # noqa: S603 # nosec B603
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise E2EFailure(f"gcloud failed: {' '.join(command)}\n{detail}")
    return json.loads(result.stdout or "[]")


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _artifact_targets(workflow: dict[str, Any]) -> list[dict[str, str]]:
    input_query = _json_object(workflow.get("input_query"))
    targets = input_query.get("targets")
    if isinstance(targets, list) and targets:
        return _explicit_artifact_targets(targets, input_query=input_query)
    return _project_artifact_targets(input_query)


def _explicit_artifact_targets(
    targets: list[Any], *, input_query: dict[str, Any]
) -> list[dict[str, str]]:
    selected = []
    for item in targets:
        if not isinstance(item, dict) or not item.get("project"):
            continue
        selected.append(
            {
                "project": str(item["project"]),
                "region": str(
                    item.get("region") or input_query.get("region") or "us-central1"
                ),
                "repository": str(
                    item.get("repository")
                    or input_query.get("repository")
                    or "synapse-staging"
                ),
            }
        )
    return selected


def _project_artifact_targets(input_query: dict[str, Any]) -> list[dict[str, str]]:
    region = str(input_query.get("region") or "us-central1")
    repository = str(input_query.get("repository") or "synapse-staging")
    return [
        {"project": str(project), "region": region, "repository": repository}
        for project in list(input_query.get("projects") or [])
    ]


def secret_projects(workflow: dict[str, Any]) -> list[str]:
    input_query = _json_object(workflow.get("input_query"))
    return [str(project) for project in input_query.get("projects") or []]


def _staging_shutdown_input(workflow: dict[str, Any]) -> dict[str, Any]:
    input_query = _json_object(workflow.get("input_query"))
    return {
        "project": str(input_query.get("project") or STAGING_PROJECT),
        "region": str(input_query.get("region") or "us-central1"),
        "cloud_sql_instance": str(input_query.get("cloud_sql_instance") or ""),
    }


def _artifact_snapshot(targets: list[dict[str, str]]) -> dict[str, Any]:
    projects: list[dict[str, Any]] = []
    for target in targets:
        image_root = (
            f"{target['region']}-docker.pkg.dev/"
            f"{target['project']}/{target['repository']}"
        )
        rows = gcloud_json(
            [
                "gcloud",
                "artifacts",
                "docker",
                "images",
                "list",
                image_root,
                "--include-tags",
                "--format=json",
            ]
        )
        projects.append({**target, "image_count": len(rows), "images": rows})
    return {
        "projects": projects,
        "image_count": sum(item["image_count"] for item in projects),
    }


def _secret_snapshot(projects: list[str]) -> dict[str, Any]:
    project_rows: list[dict[str, Any]] = []
    for project in projects:
        secrets = gcloud_json(
            ["gcloud", "secrets", "list", "--project", project, "--format=json"]
        )
        secret_rows = []
        for secret in secrets:
            secret_id = str(secret.get("name") or "").rstrip("/").rsplit("/", 1)[-1]
            if not secret_id:
                continue
            versions = gcloud_json(
                [
                    "gcloud",
                    "secrets",
                    "versions",
                    "list",
                    secret_id,
                    "--project",
                    project,
                    "--format=json",
                ]
            )
            secret_rows.append({"secret_id": secret_id, "versions": versions})
        project_rows.append(
            {
                "project": project,
                "secret_count": len(secret_rows),
                "secrets": secret_rows,
            }
        )
    return {"projects": project_rows}


def _staging_shutdown_snapshot(staging: dict[str, Any]) -> dict[str, Any]:
    project = str(staging["project"])
    region = str(staging["region"])
    snapshot: dict[str, Any] = {
        "staging": {
            "project": project,
            "cloud_run_services": _run_services(project, region),
            "scheduler_jobs": _scheduler_jobs(project, region),
        },
        "production_control": {
            "project": PROD_PROJECT,
            "cloud_run_services": _run_services(PROD_PROJECT, region),
            "sql_instances": _sql_instances(PROD_PROJECT),
        },
    }
    sql_instance = str(staging.get("cloud_sql_instance") or "")
    if sql_instance:
        snapshot["staging"]["cloud_sql_instance"] = _sql_instance(project, sql_instance)
    return snapshot


def _run_services(project: str, region: str) -> Any:
    return gcloud_json(_cloud_run_services_list_command(project=project, region=region))


def _scheduler_jobs(project: str, region: str) -> Any:
    return gcloud_json(_scheduler_jobs_list_command(project=project, region=region))


def _sql_instances(project: str) -> Any:
    return gcloud_json(
        ["gcloud", "sql", "instances", "list", "--project", project, "--format=json"]
    )


def _sql_instance(project: str, instance: str) -> Any:
    return gcloud_json(
        [
            "gcloud",
            "sql",
            "instances",
            "describe",
            instance,
            "--project",
            project,
            "--format=json",
        ]
    )


def assert_dry_run_unchanged(before: Any, after: Any, label: str) -> None:
    assert_gate(
        _stable_snapshot(before) == _stable_snapshot(after),
        f"{label} changed during dry-run",
    )


def assert_artifact_apply(
    before: dict[str, Any], after: dict[str, Any], run: dict[str, Any]
) -> None:
    deleted = int(run["result"].get("deleted_count") or 0)
    candidates = _artifact_candidate_images(run)
    after_images = _artifact_image_refs(after)
    assert_gate(
        deleted == len(candidates),
        "Artifact deleted_count does not match candidate image count",
    )
    still_present = sorted(candidates & after_images)
    assert_gate(
        not still_present,
        f"Artifact cleanup candidates still present after apply: {still_present}",
    )


def assert_secret_apply(
    before: dict[str, Any], after: dict[str, Any], run: dict[str, Any]
) -> None:
    destroyed = int(run["result"].get("destroyed_count") or 0)
    before_counts = _active_secret_versions(before)
    after_counts = _active_secret_versions(after)
    reduced = sum(
        max(0, before_counts.get(key, 0) - after_counts.get(key, 0))
        for key in before_counts
    )
    assert_gate(
        destroyed == reduced,
        "Secret destroyed_count does not match active-version reduction",
    )
    too_many = {key: count for key, count in after_counts.items() if count > 2}
    assert_gate(
        not too_many,
        f"Secret cleanup left more than 2 active versions: {too_many}",
    )


def assert_staging_shutdown_apply(
    before: dict[str, Any], after: dict[str, Any], run: dict[str, Any]
) -> None:
    _assert_production_control_unchanged(before, after)
    _assert_shutdown_commands_staging_only(run)
    _assert_staging_sql_stopped(after)
    _assert_staging_cloud_run_zero(after)
    _assert_staging_scheduler_paused(after)


def _assert_production_control_unchanged(
    before: dict[str, Any], after: dict[str, Any]
) -> None:
    assert_gate(
        _stable_shutdown_state(before).get("production_control")
        == _stable_shutdown_state(after).get("production_control"),
        "Production control snapshot changed during staging shutdown",
    )


def _assert_shutdown_commands_staging_only(run: dict[str, Any]) -> None:
    actions = run["result"].get("actions") or []
    assert_gate(actions, "Staging shutdown apply returned no actions")
    for action in actions:
        command = " ".join(str(part) for part in action.get("command") or [])
        assert_gate(
            PROD_PROJECT not in command,
            "Staging shutdown command referenced production project",
        )


def _assert_staging_sql_stopped(after: dict[str, Any]) -> None:
    sql = after.get("staging", {}).get("cloud_sql_instance") or {}
    if sql:
        policy = str(sql.get("settings", {}).get("activationPolicy") or "")
        assert_gate(
            policy == "NEVER",
            f"Staging Cloud SQL activation policy is {policy}, expected NEVER",
        )


def _assert_staging_cloud_run_zero(after: dict[str, Any]) -> None:
    state = _stable_shutdown_state(after).get("staging", {})
    min_instances = {
        item["name"]: item["min_instances"]
        for item in state.get("cloud_run_services", [])
        if item.get("min_instances") != "0"
    }
    assert_gate(
        not min_instances,
        f"Cloud Run services still have min instances: {min_instances}",
    )


def _assert_staging_scheduler_paused(after: dict[str, Any]) -> None:
    state = _stable_shutdown_state(after).get("staging", {})
    active_jobs = {
        item["name"]: item["state"]
        for item in state.get("scheduler_jobs", [])
        if item.get("state") != "PAUSED"
    }
    assert_gate(not active_jobs, f"Scheduler jobs are not paused: {active_jobs}")


def _stable_snapshot(snapshot: Any) -> Any:
    if isinstance(snapshot, dict) and {"staging", "production_control"} <= set(
        snapshot
    ):
        return _stable_shutdown_state(snapshot)
    return snapshot


def _stable_shutdown_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "staging": {
            "project": snapshot.get("staging", {}).get("project"),
            "cloud_run_services": _cloud_run_summary(
                snapshot.get("staging", {}).get("cloud_run_services") or []
            ),
            "scheduler_jobs": _scheduler_summary(
                snapshot.get("staging", {}).get("scheduler_jobs") or []
            ),
            "cloud_sql_activation_policy": _sql_activation_policy(
                snapshot.get("staging", {}).get("cloud_sql_instance") or {}
            ),
        },
        "production_control": {
            "project": snapshot.get("production_control", {}).get("project"),
            "cloud_run_services": _cloud_run_summary(
                snapshot.get("production_control", {}).get("cloud_run_services") or []
            ),
            "sql_instances": _sql_instances_summary(
                snapshot.get("production_control", {}).get("sql_instances") or []
            ),
        },
    }


def _cloud_run_summary(services: list[dict[str, Any]]) -> list[dict[str, str]]:
    summary = []
    for service in services:
        annotations = (
            service.get("spec", {})
            .get("template", {})
            .get("metadata", {})
            .get("annotations", {})
        )
        summary.append(
            {
                "name": str(service.get("metadata", {}).get("name") or ""),
                "min_instances": str(
                    annotations.get("autoscaling.knative.dev/minScale") or "0"
                ),
                "latest_ready_revision": str(
                    service.get("status", {}).get("latestReadyRevisionName") or ""
                ),
            }
        )
    return sorted(summary, key=lambda item: item["name"])


def _scheduler_summary(jobs: list[dict[str, Any]]) -> list[dict[str, str]]:
    return sorted(
        [
            {
                "name": str(job.get("name") or "").rsplit("/", 1)[-1],
                "state": str(job.get("state") or ""),
                "schedule": str(job.get("schedule") or ""),
            }
            for job in jobs
        ],
        key=lambda item: item["name"],
    )


def _sql_instances_summary(instances: list[dict[str, Any]]) -> list[dict[str, str]]:
    return sorted(
        [
            {
                "name": str(item.get("name") or ""),
                "activation_policy": _sql_activation_policy(item),
            }
            for item in instances
        ],
        key=lambda item: item["name"],
    )


def _sql_activation_policy(instance: dict[str, Any]) -> str:
    return str(instance.get("settings", {}).get("activationPolicy") or "")


def _artifact_candidate_images(run: dict[str, Any]) -> set[str]:
    images: set[str] = set()
    for project in run.get("result", {}).get("projects", []):
        for candidate in project.get("candidates", []):
            image = str(candidate.get("image") or "")
            if image:
                images.add(image)
    return images


def _artifact_image_refs(snapshot: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for project in snapshot.get("projects", []):
        for image in project.get("images", []):
            package = str(image.get("package") or "")
            version = str(image.get("version") or "")
            if package and version:
                refs.add(f"{package}@{version}")
    return refs


def _active_secret_versions(snapshot: dict[str, Any]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for project in snapshot.get("projects", []):
        project_id = str(project.get("project") or "")
        for secret in project.get("secrets", []):
            active = [
                row
                for row in secret.get("versions", [])
                if str(row.get("state") or "").upper() in {"ENABLED", "DISABLED"}
            ]
            counts[(project_id, str(secret.get("secret_id") or ""))] = len(active)
    return counts
