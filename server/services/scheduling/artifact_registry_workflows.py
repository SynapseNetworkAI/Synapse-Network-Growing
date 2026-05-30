"""Recurring workflow contract for Artifact Registry cleanup."""

from __future__ import annotations

from typing import Any

from server import config
from server.services.artifact_registry_cleanup import cleanup_artifact_registry_versions
from server.services.result_objects import ServiceObjectResult, service_object_result


ARTIFACT_REGISTRY_CLEANUP_SCHEDULE: dict[str, Any] = {
    "cadence": "interval",
    "interval_minutes": 30,
    "timezone": config.OPERATOR_TIMEZONE,
}

ARTIFACT_REGISTRY_CLEANUP_INPUT_QUERY: dict[str, Any] = {
    "targets": config.ARTIFACT_REGISTRY_CLEANUP_TARGETS,
    "projects": config.ARTIFACT_REGISTRY_CLEANUP_PROJECTS,
    "region": config.ARTIFACT_REGISTRY_CLEANUP_REGION,
    "repository": config.ARTIFACT_REGISTRY_CLEANUP_REPOSITORY,
    "keep": config.ARTIFACT_REGISTRY_CLEANUP_KEEP_VERSIONS,
    "older_than_days": config.ARTIFACT_REGISTRY_CLEANUP_OLDER_THAN_DAYS,
}


ARTIFACT_REGISTRY_CLEANUP_WORKFLOW: dict[str, Any] = {
    "workflow_key": "artifact_registry_cleanup_sweep",
    "display_name": "Artifact Registry Cleanup Sweep",
    "description": "Clean stale Artifact Registry Docker images while preserving recent and promoted release versions.",
    "trigger_type": "scheduled",
    "owner_role": "runtime_reliability_engineer",
    "schedule": ARTIFACT_REGISTRY_CLEANUP_SCHEDULE,
    "input_query": ARTIFACT_REGISTRY_CLEANUP_INPUT_QUERY,
    "output_action": {
        "kind": "cleanup_artifact_registry_versions",
        "read_image_payload": False,
        "preserve_tag_prefixes": ["prod-", "production-", "promoted-", "release-"],
    },
    "escalation_rule": {
        "on_permission_denied": "notify_portfolio_operator",
        "on_failure": "notify_portfolio_operator",
        "production_apply_requires_human_gate": True,
    },
    "validation_signal": {"success_metric": "deleted_count", "min_expected": 0},
}


@service_object_result
def run_artifact_registry_cleanup_workflow(*, dry_run: bool) -> ServiceObjectResult:
    return cleanup_artifact_registry_versions(
        targets=config.ARTIFACT_REGISTRY_CLEANUP_TARGETS,
        projects=config.ARTIFACT_REGISTRY_CLEANUP_PROJECTS,
        region=config.ARTIFACT_REGISTRY_CLEANUP_REGION,
        repository=config.ARTIFACT_REGISTRY_CLEANUP_REPOSITORY,
        keep=config.ARTIFACT_REGISTRY_CLEANUP_KEEP_VERSIONS,
        older_than_days=config.ARTIFACT_REGISTRY_CLEANUP_OLDER_THAN_DAYS,
        dry_run=dry_run,
    )
