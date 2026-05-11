import json
import subprocess
from datetime import datetime, timedelta, timezone

from server.database import DeploymentRecordRow, ReleaseTaskRow, RequirementRow
from server.schemas import ProjectPolicyCreate, ReleaseTaskPrGateOut
from server.services.projects.policy import create_project_policy
from server.services.releases import tasks as release_tasks_service


def _successful_pr_gate() -> ReleaseTaskPrGateOut:
    return ReleaseTaskPrGateOut(
        branch_exists=True,
        pr_exists=True,
        pr_url="https://github.com/SynapseNetworkAI/Synapse-Network/pull/99",
        pr_number=99,
        pr_state="open",
        checks_status="success",
        checks_summary="3 checks passed",
        can_create_pr=False,
        can_deploy_staging=True,
        blocked_reason=None,
    )


def test_manual_release_task_create_list_and_complete(synced_client, db_session):
    response = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network-growing",
            "project_display_name": "Synapse-Network-Growing",
            "branch_name": "codex/release-task-demo",
            "environment": "staging",
            "actor": "alice",
            "note": "manual staging smoke",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "manual"
    assert payload["status"] == "requested"
    assert payload["deployment_record_id"] is None
    assert payload["service_key"] is None
    assert payload["actor"] == "alice"
    assert payload["operator"] is None

    list_response = synced_client.get("/api/releases/tasks")
    assert list_response.status_code == 200
    assert [item["branch_name"] for item in list_response.json()] == ["codex/release-task-demo"]

    patch_response = synced_client.patch(
        f"/api/releases/tasks/{payload['id']}",
        json={"status": "completed", "operator": "ops-lead", "note": "deployed manually"},
    )

    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert updated["status"] == "completed"
    assert updated["operator"] == "ops-lead"
    assert updated["note"] == "deployed manually"
    assert updated["deployment_record_id"] is not None
    assert updated["deployment_status"] == "succeeded"
    assert updated["deployment_health_status"] == "passed"

    online = synced_client.get("/api/releases/online-records").json()
    assert [item["release_task_id"] for item in online] == [payload["id"]]
    assert online[0]["branch_name"] == "codex/release-task-demo"
    assert online[0]["trigger_source"] == "release_task_manual_completion"
    assert online[0]["health_status"] == "passed"


def test_manual_release_task_terminal_status_updates_linked_deployment(monkeypatch, synced_client, db_session):
    deployment = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        branch_name="codex/stale-deploy",
        actor="operator",
        notes="staging deploy requested",
    )
    db_session.add(deployment)
    db_session.flush()
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="gateway",
        branch_name="codex/stale-deploy",
        environment="staging",
        status="requested",
        actor="operator",
        deployment_record_id=int(deployment.id),
    )
    db_session.add(task)
    db_session.commit()
    monkeypatch.setattr(
        release_tasks_service,
        "_release_task_pr_gate_for",
        lambda row, repo: (_ for _ in ()).throw(AssertionError("manual terminal update must not refresh GitHub PR gate")),
    )

    response = synced_client.patch(
        f"/api/releases/tasks/{int(task.id)}",
        json={"status": "failed", "operator": "ops-lead", "note": "manual deploy failed"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["deployment_status"] == "failed"
    assert payload["deployment_health_status"] == "failed"
    assert payload["deployment_finished_at"] is not None
    assert payload["deployment_failure_summary"] == "manual deploy failed"


def test_release_task_list_caches_pr_gate_by_branch(monkeypatch, synced_client, db_session):
    calls: list[int] = []

    def fake_gate(row, repo):
        assert repo == "SynapseNetworkAI/Synapse-Network"
        calls.append(int(row.id))
        return ReleaseTaskPrGateOut(
            branch_exists=True,
            pr_exists=True,
            pr_url="https://github.com/SynapseNetworkAI/Synapse-Network/pull/27",
            pr_number=27,
            pr_state="merged",
            checks_status="success",
            checks_summary="1 checks passed",
        )

    monkeypatch.setattr(release_tasks_service, "_release_task_pr_gate_for", fake_gate)
    for note in ("first", "second"):
        db_session.add(
            ReleaseTaskRow(
                source_type="manual",
                project_key="synapse-network",
                service_key="gateway",
                branch_name="codex/shared-release-branch",
                environment="staging",
                status="requested",
                actor="operator",
                note=note,
            )
        )
    db_session.commit()

    response = synced_client.get("/api/releases/tasks")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert len(calls) == 1
    assert {item["pr_gate"]["pr_number"] for item in payload} == {27}
    assert all(item["pr_gate"]["can_deploy_staging"] for item in payload)


def test_requirement_flow_release_task_keeps_requirement_and_null_deployment_anchor(synced_client, db_session):
    requirement = RequirementRow(
        title="Release candidate",
        description_markdown="A requirement-generated release task.",
        status="done",
        project_key="synapse-network-growing",
        project_display_name="Synapse-Network-Growing",
        target_project_path="/tmp/release-task",
        acceptance_contract_json='{"execution_acceptance_steps":[]}',
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)

    response = synced_client.post(
        "/api/releases/tasks",
        json={
            "source_type": "requirement_flow",
            "requirement_id": int(requirement.id),
            "project_key": "synapse-network-growing",
            "branch_name": "ops/req-release-candidate",
            "environment": "production",
            "actor": "planner",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "requirement_flow"
    assert payload["requirement_id"] == int(requirement.id)
    assert payload["deployment_record_id"] is None
    assert payload["environment"] == "production"


def test_release_task_rejects_invalid_status_and_terminal_rewrite(synced_client, db_session):
    create_response = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network-growing",
            "branch_name": "codex/release-task-failure",
            "environment": "staging",
        },
    )
    task_id = create_response.json()["id"]

    invalid_response = synced_client.patch(
        f"/api/releases/tasks/{task_id}",
        json={"status": "requested", "operator": "ops-lead"},
    )
    assert invalid_response.status_code == 400

    failed_response = synced_client.patch(
        f"/api/releases/tasks/{task_id}",
        json={"status": "failed", "operator": "ops-lead", "note": "manual deploy failed"},
    )
    assert failed_response.status_code == 200
    assert failed_response.json()["status"] == "failed"

    rewrite_response = synced_client.patch(
        f"/api/releases/tasks/{task_id}",
        json={"status": "completed", "operator": "ops-lead"},
    )
    assert rewrite_response.status_code == 400
    assert "Terminal release task" in rewrite_response.json()["detail"]


def test_release_tasks_do_not_merge_deployment_records(synced_client, db_session):
    requirement = RequirementRow(
        title="Existing deployment",
        description_markdown="Deployment record should not appear in release task list.",
        status="done",
        project_key="synapse-network-growing",
        target_project_path="/tmp/release-task",
        acceptance_contract_json='{"execution_acceptance_steps":[]}',
    )
    db_session.add(requirement)
    db_session.flush()
    db_session.add(
        DeploymentRecordRow(
            requirement_id=int(requirement.id),
            project_key="synapse-network-growing",
            environment="staging",
            action="deploy",
            status="succeeded",
            branch_name="codex/deployment-only",
        )
    )
    db_session.add(
        ReleaseTaskRow(
            source_type="manual",
            project_key="synapse-network-growing",
            branch_name="codex/task-only",
            environment="staging",
            status="requested",
            actor="operator",
        )
    )
    db_session.commit()

    response = synced_client.get("/api/releases/tasks")

    assert response.status_code == 200
    branches = [item["branch_name"] for item in response.json()]
    assert branches == ["codex/task-only"]
    assert "codex/deployment-only" not in branches


def test_online_release_records_only_include_successful_deployments(synced_client, db_session):
    succeeded = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="succeeded",
        branch_name="codex/staging-ok",
        commit_sha="abc123",
        external_url="https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/123",
        health_status="passed",
        metadata_json=json.dumps({"service_key": "gateway", "revision": {"gateway": "gateway-0001"}}),
    )
    failed = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="failed",
        branch_name="codex/staging-failed",
        metadata_json=json.dumps({"service_key": "gateway"}),
    )
    requested = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        branch_name="codex/staging-requested",
        metadata_json=json.dumps({"service_key": "gateway"}),
    )
    db_session.add_all([succeeded, failed, requested])
    db_session.flush()
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="gateway",
        branch_name="codex/staging-ok",
        environment="staging",
        status="completed",
        deployment_record_id=int(succeeded.id),
    )
    db_session.add(task)
    db_session.commit()

    response = synced_client.get("/api/releases/online-records")

    assert response.status_code == 200
    payload = response.json()
    assert [item["branch_name"] for item in payload] == ["codex/staging-ok"]
    assert payload[0]["status"] == "succeeded"
    assert payload[0]["release_task_id"] == int(task.id)
    assert payload[0]["service_key"] == "gateway"
    assert payload[0]["metadata_summary"]["revision"] == {"gateway": "gateway-0001"}


