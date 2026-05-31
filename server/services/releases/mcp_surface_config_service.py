"""Configuration and readiness checks for MCP discovery surfaces."""

from __future__ import annotations

import os
import shutil

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from server.database import utcnow
from server.services.releases.mcp_server_catalog import (
    DEFAULT_SURFACE_CONFIGS,
    MCP_SURFACE_AUTH_MODES,
    MCP_SURFACE_SUBMISSION_MODES,
)
from server.services.releases.mcp_server_helpers import (
    clean,
    json_dump,
    record_event,
    surface_config_to_out,
    surface_to_out,
)
from server.services.releases.mcp_server_models import (
    McpDiscoverySurfaceRow,
    McpServerReleaseRow,
    McpServerRow,
    McpServerSurfaceRow,
    McpSurfaceConfigRow,
)
from server.services.releases.mcp_server_schemas import (
    McpServerSurfaceOut,
    McpSubmissionReadinessItemOut,
    McpSubmissionReadinessOut,
    McpSurfaceConfigOut,
    McpSurfaceConfigPatchRequest,
    McpSurfaceConfigVerifyOut,
    McpSurfaceLiveCheckOut,
)


def migrate_mcp_surface_config_schema(engine_) -> None:
    tables = inspect(engine_).get_table_names()
    if "mcp_surface_configs" not in tables:
        McpSurfaceConfigRow.__table__.create(bind=engine_, checkfirst=True)


def ensure_surface_configs(db: Session) -> None:
    surfaces = db.query(McpDiscoverySurfaceRow).all()
    for surface in surfaces:
        row = (
            db.query(McpSurfaceConfigRow)
            .filter(McpSurfaceConfigRow.surface_key == surface.surface_key)
            .first()
        )
        defaults = DEFAULT_SURFACE_CONFIGS.get(surface.surface_key, {})
        if row is None:
            db.add(_new_config_row(surface, defaults))
            continue
        row.docs_url = row.docs_url or surface.docs_url
        row.submission_url = row.submission_url or surface.submission_url
    db.commit()


def get_surface_config(db: Session, surface_key: str) -> McpSurfaceConfigOut:
    ensure_surface_configs(db)
    return surface_config_to_out(_require_config(db, surface_key))


def patch_surface_config(
    db: Session, surface_key: str, body: McpSurfaceConfigPatchRequest
) -> McpSurfaceConfigOut:
    ensure_surface_configs(db)
    row = _require_config(db, surface_key)
    _apply_config_patch(row, body)
    row.verification_status = "configured" if row.is_enabled else "blocked"
    row.verification_summary = "Configuration updated; verification required."
    db.commit()
    db.refresh(row)
    return surface_config_to_out(row)


def verify_surface_config(db: Session, surface_key: str) -> McpSurfaceConfigVerifyOut:
    ensure_surface_configs(db)
    row = _require_config(db, surface_key)
    missing = _missing_env_vars(_required_env_vars(row), clean(row.credential_ref))
    required_tools = _required_tools(row)
    missing_tools = [tool for tool in required_tools if shutil.which(tool) is None]
    if not row.is_enabled:
        status = "blocked"
        summary = "Surface is disabled."
    elif missing:
        status = "not_configured"
        summary = f"Missing env refs: {', '.join(missing)}."
    elif missing_tools:
        status = "not_configured"
        summary = f"Missing local tool: {', '.join(missing_tools)}."
    else:
        status = "verified"
        summary = "Configuration references are present; no secret values were stored."
    row.verification_status = status
    row.verification_summary = summary
    row.last_verified_at = utcnow()
    db.commit()
    return McpSurfaceConfigVerifyOut(
        surface_key=clean(row.surface_key),
        verification_status=status,
        verification_summary=summary,
        missing_env_vars=missing,
        required_tools=required_tools,
        checked_at=row.last_verified_at or utcnow(),
    )


def get_submission_readiness(db: Session, server_id: int) -> McpSubmissionReadinessOut:
    ensure_surface_configs(db)
    server = db.query(McpServerRow).filter(McpServerRow.id == server_id).first()
    if server is None:
        raise ValueError("MCP server not found.")
    release = server.releases[0] if server.releases else None
    items = [
        _readiness_item(db, server, release, surface)
        for surface in (release.surfaces if release else [])
    ]
    return McpSubmissionReadinessOut(
        server_id=int(server.id),
        release_id=int(release.id) if release else None,
        items=items,
    )


def live_check_surface(
    db: Session, release_id: int, surface_key: str
) -> McpSurfaceLiveCheckOut:
    release, surface = _release_surface(db, release_id, surface_key)
    config = _require_config(db, surface_key)
    status, summary = _live_status(release, surface, config)
    surface.last_checked_at = utcnow()
    surface.evidence_json = json_dump({"live_check": status, "summary": summary})
    record_event(
        db,
        release,
        action="surface_live_check",
        from_status=release.status,
        to_status=release.status,
        metadata={"surface_key": surface.surface_key, "live_check": status},
    )
    db.commit()
    return McpSurfaceLiveCheckOut(
        release_id=release_id,
        surface_key=clean(surface.surface_key),
        status=status,
        summary=summary,
        evidence={"live_check": status},
        checked_at=surface.last_checked_at or utcnow(),
    )


