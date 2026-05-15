"""Production GitHub Actions workflow routing for release tasks."""

from __future__ import annotations

PRODUCTION_WORKFLOW_FILE = "deploy-production.yml"
PROVIDER_PRODUCTION_WORKFLOW_FILE = "deploy-production-provider.yml"

_SYNAPSE_NETWORK_WORKFLOWS = {
    "gateway": "deploy-production-gateway.yml",
    "gateway-admin": "deploy-production-admin.yml",
    "admin-front": "deploy-production-frontends.yml",
    "user-front": "deploy-production-frontends.yml",
    "docs-front": "deploy-production-frontends.yml",
}

_PROJECT_WORKFLOWS = {
    "synapse-network": _SYNAPSE_NETWORK_WORKFLOWS,
    "synapse-network-provider": {
        "provider-service": PROVIDER_PRODUCTION_WORKFLOW_FILE,
    },
}


def _clean(value: object) -> str:
    return str(value or "").strip()


def production_workflow_file_for_service(
    *,
    configured_workflow_file: str | None,
    project_key: str,
    service_key: str,
) -> str:
    """Resolve the concrete production workflow for a project service.

    Project policies historically stored ``deploy-production.yml`` as the generic
    production runner. Treat that default as a signal to use the modular
    service-specific workflow. Custom policy values remain honored.
    """

    configured = _clean(configured_workflow_file)
    if configured and configured != PRODUCTION_WORKFLOW_FILE:
        return configured
    project_workflows = _PROJECT_WORKFLOWS.get(_clean(project_key).lower(), {})
    return project_workflows.get(_clean(service_key).lower(), PRODUCTION_WORKFLOW_FILE)
