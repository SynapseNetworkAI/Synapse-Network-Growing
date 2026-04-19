from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from server.database import ArtifactRow, BugRecordRow, OptimizationSignalRow, RequirementRow


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
    assert by_key["workflow_incident"]["observed_open_count"] >= 1
    assert by_key["delivery_blocker_bug"]["observed_open_count"] >= 1
    assert payload["total_open_candidates"] >= 3


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
    assert payload["bug"]["discovery_recommendation"]["discovery_action"] == "auto_materialize"
    assert payload["bug"]["materialized_requirement_id"] is not None

    row = db_session.query(BugRecordRow).one()
    assert row.bug_key.startswith("manual_bug_report::synapse-network::fp_")
    assert row.source_kind == "manual_input"
    repeat = synced_client.post(
        "/api/bugs/intake",
        json={
            "source_key": "manual_bug_report",
            "project_key": "synapse-network",
            "project_root_path": "/Users/cliff/workspace/agent/Synapse-Network",
            "title": "Gateway readiness endpoint returns 500",
            "summary": "Observed repeated 500 responses on readiness checks.",
            "severity": "high",
            "source_ref": "sentry:evt-2",
            "environment": "prod",
            "log_excerpt": "GET /readyz -> 500",
            "stack_trace": "Traceback: readiness crash",
            "metadata": {"component": "gateway"},
        },
    )
    assert repeat.status_code == 201
    assert db_session.query(BugRecordRow).count() == 1
    assert db_session.query(RequirementRow).count() == 1


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


def test_external_log_center_batch_intake_creates_and_updates_bug_records(synced_client, db_session):
    response = synced_client.post(
        "/api/bugs/intake/log-center",
        json={
            "source_system": "loki",
            "events": [
                {
                    "project_key": "synapse-network",
                    "service_name": "gateway",
                    "title": "Gateway 500 spike",
                    "message": "GET /readyz returned 500 repeatedly",
                    "severity": "error",
                    "fingerprint": "gateway-500-readyz",
                    "source_ref": "loki:evt-1",
                    "environment": "prod",
                    "metadata": {"cluster": "prod-a"},
                },
                {
                    "project_key": "synapse-network",
                    "service_name": "gateway",
                    "message": "GET /readyz returned 500 repeatedly",
                    "severity": "fatal",
                    "fingerprint": "gateway-500-readyz",
                    "source_ref": "loki:evt-2",
                    "environment": "prod",
                    "metadata": {"cluster": "prod-a"},
                },
            ],
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["source_system"] == "loki"
    assert payload["accepted_count"] == 2
    assert len(payload["created_bug_ids"]) == 1
    assert len(payload["updated_bug_ids"]) == 1
    rows = db_session.query(BugRecordRow).all()
    assert len(rows) == 1
    assert rows[0].source_key == "external_log_center_error"
    assert rows[0].severity == "critical"
    assert payload["results"][0]["bug"]["discovery_recommendation"]["discovery_action"] == "auto_materialize"


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


def test_bug_log_sweep_materializes_runtime_and_workflow_incident_candidates(synced_client, db_session, tmp_path):
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

    with patch("server.services.bugs.log_sweep.config.LOG_DIR", str(log_dir)), patch(
        "server.services.bugs.log_sweep.config.LOG_FILE",
        "ops-dashboard.log",
    ):
        response = synced_client.post("/api/recurring-workflows/bug_log_sweep/run", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["total_candidates"] >= 2
    assert len(payload["result"]["created_bug_ids"]) >= 2
    rows = db_session.query(BugRecordRow).all()
    assert len(rows) >= 2
    assert {"runtime_log_error", "workflow_incident"} <= {row.source_key for row in rows}


def test_bug_log_sweep_groups_traceback_and_keeps_stack_snippet(synced_client, db_session, tmp_path):
    log_dir = Path(tmp_path) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "ops-dashboard.log").write_text(
        "\n".join(
            [
                "2026-04-12 10:00:00 [ERROR] ops-dashboard.livecheck: AUTOBUG-LIVE-VERIFY-20260412-1940 gateway readiness live verification failure",
                "Traceback (most recent call last):",
                '  File "/app/livecheck.py", line 10, in verify',
                '    raise RuntimeError(\"gateway readiness live verification failure\")',
                "RuntimeError: gateway readiness live verification failure",
                "2026-04-12 10:00:01 [ERROR] ops-dashboard.livecheck: AUTOBUG-LIVE-VERIFY-20260412-1940 gateway readiness live verification failure",
                "Traceback (most recent call last):",
                '  File "/app/livecheck.py", line 10, in verify',
                '    raise RuntimeError(\"gateway readiness live verification failure\")',
                "RuntimeError: gateway readiness live verification failure",
            ]
        ),
        encoding="utf-8",
    )

    with patch("server.services.bugs.log_sweep.config.LOG_DIR", str(log_dir)), patch(
        "server.services.bugs.log_sweep.config.LOG_FILE",
        "ops-dashboard.log",
    ):
        response = synced_client.post("/api/recurring-workflows/bug_log_sweep/run", json={})

    assert response.status_code == 200
    rows = db_session.query(BugRecordRow).filter(BugRecordRow.source_key == "runtime_log_error").all()
    assert len(rows) == 1
    row = rows[0]
    assert row.occurrence_count == 2
    evidence = json.loads(row.evidence_json)
    assert "Traceback" in str(evidence[0]["stack_trace"])
    assert len(str(evidence[0]["stack_trace"]).splitlines()) <= 8
