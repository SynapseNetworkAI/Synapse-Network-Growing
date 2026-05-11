from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from server.database import (
    CodexSessionRow,
    HumanGateRequestRow,
    ProjectPolicyRow,
    RequirementRow,
    WorkflowRunRow,
)
from server.services.runtime.codex_session_registry import build_session_key


def _git_env() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }


VALID_ACCEPTANCE_CONTRACT = (
    '{"execution_acceptance_steps": ['
    '{"step_key": "workflow_result", '
    '"title": "Workflow result is verified", '
    '"expected_result": "Workflow completes with command evidence.", '
    '"required_evidence_types": ["workflow_command_result"]}'
    "]}"
)


def _init_test_git_repo(path: Path, *, branch: str = "main") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-b", branch],
        cwd=path,
        env=_git_env(),
        text=True,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        env=_git_env(),
        text=True,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test Operator"],
        cwd=path,
        env=_git_env(),
        text=True,
        capture_output=True,
        check=True,
    )
    (path / "README.md").write_text("trusted\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=path,
        env=_git_env(),
        text=True,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=path,
        env=_git_env(),
        text=True,
        capture_output=True,
        check=True,
    )
    return path


def test_continue_retry_requires_workspace_recovery_before_deciding_gate(
    synced_client,
    db_session,
    tmp_path,
):
    repo = _init_test_git_repo(tmp_path / "main-workspace", branch="main")
    db_session.add(
        ProjectPolicyRow(
            project_key="workspace-recovery-main",
            display_name="Workspace Recovery Main",
            root_path=str(repo),
            status="active",
        )
    )
    requirement = RequirementRow(
        title="Retry should not reset a human main workspace",
        description_markdown="Dirty main workspace must route to human review.",
        target_project_path=str(repo),
        status="blocked",
        acceptance_contract_json=VALID_ACCEPTANCE_CONTRACT,
    )
    db_session.add(requirement)
    db_session.flush()
    workflow = WorkflowRunRow(
        requirement_id=int(requirement.id),
        workflow_key="agent_self_repair",
        current_state="awaiting_operator",
        status="awaiting_operator",
        delivery_branch="main",
    )
    db_session.add(workflow)
    db_session.flush()
    gate = HumanGateRequestRow(
        workflow_run_id=int(workflow.id),
        state_key="awaiting_operator",
        status="pending",
        reason="Retry requires workspace recovery.",
        payload_json="{}",
    )
    session = CodexSessionRow(
        session_key=build_session_key(
            role_key="workflow_runner",
            project_root=str(repo),
            requirement_id=int(requirement.id),
        ),
        role_key="workflow_runner",
        project_root=str(repo),
        requirement_id=int(requirement.id),
        workflow_run_id=int(workflow.id),
        status="killed",
        workspace_trust_state="dirty_after_kill",
        requires_workspace_recovery=True,
        metadata_json=json.dumps({"workflow_branch": "main"}),
    )
    db_session.add_all([gate, session])
    db_session.commit()

    response = synced_client.post(
        f"/api/workflows/runs/{int(workflow.id)}/human-gates/{int(gate.id)}/decide",
        json={"decision": "continue_retry", "reviewer": "operator", "comment": "retry"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["root_cause"] == "workspace_not_workflow_owned"
    db_session.refresh(gate)
    db_session.refresh(session)
    assert gate.status == "pending"
    assert gate.decision is None
    assert session.workspace_trust_state == "recovery_failed"


def test_mark_workflow_runtime_killed_endpoint_marks_workspace_dirty(
    synced_client,
    db_session,
    tmp_path,
):
    repo = _init_test_git_repo(tmp_path / "runtime-workspace", branch="ops/req-1-test")
    db_session.add(
        ProjectPolicyRow(
            project_key="workspace-recovery-runtime",
            display_name="Workspace Recovery Runtime",
            root_path=str(repo),
            status="active",
        )
    )
    requirement = RequirementRow(
        title="Runtime kill marks workspace dirty",
        description_markdown="Kill should require recovery.",
        target_project_path=str(repo),
        status="running",
        acceptance_contract_json=VALID_ACCEPTANCE_CONTRACT,
    )
    db_session.add(requirement)
    db_session.flush()
    workflow = WorkflowRunRow(
        requirement_id=int(requirement.id),
        workflow_key="agent_self_repair",
        current_state="generate_patch",
        status="running",
        delivery_branch="ops/req-1-test",
    )
    db_session.add(workflow)
    db_session.commit()

    response = synced_client.post(
        f"/api/workflows/runs/{int(workflow.id)}/runtime/mark-killed",
        json={"kill_signal": "SIGTERM"},
    )

    assert response.status_code == 200
    payload = response.json()["workspace_recovery"]
    assert payload["workspace_trust_state"] == "dirty_after_kill"
    assert payload["requires_workspace_recovery"] is True
    assert payload["kill_signal"] == "SIGTERM"


def test_mark_workflow_runtime_killed_endpoint_returns_404_for_missing_run(
    synced_client,
):
    response = synced_client.post(
        "/api/workflows/runs/999999/runtime/mark-killed",
        json={"kill_signal": "SIGTERM"},
    )

    assert response.status_code == 404
