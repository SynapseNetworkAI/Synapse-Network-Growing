"""Notification routing policy for Ops Lark channels."""

from __future__ import annotations

from dataclasses import dataclass


_SEVERITY_RANK = {
    "info": 0,
    "low": 0,
    "normal": 1,
    "warning": 1,
    "high": 2,
    "critical": 3,
}

_RISK_RANK = {
    "none": 0,
    "low": 0,
    "normal": 1,
    "medium": 1,
    "high": 2,
    "critical": 3,
}

_NO_SEND_EVENTS = {
    "atom_invocation_succeeded",
    "workflow_artifact_created",
    "blackboard_snapshot_created",
    "workflow_transition_recorded",
}

_DIGEST_ONLY_EVENTS = {
    "requirement_created",
    "workflow_run_started",
    "workflow_run_succeeded",
}

_ABNORMAL_GATE_DECISIONS = {
    "blocked",
    "continue_retry_failed",
    "failed",
    "reject",
    "rejected",
}

_APPROVAL_EVENTS = {
    "human_gate_request.created",
    "risk_evidence_gate.human_required",
    "approval_manual_required",
    "approval_required",
    "deploy_requested",
}

_RELEASE_EVENTS = {
    "pr_opened",
    "pr_creation_failed",
    "branch_pushed",
    "release_ready",
    "release_blocked",
    "ci_failed",
    "ci_passed",
    "deploy_succeeded",
    "deploy_failed",
    "observing_started",
    "observing_succeeded",
    "observing_failed",
}

_ALERT_EVENTS = {
    "ci_failed",
    "gateway_slo_drift",
    "pr_creation_failed",
    "runner_crashed",
    "runner_stale",
    "workflow_retry_budget_exhausted",
    "kill_switch_triggered",
    "lark_alert_delivery_failed",
}


@dataclass(frozen=True)
class NotificationPolicy:
    """Resolved notification route for one event."""

    channel: str
    priority: str
    should_send_now: bool
    dedupe_key: str
    next_action: str
    reason: str


def normalize_severity(value: str | None) -> str:
    """Normalize external severity labels to the policy vocabulary."""

    normalized = str(value or "normal").strip().lower() or "normal"
    if normalized == "warning":
        return "normal"
    return normalized if normalized in _SEVERITY_RANK else "normal"


def normalize_risk_level(value: str | None) -> str:
    """Normalize risk labels to the policy vocabulary."""

    normalized = str(value or "normal").strip().lower() or "normal"
    return normalized if normalized in _RISK_RANK else "normal"


def priority_for(*, severity: str | None = None, risk_level: str | None = None) -> str:
    """Return p0-p3 priority from severity and risk."""

    severity_rank = _SEVERITY_RANK.get(normalize_severity(severity), 1)
    risk_rank = _RISK_RANK.get(normalize_risk_level(risk_level), 1)
    rank = max(severity_rank, risk_rank)
    if rank >= 3:
        return "p0"
    if rank == 2:
        return "p1"
    if rank == 1:
        return "p2"
    return "p3"


def severity_rank(value: str | None) -> int:
    """Return comparable severity rank for queue escalation checks."""

    return _SEVERITY_RANK.get(normalize_severity(value), 1)


def risk_rank(value: str | None) -> int:
    """Return comparable risk rank for queue escalation checks."""

    return _RISK_RANK.get(normalize_risk_level(value), 1)


