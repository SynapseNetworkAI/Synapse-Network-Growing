from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from server.database import ArtifactRow, BugRecordRow, OptimizationSignalRow, RequirementRow, TaskRow


def test_bug_source_registry_lists_builtin_sources(synced_client):
    response = synced_client.get("/api/bugs/sources")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_sources"] >= 5
    source_keys = {item["source_key"] for item in payload["sources"]}
    assert {
        "manual_bug_report",
        "runtime_log_error",
        "workflow_incident",
        "task_failure",
        "delivery_blocker_bug",
    } <= source_keys


def test_bug_source_registry_includes_live_observed_counts(synced_client, db_session):
    requirement = RequirementRow(
        title="Bug sink requirement",
        description_markdown="Used for registry evidence rows.",
        status="done",
        priority="normal",
        source="manual",
        current_plan_version=1,
    )
    db_session.add(requirement)
    db_session.flush()

    db_session.add(
        TaskRow(
            description="Failed runtime task",
            agent_id="content_writer",
            status="failed",
            priority="high",
            project_id="synapse-network-growing",
        )
    )
    db_session.add(
        ArtifactRow(
            requirement_id=requirement.id,
            artifact_type="bug_report",
            content_summary="Manual bug report candidate",
            machine_readable_payload=json.dumps({"severity": "high"}),
        )
    )
    db_session.add(
        ArtifactRow(
            requirement_id=requirement.id,
            artifact_type="delivery_state",
            content_summary="Blocked publish",
            machine_readable_payload=json.dumps({"publish_blockers": ["required check pending: pytest -q"]}),
        )
    )
    db_session.add(
        OptimizationSignalRow(
            dedupe_key="workflow-incident::1",
            signal_type="workflow_incident",
            source_kind="artifact",
            status="open",
            title="Workflow incident",
            summary="Recovery loop incident",
            severity="high",
            confidence=0.9,
            project_key="synapse-network-growing",
            evidence_json="[]",
        )
    )
    db_session.commit()

    response = synced_client.get("/api/bugs/sources")
    assert response.status_code == 200
    payload = response.json()
    by_key = {item["source_key"]: item for item in payload["sources"]}
    assert by_key["manual_bug_report"]["observed_open_count"] >= 1
    assert by_key["runtime_log_error"]["observed_open_count"] >= 1
    assert by_key["workflow_incident"]["observed_open_count"] >= 1
    assert by_key["task_failure"]["observed_open_count"] >= 1
    assert by_key["delivery_blocker_bug"]["observed_open_count"] >= 1
    assert payload["total_open_candidates"] >= 5


