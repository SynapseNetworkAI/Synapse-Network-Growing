"""Recurring workflow contract for Secret Manager version cleanup."""

from __future__ import annotations

from typing import Any

from server import config


SECRET_MANAGER_CLEANUP_SCHEDULE: dict[str, Any] = {
    "cadence": "interval",
    "interval_minutes": 30,
    "timezone": config.OPERATOR_TIMEZONE,
}

SECRET_MANAGER_CLEANUP_INPUT_QUERY: dict[str, Any] = {
    "projects": config.SECRET_MANAGER_CLEANUP_PROJECTS,
    "keep": config.SECRET_MANAGER_CLEANUP_KEEP_VERSIONS,
}

SECRET_MANAGER_CLEANUP_WORKFLOW: dict[str, Any] = {
    "workflow_key": "secret_manager_version_cleanup_sweep",
    "display_name": "Secret Manager Version Cleanup Sweep",
    "description": "Destroy old active Secret Manager versions while preserving the newest rollback window.",
    "trigger_type": "scheduled",
    "owner_role": "runtime_reliability_engineer",
    "schedule": SECRET_MANAGER_CLEANUP_SCHEDULE,
    "input_query": SECRET_MANAGER_CLEANUP_INPUT_QUERY,
    "output_action": {
        "kind": "destroy_old_secret_manager_versions",
        "payload_access": "metadata_only",
        "active_states": ["ENABLED", "DISABLED"],
    },
    "escalation_rule": {
        "on_permission_denied": "notify_portfolio_operator",
        "on_failure": "notify_portfolio_operator",
    },
    "validation_signal": {"success_metric": "destroyed_count", "min_expected": 0},
}
