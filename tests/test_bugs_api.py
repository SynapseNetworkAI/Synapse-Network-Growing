from server.database import (
    BugEventRow,
    BugFixAttemptRow,
    BugRecordRow,
    ProjectPolicyRow,
)
from server.services.bugs.serializer import (
    json_loads,
    serialize_fix_attempt,
    target_project_path,
)


def _create_bug(
    client,
    *,
    title="Provider API returns stale status",
    severity="normal",
    fingerprint="provider-stale-status",
):
    response = client.post(
        "/api/bugs/intake",
        json={
            "source_key": "manual_bug_report",
            "project_key": "synapse-network-provider",
            "project_root_path": "/Users/cliff/workspace/agent/Synapse-Network-Provider",
            "title": title,
            "summary": "The provider status page shows stale health after refresh.",
            "severity": severity,
            "fingerprint": fingerprint,
            "source_ref": "manual:test",
            "environment": "local",
            "log_excerpt": "status stayed stale after sync",
            "metadata": {
                "repro_steps": ["Open provider status page", "Click refresh"],
                "expected_behavior": "Status updates after refresh.",
                "actual_behavior": "Status remains stale.",
                "acceptance_checks": ["pytest -q tests/test_provider_status.py"],
            },
        },
    )
    assert response.status_code == 201
    return response.json()["bug"]