def resolve_notification_policy(
    *,
    event_type: str,
    object_type: str,
    object_key: str,
    severity: str | None = None,
    risk_level: str | None = None,
    status: str | None = None,
    requires_human: bool = False,
    workflow_key: str | None = None,
    current_state: str | None = None,
) -> NotificationPolicy:
    """Resolve the Lark channel and dedupe key for an Ops event.

    The policy keeps Lark high signal: normal workflow state detail remains in the
    Ops Console, while alert, approval, workflow, and release events are routed
    to their dedicated groups.
    """

    event = str(event_type or "event").strip().lower() or "event"
    obj_type = str(object_type or "object").strip().lower() or "object"
    obj_key = str(object_key or "unknown").strip() or "unknown"
    normalized_severity = normalize_severity(severity)
    normalized_risk = normalize_risk_level(risk_level)
    normalized_status = str(status or "").strip().lower()
    priority = priority_for(severity=normalized_severity, risk_level=normalized_risk)
    risk_rank = _RISK_RANK.get(normalized_risk, 1)
    severity_rank = _SEVERITY_RANK.get(normalized_severity, 1)

    if event in _NO_SEND_EVENTS:
        return NotificationPolicy(
            channel="none",
            priority=priority,
            should_send_now=False,
            dedupe_key=f"none:{event}:{obj_type}:{obj_key}",
            next_action="No Lark notification required; inspect the workflow detail if needed.",
            reason="low-signal runtime detail",
        )

    if event in _DIGEST_ONLY_EVENTS:
        return NotificationPolicy(
            channel="digest",
            priority=priority,
            should_send_now=False,
            dedupe_key=f"digest:{event}:{obj_type}:{obj_key}",
            next_action="No immediate action; keep this lifecycle event in Ops Console history.",
            reason="digest-only lifecycle event",
        )

    if event == "human_gate_request.decided" and normalized_status not in _ABNORMAL_GATE_DECISIONS:
        return NotificationPolicy(
            channel="digest",
            priority=priority,
            should_send_now=False,
            dedupe_key=f"digest:{event}:{obj_type}:{obj_key}",
            next_action="No immediate action; gate decision is available in Ops Console history.",
            reason="digest-only normal gate decision",
        )

    high_risk_failure = risk_rank >= 2 and any(token in event or token in normalized_status for token in ("failed", "blocked", "stale", "exhausted"))
    if event in _ALERT_EVENTS or severity_rank >= 2 or high_risk_failure:
        return NotificationPolicy(
            channel="alert",
            priority=priority,
            should_send_now=True,
            dedupe_key=_dedupe_key("alert", event, obj_type, obj_key, normalized_risk, workflow_key),
            next_action="Open Ops Console, inspect the linked workflow evidence, and decide whether to pause or recover the system.",
            reason="P0/P1 alert route",
        )

    if requires_human or event in _APPROVAL_EVENTS or "awaiting_operator" in {normalized_status, str(current_state or "").strip().lower()}:
        return NotificationPolicy(
            channel="approval",
            priority=priority,
            should_send_now=True,
            dedupe_key=_dedupe_key("approval", event, obj_type, obj_key, normalized_risk, workflow_key),
            next_action="Review the human gate in Ops Console and choose approve, reject, or continue retry.",
            reason="human decision required",
        )

    if event in _RELEASE_EVENTS or event.startswith("release_") or event.startswith("pr_"):
        channel = "alert" if event in {"deploy_failed", "observing_failed"} and risk_rank >= 2 else "release"
        return NotificationPolicy(
            channel=channel,
            priority=priority,
            should_send_now=True,
            dedupe_key=_dedupe_key(channel, event, obj_type, obj_key, normalized_risk, workflow_key),
            next_action="Open the release or workflow delivery panel and inspect PR, CI, deploy, or observation evidence.",
            reason="delivery/release event",
        )

    if priority == "p3":
        return NotificationPolicy(
            channel="digest",
            priority=priority,
            should_send_now=False,
            dedupe_key=f"digest:{event}:{obj_type}:{obj_key}",
            next_action="No immediate action; include this event in the operator digest.",
            reason="digest-only info event",
        )

    return NotificationPolicy(
        channel="requirement",
        priority=priority,
        should_send_now=True,
        dedupe_key=_dedupe_key("requirement", event, obj_type, obj_key, normalized_risk, workflow_key),
        next_action="Open the requirement or workflow page to monitor progress.",
        reason="workflow notification route",
    )


def _dedupe_key(
    channel: str,
    event_type: str,
    object_type: str,
    object_key: str,
    risk_level: str,
    workflow_key: str | None,
) -> str:
    workflow_part = str(workflow_key or "").strip()
    suffix = ":".join(part for part in (workflow_part, risk_level) if part)
    return f"{channel}:{event_type}:{object_type}:{object_key}" + (f":{suffix}" if suffix else "")
