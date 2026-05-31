from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.services.growth.provider_sources import run_enabled_provider_sources


GROWTH_PROVIDER_SOURCE_WORKFLOW: dict[str, Any] = {
    "workflow_key": "growth_provider_source_sweep",
    "display_name": "Growth Provider Source Sweep",
    "description": (
        "Read enabled growth source configs and create/reuse provider leads plus "
        "human-reviewed outreach drafts."
    ),
    "trigger_type": "scheduled",
    "owner_role": "growth_lead",
    "schedule": {"cadence": "interval", "interval_hours": 6},
    "input_query": {
        "lead_type": "provider",
        "source_configs": "enabled",
        "send_policy": "manual_only",
    },
    "output_action": {
        "kind": "run_growth_provider_sources",
        "auto_send": False,
        "human_gate_required": True,
    },
    "escalation_rule": {
        "on_empty": "diagnostic_only",
        "on_failure": "notify_portfolio_operator",
    },
    "validation_signal": {"success_metric": "created_or_reused_lead_count"},
}


def run_growth_provider_source_workflow(
    db: Session, *, dry_run: bool
) -> dict[str, Any]:
    return run_enabled_provider_sources(db, dry_run=dry_run)
