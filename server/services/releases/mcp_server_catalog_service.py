"""Catalog services for MCP server release matrix."""

from __future__ import annotations

from sqlalchemy import inspect, or_, text
from sqlalchemy.orm import Session

from server.database import utcnow
from server.services.releases.mcp_server_catalog import (
    DEFAULT_DISCOVERY_SURFACES,
    DEFAULT_MCP_SERVER,
    MCP_SERVER_TRANSPORT_KINDS,
    MCP_SURFACE_CATEGORIES,
)
from server.services.releases.mcp_server_helpers import (
    clean,
    discovery_surface_to_out,
    json_dump,
    release_to_out,
    server_to_out,
    validate_version,
)
from server.services.releases.mcp_server_models import (
    McpDiscoverySurfaceRow,
    McpServerReleaseRow,
    McpServerRow,
    McpServerSurfaceRow,
)
from server.services.releases.mcp_server_schemas import (
    McpDiscoverySurfaceOut,
    McpServerCreateRequest,
    McpServerOut,
    McpServerPageOut,
    McpServerReleaseCreateRequest,
    McpServerReleaseOut,
)


def migrate_mcp_server_release_schema(engine_) -> None:
    insp = inspect(engine_)
    tables = insp.get_table_names()
    if "mcp_servers" not in tables:
        McpServerRow.__table__.create(bind=engine_, checkfirst=True)
    if "mcp_discovery_surfaces" not in tables:
        McpDiscoverySurfaceRow.__table__.create(bind=engine_, checkfirst=True)
    if "mcp_server_releases" in tables:
        existing = {
            column["name"] for column in insp.get_columns("mcp_server_releases")
        }
        if "mcp_server_id" not in existing:
            _add_column(engine_, "mcp_server_releases", "mcp_server_id", "INTEGER")
    if "mcp_server_surfaces" in tables:
        existing = {
            column["name"] for column in insp.get_columns("mcp_server_surfaces")
        }
        for column, column_type in {
            "category": "TEXT DEFAULT 'directory' NOT NULL",
            "submission_url": "TEXT",
            "operator_note": "TEXT",
            "last_checked_at": "TIMESTAMP",
        }.items():
            if column not in existing:
                _add_column(engine_, "mcp_server_surfaces", column, column_type)


def _add_column(engine_, table: str, column: str, column_type: str) -> None:
    with engine_.connect() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))
        conn.commit()


