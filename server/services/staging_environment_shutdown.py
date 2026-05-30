"""Allowlisted staging environment cost-control actions."""

from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed gcloud argv runner, no shell
from datetime import datetime, timezone
from typing import Any, Callable

from server import config
from server.services.releases.scheduled_job_catalog import scheduled_job_catalog
from server.services.result_objects import ServiceObjectResult, service_object_result

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]

STAGING_PROJECT = "fabled-archive-494108-k5"


def _run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=180)  # noqa: S603 # nosec B603


def _idempotent_failure_result(
    *,
    item: dict[str, Any],
    target_type: str,
    error: str,
) -> dict[str, Any] | None:
    if (
        target_type == "cloud_sql_instance"
        and "Instance properties other than activation policy" in error
    ):
        return {
            **item,
            "status": "skipped",
            "reason": "cloud_sql_instance_already_stopped",
            "error": error,
        }
    return None


def _command_result(
    *,
    target_type: str,
    target: str,
    command: list[str],
    dry_run: bool,
    runner: CommandRunner,
) -> dict[str, Any]:
    item = {
        "target_type": target_type,
        "target": target,
        "command": command,
        "status": "planned" if dry_run else "running",
    }
    if dry_run:
        return item
    result = runner(command)
    if result.returncode == 0:
        return {**item, "status": "succeeded"}
    error = (result.stderr or result.stdout or "").strip()[:1000]
    idempotent = _idempotent_failure_result(
        item=item,
        target_type=target_type,
        error=error,
    )
    if idempotent is not None:
        return idempotent
    return {**item, "status": "failed", "error": error}


def _scheduler_jobs() -> list[str]:
    jobs: list[str] = []
    for item in scheduled_job_catalog():
        scheduler_job = str(getattr(item, "scheduler_job", "") or "").strip()
        if scheduler_job:
            jobs.append(scheduler_job)
    return jobs


def _scheduler_jobs_list_command(*, project: str, region: str) -> list[str]:
    return [
        "gcloud",
        "scheduler",
        "jobs",
        "list",
        "--project",
        project,
        "--location",
        region,
        "--format=json",
    ]


def _cloud_run_services_list_command(*, project: str, region: str) -> list[str]:
    return [
        "gcloud",
        "run",
        "services",
        "list",
        "--project",
        project,
        "--region",
        region,
        "--format=json",
    ]


def _load_json_list(raw: str) -> list[dict[str, Any]]:
    try:
        rows = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return (
        [dict(item) for item in rows if isinstance(item, dict)]
        if isinstance(rows, list)
        else []
    )


def _short_resource_name(row: dict[str, Any]) -> str:
    return (
        str(row.get("name") or row.get("metadata", {}).get("name") or "")
        .strip()
        .rsplit("/", 1)[-1]
    )


def _cloud_run_min_instances(row: dict[str, Any]) -> str:
    annotations = (
        row.get("spec", {})
        .get("template", {})
        .get("metadata", {})
        .get("annotations", {})
    )
    metadata_annotations = row.get("metadata", {}).get("annotations", {})
    return str(
        annotations.get("autoscaling.knative.dev/minScale")
        or metadata_annotations.get("run.googleapis.com/minScale")
        or "0"
    )


def _discover_cloud_run_min_instances(
    *, project: str, region: str, runner: CommandRunner
) -> dict[str, str]:
    result = runner(_cloud_run_services_list_command(project=project, region=region))
    if result.returncode != 0:
        return {}
    return {
        name: _cloud_run_min_instances(row)
        for row in _load_json_list(result.stdout)
        if (name := _short_resource_name(row))
    }


def _discover_scheduler_jobs(
    *, project: str, region: str, runner: CommandRunner
) -> list[str]:
    result = runner(_scheduler_jobs_list_command(project=project, region=region))
    if result.returncode != 0:
        fallback = _scheduler_jobs()
        if fallback:
            return fallback
        error = (result.stderr or result.stdout or "").strip()[:1000]
        raise RuntimeError(f"failed to list staging scheduler jobs: {error}")
    jobs: list[str] = []
    for row in _load_json_list(result.stdout):
        name = _short_resource_name(row)
        if name:
            jobs.append(name)
    return sorted(set(jobs))


def _ensure_staging_project(project: str) -> str:
    selected = str(project or "").strip()
    if selected != STAGING_PROJECT:
        raise ValueError(
            "staging environment shutdown only allows the staging GCP project"
        )
    return selected


def _cloud_run_command(*, service: str, project: str, region: str) -> list[str]:
    return [
        "gcloud",
        "run",
        "services",
        "update",
        service,
        "--project",
        project,
        "--region",
        region,
        "--min-instances",
        "0",
    ]


def _scheduler_pause_command(*, job: str, project: str, region: str) -> list[str]:
    return [
        "gcloud",
        "scheduler",
        "jobs",
        "pause",
        job,
        "--project",
        project,
        "--location",
        region,
    ]


