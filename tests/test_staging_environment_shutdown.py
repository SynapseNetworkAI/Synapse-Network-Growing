import subprocess
import json

import pytest

from server.services.staging_environment_shutdown import (
    _cloud_run_min_instances,
    _command_result,
    _discover_cloud_run_min_instances,
    _discover_scheduler_jobs,
    _load_json_list,
    _run_command,
    _scheduler_jobs,
    shutdown_staging_environment,
)


def _completed(cmd, returncode: int = 0):
    return subprocess.CompletedProcess(
        args=cmd, returncode=returncode, stdout="", stderr=""
    )


def test_staging_environment_shutdown_dry_run_returns_candidates_without_gcloud():
    calls: list[list[str]] = []

    result = shutdown_staging_environment(
        project="fabled-archive-494108-k5",
        region="us-central1",
        cloud_run_services=["synapse-staging-gateway"],
        scheduler_jobs=["synapse-staging-deposit-indexer-schedule"],
        cloud_sql_instance="synapse-staging-postgres",
        dry_run=True,
        runner=lambda cmd: calls.append(cmd) or _completed(cmd),
    )

    assert result["dry_run"] is True
    assert result["planned_count"] == 3
    assert result["failed_count"] == 0
    assert calls == [
        [
            "gcloud",
            "run",
            "services",
            "list",
            "--project",
            "fabled-archive-494108-k5",
            "--region",
            "us-central1",
            "--format=json",
        ]
    ]
    commands = [item["command"] for item in result["actions"]]
    assert commands[0] == [
        "gcloud",
        "run",
        "services",
        "update",
        "synapse-staging-gateway",
        "--project",
        "fabled-archive-494108-k5",
        "--region",
        "us-central1",
        "--min-instances",
        "0",
    ]
    assert commands[-1][-2:] == ["NEVER", "--quiet"]


def test_staging_environment_shutdown_apply_uses_fixed_gcloud_argv():
    calls: list[list[str]] = []

    def runner(cmd):
        calls.append(cmd)
        return _completed(cmd)

    result = shutdown_staging_environment(
        project="fabled-archive-494108-k5",
        region="us-central1",
        cloud_run_services=["synapse-staging-gateway"],
        scheduler_jobs=["synapse-staging-deposit-indexer-schedule"],
        cloud_sql_instance="synapse-staging-postgres",
        dry_run=False,
        runner=runner,
    )

    assert result["succeeded_count"] == 3
    assert all(isinstance(cmd, list) for cmd in calls)
    assert not any("bash" in cmd or "-lc" in cmd for cmd in calls)


def test_staging_environment_shutdown_discovers_all_scheduler_jobs_when_not_explicit():
    calls: list[list[str]] = []

    def runner(cmd):
        calls.append(cmd)
        if cmd[:4] == ["gcloud", "scheduler", "jobs", "list"]:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "name": "projects/fabled-archive-494108-k5/locations/us-central1/jobs/synapse-staging-a"
                        },
                        {
                            "name": "projects/fabled-archive-494108-k5/locations/us-central1/jobs/synapse-staging-b"
                        },
                    ]
                ),
                stderr="",
            )
        return _completed(cmd)

    result = shutdown_staging_environment(
        project="fabled-archive-494108-k5",
        region="us-central1",
        cloud_run_services=[],
        scheduler_jobs=None,
        cloud_sql_instance="",
        dry_run=False,
        runner=runner,
    )

    scheduler_targets = [
        item["target"]
        for item in result["actions"]
        if item["target_type"] == "cloud_scheduler_job"
    ]
    assert scheduler_targets == ["synapse-staging-a", "synapse-staging-b"]
    assert [
        "gcloud",
        "scheduler",
        "jobs",
        "list",
        "--project",
        "fabled-archive-494108-k5",
        "--location",
        "us-central1",
        "--format=json",
    ] in calls


def test_staging_environment_shutdown_skips_cloud_run_when_already_zero():
    calls: list[list[str]] = []

    def runner(cmd):
        calls.append(cmd)
        if cmd[:4] == ["gcloud", "run", "services", "list"]:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "metadata": {"name": "synapse-staging-gateway"},
                            "spec": {"template": {"metadata": {"annotations": {}}}},
                        }
                    ]
                ),
                stderr="",
            )
        return _completed(cmd)

    result = shutdown_staging_environment(
        project="fabled-archive-494108-k5",
        region="us-central1",
        cloud_run_services=["synapse-staging-gateway"],
        scheduler_jobs=[],
        cloud_sql_instance="",
        dry_run=False,
        runner=runner,
    )

    cloud_run_action = next(
        item for item in result["actions"] if item["target_type"] == "cloud_run_service"
    )
    assert cloud_run_action["status"] == "skipped"
    assert cloud_run_action["reason"] == "cloud_run_min_instances_already_zero"
    assert not any(cmd[:4] == ["gcloud", "run", "services", "update"] for cmd in calls)