def test_online_release_records_support_environment_project_and_service_filters(synced_client, db_session):
    db_session.add_all(
        [
            DeploymentRecordRow(
                project_key="synapse-network",
                environment="staging",
                action="deploy",
                status="succeeded",
                branch_name="codex/gateway",
                metadata_json=json.dumps({"deployScope": ["gateway"]}),
            ),
            DeploymentRecordRow(
                project_key="synapse-network",
                environment="production",
                action="promote",
                status="succeeded",
                branch_name="main",
                metadata_json=json.dumps({"deployScope": ["gateway"]}),
            ),
            DeploymentRecordRow(
                project_key="synapse-network",
                environment="staging",
                action="deploy",
                status="succeeded",
                branch_name="codex/admin-front",
                metadata_json=json.dumps({"deployScope": ["admin-front"]}),
            ),
            DeploymentRecordRow(
                project_key="synapse-network-provider",
                environment="staging",
                action="deploy",
                status="succeeded",
                branch_name="codex/provider",
                metadata_json=json.dumps({"deployScope": ["provider"]}),
            ),
        ]
    )
    db_session.commit()

    response = synced_client.get(
        "/api/releases/online-records",
        params={"project_key": "synapse-network", "environment": "staging", "service_key": "gateway"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["branch_name"] for item in payload] == ["codex/gateway"]
    assert payload[0]["environment"] == "staging"
    assert payload[0]["service_key"] == "gateway"


def test_release_task_deployment_status_sync_pulls_github_actions_success(monkeypatch, synced_client, db_session):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        branch_name="codex/staging-sync",
        workflow_file="deploy-staging.yml",
        actor="operator",
        trigger_source="release_task",
        metadata_json=json.dumps(
            {
                "release_task_id": 77,
                "service_key": "gateway",
                "deploy_repo_full_name": "SynapseNetworkAI/Synapse-Network",
            }
        ),
    )
    db_session.add(record)
    db_session.flush()
    task = ReleaseTaskRow(
        id=77,
        source_type="manual",
        project_key="synapse-network",
        service_key="gateway",
        branch_name="codex/staging-sync",
        environment="staging",
        status="requested",
        actor="operator",
        deployment_record_id=int(record.id),
    )
    db_session.add(task)
    db_session.commit()

    def fake_gh_json(args, *, timeout=30):
        if args[:2] == ["run", "list"]:
            return (
                "ok",
                [
                    {
                        "databaseId": 249,
                        "status": "completed",
                        "conclusion": "success",
                        "createdAt": "2030-04-25T01:00:00Z",
                        "url": "https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/249",
                        "headSha": "abc123",
                    }
                ],
                "",
            )
        if args[:2] == ["run", "view"]:
            return (
                "ok",
                {
                    "databaseId": 249,
                    "status": "completed",
                    "conclusion": "success",
                    "url": "https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/249",
                    "headSha": "abc123",
                },
                "",
            )
        return "transient_error", None, "unexpected gh call"

    monkeypatch.setattr(release_tasks_service, "_run_gh_json", fake_gh_json)
    monkeypatch.setattr(release_tasks_service, "_run_gh_text", lambda *args, **kwargs: ("transient_error", None, "logs unavailable"))

    response = synced_client.post("/api/releases/tasks/sync-deployment-statuses")

    assert response.status_code == 200
    result = response.json()
    assert result["processed_count"] == 1
    assert result["succeeded_ids"] == [int(record.id)]
    task_payload = synced_client.get("/api/releases/tasks", params={"status": "completed"}).json()[0]
    assert task_payload["id"] == 77
    assert task_payload["deployment_status"] == "succeeded"
    assert task_payload["deployment_external_run_id"] == "249"
    online = synced_client.get("/api/releases/online-records").json()
    assert [item["release_task_id"] for item in online] == [77]
    assert online[0]["external_url"].endswith("/actions/runs/249")


def test_release_task_filters_and_validation_errors(synced_client, db_session):
    synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network-growing",
            "branch_name": "codex/filter-a",
            "environment": "staging",
            "service_key": "gateway",
        },
    )
    synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network-provider",
            "branch_name": "codex/filter-b",
            "environment": "production",
        },
    )
    failed = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network-growing",
            "branch_name": "codex/filter-c",
            "environment": "staging",
        },
    ).json()
    synced_client.patch(f"/api/releases/tasks/{failed['id']}", json={"status": "failed", "operator": "ops"})

    filtered = synced_client.get(
        "/api/releases/tasks",
        params={
            "project_key": "synapse-network-provider",
            "environment": "production",
            "status": "requested",
            "source_type": "manual",
        },
    )
    assert filtered.status_code == 200
    assert [item["branch_name"] for item in filtered.json()] == ["codex/filter-b"]

    assert synced_client.post(
        "/api/releases/tasks",
        json={"source_type": "unknown", "project_key": "x", "branch_name": "b", "environment": "staging"},
    ).status_code == 400
    assert synced_client.post(
        "/api/releases/tasks",
        json={"project_key": "x", "branch_name": "b", "environment": "qa"},
    ).status_code == 400
    assert synced_client.post(
        "/api/releases/tasks",
        json={"branch_name": "b", "environment": "staging"},
    ).status_code == 400
    assert synced_client.post(
        "/api/releases/tasks",
        json={"project_key": "x", "environment": "staging"},
    ).status_code == 400
    assert synced_client.post(
        "/api/releases/tasks",
        json={"project_key": "x", "branch_name": "b", "environment": "staging", "service_key": "unknown"},
    ).status_code == 400
    assert synced_client.post(
        "/api/releases/tasks",
        json={"source_type": "requirement_flow", "requirement_id": 9999, "project_key": "x", "branch_name": "b", "environment": "staging"},
    ).status_code == 400


def test_release_task_update_unknown_id_returns_404(synced_client):
    response = synced_client.patch(
        "/api/releases/tasks/9999",
        json={"status": "completed", "operator": "ops"},
    )

    assert response.status_code == 404


