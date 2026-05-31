"""MCP server release records for the release center."""

from __future__ import annotations

from datetime import timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database import utcnow
from server.database_growth import GrowthDiscoveryListingRow
from server.services.growth.serializer import json_dumps
from server.services.releases.mcp_server_catalog import (
    DEFAULT_MCP_SERVER,
    DEFAULT_SURFACES,
    MCP_LOCAL_RUN_PREFIX,
    MCP_RELEASE_CONFIRM_PREFIX,
    MCP_RELEASE_STATUSES,
    MCP_SURFACE_STATUSES,
    MCP_TERMINAL_STATUSES,
)
from server.services.releases.mcp_server_helpers import (
    clean,
    event_to_out,
    git_tag_for,
    json_dump,
    _json_load,
    record_event,
    release_to_out,
    surface_to_out,
    validate_version,
)
from server.services.releases.mcp_server_models import (
    McpServerReleaseEventRow,
    McpServerReleaseRow,
    McpServerSurfaceRow,
)
from server.services.releases.mcp_server_schemas import (
    McpServerReleaseActionRequest,
    McpServerReleaseCreateRequest,
    McpServerReleaseEventOut,
    McpServerReleaseOut,
    McpServerReleasePageOut,
    McpServerReleaseSyncResult,
    McpServerSurfaceOut,
    McpServerSurfacePatchRequest,
)