def test_bug_intake_creates_bug_record(synced_client, db_session):
    response = synced_client.post(
        "/api/bugs/intake",
        json={
            "source_key": "manual_bug_report",
            "project_key": "synapse-network",
            "project_root_path": "/Users/cliff/workspace/agent/Synapse-Network",
            "title": "Gateway readiness endpoint returns 500",
            "summary": "Observed repeated 500 responses on readiness checks.",
            "severity": "high",
            "source_ref": "sentry:evt-1",
            "environment": "prod",
            "log_excerpt": "GET /readyz -> 500",
            "stack_trace": "Traceback: readiness crash",
            "metadata": {"component": "gateway"},
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["result"] == "created"
    assert payload["bug"]["source_key"] == "manual_bug_report"
    assert payload["bug"]["project_key"] == "synapse-network"
    assert payload["bug"]["severity"] == "high"
    assert payload["bug"]["occurrence_count"] == 1
    assert payload["bug"]["metadata"]["component"] == "gateway"
    assert payload["bug"]["metadata"]["source_display_name"] == "Manual Bug Report"
    assert payload["bug"]["scorecard"]["freshness_score"] >= 12
    assert payload["bug"]["scorecard"]["priority"] in {"normal", "high"}

    row = db_session.query(BugRecordRow).one()
    assert row.bug_key.startswith("manual_bug_report::synapse-network::fp_")
    assert row.source_kind == "manual_input"


def test_bug_intake_dedupes_same_fingerprint(synced_client, db_session):
    first = synced_client.post(
        "/api/bugs/intake",
        json={
            "source_key": "manual_bug_report",
            "project_key": "synapse-network",
            "title": "Gateway timeout spike",
            "summary": "Timeout when checking balance.",
            "severity": "normal",
            "fingerprint": "gateway-timeout-balance",
            "source_ref": "ops:1",
            "environment": "prod",
            "log_excerpt": "timeout while checking balance",
        },
    )
    assert first.status_code == 201

    second = synced_client.post(
        "/api/bugs/intake",
        json={
            "source_key": "manual_bug_report",
            "project_key": "synapse-network",
            "title": "Gateway timeout spike",
            "summary": "Timeout when checking balance.",
            "severity": "critical",
            "fingerprint": "gateway-timeout-balance",
            "source_ref": "ops:2",
            "environment": "prod",
            "log_excerpt": "timeout while checking balance",
        },
    )
    assert second.status_code == 201
    payload = second.json()
    assert payload["result"] == "updated"
    assert payload["bug"]["occurrence_count"] == 2
    assert payload["bug"]["severity"] == "critical"
    assert payload["bug"]["scorecard"]["recurrence_score"] >= 8
    assert payload["bug"]["scorecard"]["priority"] == "critical"
    assert payload["bug"]["scorecard"]["auto_intake_eligible"] is True

    rows = db_session.query(BugRecordRow).all()
    assert len(rows) == 1


def test_bug_intake_rejects_unknown_source(synced_client):
    response = synced_client.post(
        "/api/bugs/intake",
        json={
            "source_key": "unknown_source",
            "project_key": "synapse-network",
            "title": "Unknown bug source",
            "severity": "high",
        },
    )
    assert response.status_code == 400
    assert "Unknown bug source" in response.json()["detail"]


def test_bug_intake_scores_blocking_delivery_bug(synced_client):
    response = synced_client.post(
        "/api/bugs/intake",
        json={
            "source_key": "delivery_blocker_bug",
            "project_key": "synapse-network",
            "title": "Publish blocked by failing release gate",
            "summary": "Release pipeline cannot proceed.",
            "severity": "high",
            "metadata": {"publish_blocked": True, "release_blocker": "pytest"},
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["bug"]["scorecard"]["blocker_score"] >= 20
    assert "delivery_blocker" in payload["bug"]["scorecard"]["blocker_flags"]
    assert payload["bug"]["scorecard"]["priority"] in {"high", "critical"}
    assert payload["bug"]["scorecard"]["auto_intake_eligible"] is True


def test_bug_log_sweep_materializes_runtime_and_failure_candidates(synced_client, db_session, tmp_path):
    db_session.add(
        TaskRow(
            description="Rejected task",
            agent_id="content_writer",
            status="failed",
            priority="high",
            project_id="synapse-network-growing",
            last_error_message="LLM API error 500 during implementation",
            runtime_backend="codex_cli",
        )
    )
    db_session.add(
        OptimizationSignalRow(
            dedupe_key="workflow-incident::42",
            signal_type="workflow_incident",
            source_kind="artifact",
            status="open",
            title="Workflow incident: runtime chain",
            summary="Runtime recovery loop broken",
            severity="high",
            confidence=0.88,
            project_key="synapse-network-growing",
            evidence_json="[]",
        )
    )
    db_session.commit()

    log_dir = Path(tmp_path) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "ops-dashboard.log").write_text(
        "2026-04-12 10:00:00 [ERROR] ops-dashboard.workflow_orchestrator: Synapse-Network-Growing runtime explosion\n",
        encoding="utf-8",
    )

    with patch("server.services.bug_log_sweep.config.LOG_DIR", str(log_dir)), patch(
        "server.services.bug_log_sweep.config.LOG_FILE",
        "ops-dashboard.log",
    ):
        response = synced_client.post("/api/recurring-workflows/bug_log_sweep/run", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["total_candidates"] >= 3
    assert len(payload["result"]["created_bug_ids"]) >= 3
    rows = db_session.query(BugRecordRow).all()
    assert len(rows) >= 3
    assert {"runtime_log_error", "task_failure", "workflow_incident"} <= {row.source_key for row in rows}