def test_release_task_branch_options_use_github_repo(monkeypatch, synced_client):
    def fake_branch_options(repo_full_name, *, max_records=100):
        assert repo_full_name == "SynapseNetworkAI/Synapse-Network"
        assert max_records == 100
        return [
            release_tasks_service.ReleaseBranchOptionOut(
                name="main",
                commit_sha="abc123",
                protected=True,
                is_default=True,
                source="github",
            ),
            release_tasks_service.ReleaseBranchOptionOut(
                name="codex/release-branch",
                commit_sha="def456",
                protected=False,
                is_default=False,
                source="github",
            ),
        ]

    monkeypatch.setattr(release_tasks_service, "_github_branch_options", fake_branch_options)

    response = synced_client.get(
        "/api/releases/branch-options",
        params={"project_key": "synapse-network", "service_key": "gateway"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["name"] for item in payload] == ["main", "codex/release-branch"]
    assert payload[0]["protected"] is True
    assert payload[0]["source"] == "github"


def test_provider_release_task_branch_options_use_provider_repo(monkeypatch, synced_client, db_session):
    def fake_branch_options(repo_full_name, *, max_records=100):
        assert repo_full_name == "SynapseNetworkAI/Synapse-Network-Provider"
        return [
            release_tasks_service.ReleaseBranchOptionOut(
                name="main",
                commit_sha="provider-main",
                protected=True,
                is_default=True,
                source="github",
            )
        ]

    monkeypatch.setattr(release_tasks_service, "_github_branch_options", fake_branch_options)

    response = synced_client.get(
        "/api/releases/branch-options",
        params={"project_key": "synapse-network-provider", "service_key": "provider-service"},
    )

    assert response.status_code == 200
    assert response.json()[0]["commit_sha"] == "provider-main"

    invalid = synced_client.get(
        "/api/releases/branch-options",
        params={"project_key": "synapse-network-provider", "service_key": "gateway"},
    )
    assert invalid.status_code == 400
    assert "provider-service" in invalid.json()["detail"]


def test_release_task_branch_options_validate_project_and_service(monkeypatch, synced_client):
    assert synced_client.get("/api/releases/branch-options", params={"service_key": "gateway"}).status_code == 422
    assert synced_client.get(
        "/api/releases/branch-options",
        params={"project_key": "synapse-network", "service_key": "unknown"},
    ).status_code == 400
    assert synced_client.get(
        "/api/releases/branch-options",
        params={"project_key": "unknown-project", "service_key": "gateway"},
    ).status_code == 400

    def empty_branch_options(repo_full_name, *, max_records=100):
        return []

    monkeypatch.setattr(release_tasks_service, "_github_branch_options", empty_branch_options)
    assert synced_client.get(
        "/api/releases/branch-options",
        params={"project_key": "synapse-network", "service_key": "gateway"},
    ).status_code == 400


def test_github_branch_options_parse_sort_and_e2e_mode(monkeypatch):
    monkeypatch.setattr(release_tasks_service.config, "E2E_MODE", False)

    def fake_run(command, capture_output, text, timeout, check):
        assert command == ["gh", "api", "repos/example/repo/branches?per_page=2"]
        assert capture_output is True
        assert text is True
        assert timeout == 20
        assert check is False
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                [
                    {"name": "codex/feature", "commit": {"sha": "def"}, "protected": False},
                    {"name": "", "commit": {"sha": "ignored"}, "protected": False},
                    "bad-item",
                    {"name": "main", "commit": {"sha": "abc"}, "protected": True},
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr(release_tasks_service.subprocess, "run", fake_run)

    options = release_tasks_service._github_branch_options("example/repo", max_records=2)

    assert [item.name for item in options] == ["codex/feature"]
    assert options[0].commit_sha == "def"
    assert options[0].source == "github"

    monkeypatch.setattr(release_tasks_service.config, "E2E_MODE", True)
    e2e_options = release_tasks_service._github_branch_options("example/repo")
    assert [item.name for item in e2e_options][:2] == ["main", "codex/e2e-staging-release-task"]
    assert e2e_options[0].source == "e2e"


def test_github_branch_options_fail_closed(monkeypatch):
    monkeypatch.setattr(release_tasks_service.config, "E2E_MODE", False)

    def missing_gh(*args, **kwargs):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(release_tasks_service.subprocess, "run", missing_gh)
    try:
        release_tasks_service._github_branch_options("example/repo")
        assert False, "Expected missing gh to fail closed"
    except ValueError as exc:
        assert "GitHub CLI" in str(exc)

    def timeout_gh(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["gh"], timeout=20)

    monkeypatch.setattr(release_tasks_service.subprocess, "run", timeout_gh)
    try:
        release_tasks_service._github_branch_options("example/repo")
        assert False, "Expected timeout to fail closed"
    except ValueError as exc:
        assert "Timed out" in str(exc)

    def failed_gh(command, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="line1\nline2\n" + ("x" * 700))

    monkeypatch.setattr(release_tasks_service.subprocess, "run", failed_gh)
    try:
        release_tasks_service._github_branch_options("example/repo")
        assert False, "Expected non-zero gh to fail closed"
    except ValueError as exc:
        message = str(exc)
        assert "Failed to load GitHub branch options" in message
        assert "[Truncated]" in message

    def invalid_json(command, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(command, 0, stdout="{", stderr="")

    monkeypatch.setattr(release_tasks_service.subprocess, "run", invalid_json)
    try:
        release_tasks_service._github_branch_options("example/repo")
        assert False, "Expected invalid JSON to fail closed"
    except ValueError as exc:
        assert "not valid JSON" in str(exc)

    def object_json(command, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(command, 0, stdout='{"name":"main"}', stderr="")

    monkeypatch.setattr(release_tasks_service.subprocess, "run", object_json)
    try:
        release_tasks_service._github_branch_options("example/repo")
        assert False, "Expected non-list JSON to fail closed"
    except ValueError as exc:
        assert "not a list" in str(exc)


def test_release_task_pr_gate_helper_classifies_github_and_checks(monkeypatch):
    monkeypatch.setattr(release_tasks_service.config, "E2E_MODE", False)
    calls = []

    def fake_run(command, capture_output, text, timeout, check, env):
        calls.append(command)
        if command[1] == "api":
            return subprocess.CompletedProcess(command, 0, stdout='{"name":"codex/ok"}', stderr="")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                [
                    {
                        "number": 12,
                        "url": "https://github.com/SynapseNetworkAI/Synapse-Network/pull/12",
                        "state": "OPEN",
                        "isDraft": False,
                        "statusCheckRollup": [
                            {"conclusion": "SUCCESS"},
                            {"status": "SUCCESS"},
                        ],
                    }
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr(release_tasks_service.subprocess, "run", fake_run)
    row = ReleaseTaskRow(
        project_key="synapse-network",
        branch_name="codex/ok",
        environment="staging",
        status="requested",
    )

    gate = release_tasks_service._release_task_pr_gate_for(row, "SynapseNetworkAI/Synapse-Network")

    assert gate.branch_exists is True
    assert gate.pr_exists is True
    assert gate.pr_number == 12
    assert gate.checks_status == "success"
    assert gate.can_deploy_staging is True
    assert calls[0][2].endswith("/codex%2Fok")


def test_release_task_pr_gate_accepts_merged_pr_with_green_checks(monkeypatch):
    monkeypatch.setattr(release_tasks_service.config, "E2E_MODE", False)

    def merged_pr(command, capture_output, text, timeout, check, env):
        if command[1] == "api":
            return subprocess.CompletedProcess(command, 0, stdout='{"name":"codex/merged"}', stderr="")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                [
                    {
                        "number": 26,
                        "url": "https://github.com/example/repo/pull/26",
                        "state": "MERGED",
                        "isDraft": False,
                        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
                    }
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr(release_tasks_service.subprocess, "run", merged_pr)
    row = ReleaseTaskRow(branch_name="codex/merged", environment="staging", status="requested")

    gate = release_tasks_service._release_task_pr_gate_for(row, "example/repo")

    assert gate.pr_exists is True
    assert gate.pr_state == "merged"
    assert gate.checks_status == "success"
    assert gate.can_deploy_staging is True


def test_release_task_pr_gate_allows_main_direct_staging_without_pr(monkeypatch):
    monkeypatch.setattr(release_tasks_service.config, "E2E_MODE", False)

    def branch_only(command, capture_output, text, timeout, check, env):
        assert command[1] == "api"
        return subprocess.CompletedProcess(command, 0, stdout='{"name":"main"}', stderr="")

    monkeypatch.setattr(release_tasks_service.subprocess, "run", branch_only)
    row = ReleaseTaskRow(branch_name="main", environment="staging", status="requested")

    gate = release_tasks_service._release_task_pr_gate_for(row, "example/repo")

    assert gate.branch_exists is True
    assert gate.pr_exists is False
    assert gate.pr_state == "main"
    assert gate.checks_status == "success"
    assert gate.checks_summary == "main 分支可直接发布 staging，不需要 PR gate。"
    assert gate.can_create_pr is False
    assert gate.can_deploy_staging is True


def test_release_task_pr_gate_helper_blocks_missing_branch_and_missing_pr(monkeypatch):
    monkeypatch.setattr(release_tasks_service.config, "E2E_MODE", False)

    def missing_branch(command, capture_output, text, timeout, check, env):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="HTTP 404 Not Found")

    monkeypatch.setattr(release_tasks_service.subprocess, "run", missing_branch)
    row = ReleaseTaskRow(branch_name="codex/missing", environment="staging", status="requested")

    missing_gate = release_tasks_service._release_task_pr_gate_for(row, "example/repo")

    assert missing_gate.branch_exists is False
    assert "分支不存在" in missing_gate.blocked_reason

    def no_pr(command, capture_output, text, timeout, check, env):
        if command[1] == "api":
            return subprocess.CompletedProcess(command, 0, stdout='{"name":"codex/no-pr"}', stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")

    monkeypatch.setattr(release_tasks_service.subprocess, "run", no_pr)
    row.branch_name = "codex/no-pr"

    no_pr_gate = release_tasks_service._release_task_pr_gate_for(row, "example/repo")

    assert no_pr_gate.branch_exists is True
    assert no_pr_gate.pr_exists is False
    assert no_pr_gate.can_create_pr is True
    assert no_pr_gate.can_deploy_staging is False


def test_release_task_pr_gate_helper_classifies_pending_failed_unknown_and_draft(monkeypatch):
    assert release_tasks_service._checks_summary([]) == ("unknown", "PR checks 状态未知")
    assert release_tasks_service._checks_summary([{"status": "IN_PROGRESS"}, {"conclusion": "SUCCESS"}])[0] == "pending"
    assert release_tasks_service._checks_summary([{"conclusion": "FAILURE"}, {"status": "SUCCESS"}])[0] == "failed"

    monkeypatch.setattr(release_tasks_service.config, "E2E_MODE", False)

    def draft_pr(command, capture_output, text, timeout, check, env):
        if command[1] == "api":
            return subprocess.CompletedProcess(command, 0, stdout='{"name":"codex/draft"}', stderr="")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                [
                    {
                        "number": 13,
                        "url": "https://github.com/example/repo/pull/13",
                        "state": "OPEN",
                        "isDraft": True,
                        "statusCheckRollup": [{"status": "IN_PROGRESS"}],
                    }
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr(release_tasks_service.subprocess, "run", draft_pr)
    row = ReleaseTaskRow(branch_name="codex/draft", environment="staging", status="requested")

    gate = release_tasks_service._release_task_pr_gate_for(row, "example/repo")

    assert gate.pr_state == "draft"
    assert gate.checks_status == "pending"
    assert gate.can_deploy_staging is False

    def draft_green_pr(command, capture_output, text, timeout, check, env):
        if command[1] == "api":
            return subprocess.CompletedProcess(command, 0, stdout='{"name":"codex/draft"}', stderr="")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                [
                    {
                        "number": 14,
                        "url": "https://github.com/example/repo/pull/14",
                        "state": "OPEN",
                        "isDraft": True,
                        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
                    }
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr(release_tasks_service.subprocess, "run", draft_green_pr)
    draft_green_gate = release_tasks_service._release_task_pr_gate_for(row, "example/repo")

    assert draft_green_gate.pr_state == "draft"
    assert draft_green_gate.checks_status == "success"
    assert draft_green_gate.can_deploy_staging is False
    assert "Draft" in draft_green_gate.blocked_reason


def test_run_gh_json_classifies_errors(monkeypatch):
    def missing_gh(*args, **kwargs):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(release_tasks_service.subprocess, "run", missing_gh)
    assert release_tasks_service._run_gh_json(["api", "x"])[0] == "transient_error"

    def timeout_gh(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["gh"], timeout=30)

    monkeypatch.setattr(release_tasks_service.subprocess, "run", timeout_gh)
    assert release_tasks_service._run_gh_json(["api", "x"])[2] == "GitHub CLI request timed out."

    def failed(command, capture_output, text, timeout, check, env):
        stderr = {
            "not-found": "HTTP 404 Not Found",
            "auth": "HTTP 403 permission denied",
            "bad-json": "",
            "other": "boom",
        }[command[-1]]
        stdout = "{" if command[-1] == "bad-json" else ""
        return subprocess.CompletedProcess(command, 0 if command[-1] == "bad-json" else 1, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(release_tasks_service.subprocess, "run", failed)
    assert release_tasks_service._run_gh_json(["api", "not-found"])[0] == "not_found"
    assert release_tasks_service._run_gh_json(["api", "auth"])[0] == "auth_error"
    assert release_tasks_service._run_gh_json(["api", "other"])[0] == "transient_error"
    assert release_tasks_service._run_gh_json(["api", "bad-json"])[0] == "transient_error"


def test_run_gh_text_classifies_errors(monkeypatch):
    def ok_run(command, capture_output, text, timeout, check, env):
        return subprocess.CompletedProcess(command, 0, stdout="plain log", stderr="")

    monkeypatch.setattr(release_tasks_service.subprocess, "run", ok_run)
    assert release_tasks_service._run_gh_text(["run", "view"])[1] == "plain log"

    def failed_run(command, capture_output, text, timeout, check, env):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="boom")

    monkeypatch.setattr(release_tasks_service.subprocess, "run", failed_run)
    assert release_tasks_service._run_gh_text(["run", "view"])[0] == "transient_error"

    monkeypatch.setattr(release_tasks_service.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("gh")))
    assert "GitHub CLI" in release_tasks_service._run_gh_text(["run"])[2]

    monkeypatch.setattr(
        release_tasks_service.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd=["gh"], timeout=1)),
    )
    assert release_tasks_service._run_gh_text(["run"])[2] == "GitHub CLI request timed out."


def test_github_actions_sync_helpers_cover_edges(monkeypatch, db_session):
    assert release_tasks_service._github_actions_run_id_from_url("https://github.com/o/r/actions/runs/123") == "123"
    assert release_tasks_service._github_actions_run_id_from_url("https://github.com/o/r/actions/workflows/x.yml") is None
    assert release_tasks_service._parse_github_timestamp("") is None
    assert release_tasks_service._parse_github_timestamp("bad") is None
    assert release_tasks_service._as_utc(None) is None
    assert release_tasks_service._as_utc(datetime(2026, 4, 25, 1, 0, 0, tzinfo=timezone.utc)).tzinfo is not None

    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        branch_name="codex/match",
        workflow_file="deploy-staging.yml",
        trigger_source="release_task",
        metadata_json=json.dumps({"service_key": "gateway", "deploy_repo_full_name": "example/repo"}),
        started_at=datetime(2026, 4, 25, 1, 0, 0),
    )
    db_session.add(record)
    db_session.flush()

    monkeypatch.setattr(release_tasks_service, "_run_gh_json", lambda *args, **kwargs: ("transient_error", None, "no list"))
    assert release_tasks_service._find_recent_actions_run_id("example/repo", record, {}) is None

    def list_with_noise(args, *, timeout=30):
        return (
            "ok",
            [
                "bad",
                {"createdAt": "2026-04-25T00:00:00Z", "databaseId": 1},
                {"createdAt": "2026-04-25T00:59:00Z", "databaseId": 99},
                {"createdAt": "bad", "databaseId": None},
                {"createdAt": "2026-04-25T01:01:00Z", "databaseId": 2},
            ],
            "",
        )

    monkeypatch.setattr(release_tasks_service, "_run_gh_json", list_with_noise)
    monkeypatch.setattr(release_tasks_service, "_run_gh_text", lambda *args, **kwargs: ("ok", "SOURCE codex/match gateway", ""))
    assert release_tasks_service._find_recent_actions_run_id("example/repo", record, {"service_key": "gateway"}) == "2"

    monkeypatch.setattr(release_tasks_service, "_run_gh_json", lambda *args, **kwargs: ("auth_error", None, "no auth"))
    assert release_tasks_service._github_actions_run_view("example/repo", "2") == (None, "no auth")


def test_apply_github_run_to_deployment_handles_running_failed_and_pending(db_session):
    running = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        trigger_source="release_task",
    )
    failed = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        trigger_source="release_task",
    )
    pending = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        trigger_source="release_task",
    )
    db_session.add_all([running, failed, pending])
    db_session.flush()
    running_task = ReleaseTaskRow(source_type="manual", project_key="synapse-network", branch_name="codex/running", environment="staging", status="requested", deployment_record_id=int(running.id))
    failed_task = ReleaseTaskRow(source_type="manual", project_key="synapse-network", branch_name="codex/failed", environment="staging", status="requested", deployment_record_id=int(failed.id))
    pending_task = ReleaseTaskRow(source_type="manual", project_key="synapse-network", branch_name="codex/pending", environment="staging", status="requested", deployment_record_id=int(pending.id))
    db_session.add_all([running_task, failed_task, pending_task])
    db_session.commit()

    assert release_tasks_service._apply_github_run_to_deployment(db_session, running, run_payload={"status": "in_progress"}, run_id="1") == "running"
    assert running.status == "running"
    assert running_task.status == "deploying"
    assert release_tasks_service._apply_github_run_to_deployment(db_session, failed, run_payload={"status": "completed", "conclusion": "failure"}, run_id="2") == "failed"
    assert failed.status == "failed"
    assert release_tasks_service._apply_github_run_to_deployment(db_session, pending, run_payload={"status": "completed", "conclusion": ""}, run_id="3") == "pending"
    assert pending.status == "requested"
    assert pending_task.status == "deploying"


def test_release_task_deployment_status_sync_handles_missing_run_and_view_errors(monkeypatch, db_session):
    missing_repo = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        trigger_source="release_task",
        metadata_json="{}",
    )
    missing_run = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        trigger_source="release_task",
        metadata_json=json.dumps({"deploy_repo_full_name": "example/repo"}),
    )
    view_error = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        external_url="https://github.com/example/repo/actions/runs/55",
        trigger_source="release_task",
        metadata_json=json.dumps({"deploy_repo_full_name": "example/repo"}),
    )
    db_session.add_all([missing_repo, missing_run, view_error])
    db_session.flush()
    missing_run_task = ReleaseTaskRow(source_type="manual", project_key="synapse-network", branch_name="main", environment="staging", status="requested", deployment_record_id=int(missing_run.id))
    db_session.add(missing_run_task)
    db_session.commit()

    monkeypatch.setattr(release_tasks_service, "_find_recent_actions_run_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(release_tasks_service, "_github_actions_run_view", lambda *args, **kwargs: (None, "boom"))

    result = release_tasks_service.sync_release_task_deployment_statuses(db_session)

    assert result["processed_count"] == 3
    assert int(missing_repo.id) in result["error_ids"]
    assert int(missing_run.id) in result["pending_ids"]
    assert int(view_error.id) in result["error_ids"]
    assert missing_run_task.status == "deploying"


def test_release_task_deployment_status_sync_handles_missing_repo_and_terminal_record(monkeypatch, db_session):
    missing_repo = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        trigger_source="release_task",
        metadata_json="{}",
    )
    terminal = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="succeeded",
        trigger_source="release_task",
        metadata_json=json.dumps({"deploy_repo_full_name": "example/repo"}),
    )
    odd_status = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="paused",
        trigger_source="release_task",
        metadata_json=json.dumps({"deploy_repo_full_name": "example/repo"}),
    )
    db_session.add_all([missing_repo, terminal, odd_status])
    db_session.commit()

    result = release_tasks_service.sync_release_task_deployment_statuses(db_session)

    assert int(missing_repo.id) in result["error_ids"]
    assert int(terminal.id) not in result["error_ids"]
    assert int(odd_status.id) not in result["error_ids"]
    db_session.refresh(missing_repo)
    assert "missing deploy_repo_full_name" in (missing_repo.notes or "")


