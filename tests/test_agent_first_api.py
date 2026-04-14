from __future__ import annotations

from unittest.mock import patch

from server.database import ExecutionRunRow, RequirementRow, ValidationRecordRow


def test_agent_first_requirement_creates_direct_execution_flow(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Simplify release summary",
            "description_markdown": "Update the release summary copy and keep the change minimal.",
            "acceptance_criteria_markdown": "- Copy updated\n- No unrelated edits",
            "priority": "normal",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
        },
    )

    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    submit_resp = synced_client.post(f"/api/requirements/{requirement_id}/submit")
    assert submit_resp.status_code == 200
    assert submit_resp.json()["requirement"]["status"] == "ready"

    execution_resp = synced_client.post("/api/executions", json={"requirement_id": requirement_id})

    assert execution_resp.status_code == 201
    payload = execution_resp.json()
    assert payload["execution"]["execution_mode"] == "direct"
    assert payload["execution"]["validation_profile"] == "minimal"
    assert [node["node_type"] for node in payload["nodes"]] == ["execute"]
    assert [node["node_key"] for node in payload["nodes"]] == ["execute"]


def test_agent_first_release_flow_uses_validate_gate_and_open_pr(synced_client, db_session):
    requirement = RequirementRow(
        title="Promote validated change",
        description_markdown="Validated change ready for release.",
        status="delivery_ready",
        approval_status="waived",
        priority="normal",
        source="manual",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
    )
    db_session.add(requirement)
    db_session.flush()

    run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="succeeded",
        validation_profile="release_candidate",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network"]',
    )
    db_session.add(run)
    db_session.flush()

    db_session.add(
        ValidationRecordRow(
            requirement_id=int(requirement.id),
            execution_run_id=int(run.id),
            profile="release_candidate",
            status="passed",
            summary_markdown="Validation passed.",
            checks_json="[]",
        )
    )
    db_session.commit()

    candidates = synced_client.get("/api/releases/candidates")
    assert candidates.status_code == 200
    payload = candidates.json()
    candidate = next(item for item in payload if item["requirement"]["id"] == requirement.id)
    assert candidate["validation"]["status"] == "passed"

    with patch(
        "server.services.workflows.agent_first.execute_requirement_delivery_vcs",
        return_value={
            "branch_name": "ops/req-1-promote-validated-change",
            "base_branch": "main",
            "blockers": [],
            "repositories": [
                {
                    "remote_url": "https://github.com/example/synapse-network.git",
                    "commit_sha": "abc123",
                    "remote_sha": "abc123",
                }
            ],
        },
    ), patch(
        "server.services.workflows.agent_first.sync_requirement_review_pr",
        return_value={
            "compare_url": "https://github.com/example/synapse-network/compare/main...ops/req-1-promote-validated-change",
            "pr_url": "https://github.com/example/synapse-network/pull/7",
            "pr_number": 7,
        },
    ):
        prepare_resp = synced_client.post(
            f"/api/releases/{requirement.id}/prepare",
            json={"actor": "operator", "note": "prepare"},
        )
        assert prepare_resp.status_code == 200
        assert prepare_resp.json()["release"]["status"] == "branch_prepared"

        open_pr_resp = synced_client.post(
            f"/api/releases/{requirement.id}/open-pr",
            json={"actor": "operator", "note": "open pr"},
        )
        assert open_pr_resp.status_code == 200
        release = open_pr_resp.json()["release"]
        assert release["status"] == "pr_opened"
        assert release["pr_number"] == 7
        assert release["commit_sha"] == "abc123"