def list_mcp_server_releases(
    db: Session,
    *,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> McpServerReleasePageOut:
    query = db.query(McpServerReleaseRow)
    if clean(status):
        query = query.filter(McpServerReleaseRow.status == clean(status).lower())
    if clean(search):
        needle = f"%{clean(search).lower()}%"
        query = query.filter(
            or_(
                McpServerReleaseRow.server_name.ilike(needle),
                McpServerReleaseRow.package_name.ilike(needle),
                McpServerReleaseRow.package_version.ilike(needle),
                McpServerReleaseRow.registry_name.ilike(needle),
                McpServerReleaseRow.status.ilike(needle),
            )
        )
    safe_page = max(1, page)
    safe_page_size = max(1, min(page_size, 100))
    total = query.count()
    rows = (
        query.order_by(
            McpServerReleaseRow.updated_at.desc(), McpServerReleaseRow.id.desc()
        )
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
        .all()
    )
    total_pages = (total + safe_page_size - 1) // safe_page_size if total else 0
    return McpServerReleasePageOut(
        items=[release_to_out(row) for row in rows],
        total=total,
        page=safe_page,
        page_size=safe_page_size,
        total_pages=total_pages,
    )


def create_mcp_server_release(
    db: Session, body: McpServerReleaseCreateRequest
) -> McpServerReleaseOut:
    version = validate_version(body.package_version)
    server_key = clean(body.server_key) or DEFAULT_MCP_SERVER["server_key"]
    existing = (
        db.query(McpServerReleaseRow)
        .filter(
            McpServerReleaseRow.server_key == server_key,
            McpServerReleaseRow.package_version == version,
        )
        .first()
    )
    if existing is not None:
        return release_to_out(existing)
    row = McpServerReleaseRow(
        server_key=server_key,
        server_name=DEFAULT_MCP_SERVER["server_name"],
        package_name=DEFAULT_MCP_SERVER["package_name"],
        package_registry=DEFAULT_MCP_SERVER["package_registry"],
        package_version=version,
        registry_name=DEFAULT_MCP_SERVER["registry_name"],
        git_tag=git_tag_for(version),
        install_command=DEFAULT_MCP_SERVER["install_command"],
        release_notes=clean(body.release_notes) or None,
        metadata_json=json_dump(
            {"distribution_channel": "npm_stdio", "remote_mcp": "future"}
        ),
    )
    db.add(row)
    db.flush()
    for key, label in DEFAULT_SURFACES:
        db.add(
            McpServerSurfaceRow(
                mcp_server_release_id=int(row.id),
                surface_key=key,
                surface_label=label,
                status="candidate",
            )
        )
    record_event(
        db,
        row,
        action="initialize_mcp_release",
        from_status=None,
        to_status="planned",
        actor="operator",
        note=body.release_notes,
        metadata={"package_version": version, "package_name": row.package_name},
    )
    db.commit()
    db.refresh(row)
    return release_to_out(row)


def get_mcp_server_release(db: Session, release_id: int) -> McpServerReleaseOut:
    return release_to_out(_require_release(db, release_id))


def list_mcp_server_release_events(
    db: Session, release_id: int
) -> list[McpServerReleaseEventOut]:
    _require_release(db, release_id)
    rows = (
        db.query(McpServerReleaseEventRow)
        .filter(McpServerReleaseEventRow.mcp_server_release_id == release_id)
        .order_by(McpServerReleaseEventRow.id.asc())
        .all()
    )
    return [event_to_out(row) for row in rows]


def run_mcp_release_readiness(
    db: Session, release_id: int, body: McpServerReleaseActionRequest
) -> McpServerReleaseOut:
    row = _require_release(db, release_id)
    if clean(row.status) in MCP_TERMINAL_STATUSES:
        raise ValueError("Terminal MCP server releases cannot run readiness.")
    return _move_to_runner_state(db, row, "readiness_running", "run_readiness", body)


def publish_mcp_npm_release(
    db: Session, release_id: int, body: McpServerReleaseActionRequest
) -> McpServerReleaseOut:
    row = _require_release(db, release_id)
    if clean(row.status) != "ready_to_publish":
        raise ValueError("MCP server release must pass readiness before npm publish.")
    _require_confirm(row, body)
    return _move_to_runner_state(db, row, "npm_publishing", "publish_npm", body)


def submit_mcp_registry_release(
    db: Session, release_id: int, body: McpServerReleaseActionRequest
) -> McpServerReleaseOut:
    row = _require_release(db, release_id)
    if clean(row.status) != "npm_published":
        raise ValueError(
            "MCP server npm package must be published before registry submit."
        )
    return _move_to_runner_state(
        db, row, "registry_submitting", "submit_registry", body
    )


def run_mcp_prod_smoke(
    db: Session, release_id: int, body: McpServerReleaseActionRequest
) -> McpServerReleaseOut:
    row = _require_release(db, release_id)
    if clean(row.status) != "registry_listed":
        raise ValueError("Official MCP Registry listing is required before prod smoke.")
    return _move_to_runner_state(db, row, "prod_smoke_running", "run_prod_smoke", body)


def patch_mcp_surface(
    db: Session, release_id: int, surface_key: str, body: McpServerSurfacePatchRequest
) -> McpServerSurfaceOut:
    release = _require_release(db, release_id)
    row = (
        db.query(McpServerSurfaceRow)
        .filter(
            McpServerSurfaceRow.mcp_server_release_id == release_id,
            McpServerSurfaceRow.surface_key == clean(surface_key),
        )
        .first()
    )
    if row is None:
        raise ValueError("MCP discovery surface not found.")
    if body.status is not None:
        if body.status not in MCP_SURFACE_STATUSES:
            raise ValueError("invalid MCP discovery surface status.")
        row.status = body.status
    if body.listing_url is not None:
        row.listing_url = clean(body.listing_url) or None
    if body.failure_reason is not None:
        row.failure_reason = clean(body.failure_reason) or None
    if body.evidence is not None:
        row.evidence_json = json_dump(body.evidence)
    record_event(
        db,
        release,
        action="surface_updated",
        from_status=release.status,
        to_status=release.status,
        actor="operator",
        metadata={"surface_key": row.surface_key, "surface_status": row.status},
    )
    sync_growth_discovery_listing(db, release)
    db.commit()
    db.refresh(row)
    return surface_to_out(row)


def sync_mcp_server_release_statuses(
    db: Session, *, max_records: int = 50
) -> McpServerReleaseSyncResult:
    rows = (
        db.query(McpServerReleaseRow)
        .filter(
            McpServerReleaseRow.status.in_(
                [
                    "readiness_running",
                    "npm_publishing",
                    "registry_submitting",
                    "prod_smoke_running",
                ]
            )
        )
        .order_by(McpServerReleaseRow.updated_at.asc())
        .limit(max(1, min(max_records, 200)))
        .all()
    )
    result = McpServerReleaseSyncResult(processed_count=len(rows))
    for row in rows:
        status = clean(row.status)
        if status not in MCP_RELEASE_STATUSES:
            result.error_ids.append(int(row.id))
        elif status == "readiness_running":
            result.ready_ids.append(int(row.id))
        elif status == "npm_publishing":
            result.package_published_ids.append(int(row.id))
        elif status == "registry_submitting":
            result.registry_listed_ids.append(int(row.id))
        elif status == "prod_smoke_running":
            result.smoke_passed_ids.append(int(row.id))
        record_event(
            db,
            row,
            action="sync_status",
            from_status=status,
            to_status=status,
            metadata={
                "local_runner": True,
                "message": "Status is owned by local MCP publish worker.",
            },
        )
        row.updated_at = utcnow().astimezone(timezone.utc)
    db.commit()
    return result


def mark_mcp_release_completed(
    db: Session, release_id: int, actor: str = "operator"
) -> McpServerReleaseOut:
    row = _require_release(db, release_id)
    if clean(row.status) != "directories_pending":
        raise ValueError("MCP release must pass prod smoke before completion.")
    from_status = clean(row.status)
    row.status = "completed"
    record_event(
        db,
        row,
        action="complete",
        from_status=from_status,
        to_status="completed",
        actor=actor,
    )
    db.commit()
    return release_to_out(row)


def _require_release(db: Session, release_id: int) -> McpServerReleaseRow:
    row = (
        db.query(McpServerReleaseRow)
        .filter(McpServerReleaseRow.id == release_id)
        .first()
    )
    if row is None:
        raise ValueError("MCP server release not found.")
    return row


def _require_confirm(
    row: McpServerReleaseRow, body: McpServerReleaseActionRequest
) -> None:
    expected = f"{MCP_RELEASE_CONFIRM_PREFIX}{clean(row.package_version)}"
    if clean(body.confirm_phrase) != expected:
        raise ValueError(
            f"confirm_phrase must be {expected} to publish MCP server packages."
        )


def _move_to_runner_state(
    db: Session,
    row: McpServerReleaseRow,
    status: str,
    action: str,
    body: McpServerReleaseActionRequest,
) -> McpServerReleaseOut:
    from_status = clean(row.status) or "planned"
    row.status = status
    row.failure_summary = None
    row.workflow_run_url = f"{MCP_LOCAL_RUN_PREFIX}{status}:{int(row.id)}"
    record_event(
        db,
        row,
        action=action,
        from_status=from_status,
        to_status=status,
        actor=body.actor,
        note=body.note,
        metadata={
            "package_version": clean(row.package_version),
            "runner_state": status,
        },
    )
    db.commit()
    db.refresh(row)
    return release_to_out(row)


def sync_growth_discovery_listing(db: Session, row: McpServerReleaseRow) -> None:
    for surface in row.surfaces:
        if clean(surface.status) not in {"listed", "verified"}:
            continue
        existing = (
            db.query(GrowthDiscoveryListingRow)
            .filter(
                GrowthDiscoveryListingRow.surface == clean(surface.surface_key),
                GrowthDiscoveryListingRow.package_name == clean(row.package_name),
            )
            .first()
        )
        evidence = {"source": "mcp_release", "mcp_release_id": int(row.id)}
        if existing is None:
            db.add(
                GrowthDiscoveryListingRow(
                    surface=clean(surface.surface_key),
                    target_repo="https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server",
                    package_name=clean(row.package_name),
                    listing_url=clean(surface.listing_url) or "",
                    status=clean(surface.status),
                    submission_evidence_json=json_dumps(evidence),
                    verification_evidence_json=json_dumps(
                        _json_load(surface.evidence_json)
                    ),
                    last_checked_at=utcnow(),
                )
            )
        else:
            existing.listing_url = clean(surface.listing_url) or existing.listing_url
            existing.status = clean(surface.status)
            existing.verification_evidence_json = json_dumps(
                _json_load(surface.evidence_json)
            )
            existing.last_checked_at = utcnow()