def test_release_task_deployment_age_handles_empty_and_naive_timestamps():
    record = DeploymentRecordRow(project_key="synapse-network", environment="staging", action="deploy")
    record.started_at = None
    record.created_at = None
    assert release_tasks_service._deployment_age_seconds(record, now=datetime.now(timezone.utc)) == 0.0

    record.started_at = datetime(2030, 1, 1, 0, 0, 0)
    now = datetime(2030, 1, 1, 0, 1, 0, tzinfo=timezone.utc)
    assert release_tasks_service._deployment_age_seconds(record, now=now) == 60.0


def test_release_task_deployment_status_sync_is_terminal_safe(monkeypatch, db_session):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        trigger_source="release_task",
        metadata_json=json.dumps({"deploy_repo_full_name": "example/repo"}),
    )
    db_session.add(record)
    db_session.flush()
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        environment="staging",
        status="completed",
        actor="operator",
        deployment_record_id=int(record.id),
    )
    db_session.add(task)
    db_session.commit()

    monkeypatch.setattr(release_tasks_service, "_find_recent_actions_run_id", lambda *args, **kwargs: "99")
    monkeypatch.setattr(
        release_tasks_service,
        "_github_actions_run_view",
        lambda *args, **kwargs: (
            {
                "databaseId": 99,
                "status": "completed",
                "conclusion": "success",
                "url": "https://github.com/example/repo/actions/runs/99",
                "headSha": "abc123",
            },
            None,
        ),
    )

    result = release_tasks_service.sync_release_task_deployment_statuses(db_session)

    assert result["processed_count"] == 0
    assert int(record.id) in result["skipped_terminal_ids"]
    db_session.refresh(record)
    db_session.refresh(task)
    assert record.status == "requested"
    assert task.status == "completed"