def test_bug_list_detail_and_agent_queue(synced_client):
    bug = _create_bug(synced_client)

    list_response = synced_client.get("/api/bugs?q=Provider")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == bug["id"]
    assert payload["items"][0]["project_key"] == "synapse-network-provider"

    detail_response = synced_client.get(f"/api/bugs/{bug['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["bug"]["title"] == "Provider API returns stale status"
    assert (
        detail["agent_context"]["target_project_path"]
        == "/Users/cliff/workspace/agent/Synapse-Network-Provider"
    )
    assert detail["agent_context"]["acceptance_checks"] == [
        "pytest -q tests/test_provider_status.py"
    ]
    assert detail["events"][0]["event_type"] == "intake_created"

    queue_response = synced_client.get("/api/bugs/agent-queue")
    assert queue_response.status_code == 200
    assert queue_response.json()["items"][0]["bug"]["id"] == bug["id"]


def test_bug_claim_is_exclusive_and_records_event(synced_client, db_session):
    bug = _create_bug(synced_client, title="SDK docs typo", fingerprint="sdk-docs-typo")

    first = synced_client.post(
        f"/api/bugs/{bug['id']}/claim", json={"agent_id": "codex"}
    )
    assert first.status_code == 200
    payload = first.json()
    assert payload["bug"]["status"] == "fixing"
    assert payload["fix_attempt"]["agent_id"] == "codex"

    second = synced_client.post(
        f"/api/bugs/{bug['id']}/claim", json={"agent_id": "other-agent"}
    )
    assert second.status_code == 409
    assert db_session.query(BugFixAttemptRow).count() == 1
    assert (
        db_session.query(BugEventRow)
        .filter(BugEventRow.event_type == "claimed")
        .count()
        == 1
    )


def test_bug_fix_verification_close_and_reopen_flow(synced_client, db_session):
    bug = _create_bug(
        synced_client, title="Provider retry bug", fingerprint="provider-retry-bug"
    )

    claim = synced_client.post(
        f"/api/bugs/{bug['id']}/claim", json={"agent_id": "codex"}
    )
    assert claim.status_code == 200

    close_without_evidence = synced_client.post(
        f"/api/bugs/{bug['id']}/close", json={"actor": "codex"}
    )
    assert close_without_evidence.status_code == 400

    link = synced_client.post(
        f"/api/bugs/{bug['id']}/link-fix",
        json={
            "agent_id": "codex",
            "branch_name": "codex/fix-provider-retry",
            "commit_sha": "deadbeef1234567890",
            "pr_url": "https://github.com/SynapseNetworkAI/Synapse-Network-Provider/pull/12",
        },
    )
    assert link.status_code == 200
    assert link.json()["latest_fix_attempt"]["commit_sha"] == "deadbeef1234567890"

    verify = synced_client.post(
        f"/api/bugs/{bug['id']}/verification",
        json={
            "agent_id": "codex",
            "status": "verified",
            "summary": "Provider retry regression passed.",
            "commands": [
                {
                    "command": "pytest -q tests/test_provider_retry.py",
                    "status": "passed",
                }
            ],
            "screenshots": [
                {"path": "/tmp/provider-retry.png", "label": "verification"}
            ],
        },
    )
    assert verify.status_code == 200
    assert verify.json()["bug"]["status"] == "verified"

    close = synced_client.post(f"/api/bugs/{bug['id']}/close", json={"actor": "codex"})
    assert close.status_code == 200
    assert close.json()["bug"]["status"] == "closed"

    reopen = synced_client.post(
        f"/api/bugs/{bug['id']}/reopen",
        json={"actor": "codex", "reason": "Regression returned"},
    )
    assert reopen.status_code == 200
    assert reopen.json()["bug"]["status"] == "reopened"
    events = [
        row.event_type
        for row in db_session.query(BugEventRow).order_by(BugEventRow.id.asc()).all()
    ]
    assert "commit_linked" in events
    assert "verification_added" in events
    assert "closed" in events
    assert "reopened" in events

    row = db_session.query(BugRecordRow).filter(BugRecordRow.id == bug["id"]).one()
    assert row.status == "reopened"


def test_bug_workbench_fail_closed_endpoints(synced_client):
    missing_detail = synced_client.get("/api/bugs/999999")
    assert missing_detail.status_code == 404

    missing_materialize = synced_client.post("/api/bugs/999999/materialize-requirement")
    assert missing_materialize.status_code == 400

    missing_link = synced_client.post(
        "/api/bugs/999999/link-fix", json={"branch_name": "codex/missing"}
    )
    assert missing_link.status_code == 400

    missing_reopen = synced_client.post(
        "/api/bugs/999999/reopen", json={"actor": "codex", "reason": "not found"}
    )
    assert missing_reopen.status_code == 400

    bug = _create_bug(
        synced_client,
        title="Frontend screenshot bug",
        fingerprint="frontend-screenshot-required",
    )
    verify_without_claim = synced_client.post(
        f"/api/bugs/{bug['id']}/verification",
        json={"status": "invalid", "summary": "should fail"},
    )
    assert verify_without_claim.status_code == 400

    assert (
        synced_client.post(
            f"/api/bugs/{bug['id']}/claim", json={"agent_id": "codex"}
        ).status_code
        == 200
    )
    bad_status = synced_client.post(
        f"/api/bugs/{bug['id']}/verification",
        json={"status": "invalid", "summary": "bad status"},
    )
    assert bad_status.status_code == 400

    missing_summary = synced_client.post(
        f"/api/bugs/{bug['id']}/verification",
        json={"status": "verified", "summary": "   "},
    )
    assert missing_summary.status_code == 400


def test_agent_bug_actions_require_matching_token(monkeypatch, synced_client):
    monkeypatch.setattr("server.config.OPS_AGENT_BUG_API_TOKEN", "bug-token")
    bug = _create_bug(
        synced_client,
        title="Agent token gated bug",
        fingerprint="agent-token-gated-bug",
    )

    missing = synced_client.post(
        f"/api/bugs/agent-actions/{bug['id']}/claim",
        json={"agent_id": "codex"},
    )
    wrong = synced_client.post(
        f"/api/bugs/agent-actions/{bug['id']}/claim",
        headers={"X-Growing-Agent-Bug-Token": "wrong-token"},
        json={"agent_id": "codex"},
    )
    allowed = synced_client.post(
        f"/api/bugs/agent-actions/{bug['id']}/claim",
        headers={"X-Growing-Agent-Bug-Token": "bug-token"},
        json={"agent_id": "codex"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["bug"]["status"] == "fixing"


def test_agent_bug_actions_cover_intake_fix_verify_and_close(monkeypatch, synced_client):
    monkeypatch.setattr("server.config.OPS_AGENT_BUG_API_TOKEN", "bug-token")
    headers = {"X-Growing-Agent-Bug-Token": "bug-token"}

    intake = synced_client.post(
        "/api/bugs/agent-actions/intake",
        headers=headers,
        json={
            "source_key": "manual_bug_report",
            "project_key": "growing",
            "title": "MCP smoke bug",
            "summary": "MCP smoke needs evidence lifecycle.",
            "severity": "normal",
            "fingerprint": "mcp-smoke-bug",
        },
    )
    assert intake.status_code == 201
    bug = intake.json()["bug"]

    assert synced_client.post(
        f"/api/bugs/agent-actions/{bug['id']}/claim",
        headers=headers,
        json={"agent_id": "codex"},
    ).status_code == 200
    link = synced_client.post(
        f"/api/bugs/agent-actions/{bug['id']}/link-fix",
        headers=headers,
        json={
            "agent_id": "codex",
            "branch_name": "codex/mcp-smoke",
            "commit_sha": "abc1234567890",
            "pr_url": "https://github.com/SynapseNetworkAI/Synapse-Network-Growing/pull/1",
        },
    )
    assert link.status_code == 200
    verify = synced_client.post(
        f"/api/bugs/agent-actions/{bug['id']}/verification",
        headers=headers,
        json={
            "agent_id": "codex",
            "status": "verified",
            "summary": "MCP smoke validation passed.",
            "commands": [{"command": "python scripts/e2e/bug_list_mcp_live_e2e.py", "status": "passed"}],
            "screenshots": [{"path": "docs/archive/evidence/bugs/mcp-smoke.png", "label": "MCP smoke"}],
        },
    )
    assert verify.status_code == 200
    close = synced_client.post(
        f"/api/bugs/agent-actions/{bug['id']}/close",
        headers=headers,
        json={"actor": "codex", "resolution": "verified"},
    )
    assert close.status_code == 200
    assert close.json()["bug"]["status"] == "closed"


def test_ui_bug_actions_stay_compatible_without_agent_token(monkeypatch, synced_client):
    monkeypatch.setattr("server.config.OPS_AGENT_BUG_API_TOKEN", "bug-token")
    bug = _create_bug(
        synced_client,
        title="UI compatibility bug",
        fingerprint="ui-compatibility-bug",
    )

    response = synced_client.post(
        f"/api/bugs/{bug['id']}/claim",
        json={"agent_id": "codex"},
    )

    assert response.status_code == 200
    assert response.json()["bug"]["status"] == "fixing"


def test_bug_serializer_fallbacks_and_project_policy(db_session):
    assert json_loads(None, []) == []
    assert json_loads("{bad json", {"fallback": True}) == {"fallback": True}

    bug = BugRecordRow(
        bug_key="BUG-SERIALIZER",
        source_key="manual_bug_report",
        source_kind="manual",
        status="open",
        title="Serializer fallback",
        summary="Serializer fallback coverage",
        severity="normal",
        fingerprint="serializer-fallback",
        project_key="synapse-network-provider",
    )
    db_session.add(
        ProjectPolicyRow(
            project_key="synapse-network-provider",
            display_name="Provider",
            root_path="/Users/cliff/workspace/agent/Synapse-Network-Provider",
        )
    )
    db_session.add(bug)
    db_session.flush()

    attempt = BugFixAttemptRow(
        bug_id=bug.id,
        status="",
        agent_id="",
        branch_name="",
        commit_sha="abc123",
        pr_url="",
        verification_summary="",
        failure_reason="",
    )
    db_session.add(attempt)
    db_session.flush()

    assert target_project_path(db_session, bug).endswith("Synapse-Network-Provider")
    serialized = serialize_fix_attempt(attempt)
    assert serialized.status == "claimed"
    assert serialized.agent_id == "agent"
    assert serialized.branch_name is None
    assert serialized.commit_sha == "abc123"
