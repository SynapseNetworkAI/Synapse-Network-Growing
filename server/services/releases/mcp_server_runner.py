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
    MCP_REMOTE_CLOUD_RUN_REGION,
    MCP_REMOTE_CLOUD_RUN_SERVICE,
    MCP_REMOTE_ENDPOINT_URL,
    MCP_REMOTE_GCP_PROJECT_ID,
    MCP_REPO_PATH_ENV,
    MCP_RUNNER_ACTIVE_STATUSES,
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
    needs_envs: tuple[str, ...] = ()


def process_mcp_server_release(db: Session, *, release_id: int | None = None) -> int:
    query = db.query(McpServerReleaseRow).filter(
        McpServerReleaseRow.status.in_(MCP_RUNNER_ACTIVE_STATUSES)
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
    if status == "remote_prod_deploying":
        return [
            Step(
                "remote_gcloud_deploy",
                "npm run deploy:gcloud:remote",
            )
        ]
    if status == "remote_prod_deployed":
        return [
            Step(
                "remote_public_probe",
                _remote_public_probe_command(),
            )
        ]
    if status == "openai_smoke_running":
        return [
            Step(
                "openai_remote_smoke",
                "npm run test:e2e:remote:openai",
                needs_envs=("SYNAPSE_REMOTE_MCP_AUTH_TOKEN", "OPENAI_API_KEY"),
            )
        ]
    return []


def _remote_public_probe_command() -> str:
    return r"""
set -euo pipefail
host="mcp.synapse-network.ai"
ready_url="https://${host}/readyz"
mcp_url="https://${host}/mcp"
payload='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"release-probe","version":"0"}}}'
probe_mcp() {
  status=$(curl "$@" -sS -o /dev/null -w '%{http_code}' -X POST "$mcp_url" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    --data "$payload")
  test "$status" = "401"
}
if curl -fsS --connect-timeout 8 "$ready_url" && probe_mcp --connect-timeout 8; then
  exit 0
fi
ip=$(dig +short "$host" | awk '/^[0-9.]+$/ { print; exit }')
test -n "$ip"
curl --resolve "${host}:443:${ip}" -fsS --connect-timeout 8 "$ready_url"
probe_mcp --resolve "${host}:443:${ip}" --connect-timeout 8
""".strip()


def _next_status(status: str) -> str:
    return {
        "readiness_running": "ready_to_publish",
        "npm_publishing": "npm_published",
        "registry_submitting": "registry_listed",
        "prod_smoke_running": "directories_pending",
        "remote_prod_deploying": "remote_prod_deployed",
        "remote_prod_deployed": "openai_smoke_running",
        "openai_smoke_running": "remote_prod_verified",
    }[status]


def _process_one(db: Session, row: McpServerReleaseRow) -> None:
    repo_path = _repo_path(row)
    if not repo_path.exists():
        raise RuntimeError(f"MCP server repo path not found: {repo_path}")
    _assert_manifest_version(row, repo_path)
    status = clean(row.status)
    env = os.environ.copy()
    env["MCP_PACKAGE_NAME"] = clean(row.package_name)
    env.setdefault("PROJECT_ID", MCP_REMOTE_GCP_PROJECT_ID)
    env.setdefault("REGION", MCP_REMOTE_CLOUD_RUN_REGION)
    env.setdefault("SERVICE_NAME", MCP_REMOTE_CLOUD_RUN_SERVICE)
    env.setdefault("SYNAPSE_REMOTE_MCP_URL", MCP_REMOTE_ENDPOINT_URL)
    from_status = status
    for step in _steps(status):
        missing = _missing_env_names(step, env)
        if missing:
            raise RuntimeError(f"credential_missing: {', '.join(missing)}")
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
        metadata={
            "package_url": row.package_url,
            "registry_url": row.registry_url,
            "remote_endpoint_url": MCP_REMOTE_ENDPOINT_URL,
        },
    )
    if clean(row.status) == "remote_prod_verified":
        from server.services.releases.mcp_remote_tasks import (
            sync_linked_task_for_release,
        )

        sync_linked_task_for_release(db, row)
    sync_growth_discovery_listing(db, row)
    db.commit()