def test_release_task_deployment_apply_skips_terminal_record(db_session):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="succeeded",
        trigger_source="release_task",
        metadata_json=json.dumps({"deploy_repo_full_name": "example/repo"}),
    )
    db_session.add(record)
    db_session.commit()

    state = release_tasks_service._apply_github_run_to_deployment(
        db_session,
        record,
        run_payload={
            "databaseId": 99,
            "status": "in_progress",
            "conclusion": "",
            "url": "https://github.com/example/repo/actions/runs/99",
            "headSha": "abc123",
        },
        run_id="99",
    )

    assert state == "succeeded"
    assert record.status == "succeeded"


def test_release_task_deployment_status_sync_marks_removed_run_failed(monkeypatch, db_session):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        external_run_id="55",
        trigger_source="release_task",
        metadata_json=json.dumps({"deploy_repo_full_name": "example/repo"}),
    )
    db_session.add(record)
    db_session.flush()
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        environment="staging",
        status="requested",
        actor="operator",
        deployment_record_id=int(record.id),
    )
    db_session.add(task)
    db_session.commit()

    monkeypatch.setattr(
        release_tasks_service,
        "_github_actions_run_view",
        lambda *args, **kwargs: (None, "GitHub resource was not found."),
    )

    result = release_tasks_service.sync_release_task_deployment_statuses(db_session)

    assert int(record.id) in result["failed_ids"]
    assert int(record.id) in result["removed_run_ids"]
    db_session.refresh(record)
    db_session.refresh(task)
    assert record.status == "failed"
    assert task.status == "failed"
    assert "manual deletion detected" in (record.notes or "")
    assert json.loads(record.metadata_json)["deploymentSyncFailureKind"] == "run_removed_from_source"