def _cloud_sql_stop_command(*, instance: str, project: str) -> list[str]:
    return [
        "gcloud",
        "sql",
        "instances",
        "patch",
        instance,
        "--project",
        project,
        "--activation-policy",
        "NEVER",
        "--quiet",
    ]


def _cloud_run_actions(
    *,
    services: list[str],
    project: str,
    region: str,
    current_min_instances: dict[str, str],
    dry_run: bool,
    runner: CommandRunner,
) -> list[dict[str, Any]]:
    actions = []
    for service in services:
        service_name = str(service)
        current_min = str(current_min_instances.get(service_name, ""))
        command = _cloud_run_command(
            service=service_name,
            project=project,
            region=region,
        )
        if current_min in {"", "0"} and service_name in current_min_instances:
            actions.append(
                {
                    "target_type": "cloud_run_service",
                    "target": service_name,
                    "command": command,
                    "status": "skipped",
                    "reason": "cloud_run_min_instances_already_zero",
                }
            )
            continue
        actions.append(
            _command_result(
                target_type="cloud_run_service",
                target=service_name,
                command=command,
                dry_run=dry_run,
                runner=runner,
            )
        )
    return actions


def _scheduler_actions(
    *,
    jobs: list[str],
    project: str,
    region: str,
    dry_run: bool,
    runner: CommandRunner,
) -> list[dict[str, Any]]:
    return [
        _command_result(
            target_type="cloud_scheduler_job",
            target=str(job),
            command=_scheduler_pause_command(
                job=str(job),
                project=project,
                region=region,
            ),
            dry_run=dry_run,
            runner=runner,
        )
        for job in jobs
    ]


def _cloud_sql_action(
    *,
    instance: str,
    project: str,
    dry_run: bool,
    runner: CommandRunner,
) -> dict[str, Any]:
    if not instance:
        return {
            "target_type": "cloud_sql_instance",
            "target": "",
            "status": "skipped",
            "reason": "staging_cloud_sql_instance_not_configured",
        }
    return _command_result(
        target_type="cloud_sql_instance",
        target=instance,
        command=_cloud_sql_stop_command(instance=instance, project=project),
        dry_run=dry_run,
        runner=runner,
    )


def _action_count(actions: list[dict[str, Any]], status: str) -> int:
    return sum(1 for item in actions if item.get("status") == status)


@service_object_result
def shutdown_staging_environment(
    *,
    project: str | None = None,
    region: str | None = None,
    cloud_run_services: list[str] | None = None,
    scheduler_jobs: list[str] | None = None,
    cloud_sql_instance: str | None = None,
    dry_run: bool = True,
    runner: CommandRunner | None = None,
) -> ServiceObjectResult:
    """Put staging into its lowest-cost idle posture.

    Cloud Run services are not deleted. They are configured with min-instances=0.
    Cloud Scheduler jobs are paused so stopped databases do not receive work.
    Cloud SQL is stopped via activation-policy=NEVER.
    """

    selected_project = _ensure_staging_project(
        project or config.STAGING_ENVIRONMENT_PROJECT
    )
    selected_region = (
        str(region or config.STAGING_ENVIRONMENT_REGION).strip() or "us-central1"
    )
    selected_services = list(cloud_run_services or config.STAGING_CLOUD_RUN_SERVICES)
    command_runner = runner or _run_command
    current_cloud_run_min_instances = _discover_cloud_run_min_instances(
        project=selected_project,
        region=selected_region,
        runner=command_runner,
    )
    selected_scheduler_jobs = (
        list(scheduler_jobs)
        if scheduler_jobs is not None
        else _discover_scheduler_jobs(
            project=selected_project,
            region=selected_region,
            runner=command_runner,
        )
    )
    selected_sql_instance = str(
        cloud_sql_instance or config.STAGING_CLOUD_SQL_INSTANCE
    ).strip()
    actions = [
        *_cloud_run_actions(
            services=selected_services,
            project=selected_project,
            region=selected_region,
            current_min_instances=current_cloud_run_min_instances,
            dry_run=dry_run,
            runner=command_runner,
        ),
        *_scheduler_actions(
            jobs=selected_scheduler_jobs,
            project=selected_project,
            region=selected_region,
            dry_run=dry_run,
            runner=command_runner,
        ),
        _cloud_sql_action(
            instance=selected_sql_instance,
            project=selected_project,
            dry_run=dry_run,
            runner=command_runner,
        ),
    ]

    return _shutdown_summary(
        actions=actions,
        dry_run=dry_run,
        project=selected_project,
        region=selected_region,
    )


def _shutdown_summary(
    *,
    actions: list[dict[str, Any]],
    dry_run: bool,
    project: str,
    region: str,
) -> dict[str, Any]:
    return {
        "dry_run": bool(dry_run),
        "project": project,
        "region": region,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "action_count": len(actions),
        "failed_count": _action_count(actions, "failed"),
        "succeeded_count": _action_count(actions, "succeeded"),
        "planned_count": _action_count(actions, "planned"),
        "skipped_count": _action_count(actions, "skipped"),
        "actions": actions,
    }
