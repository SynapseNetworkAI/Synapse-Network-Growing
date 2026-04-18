from datetime import timedelta

from server.database import NotificationDeliveryRow, NotificationEventRow, NotificationFingerprintRow, utcnow
from server.services.runtime.alerting import build_lark_card, deliver_policy_notification
from server.services.runtime.notification_queue import dispatch_notification_queue, enqueue_notification_event


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
    event = db_session.query(NotificationEventRow).filter(NotificationEventRow.delivery_id == row.id).one()
    assert event.status == "delivered"
    fingerprint = db_session.query(NotificationFingerprintRow).filter(NotificationFingerprintRow.fingerprint_key == row.fingerprint_key).one()
    assert fingerprint.occurrence_count == 1


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


def test_notification_queue_suppresses_duplicate_within_cooldown(db_session, monkeypatch):
    monkeypatch.setattr("server.config.LARK_ALERT_WEBHOOK_URL", "")

    first = enqueue_notification_event(
        db_session,
        event_type="gateway_slo_drift",
        object_type="error_fingerprint",
        object_key="gateway-timeout",
        service_name="Gateway",
        summary="Gateway SLO drift detected.",
        severity="high",
        risk_level="high",
        workflow_key="gateway_reliability_repair",
    )
    second = enqueue_notification_event(
        db_session,
        event_type="gateway_slo_drift",
        object_type="error_fingerprint",
        object_key="gateway-timeout",
        service_name="Gateway",
        summary="Gateway SLO drift detected again.",
        severity="high",
        risk_level="high",
        workflow_key="gateway_reliability_repair",
    )

    assert first is not None
    assert second is not None
    assert first.status == "delivered"
    assert second.status == "suppressed"
    assert db_session.query(NotificationDeliveryRow).count() == 1
    fingerprint = db_session.query(NotificationFingerprintRow).filter(NotificationFingerprintRow.fingerprint_key == first.fingerprint_key).one()
    assert fingerprint.occurrence_count == 2
    assert fingerprint.suppressed_count == 1
    assert "cooldown" in str(second.suppressed_reason)


def test_notification_queue_severity_upgrade_breaks_cooldown(db_session, monkeypatch):
    monkeypatch.setattr("server.config.LARK_ALERT_WEBHOOK_URL", "")

    first = enqueue_notification_event(
        db_session,
        event_type="gateway_slo_drift",
        object_type="error_fingerprint",
        object_key="gateway-timeout",
        service_name="Gateway",
        summary="Gateway SLO drift detected.",
        severity="high",
        risk_level="high",
        workflow_key="gateway_reliability_repair",
    )
    upgraded = enqueue_notification_event(
        db_session,
        event_type="gateway_slo_drift",
        object_type="error_fingerprint",
        object_key="gateway-timeout",
        service_name="Gateway",
        summary="Gateway SLO drift escalated.",
        severity="critical",
        risk_level="high",
        workflow_key="gateway_reliability_repair",
    )

    assert first is not None
    assert upgraded is not None
    assert upgraded.status == "delivered"
    assert db_session.query(NotificationDeliveryRow).count() == 2
    fingerprint = db_session.query(NotificationFingerprintRow).filter(NotificationFingerprintRow.fingerprint_key == first.fingerprint_key).one()
    assert fingerprint.escalation_level == 1
    assert fingerprint.severity == "critical"


def test_notification_queue_retries_and_dead_letters_failed_lark_delivery(db_session, monkeypatch):
    monkeypatch.setattr("server.config.LARK_ALERT_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setattr("server.config.NOTIFICATION_MAX_DELIVERY_ATTEMPTS", 2)
    monkeypatch.setattr(
        "server.services.runtime.alerting._send_lark_payload",
        lambda *_args, **_kwargs: (False, "network down"),
    )

    event = enqueue_notification_event(
        db_session,
        event_type="gateway_slo_drift",
        object_type="error_fingerprint",
        object_key="gateway-timeout",
        service_name="Gateway",
        summary="Gateway SLO drift detected.",
        severity="high",
        risk_level="high",
        workflow_key="gateway_reliability_repair",
    )

    assert event is not None
    assert event.status == "queued"
    event.next_attempt_at = utcnow() - timedelta(seconds=1)
    dispatch_notification_queue(db_session, event_id=event.id, limit=1)
    db_session.refresh(event)

    assert event.status == "dead_letter"
    assert event.attempt_count == 2
    assert db_session.query(NotificationDeliveryRow).count() == 2
    failure_event = (
        db_session.query(NotificationEventRow)
        .filter(NotificationEventRow.event_type == "lark_alert_delivery_failed")
        .one()
    )
    assert failure_event.status == "queued"


def test_notification_queue_alert_storm_rolls_up_after_channel_limit(db_session, monkeypatch):
    monkeypatch.setattr("server.config.LARK_ALERT_WEBHOOK_URL", "")
    monkeypatch.setattr("server.config.NOTIFICATION_ALERT_BURST_PER_MINUTE", 2)

    for index in range(3):
        enqueue_notification_event(
            db_session,
            event_type="gateway_slo_drift",
            object_type="error_fingerprint",
            object_key=f"gateway-timeout-{index}",
            service_name="Gateway",
            summary=f"Gateway SLO drift detected {index}.",
            severity="high",
            risk_level="high",
            workflow_key="gateway_reliability_repair",
        )

    events = db_session.query(NotificationEventRow).order_by(NotificationEventRow.id.asc()).all()
    assert events[-1].status == "suppressed"
    assert events[-1].suppressed_reason == "alert storm rollup emitted"
    deliveries = db_session.query(NotificationDeliveryRow).order_by(NotificationDeliveryRow.id.asc()).all()
    assert [row.event_type for row in deliveries][-1] == "alert_storm_rollup"


def test_lark_card_uses_channel_keyword_and_readable_markdown(monkeypatch):
    monkeypatch.setattr("server.config.LARK_APPROVAL_KEYWORD", "审批")
    card = build_lark_card(
        {
            "service": "Synapse Ops",
            "event_type": "human_gate_request.created",
            "occurred_at": "2026-04-18 14:00:00 UTC",
            "status_or_severity": "p1 · pending",
            "actor_or_source": "risk_evidence_gate",
            "summary": "Workflow requires operator approval before delivery.",
            "next_action": "Open Gates & Delivery and choose approve, reject, or continue retry.",
            "object_refs": {"workflow_run_id": 7, "gate_id": 41, "risk_level": "high"},
            "links": {"审批": "http://localhost:9700/workflows/7?tab=gates"},
        },
        channel="approval",
    )

    assert card["card"]["header"]["title"]["content"].startswith("审批｜人工审批")
    markdown_blocks = [
        element.get("text", {}).get("content", "")
        for element in card["card"]["elements"]
        if element.get("tag") == "div"
    ]
    rendered = "\n".join(markdown_blocks)
    assert "**审批｜人工审批**" in rendered
    assert "**发生了什么**" in rendered
    assert "**下一步动作**" in rendered
    assert "gate_id: `41`" in rendered
