"""Shared helpers for MCP server release services."""

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from server.services.releases.mcp_server_catalog import DEFAULT_MCP_SERVER
from server.services.releases.mcp_server_models import (
    McpServerReleaseEventRow,
    McpServerReleaseRow,
    McpServerSurfaceRow,
)
from server.services.releases.mcp_server_schemas import (
    McpServerReleaseEventOut,
    McpServerReleaseOut,
    McpServerSurfaceOut,
)


def clean(value: object) -> str:
    return str(value or "").strip()


def json_dump(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_load(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def validate_version(value: str) -> str:
    version = clean(value)
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
        raise ValueError("package_version must be a SemVer value, for example 0.1.0.")
    return version


def git_tag_for(version: str) -> str:
    return f"mcp/v{version}"


def package_url_for(package_name: str, version: str) -> str:
    template = DEFAULT_MCP_SERVER["package_url_template"]
    return template.format(package_name=package_name, version=version)


def surface_to_out(row: McpServerSurfaceRow) -> McpServerSurfaceOut:
    return McpServerSurfaceOut(
        id=int(row.id),
        mcp_server_release_id=int(row.mcp_server_release_id),
        surface_key=clean(row.surface_key),
        surface_label=clean(row.surface_label),
        status=clean(row.status) or "candidate",
        listing_url=clean(row.listing_url) or None,
        failure_reason=clean(row.failure_reason) or None,
        evidence=_json_load(row.evidence_json),
        updated_at=row.updated_at,
    )


def release_to_out(row: McpServerReleaseRow) -> McpServerReleaseOut:
    return McpServerReleaseOut(
        id=int(row.id),
        server_key=clean(row.server_key),
        server_name=clean(row.server_name),
        package_name=clean(row.package_name),
        package_registry=clean(row.package_registry) or "npm",
        package_version=clean(row.package_version),
        registry_name=clean(row.registry_name),
        git_tag=clean(row.git_tag) or None,
        install_command=clean(row.install_command),
        status=clean(row.status) or "planned",
        package_url=clean(row.package_url) or None,
        registry_url=clean(row.registry_url) or None,
        workflow_run_url=clean(row.workflow_run_url) or None,
        failure_summary=clean(row.failure_summary) or None,
        release_notes=clean(row.release_notes) or None,
        smoke_evidence=_json_load(row.smoke_evidence_json),
        metadata=_json_load(row.metadata_json),
        surfaces=[surface_to_out(surface) for surface in row.surfaces],
        published_at=row.published_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def event_to_out(row: McpServerReleaseEventRow) -> McpServerReleaseEventOut:
    return McpServerReleaseEventOut(
        id=int(row.id),
        mcp_server_release_id=int(row.mcp_server_release_id),
        action=clean(row.action),
        from_status=clean(row.from_status) or None,
        to_status=clean(row.to_status) or None,
        actor=clean(row.actor) or None,
        note=clean(row.note) or None,
        workflow_run_url=clean(row.workflow_run_url) or None,
        error_summary=clean(row.error_summary) or None,
        metadata=_json_load(row.metadata_json),
        created_at=row.created_at,
    )


def record_event(
    db: Session,
    row: McpServerReleaseRow,
    *,
    action: str,
    from_status: str | None,
    to_status: str | None,
    actor: str | None = None,
    note: str | None = None,
    error_summary: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        McpServerReleaseEventRow(
            mcp_server_release_id=int(row.id),
            action=action,
            from_status=clean(from_status) or None,
            to_status=clean(to_status) or None,
            actor=clean(actor) or None,
            note=clean(note) or None,
            workflow_run_url=clean(row.workflow_run_url) or None,
            error_summary=clean(error_summary) or None,
            metadata_json=json_dump(metadata or {}),
        )
    )