def submit_surface_with_readiness(
    db: Session, release_id: int, surface_key: str, actor: str, note: str | None
) -> McpServerSurfaceOut:
    release, surface = _release_surface(db, release_id, surface_key)
    server = release.server
    item = _readiness_item(db, server, release, surface)
    if item.readiness_status != "submit_eligible":
        surface.status = (
            "failed" if item.readiness_status == "blocked" else surface.status
        )
        surface.failure_reason = item.reason
        record_event(
            db,
            release,
            action="surface_submit_blocked",
            from_status=release.status,
            to_status=release.status,
            actor=actor,
            note=note,
            error_summary=item.reason,
            metadata={
                "surface_key": surface.surface_key,
                "readiness": item.readiness_status,
            },
        )
        db.commit()
        raise ValueError(item.reason or item.readiness_status)
    surface.status = (
        "under_review" if clean(surface.category) == "llm_platform" else "submitted"
    )
    surface.operator_note = clean(note) or None
    surface.last_checked_at = utcnow()
    record_event(
        db,
        release,
        action="surface_submitted",
        from_status=release.status,
        to_status=release.status,
        actor=actor,
        note=note,
        metadata={"surface_key": surface.surface_key, "surface_status": surface.status},
    )
    db.commit()
    db.refresh(surface)
    return surface_to_out(surface)


def _new_config_row(
    surface: McpDiscoverySurfaceRow, defaults: dict[str, object]
) -> McpSurfaceConfigRow:
    return McpSurfaceConfigRow(
        surface_key=surface.surface_key,
        submission_mode=clean(defaults.get("submission_mode")) or "manual",
        auth_mode=clean(defaults.get("auth_mode")) or "manual",
        credential_ref=clean(defaults.get("credential_ref")) or None,
        required_env_vars_json=json_dump(
            {"items": defaults.get("required_env_vars") or []}
        ),
        docs_url=surface.docs_url,
        submission_url=surface.submission_url,
        verification_status="not_configured",
    )


def _require_config(db: Session, surface_key: str) -> McpSurfaceConfigRow:
    row = (
        db.query(McpSurfaceConfigRow)
        .filter(McpSurfaceConfigRow.surface_key == clean(surface_key))
        .first()
    )
    if row is None:
        raise ValueError("MCP surface config not found.")
    return row


def _release_surface(
    db: Session, release_id: int, surface_key: str
) -> tuple[McpServerReleaseRow, McpServerSurfaceRow]:
    release = (
        db.query(McpServerReleaseRow)
        .filter(McpServerReleaseRow.id == release_id)
        .first()
    )
    if release is None:
        raise ValueError("MCP server release not found.")
    surface = (
        db.query(McpServerSurfaceRow)
        .filter(
            McpServerSurfaceRow.mcp_server_release_id == release_id,
            McpServerSurfaceRow.surface_key == clean(surface_key),
        )
        .first()
    )
    if surface is None:
        raise ValueError("MCP discovery surface not found.")
    return release, surface


def _readiness_item(
    db: Session,
    server: McpServerRow,
    release: McpServerReleaseRow | None,
    surface: McpServerSurfaceRow,
) -> McpSubmissionReadinessItemOut:
    config = _require_config(db, surface.surface_key)
    required_env_vars = _required_env_vars(config)
    missing = _missing_env_vars(required_env_vars, clean(config.credential_ref))
    status, reason = _readiness_status(server, release, surface, config, missing)
    return McpSubmissionReadinessItemOut(
        surface_key=clean(surface.surface_key),
        surface_label=clean(surface.surface_label),
        category=clean(surface.category),
        surface_status=clean(surface.status),
        config_status=clean(config.verification_status),
        readiness_status=status,
        reason=reason,
        required_env_vars=required_env_vars,
        missing_env_vars=missing,
        submission_mode=clean(config.submission_mode) or "manual",
        credential_ref=clean(config.credential_ref) or None,
    )


def _apply_config_patch(
    row: McpSurfaceConfigRow, body: McpSurfaceConfigPatchRequest
) -> None:
    if body.submission_mode is not None:
        row.submission_mode = _validated_choice(
            body.submission_mode,
            MCP_SURFACE_SUBMISSION_MODES,
            "invalid MCP surface submission_mode.",
        )
    if body.auth_mode is not None:
        row.auth_mode = _validated_choice(
            body.auth_mode,
            MCP_SURFACE_AUTH_MODES,
            "invalid MCP surface auth_mode.",
        )
    _apply_config_text_fields(row, body)
    if body.is_enabled is not None:
        row.is_enabled = 1 if body.is_enabled else 0
    if body.metadata is not None:
        row.metadata_json = json_dump(body.metadata)


