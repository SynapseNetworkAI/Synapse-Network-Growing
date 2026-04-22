from server.services.runtime.notification_policy import resolve_notification_policy


def test_notification_policy_routes_human_gate_to_approval():
    policy = resolve_notification_policy(
        event_type="human_gate_request.created",
        object_type="human_gate",
        object_key="42",
        risk_level="high",
        status="pending",
        requires_human=True,
        workflow_key="agent_self_repair",
        current_state="awaiting_operator",
    )

    assert policy.channel == "approval"
    assert policy.priority == "p1"
    assert policy.should_send_now is True
    assert "approval:human_gate_request.created:human_gate:42" in policy.dedupe_key


def test_notification_policy_routes_high_severity_to_alert():
    policy = resolve_notification_policy(
        event_type="error_logged",
        object_type="error_fingerprint",
        object_key="runtime_log_error:abc",
        severity="critical",
        risk_level="critical",
    )

    assert policy.channel == "alert"
    assert policy.priority == "p0"
    assert policy.should_send_now is True


def test_notification_policy_routes_release_events_to_release():
    policy = resolve_notification_policy(
        event_type="pr_opened",
        object_type="workflow_run",
        object_key="7",
        severity="normal",
        risk_level="medium",
    )

    assert policy.channel == "release"
    assert policy.priority == "p2"
    assert policy.should_send_now is True


def test_notification_policy_routes_blocking_delivery_failures_to_alert():
    policy = resolve_notification_policy(
        event_type="pr_creation_failed",
        object_type="workflow_run",
        object_key="7",
        severity="normal",
        risk_level="normal",
    )

    assert policy.channel == "alert"
    assert policy.should_send_now is True


def test_notification_policy_keeps_lifecycle_events_digest_only():
    policy = resolve_notification_policy(
        event_type="workflow_run_started",
        object_type="workflow_run",
        object_key="7",
        severity="normal",
        risk_level="normal",
    )

    assert policy.channel == "digest"
    assert policy.should_send_now is False


def test_notification_policy_keeps_normal_gate_decisions_digest_only():
    policy = resolve_notification_policy(
        event_type="human_gate_request.decided",
        object_type="human_gate",
        object_key="42",
        status="approved",
        risk_level="normal",
    )

    assert policy.channel == "digest"
    assert policy.should_send_now is False


def test_notification_policy_suppresses_atom_success_noise():
    policy = resolve_notification_policy(
        event_type="atom_invocation_succeeded",
        object_type="workflow_run",
        object_key="7",
        severity="info",
        risk_level="low",
    )

    assert policy.channel == "none"
    assert policy.should_send_now is False
