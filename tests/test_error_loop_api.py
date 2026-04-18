from __future__ import annotations

import logging
from unittest.mock import patch

from server.database import (
    ApprovalRequestRow,
    ErrorFingerprintRow,
    NotificationDeliveryRow,
    RequirementRow,
)


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
    with patch("server.services.workflows.agent_first.dispatch", return_value=None):
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
    assert {"requirement_created", "approval_auto_approved", "error_logged"} <= event_types


def test_error_intake_emits_structured_error_loop_logs(synced_client, caplog):
    with patch("server.services.workflows.agent_first.dispatch", return_value=None), caplog.at_level(logging.INFO):
        response = synced_client.post("/api/errors/intake", json=_intake_payload())

    assert response.status_code == 201
    payload = response.json()
    text = caplog.text
    assert "error_event_ingested" in text
    assert "error_requirement_materialized" in text
    assert "error_requirement_submitted" in text
    assert payload["fingerprint"]["fingerprint_key"] in text


def test_error_intake_materializes_new_requirement_when_previous_workflow_terminal(synced_client, db_session):
    with patch("server.services.workflows.agent_first.dispatch", return_value=None):
        first = synced_client.post("/api/errors/intake", json=_intake_payload())
        second = synced_client.post("/api/errors/intake", json=_intake_payload(message="TimeoutError: request 999 exceeded 31s budget at /faq/77"))

    assert first.status_code == 201
    assert second.status_code == 201
    first_requirement_id = first.json()["requirement"]["id"]
    second_requirement_id = second.json()["requirement"]["id"]
    assert first_requirement_id != second_requirement_id
    assert second.json()["fingerprint"]["occurrence_count"] == 2
    assert db_session.query(RequirementRow).count() == 2
    assert db_session.query(ErrorFingerprintRow).count() == 1


def test_high_risk_error_intake_routes_to_manual_approval(synced_client, db_session):
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
    assert payload["requirement"]["status"] == "blocked"
    assert payload["requirement"]["approval_status"] == "pending_approval"
    pending = db_session.query(ApprovalRequestRow).filter(ApprovalRequestRow.status == "pending").one()
    assert pending.approval_type == "requirement_execution_approval"

    event_types = {row.event_type for row in db_session.query(NotificationDeliveryRow).all()}
    assert {"requirement_created", "approval_manual_required", "error_logged"} <= event_types


def test_done_requirement_is_not_reused_for_same_fingerprint(synced_client, db_session):
    with patch("server.services.workflows.agent_first.dispatch", return_value=None):
        first = synced_client.post("/api/errors/intake", json=_intake_payload())

    assert first.status_code == 201
    requirement_id = first.json()["requirement"]["id"]
    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).one()
    requirement.status = "done"
    db_session.commit()

    with patch("server.services.workflows.agent_first.dispatch", return_value=None):
        second = synced_client.post("/api/errors/intake", json=_intake_payload(message="TimeoutError: request 1001 exceeded 30s budget at /faq/88"))

    assert second.status_code == 201
    assert second.json()["requirement"]["id"] != requirement_id


def test_low_signal_error_can_be_ignored_without_requirement(synced_client):
    response = synced_client.post(
        "/api/errors/intake",
        json=_intake_payload(
            source_kind="task_failure",
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