def test_staging_environment_shutdown_rejects_production_project():
    with pytest.raises(ValueError, match="only allows the staging GCP project"):
        shutdown_staging_environment(
            project="synapse-network-prod",
            dry_run=True,
            runner=lambda cmd: _completed(cmd),
        )


def test_staging_environment_shutdown_helper_error_branches(monkeypatch):
    assert _load_json_list("{") == []
    assert _load_json_list("{}") == []
    assert (
        _cloud_run_min_instances(
            {"metadata": {"annotations": {"run.googleapis.com/minScale": "2"}}}
        )
        == "2"
    )

    result = _command_result(
        target_type="cloud_sql_instance",
        target="synapse-staging-postgres",
        command=["gcloud", "sql"],
        dry_run=False,
        runner=lambda cmd: _completed(
            cmd,
            returncode=1,
        ),
    )
    assert result["status"] == "failed"

    idempotent = _command_result(
        target_type="cloud_sql_instance",
        target="synapse-staging-postgres",
        command=["gcloud", "sql"],
        dry_run=False,
        runner=lambda cmd: subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr="Instance properties other than activation policy are not allowed",
        ),
    )
    assert idempotent["status"] == "skipped"
    assert idempotent["reason"] == "cloud_sql_instance_already_stopped"

    monkeypatch.setattr(
        "server.services.staging_environment_shutdown.scheduled_job_catalog",
        lambda: [],
    )
    with pytest.raises(RuntimeError, match="failed to list staging scheduler jobs"):
        _discover_scheduler_jobs(
            project="fabled-archive-494108-k5",
            region="us-central1",
            runner=lambda cmd: _completed(cmd, returncode=1),
        )


def test_staging_environment_shutdown_discovery_fallback_and_no_sql(monkeypatch):
    monkeypatch.setattr(
        "server.services.staging_environment_shutdown.scheduled_job_catalog",
        lambda: [
            type("Job", (), {"scheduler_job": "synapse-staging-fallback"})(),
            type("Job", (), {"scheduler_job": ""})(),
        ],
    )
    assert _scheduler_jobs() == ["synapse-staging-fallback"]
    assert _discover_scheduler_jobs(
        project="fabled-archive-494108-k5",
        region="us-central1",
        runner=lambda cmd: _completed(cmd, returncode=1),
    ) == ["synapse-staging-fallback"]

    monkeypatch.setattr(
        "server.services.staging_environment_shutdown.config.STAGING_CLOUD_SQL_INSTANCE",
        "",
    )
    monkeypatch.setattr(
        "server.services.staging_environment_shutdown.config.STAGING_CLOUD_RUN_SERVICES",
        [],
    )
    result = shutdown_staging_environment(
        project="fabled-archive-494108-k5",
        region="us-central1",
        cloud_run_services=[],
        scheduler_jobs=[],
        cloud_sql_instance="",
        dry_run=True,
        runner=lambda cmd: _completed(cmd),
    )
    assert result["skipped_count"] == 1
    assert result["actions"][0]["reason"] == "staging_cloud_sql_instance_not_configured"


def test_staging_environment_shutdown_run_command_and_cloud_run_discovery():
    result = _run_command(["python", "-c", "print('ok')"])
    assert result.returncode == 0

    discovered = _discover_cloud_run_min_instances(
        project="fabled-archive-494108-k5",
        region="us-central1",
        runner=lambda cmd: subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "metadata": {"name": "synapse-staging-gateway"},
                        "spec": {
                            "template": {
                                "metadata": {
                                    "annotations": {
                                        "autoscaling.knative.dev/minScale": "1"
                                    }
                                }
                            }
                        },
                    }
                ]
            ),
            stderr="",
        ),
    )
    assert discovered == {"synapse-staging-gateway": "1"}
    assert (
        _discover_cloud_run_min_instances(
            project="fabled-archive-494108-k5",
            region="us-central1",
            runner=lambda cmd: _completed(cmd, returncode=1),
        )
        == {}
    )