def test_release_task_deployment_status_sync_times_out_missing_run_id(monkeypatch, db_session):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        trigger_source="release_task",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=20),
        metadata_json=json.dumps({"deploy_repo_full_name": "example/repo"}),
    )
    db_session.add(record)
    db_session.commit()
    monkeypatch.setattr(release_tasks_service.config, "RELEASE_DEPLOYMENT_PENDING_RUN_ID_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(release_tasks_service, "_find_recent_actions_run_id", lambda *args, **kwargs: None)

    result = release_tasks_service.sync_release_task_deployment_statuses(db_session)

    assert int(record.id) in result["failed_ids"]
    assert int(record.id) in result["timeout_ids"]
    db_session.refresh(record)
    assert record.status == "failed"
    assert "run id not found" in (record.notes or "")


def test_release_task_deployment_status_sync_times_out_running_run(monkeypatch, db_session):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="running",
        external_run_id="101",
        trigger_source="release_task",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=40),
        metadata_json=json.dumps({"deploy_repo_full_name": "example/repo"}),
    )
    db_session.add(record)
    db_session.commit()
    monkeypatch.setattr(release_tasks_service.config, "RELEASE_DEPLOYMENT_RUNNING_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(
        release_tasks_service,
        "_github_actions_run_view",
        lambda *args, **kwargs: (
            {
                "databaseId": 101,
                "status": "in_progress",
                "conclusion": "",
                "url": "https://github.com/example/repo/actions/runs/101",
                "headSha": "abc123",
            },
            None,
        ),
    )

    result = release_tasks_service.sync_release_task_deployment_statuses(db_session)

    assert int(record.id) in result["failed_ids"]
    db_session.refresh(record)
    assert record.status == "failed"
    assert "still running" in (record.notes or "")


def test_release_task_pr_gate_projects_branch_pr_and_checks(monkeypatch, synced_client, db_session):
    def fake_gate(row, repo):
        assert repo == "SynapseNetworkAI/Synapse-Network"
        assert row.branch_name == "codex/pr-gated-staging"
        return ReleaseTaskPrGateOut(
            branch_exists=True,
            pr_exists=True,
            pr_url="https://github.com/SynapseNetworkAI/Synapse-Network/pull/88",
            pr_number=88,
            pr_state="open",
            checks_status="success",
            checks_summary="4 checks passed",
            can_deploy_staging=True,
        )

    monkeypatch.setattr(release_tasks_service, "_release_task_pr_gate_for", fake_gate)
    synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "gateway",
            "branch_name": "codex/pr-gated-staging",
            "environment": "staging",
        },
    )

    payload = synced_client.get("/api/releases/tasks").json()[0]

    assert payload["pr_gate"]["branch_exists"] is True
    assert payload["pr_gate"]["pr_exists"] is True
    assert payload["pr_gate"]["checks_status"] == "success"
    assert payload["pr_gate"]["can_deploy_staging"] is True


def test_release_task_create_pr_requires_branch_and_returns_pending_gate(monkeypatch, synced_client, db_session):
    def fake_gate(row, repo):
        return ReleaseTaskPrGateOut(
            branch_exists=True,
            pr_exists=False,
            can_create_pr=True,
            blocked_reason="未提交 PR",
        )

    def fake_run(command, capture_output, text, timeout, check, env):
        assert command[:4] == ["gh", "pr", "create", "--repo"]
        assert "--base" in command and "main" in command
        assert "--head" in command and "codex/no-pr-yet" in command
        return subprocess.CompletedProcess(command, 0, stdout="https://github.com/SynapseNetworkAI/Synapse-Network/pull/77\n", stderr="")

    monkeypatch.setattr(release_tasks_service, "_release_task_pr_gate_for", fake_gate)
    monkeypatch.setattr(release_tasks_service.subprocess, "run", fake_run)
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "gateway",
            "branch_name": "codex/no-pr-yet",
            "environment": "staging",
        },
    ).json()

    response = synced_client.post(f"/api/releases/tasks/{task['id']}/create-pr", json={"actor": "operator"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["pr_gate"]["pr_exists"] is True
    assert payload["pr_gate"]["checks_status"] == "pending"
    assert payload["pr_gate"]["pr_url"].endswith("/pull/77")


def test_release_task_create_pr_is_idempotent_and_fails_missing_branch(monkeypatch, synced_client, db_session):
    existing_gate = ReleaseTaskPrGateOut(
        branch_exists=True,
        pr_exists=True,
        pr_url="https://github.com/SynapseNetworkAI/Synapse-Network/pull/78",
        pr_number=78,
        pr_state="open",
        checks_status="pending",
        checks_summary="1 pending",
        can_create_pr=False,
        can_deploy_staging=False,
        blocked_reason="1 pending",
    )
    monkeypatch.setattr(release_tasks_service, "_release_task_pr_gate_for", lambda row, repo: existing_gate)
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "gateway",
            "branch_name": "codex/existing-pr",
            "environment": "staging",
        },
    ).json()

    existing = synced_client.post(f"/api/releases/tasks/{task['id']}/create-pr", json={})

    assert existing.status_code == 200
    assert existing.json()["pr_gate"]["pr_number"] == 78

    missing_gate = ReleaseTaskPrGateOut(branch_exists=False, blocked_reason="分支不存在，请重新选择有效远端分支")
    monkeypatch.setattr(release_tasks_service, "_release_task_pr_gate_for", lambda row, repo: missing_gate)
    missing = synced_client.post(f"/api/releases/tasks/{task['id']}/create-pr", json={})

    assert missing.status_code == 400
    assert "分支不存在" in missing.json()["detail"]