def ensure_discovery_surfaces(db: Session) -> None:
    for definition in DEFAULT_DISCOVERY_SURFACES:
        surface_key = clean(definition["surface_key"])
        row = (
            db.query(McpDiscoverySurfaceRow)
            .filter(McpDiscoverySurfaceRow.surface_key == surface_key)
            .first()
        )
        values = _surface_definition_values(definition)
        if row is None:
            db.add(McpDiscoverySurfaceRow(**values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
    db.commit()
    from server.services.releases.mcp_surface_config_service import (
        ensure_surface_configs,
    )

    ensure_surface_configs(db)


def ensure_default_mcp_server(db: Session) -> McpServerRow:
    ensure_discovery_surfaces(db)
    row = (
        db.query(McpServerRow)
        .filter(McpServerRow.server_key == DEFAULT_MCP_SERVER["server_key"])
        .first()
    )
    values = _default_server_values()
    if row is None:
        row = McpServerRow(**values)
        db.add(row)
        db.commit()
        db.refresh(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
        db.commit()
    _backfill_legacy_releases(db, row)
    return row


def list_mcp_servers(
    db: Session,
    *,
    search: str | None = None,
    transport_kind: str | None = None,
    status: str | None = None,
    surface_category: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> McpServerPageOut:
    ensure_default_mcp_server(db)
    query = db.query(McpServerRow)
    if clean(search):
        needle = f"%{clean(search).lower()}%"
        query = query.filter(
            or_(
                McpServerRow.server_name.ilike(needle),
                McpServerRow.repo_full_name.ilike(needle),
                McpServerRow.package_name.ilike(needle),
                McpServerRow.registry_name.ilike(needle),
            )
        )
    if clean(transport_kind):
        query = query.filter(McpServerRow.transport_kind == clean(transport_kind))
    if clean(status):
        query = query.filter(McpServerRow.status == clean(status))
    if clean(surface_category):
        query = query.filter(
            McpServerRow.releases.any(
                McpServerReleaseRow.surfaces.any(
                    McpServerSurfaceRow.category == clean(surface_category)
                )
            )
        )
    safe_page = max(1, page)
    safe_page_size = max(1, min(page_size, 100))
    total = query.count()
    rows = (
        query.order_by(McpServerRow.updated_at.desc(), McpServerRow.id.desc())
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
        .all()
    )
    return McpServerPageOut(
        items=[server_to_out(row) for row in rows],
        total=total,
        page=safe_page,
        page_size=safe_page_size,
        total_pages=(total + safe_page_size - 1) // safe_page_size if total else 0,
    )


def create_mcp_server(db: Session, body: McpServerCreateRequest) -> McpServerOut:
    ensure_discovery_surfaces(db)
    server_key = clean(body.server_key)
    if not server_key:
        raise ValueError("server_key is required.")
    if clean(body.transport_kind) not in MCP_SERVER_TRANSPORT_KINDS:
        raise ValueError("invalid MCP server transport_kind.")
    existing = (
        db.query(McpServerRow).filter(McpServerRow.server_key == server_key).first()
    )
    if existing is not None:
        return server_to_out(existing)
    row = McpServerRow(
        server_key=server_key,
        server_name=clean(body.server_name),
        repo_full_name=clean(body.repo_full_name),
        repo_url=clean(body.repo_url),
        local_repo_path=clean(body.local_repo_path) or None,
        package_name=clean(body.package_name),
        package_registry=clean(body.package_registry) or "npm",
        registry_name=clean(body.registry_name),
        transport_kind=clean(body.transport_kind),
        remote_endpoint_url=clean(body.remote_endpoint_url) or None,
        install_command=clean(body.install_command),
        tools_json=json_dump({"items": body.tools}),
        security_boundary=clean(body.security_boundary) or None,
        status=clean(body.status) or "active",
        metadata_json=json_dump(body.metadata),
    )
    _validate_server_row(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return server_to_out(row)


def get_mcp_server(db: Session, server_id: int) -> McpServerOut:
    return server_to_out(_require_server(db, server_id))


def create_release_for_server(
    db: Session, server_id: int, body: McpServerReleaseCreateRequest
) -> McpServerReleaseOut:
    server = _require_server(db, server_id)
    version = validate_version(body.package_version)
    existing = (
        db.query(McpServerReleaseRow)
        .filter(
            McpServerReleaseRow.mcp_server_id == int(server.id),
            McpServerReleaseRow.package_version == version,
        )
        .first()
    )
    if existing is not None:
        return release_to_out(existing)
    row = _build_release_row(server, version, body.release_notes)
    db.add(row)
    db.flush()
    create_release_surfaces(db, row, server)
    db.commit()
    db.refresh(row)
    return release_to_out(row)


def list_discovery_surfaces(db: Session) -> list[McpDiscoverySurfaceOut]:
    ensure_discovery_surfaces(db)
    rows = (
        db.query(McpDiscoverySurfaceRow)
        .order_by(
            McpDiscoverySurfaceRow.priority.asc(), McpDiscoverySurfaceRow.id.asc()
        )
        .all()
    )
    return [discovery_surface_to_out(row) for row in rows]


def create_release_surfaces(
    db: Session, release: McpServerReleaseRow, server: McpServerRow
) -> None:
    ensure_discovery_surfaces(db)
    rows = (
        db.query(McpDiscoverySurfaceRow)
        .order_by(
            McpDiscoverySurfaceRow.priority.asc(), McpDiscoverySurfaceRow.id.asc()
        )
        .all()
    )
    for surface in rows:
        db.add(
            McpServerSurfaceRow(
                mcp_server_release_id=int(release.id),
                surface_key=surface.surface_key,
                surface_label=surface.surface_label,
                category=surface.category,
                status=_initial_surface_status(surface, server),
                submission_url=surface.submission_url,
            )
        )


def sync_release_surfaces(db: Session, release: McpServerReleaseRow) -> None:
    server = release.server or _server_from_release(db, release)
    for surface in release.surfaces:
        surface.status = _project_surface_status(surface, release, server)
        surface.last_checked_at = utcnow()
    db.commit()


def _surface_definition_values(definition: dict[str, object]) -> dict[str, object]:
    category = clean(definition["category"])
    if category not in MCP_SURFACE_CATEGORIES:
        raise ValueError(f"invalid MCP surface category: {category}")
    return {
        "surface_key": clean(definition["surface_key"]),
        "surface_label": clean(definition["surface_label"]),
        "category": category,
        "requires_npm": 1 if definition.get("requires_npm") else 0,
        "requires_remote_http": 1 if definition.get("requires_remote_http") else 0,
        "supports_auto_submit": 1 if definition.get("supports_auto_submit") else 0,
        "submission_url": clean(definition.get("submission_url")) or None,
        "docs_url": clean(definition.get("docs_url")) or None,
        "priority": int(definition.get("priority") or 100),
        "status": "active",
    }


def _default_server_values() -> dict[str, object]:
    return {
        "server_key": DEFAULT_MCP_SERVER["server_key"],
        "server_name": DEFAULT_MCP_SERVER["server_name"],
        "repo_full_name": DEFAULT_MCP_SERVER["repo_full_name"],
        "repo_url": DEFAULT_MCP_SERVER["repo_url"],
        "local_repo_path": DEFAULT_MCP_SERVER["local_repo_path"],
        "package_name": DEFAULT_MCP_SERVER["package_name"],
        "package_registry": DEFAULT_MCP_SERVER["package_registry"],
        "registry_name": DEFAULT_MCP_SERVER["registry_name"],
        "transport_kind": DEFAULT_MCP_SERVER["transport_kind"],
        "remote_endpoint_url": None,
        "install_command": DEFAULT_MCP_SERVER["install_command"],
        "tools_json": json_dump({"items": DEFAULT_MCP_SERVER["tools"]}),
        "security_boundary": DEFAULT_MCP_SERVER["security_boundary"],
        "status": "active",
        "metadata_json": json_dump({"source": "default_catalog"}),
    }


def _build_release_row(
    server: McpServerRow, version: str, release_notes: str | None
) -> McpServerReleaseRow:
    return McpServerReleaseRow(
        mcp_server_id=int(server.id),
        server_key=server.server_key,
        server_name=server.server_name,
        package_name=server.package_name,
        package_registry=server.package_registry,
        package_version=version,
        registry_name=server.registry_name,
        git_tag=f"mcp/v{version}",
        install_command=server.install_command,
        release_notes=clean(release_notes) or None,
        metadata_json=json_dump({"distribution_channel": server.transport_kind}),
    )


def _initial_surface_status(
    surface: McpDiscoverySurfaceRow, server: McpServerRow
) -> str:
    if surface.requires_remote_http and clean(server.transport_kind) == "stdio":
        return "blocked_requires_remote_mcp"
    if surface.requires_npm:
        return "blocked_missing_artifact"
    return "candidate"


def _project_surface_status(
    surface: McpServerSurfaceRow, release: McpServerReleaseRow, server: McpServerRow
) -> str:
    current = clean(surface.status)
    if current in {
        "listed",
        "verified",
        "submitted",
        "under_review",
        "needs_fix",
        "failed",
    }:
        return current
    if surface.surface_key == "npm_registry" and clean(release.package_url):
        return "listed"
    if (
        clean(surface.category) == "llm_platform"
        and clean(server.transport_kind) == "stdio"
    ):
        return "blocked_requires_remote_mcp"
    if clean(surface.category) == "llm_platform" and not clean(
        server.remote_endpoint_url
    ):
        return "blocked_requires_remote_mcp"
    if clean(surface.category) != "artifact" and not clean(release.package_url):
        return "blocked_missing_artifact"
    return "package_ready"


def _validate_server_row(row: McpServerRow) -> None:
    required = [
        row.server_name,
        row.repo_full_name,
        row.repo_url,
        row.package_name,
        row.registry_name,
        row.install_command,
    ]
    if any(not clean(value) for value in required):
        raise ValueError(
            "server name, repo, package, registry, and install command are required."
        )


def _require_server(db: Session, server_id: int) -> McpServerRow:
    row = db.query(McpServerRow).filter(McpServerRow.id == server_id).first()
    if row is None:
        raise ValueError("MCP server not found.")
    return row


def _server_from_release(db: Session, release: McpServerReleaseRow) -> McpServerRow:
    if release.mcp_server_id:
        return _require_server(db, int(release.mcp_server_id))
    row = (
        db.query(McpServerRow)
        .filter(McpServerRow.server_key == release.server_key)
        .first()
    )
    return row or ensure_default_mcp_server(db)


def _backfill_legacy_releases(db: Session, server: McpServerRow) -> None:
    rows = (
        db.query(McpServerReleaseRow)
        .filter(
            McpServerReleaseRow.server_key == server.server_key,
            McpServerReleaseRow.mcp_server_id.is_(None),
        )
        .all()
    )
    for row in rows:
        row.mcp_server_id = int(server.id)
    if rows:
        db.commit()
