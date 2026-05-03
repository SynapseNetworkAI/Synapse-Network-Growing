import json
from datetime import datetime, timedelta, timezone

from server.database import DeploymentRecordRow, ReleaseTaskRow
from server.services.releases import github_actions_logs, github_cli
from server.services.releases import tasks as release_tasks_service


def _failed_wif_log() -> str:
    return "\n".join(
        [
            "deploy\tAuthenticate to Google Cloud\t2026-05-03T08:23:50Z ##[error]google-github-actions/auth failed with: failed to generate Google Cloud federated token",
            'deploy\tAuthenticate to Google Cloud\t{"error":"unauthorized_client","error_description":"The given credential is rejected by the attribute condition."}',
        ]
    )


def test_release_task_deployment_failed_run_records_actions_log_excerpt(
    monkeypatch, db_session
):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="running",
        external_run_id="25274187647",
        trigger_source="release_task",
        started_at=datetime.now(timezone.utc),
        metadata_json=json.dumps(
            {"deploy_repo_full_name": "SynapseNetworkAI/Synapse-Network"}
        ),
    )
    db_session.add(record)
    db_session.flush()
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="docs-front",
        branch_name="main",
        environment="staging",
        status="deploying",
        actor="operator",
        deployment_record_id=int(record.id),
    )
    db_session.add(task)
    db_session.commit()
    monkeypatch.setattr(
        release_tasks_service,
        "_run_gh_text",
        lambda *args, **kwargs: ("ok", _failed_wif_log(), ""),
    )

    state = release_tasks_service._apply_github_run_to_deployment(
        db_session,
        record,
        run_id="25274187647",
        run_payload={
            "databaseId": 25274187647,
            "status": "completed",
            "conclusion": "failure",
            "url": "https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/25274187647",
            "headSha": "abc123",
        },
    )

    assert state == "failed"
    assert record.status == "failed"
    assert "unauthorized_client" in (record.notes or "")
    metadata = json.loads(record.metadata_json)
    assert metadata["githubFailureLogStatus"] == "ok"
    assert "attribute condition" in metadata["githubFailureLogExcerpt"]


def test_release_task_deployment_status_sync_enriches_recent_failed_run_logs(
    monkeypatch, db_session
):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="failed",
        external_run_id="25274187647",
        trigger_source="release_task",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        finished_at=datetime.now(timezone.utc),
        metadata_json=json.dumps(
            {
                "deploy_repo_full_name": "SynapseNetworkAI/Synapse-Network",
                "githubRunConclusion": "failure",
            }
        ),
    )
    db_session.add(record)
    db_session.commit()
    monkeypatch.setattr(
        release_tasks_service,
        "_run_gh_text",
        lambda *args, **kwargs: ("ok", _failed_wif_log(), ""),
    )

    result = release_tasks_service.sync_release_task_deployment_statuses(db_session)

    assert int(record.id) in result["enriched_failed_log_ids"]
    db_session.refresh(record)
    assert "attribute condition" in (record.notes or "")
    assert "githubFailureLogExcerpt" in json.loads(record.metadata_json)


def test_release_task_deployment_status_sync_reconciles_rerun_success(
    monkeypatch, db_session
):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="failed",
        external_run_id="25274187647",
        trigger_source="release_task",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        finished_at=datetime.now(timezone.utc),
        metadata_json=json.dumps(
            {"deploy_repo_full_name": "SynapseNetworkAI/Synapse-Network"}
        ),
    )
    db_session.add(record)
    db_session.flush()
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="docs-front",
        branch_name="main",
        environment="staging",
        status="failed",
        actor="operator",
        deployment_record_id=int(record.id),
    )
    db_session.add(task)
    db_session.commit()
    monkeypatch.setattr(
        release_tasks_service,
        "_github_actions_run_view",
        lambda *args, **kwargs: (
            {
                "status": "completed",
                "conclusion": "success",
                "url": "https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/25274187647",
                "headSha": "abc123",
            },
            None,
        ),
    )

    result = release_tasks_service.sync_release_task_deployment_statuses(db_session)

    assert int(record.id) in result["succeeded_ids"]
    db_session.refresh(record)
    db_session.refresh(task)
    assert record.status == "succeeded"
    assert record.health_status == "passed"
    assert task.status == "completed"


def test_github_failure_log_result_handles_error_empty_and_truncation():
    error_result = github_actions_logs.github_failure_log_result(
        "owner/repo",
        "1",
        conclusion="failure",
        run_gh_text=lambda args: ("auth_error", None, "HTTP 403 permission denied"),
    )
    assert error_result.excerpt is None
    assert error_result.metadata["githubFailureLogStatus"] == "auth_error"
    assert "permission denied" in error_result.metadata["githubFailureLogError"]

    empty_result = github_actions_logs.github_failure_log_result(
        "owner/repo",
        "1",
        conclusion="failure",
        run_gh_text=lambda args: ("ok", "", ""),
    )
    assert empty_result.metadata["githubFailureLogStatus"] == "empty"

    long_line = "##[error]" + ("x" * 700)
    excerpt = github_actions_logs._extract_github_failed_log_excerpt(
        "\n".join([long_line, long_line])
    )
    assert excerpt is not None
    assert "[Truncated]" in excerpt


def test_github_cli_branch_exists_edges(monkeypatch):
    assert github_cli.github_branch_exists(
        "owner/repo",
        "main",
        e2e_mode=True,
        e2e_branch_options=["main"],
    ) == (True, None)
    assert github_cli.github_branch_exists(
        "owner/repo",
        "missing",
        e2e_mode=True,
        e2e_branch_options=["main"],
    ) == (False, "分支不存在，请重新选择有效远端分支")

    monkeypatch.setattr(
        github_cli,
        "run_gh_json",
        lambda *args, **kwargs: ("ok", {"name": "main"}, ""),
    )
    assert github_cli.github_branch_exists(
        "owner/repo",
        "main",
        e2e_mode=False,
        e2e_branch_options=[],
    ) == (True, None)

    monkeypatch.setattr(
        github_cli,
        "run_gh_json",
        lambda *args, **kwargs: ("not_found", None, "no branch"),
    )
    assert github_cli.github_branch_exists(
        "owner/repo",
        "missing",
        e2e_mode=False,
        e2e_branch_options=[],
    ) == (False, "分支不存在，请重新选择有效远端分支")

    monkeypatch.setattr(
        github_cli,
        "run_gh_json",
        lambda *args, **kwargs: ("transient_error", None, "boom"),
    )
    assert github_cli.github_branch_exists(
        "owner/repo",
        "missing",
        e2e_mode=False,
        e2e_branch_options=[],
    ) == (False, "boom")


def test_deployment_failure_log_enrichment_predicates():
    record = DeploymentRecordRow(
        status="failed", external_run_id="1", metadata_json="{}"
    )
    assert release_tasks_service._deployment_needs_failure_log_enrichment(record)

    record.metadata_json = json.dumps({"githubFailureLogExcerpt": "already synced"})
    assert not release_tasks_service._deployment_needs_failure_log_enrichment(record)

    record.metadata_json = json.dumps({"githubRunConclusion": "success"})
    assert not release_tasks_service._deployment_needs_failure_log_enrichment(record)

    record.metadata_json = "{}"
    record.external_run_id = ""
    record.external_url = ""
    assert not release_tasks_service._deployment_needs_failure_log_enrichment(record)
