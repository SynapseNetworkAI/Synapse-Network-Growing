from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.services.social.distribution_reply_blocks import (
    run_x_social_daily_reply_block_publisher,
)

REPLY_BLOCK_RECURRING_WORKFLOW: dict[str, Any] = {
    "workflow_key": "x_social_daily_reply_block_publisher",
    "display_name": "X Social Daily Reply Block Publisher",
    "description": (
        "Daily agent-reviewed reply block preflight for due X engagement tasks; "
        "queues candidates and records evidence without background public posting."
    ),
    "trigger_type": "scheduled",
    "owner_role": "growth_lead",
    "schedule": {
        "cadence": "daily",
        "window": "afternoon",
        "suggested_local_time": "13:30",
    },
    "input_query": {
        "platform": "x",
        "post_intent": "engagement_reply",
        "requires_source_posts": True,
        "max_replies": 5,
    },
    "output_action": {
        "kind": "create_agent_reviewed_reply_candidates",
        "auto_reply": False,
        "human_gate_required": True,
    },
    "escalation_rule": {
        "on_empty": "no_op",
        "on_auth_or_policy_failure": "operator_review",
    },
    "validation_signal": {"success_metric": "reply_ids_or_blocked_reason"},
}

REPLY_BLOCK_DRY_RUN: dict[str, Any] = {
    "platform": "x",
    "cadence": "daily",
    "source": "engagement_reply_assets",
    "max_replies": 5,
    "auto_reply": False,
    "human_gate_required": True,
}


def run_reply_block_workflow(db: Session) -> Any:
    return run_x_social_daily_reply_block_publisher(db)