def test_release_task_create_pr_records_gh_failures(monkeypatch, synced_client, db_session):
    monkeypatch.setattr(
        release_tasks_service,
        "_release_task_pr_gate_for",
        lambda row, repo: ReleaseTaskPrGateOut(branch_exists=True, pr_exists=False, can_create_pr=True),
    )
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "gateway",
            "branch_name": "codex/pr-create-fails",
            "environment": "staging",
        },
    ).json()

    def failed_run(command, capture_output, text, timeout, check, env):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="cannot create pr")

    monkeypatch.setattr(release_tasks_service.subprocess, "run", failed_run)

    response = synced_client.post(f"/api/releases/tasks/{task['id']}/create-pr", json={})

    assert response.status_code == 400
    assert "cannot create pr" in response.json()["detail"]
    assert synced_client.post("/api/releases/tasks/9999/create-pr", json={}).status_code == 404


def test_release_task_staging_deploy_requires_successful_pr_gate(monkeypatch, synced_client, db_session):
    monkeypatch.setattr(
        release_tasks_service,
        "_release_task_pr_gate_for",
        lambda row, repo: ReleaseTaskPrGateOut(
            branch_exists=True,
            pr_exists=True,
            pr_url="https://github.com/SynapseNetworkAI/Synapse-Network/pull/10",
            pr_number=10,
            pr_state="open",
            checks_status="failed",
            checks_summary="1 failed, 2 passed",
            can_deploy_staging=False,
            blocked_reason="1 failed, 2 passed",
        ),
    )
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "gateway",
            "branch_name": "codex/checks-failed",
            "environment": "staging",
        },
    ).json()

    response = synced_client.post(f"/api/releases/tasks/{task['id']}/deploy-staging", json={})

    assert response.status_code == 400
    assert "1 failed" in response.json()["detail"]


def test_release_task_staging_deploy_dispatches_workflow_and_links_deployment(monkeypatch, synced_client, db_session):
    calls = []

    def fake_dispatch(**kwargs):
        calls.append(kwargs)
        return "https://github.com/SynapseNetworkAI/Synapse-Network/actions/workflows/deploy-staging-gateway.yml"

    monkeypatch.setattr(release_tasks_service, "_dispatch_github_workflow", fake_dispatch)
    monkeypatch.setattr(release_tasks_service, "_callback_url", lambda record_id: f"https://ops.example/api/deployments/{record_id}/report")
    monkeypatch.setattr(release_tasks_service, "_release_task_pr_gate_for", lambda row, repo: _successful_pr_gate())
    monkeypatch.setattr(release_tasks_service, "_missing_required_staging_deploy_secrets", lambda repo, **kwargs: ([], None))

    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "gateway",
            "branch_name": "codex/staging-gateway",
            "environment": "staging",
        },
    ).json()

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        json={"actor": "ops-lead", "note": "ship gateway staging"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "deploying"
    assert payload["operator"] == "ops-lead"
    assert payload["deployment_record_id"] is not None
    assert payload["deployment_status"] == "requested"
    assert calls[0]["repo_full_name"] == "SynapseNetworkAI/Synapse-Network"
    assert calls[0]["workflow_file"] == "deploy-staging-gateway.yml"
    assert calls[0]["ref"] == "main"
    assert calls[0]["inputs"]["deploy_scope"] == "gateway"
    assert calls[0]["inputs"]["source_ref"] == "codex/staging-gateway"


def test_provider_release_task_staging_deploy_dispatches_provider_workflow(monkeypatch, synced_client, db_session):
    calls = []
    secret_checks = []

    def fake_dispatch(**kwargs):
        calls.append(kwargs)
        return "https://github.com/SynapseNetworkAI/Synapse-Network-Provider/actions/workflows/deploy-staging.yml"

    def fake_secret_check(repo, **kwargs):
        secret_checks.append((repo, kwargs.get("project_key")))
        return [], None

    monkeypatch.setattr(release_tasks_service, "_dispatch_github_workflow", fake_dispatch)
    monkeypatch.setattr(release_tasks_service, "_callback_url", lambda record_id: f"https://ops.example/api/deployments/{record_id}/report")
    monkeypatch.setattr(release_tasks_service, "_release_task_pr_gate_for", lambda row, repo: _successful_pr_gate())
    monkeypatch.setattr(release_tasks_service, "_missing_required_staging_deploy_secrets", fake_secret_check)

    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network-provider",
            "project_display_name": "Synapse-Network-Provider",
            "service_key": "provider-service",
            "branch_name": "codex/provider-staging",
            "environment": "staging",
        },
    ).json()

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        json={"actor": "ops-lead", "note": "ship provider staging"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deployment_record_id"] is not None
    assert secret_checks == [("SynapseNetworkAI/Synapse-Network-Provider", "synapse-network-provider")]
    assert calls[0]["repo_full_name"] == "SynapseNetworkAI/Synapse-Network-Provider"
    assert calls[0]["workflow_file"] == "deploy-staging.yml"
    assert calls[0]["inputs"]["deploy_scope"] == "provider-service"
    assert calls[0]["inputs"]["source_ref"] == "codex/provider-staging"

    deployment = db_session.get(DeploymentRecordRow, payload["deployment_record_id"])
    metadata = json.loads(deployment.metadata_json)
    assert metadata["deploy_strategy"] == "github_actions_wif_cloudrun"
    assert metadata["service_key"] == "provider-service"
    assert metadata["controlledSteps"] == [
        "checkout",
        "resolve_ref",
        "wif_auth",
        "cloud_build",
        "artifact_push",
        "cloud_run_deploy",
        "health_check",
    ]
    assert metadata["cloud_run_service"] == "synapse-staging-provider"


def test_release_task_staging_deploy_blocks_missing_github_auth_secrets(monkeypatch, synced_client, db_session):
    calls = []
    monkeypatch.setattr(release_tasks_service, "_dispatch_github_workflow", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(release_tasks_service, "_release_task_pr_gate_for", lambda row, repo: _successful_pr_gate())
    monkeypatch.setattr(
        release_tasks_service,
        "_missing_required_staging_deploy_secrets",
        lambda repo, **kwargs: (["GCP_DEPLOY_SERVICE_ACCOUNT", "GCP_WORKLOAD_IDENTITY_PROVIDER"], None),
    )
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "gateway",
            "branch_name": "codex/staging-missing-secrets",
            "environment": "staging",
        },
    ).json()

    response = synced_client.post(f"/api/releases/tasks/{task['id']}/deploy-staging", json={})

    assert response.status_code == 400
    assert "missing GitHub secrets" in response.json()["detail"]
    assert "GCP_WORKLOAD_IDENTITY_PROVIDER" in response.json()["detail"]
    assert calls == []


def test_release_task_staging_secret_preflight_helper(monkeypatch):
    monkeypatch.setattr(
        release_tasks_service,
        "_run_gh_json",
        lambda *args, **kwargs: (
            "ok",
            [{"name": "GCP_WORKLOAD_IDENTITY_PROVIDER"}, {"name": "UNRELATED"}],
            "",
        ),
    )

    missing, error = release_tasks_service._missing_required_staging_deploy_secrets("example/repo")

    assert missing == ["GCP_DEPLOY_SERVICE_ACCOUNT"]
    assert error is None

    monkeypatch.setattr(release_tasks_service, "_run_gh_json", lambda *args, **kwargs: ("ok", {}, ""))
    missing, error = release_tasks_service._missing_required_staging_deploy_secrets("example/repo")
    assert missing == ["GCP_DEPLOY_SERVICE_ACCOUNT", "GCP_WORKLOAD_IDENTITY_PROVIDER"]
    assert "not valid" in error

    monkeypatch.setattr(release_tasks_service, "_run_gh_json", lambda *args, **kwargs: ("auth_error", None, "no auth"))
    missing, error = release_tasks_service._missing_required_staging_deploy_secrets("example/repo")
    assert missing == ["GCP_DEPLOY_SERVICE_ACCOUNT", "GCP_WORKLOAD_IDENTITY_PROVIDER"]
    assert error == "no auth"

    monkeypatch.setattr(release_tasks_service.config, "E2E_MODE", True)
    assert release_tasks_service._missing_required_staging_deploy_secrets("example/repo") == ([], None)


