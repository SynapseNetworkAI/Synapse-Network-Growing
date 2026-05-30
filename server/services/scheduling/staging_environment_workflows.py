"""Recurring workflow contract for staging environment shutdown."""

from __future__ import annotations

from typing import Any

from server import config


STAGING_ENVIRONMENT_SHUTDOWN_SCHEDULE: dict[str, Any] = {
    "cadence": "daily",
    "suggested_local_time": "23:00",
    "timezone": config.OPERATOR_TIMEZONE,
}

STAGING_ENVIRONMENT_SHUTDOWN_INPUT_QUERY: dict[str, Any] = {
    "project": config.STAGING_ENVIRONMENT_PROJECT,
    "region": config.STAGING_ENVIRONMENT_REGION,
    "cloud_run_services": config.STAGING_CLOUD_RUN_SERVICES,
    "cloud_sql_instance": config.STAGING_CLOUD_SQL_INSTANCE,
}

STAGING_ENVIRONMENT_SHUTDOWN_WORKFLOW: dict[str, Any] = {
    "workflow_key": "staging_environment_shutdown_sweep",
    "display_name": "Staging Environment Shutdown Sweep",
    "description": "Put staging Cloud Run, Cloud Scheduler, and Cloud SQL into a low-cost overnight posture.",
    "trigger_type": "scheduled",
    "owner_role": "runtime_reliability_engineer",
    "schedule": STAGING_ENVIRONMENT_SHUTDOWN_SCHEDULE,
    "input_query": STAGING_ENVIRONMENT_SHUTDOWN_INPUT_QUERY,
    "output_action": {
        "kind": "shutdown_staging_environment",
        "allow_production": False,
        "cloud_run_min_instances": 0,
        "cloud_sql_activation_policy": "NEVER",
    },
    "escalation_rule": {
        "on_permission_denied": "notify_portfolio_operator",
        "on_failure": "notify_portfolio_operator",
        "manual_start_required": True,
    },
    "validation_signal": {"success_metric": "succeeded_count", "min_expected": 0},
}
