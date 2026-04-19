from __future__ import annotations

import logging

import pytest

from server.database import (
    ErrorFingerprintRow,
    HumanGateRequestRow,
    NotificationDeliveryRow,
    RequirementIntakeFingerprintRow,
    RequirementRow,
)


@pytest.fixture(autouse=True)
def _disable_lark_webhooks(monkeypatch):
    for name in (
        "LARK_REQUIREMENT_WEBHOOK_URL",
        "LARK_ALERT_WEBHOOK_URL",
        "LARK_APPROVAL_WEBHOOK_URL",
        "LARK_RELEASE_WEBHOOK_URL",
    ):
        monkeypatch.setattr(f"server.config.{name}", "")


def _intake_payload(**overrides):
    payload = {
        "source_kind": "runtime_log_error",
        "service_name": "Synapse Gateway",
        "summary": "Gateway timeout while opening FAQ route",
        "message": "TimeoutError: request 123 exceeded 30s budget at /faq/42",
        "severity": "normal",
        "project_key": "synapse-network-growing",
        "project_root_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
        "incident_code": "gateway_timeout",
        "stack_trace": "TimeoutError: request 123 exceeded 30s budget\nat gateway.py:42\nat routes.py:17",
    }
    payload.update(overrides)
    return payload


def test_error_intake_creates_requirement_and_declarative_workflow(synced_client, db_session):
    response = synced_client.post("/api/errors/intake", json=_intake_payload())

    assert response.status_code == 201
    payload = response.json()
    assert payload["requirement"] is not None
    assert payload["requirement"]["status"] in {"running", "ready", "completed", "done"}
    assert payload["fingerprint"]["active_workflow_run_id"] is not None
    assert payload["fingerprint"]["active_workflow_run_summary"]["workflow_key"] == "gateway_reliability_repair"
    assert payload["fingerprint"]["occurrence_count"] == 1
    assert payload["fingerprint"]["discovery_status"] in {"materialized", "linked_active_requirement"}
    assert payload["fingerprint"]["discovery_recommendation"]["discovery_action"] == "auto_materialize"

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == payload["requirement"]["id"]).one()
    assert requirement.source == "bug_intake"
    assert requirement.source_ref == f"error-fingerprint:{payload['fingerprint']['fingerprint_key']}"

    deliveries = db_session.query(NotificationDeliveryRow).all()
    event_types = {row.event_type for row in deliveries}
    assert {"requirement_created", "workflow_run_succeeded", "error_logged"} & event_types


def test_error_intake_emits_structured_error_loop_logs(synced_client, caplog):
    with caplog.at_level(logging.INFO):
        response = synced_client.post("/api/errors/intake", json=_intake_payload())

    assert response.status_code == 201
    payload = response.json()
    text = caplog.text
    assert "error_event_ingested" in text
    assert "error_requirement_materialized" in text
    assert "error_requirement_submitted" in text
    assert payload["fingerprint"]["fingerprint_key"] in text


def test_error_intake_reuses_active_requirement_for_same_fingerprint(synced_client, db_session):
    first = synced_client.post("/api/errors/intake", json=_intake_payload())
    second = synced_client.post(
        "/api/errors/intake",
        json=_intake_payload(message="TimeoutError: request 999 exceeded 31s budget at /faq/77"),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    first_requirement_id = first.json()["requirement"]["id"]
    second_requirement_id = second.json()["requirement"]["id"]
    assert first_requirement_id == second_requirement_id
    assert second.json()["fingerprint"]["occurrence_count"] == 2
    assert db_session.query(RequirementRow).count() == 1
    assert db_session.query(ErrorFingerprintRow).count() == 1


def test_high_risk_error_intake_routes_to_workflow_human_gate(synced_client, db_session):
    response = synced_client.post(
        "/api/errors/intake",
        json=_intake_payload(
            source_kind="workflow_incident",
            severity="critical",
            summary="Production release workflow failed during deploy gate",
            message="WorkflowIncident: production deploy gate failed after publish impact review",
            project_key="synapse-network",
            project_root_path="/Users/cliff/workspace/agent/Synapse-Network",
        ),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["fingerprint"]["active_workflow_run_id"] is not None
    pending = db_session.query(HumanGateRequestRow).filter(HumanGateRequestRow.status == "pending").all()
    assert pending

    event_types = {row.event_type for row in db_session.query(NotificationDeliveryRow).all()}
    assert "error_logged" in event_types


def test_done_requirement_is_not_reused_for_same_fingerprint(synced_client, db_session):
    first = synced_client.post("/api/errors/intake", json=_intake_payload())

    assert first.status_code == 201
    requirement_id = first.json()["requirement"]["id"]
    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).one()
    requirement.status = "done"
    db_session.commit()

    second = synced_client.post("/api/errors/intake", json=_intake_payload())

    assert second.status_code == 201
    assert second.json()["requirement"]["id"] == requirement_id
    assert db_session.query(RequirementRow).count() == 1
    gate = db_session.query(RequirementIntakeFingerprintRow).one()
    assert gate.status == "suppressed"
    assert gate.suppressed_count >= 1


def test_resolved_error_fingerprint_can_reopen_regression_requirement(synced_client, db_session):
    first = synced_client.post("/api/errors/intake", json=_intake_payload())

    assert first.status_code == 201
    requirement_id = first.json()["requirement"]["id"]
    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).one()
    requirement.status = "done"
    gate = db_session.query(RequirementIntakeFingerprintRow).one()
    gate.status = "resolved"
    db_session.commit()

    second = synced_client.post("/api/errors/intake", json=_intake_payload())

    assert second.status_code == 201
    assert second.json()["requirement"]["id"] != requirement_id
    assert second.json()["requirement"]["title"].startswith("Regression:")
    assert db_session.query(RequirementRow).count() == 2


def test_low_signal_error_can_be_ignored_without_requirement(synced_client):
    response = synced_client.post(
        "/api/errors/intake",
        json=_intake_payload(
            source_kind="runtime_log_error",
            severity="low",
            project_key=None,
            project_root_path=None,
            stack_trace=None,
            message="minor warning while checking stale cache key",
            summary="Minor cache warning",
        ),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["requirement"] is None
    assert payload["fingerprint"]["active_workflow_run_id"] is None
    assert payload["fingerprint"]["discovery_recommendation"]["discovery_action"] == "ignore_as_noise"