def _apply_config_text_fields(
    row: McpSurfaceConfigRow, body: McpSurfaceConfigPatchRequest
) -> None:
    if body.credential_ref is not None:
        row.credential_ref = clean(body.credential_ref) or None
    if body.required_env_vars is not None:
        row.required_env_vars_json = json_dump(
            {"items": _clean_list(body.required_env_vars)}
        )
    if body.docs_url is not None:
        row.docs_url = clean(body.docs_url) or None
    if body.submission_url is not None:
        row.submission_url = clean(body.submission_url) or None


def _validated_choice(value: str, allowed: set[str], message: str) -> str:
    cleaned = clean(value)
    if cleaned not in allowed:
        raise ValueError(message)
    return cleaned


def _readiness_status(
    server: McpServerRow,
    release: McpServerReleaseRow | None,
    surface: McpServerSurfaceRow,
    config: McpSurfaceConfigRow,
    missing: list[str],
) -> tuple[str, str | None]:
    reason = _readiness_block_reason(server, release, surface, config, missing)
    if reason is None:
        return "submit_eligible", None
    if reason.startswith("Missing env") or reason.startswith("Surface config"):
        return "not_configured", reason
    return "blocked", reason


def _readiness_block_reason(
    server: McpServerRow,
    release: McpServerReleaseRow | None,
    surface: McpServerSurfaceRow,
    config: McpSurfaceConfigRow,
    missing: list[str],
) -> str | None:
    checks = [
        _config_disabled_reason(config),
        _missing_env_reason(missing),
        _config_unverified_reason(config),
        _surface_blocked_reason(surface),
        _remote_endpoint_reason(server, surface),
        _npm_artifact_reason(release, surface),
    ]
    for reason in checks:
        if reason:
            return reason
    return None


def _config_disabled_reason(config: McpSurfaceConfigRow) -> str | None:
    return "Surface disabled." if not config.is_enabled else None


def _missing_env_reason(missing: list[str]) -> str | None:
    return f"Missing env refs: {', '.join(missing)}." if missing else None


def _config_unverified_reason(config: McpSurfaceConfigRow) -> str | None:
    if clean(config.verification_status) in {"configured", "verified"}:
        return None
    return config.verification_summary or "Surface config is not verified."


def _surface_blocked_reason(surface: McpServerSurfaceRow) -> str | None:
    status = clean(surface.status)
    return status if status.startswith("blocked_") else None


def _remote_endpoint_reason(
    server: McpServerRow, surface: McpServerSurfaceRow
) -> str | None:
    if clean(surface.category) != "llm_platform":
        return None
    return (
        None
        if clean(server.remote_endpoint_url)
        else "Remote MCP endpoint is required."
    )


def _npm_artifact_reason(
    release: McpServerReleaseRow | None, surface: McpServerSurfaceRow
) -> str | None:
    if not _requires_npm_artifact(surface) or not release:
        return None
    return None if clean(release.package_url) else "npm artifact is not verified yet."


def _requires_npm_artifact(surface: McpServerSurfaceRow) -> bool:
    return clean(surface.category) in {
        "official_registry",
        "directory",
        "client_config",
    }


def _live_status(
    release: McpServerReleaseRow,
    surface: McpServerSurfaceRow,
    config: McpSurfaceConfigRow,
) -> tuple[str, str]:
    if clean(surface.surface_key) == "npm_registry":
        return (
            ("pass", "npm package URL is recorded.")
            if clean(release.package_url)
            else ("blocked", "npm package URL is missing.")
        )
    if clean(surface.category) == "client_config":
        return (
            "pass",
            "Client config snippet can be generated without external credentials.",
        )
    if clean(config.verification_status) not in {"configured", "verified"}:
        return (
            "blocked",
            config.verification_summary or "Surface config is not verified.",
        )
    if clean(surface.category) == "llm_platform" and not clean(
        release.server.remote_endpoint_url
    ):
        return "blocked", "Remote MCP endpoint is required."
    return (
        "pass",
        "Ledger preconditions are satisfied; no external submission was performed.",
    )


def _required_env_vars(row: McpSurfaceConfigRow) -> list[str]:
    try:
        import json

        payload = json.loads(row.required_env_vars_json or "[]")
    except ValueError:
        payload = []
    if isinstance(payload, dict):
        payload = payload.get("items", [])
    return (
        [clean(item) for item in payload if clean(item)]
        if isinstance(payload, list)
        else []
    )


def _missing_env_vars(required: list[str], credential_ref: str) -> list[str]:
    refs = list(required)
    if credential_ref.startswith("env:"):
        refs.append(credential_ref.removeprefix("env:"))
    missing: list[str] = []
    for ref in refs:
        options = [part.strip() for part in ref.split("|") if part.strip()]
        if options and not any(os.getenv(option) for option in options):
            missing.append(ref)
    return sorted(set(missing))


def _required_tools(row: McpSurfaceConfigRow) -> list[str]:
    if clean(row.surface_key) == "official_mcp_registry":
        return ["mcp-publisher"]
    return []


def _clean_list(values: list[str]) -> list[str]:
    return [clean(value) for value in values if clean(value)]
