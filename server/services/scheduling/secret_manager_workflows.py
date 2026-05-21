"""Recurring workflow contract for Secret Manager version cleanup."""

from __future__ import annotations

from typing import Any

from server import config
from server.services.secret_manager_cleanup import cleanup_secret_manager_versions
from server.services.result_objects import ServiceObjectResult, service_object_result

SECRET_MANAGER_VERSION_CLEANUP_WORKFLOW: dict[str, Any] = {
    "workflow_key": "secret_manager_version_cleanup_sweep",
    "display_name": "Secret Manager Version Cleanup Sweep",
    "description": "Destroy old Secret Manager versions across staging and production, keeping the newest three active versions per secret.",
    "trigger_type": "scheduled",
    "owner_role": "runtime_reliability_engineer",
    "schedule": {
        "cadence": "daily",
        "suggested_local_time": "12:00",
        "timezone": config.OPERATOR_TIMEZONE,
    },
    "input_query": {
        "projects": config.SECRET_MANAGER_CLEANUP_PROJECTS,
        "active_states": ["ENABLED", "DISABLED"],
        "keep": config.SECRET_MANAGER_CLEANUP_KEEP_VERSIONS,
    },
    "output_action": {
        "kind": "destroy_old_secret_manager_versions",
        "read_secret_payload": False,  # nosec B105 - policy flag, not a password
    },
    "escalation_rule": {
        "on_permission_denied": "notify_portfolio_operator",
        "on_failure": "notify_portfolio_operator",
    },
    "validation_signal": {"success_metric": "destroyed_count", "min_expected": 0},
}


@service_object_result
def run_secret_manager_version_cleanup_workflow(
    *, dry_run: bool
) -> ServiceObjectResult:
    return cleanup_secret_manager_versions(
        projects=config.SECRET_MANAGER_CLEANUP_PROJECTS,
        keep=config.SECRET_MANAGER_CLEANUP_KEEP_VERSIONS,
        dry_run=dry_run,
    )
