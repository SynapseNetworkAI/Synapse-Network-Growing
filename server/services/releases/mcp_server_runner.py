"""Local MCP server readiness and publish runner."""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from server.database import utcnow
from server.services.releases.mcp_server_catalog import (
    MCP_REPO_PATH_ENV,
)
from server.services.releases.mcp_server_helpers import (
    clean,
    json_dump,
    package_url_for,
    record_event,
)
from server.services.releases.mcp_server_catalog_service import sync_release_surfaces
from server.services.releases.mcp_server_models import (
    McpServerReleaseRow,
    McpServerSurfaceRow,
)
from server.services.releases.mcp_servers import sync_growth_discovery_listing

MCP_REPO = Path(
    os.environ.get(
        MCP_REPO_PATH_ENV,
        "/Users/cliff/workspace/agent/Synapse-Network-MCP-Server",
    )
)


@dataclass(frozen=True)
class Step:
    key: str
    command: str
    needs_env: str | None = None


def process_mcp_server_release(db: Session, *, release_id: int | None = None) -> int:
    query = db.query(McpServerReleaseRow).filter(
        McpServerReleaseRow.status.in_(
            [
                "readiness_running",
                "npm_publishing",
                "registry_submitting",
                "prod_smoke_running",
            ]
        )
    )
    if release_id is not None:
        query = query.filter(McpServerReleaseRow.id == release_id)
    rows = (
        query.order_by(McpServerReleaseRow.updated_at.asc())
        .limit(1 if release_id else 10)
        .all()
    )
    processed = 0
    for row in rows:
        processed += 1
        try:
            _process_one(db, row)
        except Exception as exc:  # noqa: BLE001 - runner must persist bounded failure.
            _set_failure(db, row, str(exc))
    return processed


def _steps(status: str) -> list[Step]:
    if status == "readiness_running":
        return [Step("release_readiness", "npm run release:readiness")]
    if status == "npm_publishing":
        return [
            Step(
                "npm_publish",
                "npm publish --access public --registry=https://registry.npmjs.org",
                "NODE_AUTH_TOKEN",
            ),
            Step(
                "npm_view",
                "npm view ${MCP_PACKAGE_NAME} --registry=https://registry.npmjs.org",
            ),
            Step("npx_help", "npx -y ${MCP_PACKAGE_NAME} --help"),
        ]
    if status == "registry_submitting":
        return [Step("mcp_registry_publish", "mcp-publisher publish")]
    if status == "prod_smoke_running":
        return [
            Step(
                "prod_smoke",
                "SYNAPSE_ENV=prod npm run test:e2e:prod",
                "SYNAPSE_AGENT_KEY",
            )
        ]
    return []


def _next_status(status: str) -> str:
    return {
        "readiness_running": "ready_to_publish",
        "npm_publishing": "npm_published",
        "registry_submitting": "registry_listed",
        "prod_smoke_running": "directories_pending",
    }[status]


def _process_one(db: Session, row: McpServerReleaseRow) -> None:
    repo_path = _repo_path(row)
    if not repo_path.exists():
        raise RuntimeError(f"MCP server repo path not found: {repo_path}")
    _assert_manifest_version(row, repo_path)
    status = clean(row.status)
    env = os.environ.copy()
    env["MCP_PACKAGE_NAME"] = clean(row.package_name)
    from_status = status
    for step in _steps(status):
        if step.needs_env and not env.get(step.needs_env):
            raise RuntimeError(f"credential_missing: {step.needs_env}")
        _run_step(db, row, step, env, repo_path)
    row.status = _next_status(status)
    row.failure_summary = None
    _apply_success_metadata(db, row, from_status)
    sync_release_surfaces(db, row)
    row.updated_at = utcnow()
    record_event(
        db,
        row,
        action="runner_succeeded",
        from_status=from_status,
        to_status=clean(row.status),
        metadata={"package_url": row.package_url, "registry_url": row.registry_url},
    )
    sync_growth_discovery_listing(db, row)
    db.commit()