def test_provider_release_task_staging_secret_preflight_uses_wif_secrets(monkeypatch):
    monkeypatch.setattr(release_tasks_service.config, "E2E_MODE", False)
    monkeypatch.setattr(
        release_tasks_service,
        "_run_gh_json",
        lambda *args, **kwargs: (
            "ok",
            [{"name": "GCP_WORKLOAD_IDENTITY_PROVIDER"}],
            "",
        ),
    )

    missing, error = release_tasks_service._missing_required_staging_deploy_secrets(
        "SynapseNetworkAI/Synapse-Network-Provider",
        project_key="synapse-network-provider",
    )

    assert missing == [
        "GCP_DEPLOY_SERVICE_ACCOUNT",
        "STAGING_ARTIFACT_REGISTRY_REPOSITORY",
        "STAGING_EVIDENCE_BUCKET",
        "STAGING_GCP_PROJECT_ID",
        "STAGING_GCP_REGION",
    ]
    assert error is None


def test_release_task_pr_gate_helper_edges(monkeypatch):
    assert release_tasks_service._checks_summary([object(), {"status": "WEIRD"}]) == (
        "pending",
        "1 pending, 0 passed",
    )
    assert release_tasks_service._checks_summary([object()]) == ("unknown", "PR checks 状态未知")

    monkeypatch.setattr(release_tasks_service.config, "E2E_MODE", True)
    assert release_tasks_service._github_branch_exists("example/repo", "main") == (True, None)
    assert release_tasks_service._github_pr_for_branch("example/repo", "main") == (None, None)

    monkeypatch.setattr(release_tasks_service.config, "E2E_MODE", False)
    monkeypatch.setattr(release_tasks_service, "_run_gh_json", lambda *args, **kwargs: ("transient_error", None, "boom"))
    assert release_tasks_service._github_branch_exists("example/repo", "missing") == (False, "boom")
    assert release_tasks_service._github_pr_for_branch("example/repo", "missing") == (None, "boom")


def test_release_task_staging_deploy_uses_project_policy_repo_and_callback_token(monkeypatch, synced_client, db_session):
    calls = []
    monkeypatch.setattr(release_tasks_service.config, "DEPLOY_WEBHOOK_TOKEN", "secret-token")
    monkeypatch.setattr(release_tasks_service, "_callback_url", lambda record_id: f"https://ops.example/api/deployments/{record_id}/report")

    def fake_dispatch(**kwargs):
        calls.append(kwargs)
        return "https://github.com/example/custom/actions/workflows/custom-staging.yml"

    monkeypatch.setattr(release_tasks_service, "_dispatch_github_workflow", fake_dispatch)
    monkeypatch.setattr(release_tasks_service, "_release_task_pr_gate_for", lambda row, repo: _successful_pr_gate())
    monkeypatch.setattr(release_tasks_service, "_missing_required_staging_deploy_secrets", lambda repo, **kwargs: ([], None))
    create_project_policy(
        db_session,
        **ProjectPolicyCreate(
            project_key="custom-project",
            display_name="Custom Project",
            root_path="/tmp/custom-project",
            deploy_repo_full_name="example/custom",
            staging_workflow_file="custom-staging.yml",
        ).model_dump(),
    )
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "custom-project",
            "service_key": "gateway-admin",
            "branch_name": "codex/custom-staging",
            "environment": "staging",
        },
    ).json()

    response = synced_client.post(f"/api/releases/tasks/{task['id']}/deploy-staging", json={})

    assert response.status_code == 200
    assert calls[0]["repo_full_name"] == "example/custom"
    assert calls[0]["workflow_file"] == "custom-staging.yml"
    assert calls[0]["inputs"]["callback_token"] == "secret-token"


def test_release_task_staging_deploy_validation_and_callback_closure(monkeypatch, synced_client, db_session):
    monkeypatch.setattr(release_tasks_service, "_dispatch_github_workflow", lambda **kwargs: "https://example.test/workflow")
    monkeypatch.setattr(release_tasks_service, "_release_task_pr_gate_for", lambda row, repo: _successful_pr_gate())
    monkeypatch.setattr(release_tasks_service, "_missing_required_staging_deploy_secrets", lambda repo, **kwargs: ([], None))

    production_task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "gateway",
            "branch_name": "codex/prod",
            "environment": "production",
        },
    ).json()
    assert synced_client.post(f"/api/releases/tasks/{production_task['id']}/deploy-staging", json={}).status_code == 400
    assert synced_client.post("/api/releases/tasks/99999/deploy-staging", json={}).status_code == 404

    invalid_service = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network-growing",
            "branch_name": "codex/no-service",
            "environment": "staging",
        },
    ).json()
    assert synced_client.post(f"/api/releases/tasks/{invalid_service['id']}/deploy-staging", json={}).status_code == 400

    missing_repo = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "unknown-project",
            "service_key": "gateway",
            "branch_name": "codex/missing-repo",
            "environment": "staging",
        },
    ).json()
    assert synced_client.post(f"/api/releases/tasks/{missing_repo['id']}/deploy-staging", json={}).status_code == 400

    staging_task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "admin-front",
            "branch_name": "codex/staging-admin",
            "environment": "staging",
        },
    ).json()
    deployed = synced_client.post(f"/api/releases/tasks/{staging_task['id']}/deploy-staging", json={}).json()
    report = synced_client.post(
        f"/api/deployments/{deployed['deployment_record_id']}/report",
        json={"status": "succeeded", "health_status": "passed", "notes": "staging deploy succeeded"},
    )
    assert report.status_code == 200
    updated = synced_client.get("/api/releases/tasks", params={"status": "completed"}).json()
    assert [item["id"] for item in updated] == [staging_task["id"]]
    assert updated[0]["operator"] == "operator"


def test_release_task_staging_deploy_failures_are_recorded(monkeypatch, synced_client, db_session):
    def failing_dispatch(**kwargs):
        raise RuntimeError("GitHub workflow dispatch failed: missing workflow")

    monkeypatch.setattr(release_tasks_service, "_dispatch_github_workflow", failing_dispatch)
    monkeypatch.setattr(release_tasks_service, "_release_task_pr_gate_for", lambda row, repo: _successful_pr_gate())
    monkeypatch.setattr(release_tasks_service, "_missing_required_staging_deploy_secrets", lambda repo, **kwargs: ([], None))
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "user-front",
            "branch_name": "codex/staging-user-front",
            "environment": "staging",
        },
    ).json()

    response = synced_client.post(f"/api/releases/tasks/{task['id']}/deploy-staging", json={"actor": "ops"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["deployment_status"] == "failed"
    assert "missing workflow" in payload["deployment_failure_summary"]
    assert synced_client.post(f"/api/releases/tasks/{task['id']}/deploy-staging", json={}).status_code == 400
