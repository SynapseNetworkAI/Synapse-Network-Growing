"""Staging workflow routing for release tasks."""

from __future__ import annotations

SYNAPSE_NETWORK_PROJECT_KEY = "synapse-network"
STAGING_WORKFLOW_FILE = "deploy-staging.yml"

SYNAPSE_NETWORK_STAGING_WORKFLOW_BY_SERVICE = {
    (SYNAPSE_NETWORK_PROJECT_KEY, "gateway"): "deploy-staging-gateway.yml",
    (SYNAPSE_NETWORK_PROJECT_KEY, "gateway-admin"): "deploy-staging-admin.yml",
    (SYNAPSE_NETWORK_PROJECT_KEY, "admin-front"): "deploy-staging-frontends.yml",
    (SYNAPSE_NETWORK_PROJECT_KEY, "user-front"): "deploy-staging-frontends.yml",
    (SYNAPSE_NETWORK_PROJECT_KEY, "docs-front"): "deploy-staging-frontends.yml",
}

CONFIGURED_WORKFLOW_DEFAULTS = {
    "": STAGING_WORKFLOW_FILE,
    "None": STAGING_WORKFLOW_FILE,
}


def staging_workflow_file_for_service(
    *,
    configured_workflow_file: str | None,
    project_key: str | None,
    service_key: str | None,
) -> str:
    """Return the workflow file used by a staging Release Task."""

    project = str(project_key or "").strip()
    service = str(service_key or "").strip().lower()
    configured = str(configured_workflow_file).strip()
    default_workflow = CONFIGURED_WORKFLOW_DEFAULTS.get(configured, configured)
    return SYNAPSE_NETWORK_STAGING_WORKFLOW_BY_SERVICE.get(
        (project, service), default_workflow
    )