def _run_step(
    db: Session,
    row: McpServerReleaseRow,
    step: Step,
    env: dict[str, str],
    repo_path: Path,
) -> None:
    record_event(
        db,
        row,
        action="runner_step_started",
        from_status=clean(row.status),
        to_status=clean(row.status),
        metadata={"step": step.key, "command": step.command},
    )
    db.commit()
    result = subprocess.run(  # nosec B603
        ["/bin/bash", "-lc", step.command],
        cwd=str(repo_path),
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=1800,
    )
    record_event(
        db,
        row,
        action="runner_step_finished",
        from_status=clean(row.status),
        to_status=clean(row.status),
        metadata={
            "step": step.key,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    db.commit()
    if result.returncode != 0:
        output = (
            (result.stderr or result.stdout or f"{step.key} failed")
            .strip()
            .splitlines()
        )
        raise RuntimeError(output[-1][:800] if output else f"{step.key} failed")


def _assert_manifest_version(row: McpServerReleaseRow, repo_path: Path) -> None:
    manifest = json.loads((repo_path / "package.json").read_text())
    server_json = json.loads((repo_path / "server.json").read_text())
    expected = clean(row.package_version)
    if manifest.get("version") != expected:
        raise RuntimeError(
            f"manifest_version_mismatch: package.json has {manifest.get('version')}, expected {expected}"
        )
    if manifest.get("mcpName") != clean(row.registry_name):
        raise RuntimeError(
            "mcp_name_mismatch: package.json mcpName must match release registry name"
        )
    if server_json.get("version") != expected:
        raise RuntimeError(
            f"server_json_version_mismatch: server.json has {server_json.get('version')}, expected {expected}"
        )


def _apply_success_metadata(
    db: Session, row: McpServerReleaseRow, from_status: str
) -> None:
    if from_status == "npm_publishing":
        row.package_url = package_url_for(
            clean(row.package_name), clean(row.package_version)
        )
        row.published_at = utcnow()
    if from_status == "registry_submitting":
        row.registry_url = (
            "https://registry.modelcontextprotocol.io/servers/"
            f"{clean(row.registry_name)}"
        )
        _mark_surface(db, row, "official_mcp_registry", "listed", row.registry_url)
    if from_status == "prod_smoke_running":
        row.smoke_evidence_json = json_dump(
            {"status": "passed", "command": "SYNAPSE_ENV=prod npm run test:e2e:prod"}
        )
    metadata = json.loads(row.metadata_json or "{}")
    metadata["artifact_manifest"] = {
        "package_name": clean(row.package_name),
        "package_version": clean(row.package_version),
        "registry_name": clean(row.registry_name),
        "install_command": clean(row.install_command),
    }
    metadata["verify_result"] = {"status": "passed", "runner_state": from_status}
    row.metadata_json = json_dump(metadata)


def _mark_surface(
    db: Session,
    row: McpServerReleaseRow,
    surface_key: str,
    status: str,
    listing_url: str,
) -> None:
    surface = (
        db.query(McpServerSurfaceRow)
        .filter(
            McpServerSurfaceRow.mcp_server_release_id == int(row.id),
            McpServerSurfaceRow.surface_key == surface_key,
        )
        .first()
    )
    if surface is None:
        return
    surface.status = status
    surface.listing_url = listing_url
    surface.evidence_json = json_dump(
        {"source": "mcp-publisher", "mcp_release_id": int(row.id)}
    )


def _repo_path(row: McpServerReleaseRow) -> Path:
    if row.server and clean(row.server.local_repo_path):
        return Path(clean(row.server.local_repo_path))
    return MCP_REPO


def _set_failure(db: Session, row: McpServerReleaseRow, message: str) -> None:
    from_status = clean(row.status)
    row.status = "failed"
    row.failure_summary = message[:1000]
    row.updated_at = utcnow()
    record_event(
        db,
        row,
        action="runner_failed",
        from_status=from_status,
        to_status="failed",
        error_summary=row.failure_summary,
    )
    db.commit()
