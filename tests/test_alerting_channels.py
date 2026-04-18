from server.database import NotificationDeliveryRow
from server.services.runtime.alerting import deliver_policy_notification


def test_deliver_policy_notification_persists_approval_channel_when_webhook_missing(db_session, monkeypatch):
    monkeypatch.setattr("server.config.LARK_APPROVAL_WEBHOOK_URL", "")
    row = deliver_policy_notification(
        db_session,
        event_type="human_gate_request.created",
        object_type="human_gate",
        object_key="100",
        service_name="Synapse Ops",
        summary="Workflow requires operator approval.",
        severity="normal",
        risk_level="high",
        status="pending",
        requires_human=True,
        workflow_key="agent_self_repair",
        current_state="awaiting_operator",
        object_refs={"gate_id": 100, "workflow_run_id": 7},
    )

    assert row is not None
    assert row.channel == "approval"
    assert row.status == "skipped"
    persisted = db_session.query(NotificationDeliveryRow).filter(NotificationDeliveryRow.event_key == row.event_key).one()
    assert persisted.channel == "approval"
    assert "Webhook not configured" in str(persisted.response_excerpt)


def test_deliver_policy_notification_suppresses_low_signal_atom_success(db_session):
    row = deliver_policy_notification(
        db_session,
        event_type="atom_invocation_succeeded",
        object_type="workflow_run",
        object_key="7",
        service_name="Synapse Ops",
        summary="Atom completed.",
        severity="info",
        risk_level="low",
    )

    assert row is None
    assert db_session.query(NotificationDeliveryRow).count() == 0