def _missing_env_names(step: Step, env: dict[str, str]) -> list[str]:
    names = [step.needs_env] if step.needs_env else []
    names.extend(step.needs_envs)
    return [name for name in names if name and not env.get(name)]


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
            "stdout": _redact(result.stdout, env),
            "stderr": _redact(result.stderr, env),
        },
    )
    db.commit()
    if result.returncode != 0:
        raise RuntimeError(
            _failure_summary(
                _redact(result.stderr or result.stdout or f"{step.key} failed", env),
                fallback=f"{step.key} failed",
            )
        )


def _redact(value: str | None, env: dict[str, str]) -> str:
    text = value or ""
    for name in (
        "SYNAPSE_AGENT_KEY",
        "SYNAPSE_REMOTE_MCP_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "NODE_AUTH_TOKEN",
    ):
        secret = env.get(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _failure_summary(output: str | None, *, fallback: str) -> str:
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if "Error:" in line and (
            "ENOTFOUND" in line or "ECONNREFUSED" in line or "ETIMEDOUT" in line
        ):
            return line[:800]
    for line in reversed(lines):
        if "ENOTFOUND" in line or "ECONNREFUSED" in line or "ETIMEDOUT" in line:
            return line[:800]
    for line in reversed(lines):
        if "getaddrinfo" in line:
            return line[:800]
    for line in reversed(lines):
        if line.startswith("Node.js v"):
            continue
        if line in {"}", "^"}:
            continue
        if line.startswith("at "):
            continue
        return line[:800]
    return fallback


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
    if from_status == "remote_prod_deploying":
        metadata = json.loads(row.metadata_json or "{}")
        metadata["remote_prod_deploy"] = {
            "status": "passed",
            "gcpProjectId": MCP_REMOTE_GCP_PROJECT_ID,
            "cloudRunRegion": MCP_REMOTE_CLOUD_RUN_REGION,
            "cloudRunService": MCP_REMOTE_CLOUD_RUN_SERVICE,
            "remoteEndpointUrl": MCP_REMOTE_ENDPOINT_URL,
        }
        row.metadata_json = json_dump(metadata)
    if from_status == "remote_prod_deployed":
        row.smoke_evidence_json = json_dump(
            {
                "status": "public_probe_passed",
                "healthz": "skipped_cloud_run_reserved_path",
                "readyz": "passed",
                "unauthenticated_mcp_status": 401,
                "remote_endpoint_url": MCP_REMOTE_ENDPOINT_URL,
            }
        )
    if from_status == "openai_smoke_running":
        row.smoke_evidence_json = json_dump(
            {
                "status": "passed",
                "provider": "openai",
                "allowed_tools": ["discover_services"],
                "command": "npm run test:e2e:remote:openai",
                "remote_endpoint_url": MCP_REMOTE_ENDPOINT_URL,
            }
        )
        _mark_surface(
            db,
            row,
            "openai_remote_mcp",
            "verified",
            MCP_REMOTE_ENDPOINT_URL,
            source="openai_remote_smoke",
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
    source: str = "mcp-publisher",
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
    surface.evidence_json = json_dump({"source": source, "mcp_release_id": int(row.id)})


def _repo_path(row: McpServerReleaseRow) -> Path:
    if row.server and clean(row.server.local_repo_path):
        return Path(clean(row.server.local_repo_path))
    return MCP_REPO


def _set_failure(db: Session, row: McpServerReleaseRow, message: str) -> None:
    from_status = clean(row.status)
    metadata = json.loads(row.metadata_json or "{}")
    metadata["last_failed_runner_state"] = from_status
    row.status = "failed"
    row.failure_summary = message[:1000]
    row.metadata_json = json_dump(metadata)
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
