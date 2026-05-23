"""Create fast-return local deploy runner records for release tasks."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow, ReleaseTaskRow, utcnow
from server.schemas import ReleaseTaskOut, ReleaseTaskPrGateOut
from server.services.delivery.deployment_governance import _json_dump
from server.services.local_runner.json_utils import _json_load_dict
from server.services.releases.prebuilt_images import PREBUILT_FRONTEND_SERVICES
from server.services.releases import deployment_task_events
from server.services.releases.tasks import (
    _clean,
    _policy_for_project,
    _release_task_deploy_repo,
    _release_task_to_out,
    _service_key_error_for_project,
    _valid_service_keys_for_project,
)

SYNAPSE_NETWORK_REPO_PATH = "/Users/cliff/workspace/agent/Synapse-Network"
SYNAPSE_NETWORK_PROVIDER_REPO_PATH = (
    "/Users/cliff/workspace/agent/Synapse-Network-Provider"
)
SYNAPSE_NETWORK_PROJECT_KEY = "synapse-network"
SYNAPSE_PROVIDER_PROJECT_KEY = "synapse-network-provider"
SYNAPSE_STAGING_LOCAL_SERVICES = PREBUILT_FRONTEND_SERVICES | {
    "gateway",
    "gateway-admin",
}
SYNAPSE_PROVIDER_STAGING_LOCAL_SERVICES = {"provider-service"}


def _release_task_metadata(row: ReleaseTaskRow) -> dict[str, Any]:
    return _json_load_dict(getattr(row, "metadata_json", None))


def _unsupported_command(message: str) -> list[str]:
    return ["bash", "-lc", f"echo '{message}'; exit 2"]


def _synapse_network_staging_command(
    row: ReleaseTaskRow, *, service_key: str
) -> list[str]:
    if service_key not in SYNAPSE_STAGING_LOCAL_SERVICES:
        return _unsupported_command(
            "Local staging recipe is configured for Synapse-Network "
            "gateway/gateway-admin/admin-front/user-front/docs-front only."
        )
    metadata = _release_task_metadata(row)
    command = [
        "bash",
        "scripts/local/deploy_synapse_staging.sh",
        "--service",
        service_key,
        "--ref",
        _clean(row.branch_name) or "main",
        "--target-repo",
        SYNAPSE_NETWORK_REPO_PATH,
    ]
    prebuilt_digest = _clean(metadata.get("prebuiltImageDigest"))
    if prebuilt_digest and service_key in PREBUILT_FRONTEND_SERVICES:
        command.extend(["--prebuilt-image-digest", prebuilt_digest])
    return command


def _synapse_provider_staging_command(
    row: ReleaseTaskRow, *, service_key: str
) -> list[str]:
    if service_key not in SYNAPSE_PROVIDER_STAGING_LOCAL_SERVICES:
        return _unsupported_command(
            "Local staging recipe is configured for "
            "Synapse-Network-Provider provider-service only."
        )
    return [
        "bash",
        "scripts/local/deploy_synapse_provider_staging.sh",
        "--ref",
        _clean(row.branch_name) or "main",
        "--target-repo",
        SYNAPSE_NETWORK_PROVIDER_REPO_PATH,
    ]


def _production_promote_digest(
    row: ReleaseTaskRow, metadata_override: dict[str, Any] | None = None
) -> str:
    metadata = dict(_release_task_metadata(row))
    metadata.update(metadata_override or {})
    for key in ("promoteImageDigest", "prebuiltImageDigest", "stagingImageDigest"):
        image_digest = _clean(metadata.get(key))
        if image_digest:
            return image_digest
    return ""


def _production_promote_command(
    row: ReleaseTaskRow,
    *,
    service_key: str,
    metadata_override: dict[str, Any] | None = None,
) -> list[str]:
    metadata = dict(_release_task_metadata(row))
    metadata.update(metadata_override or {})
    image_digest = _production_promote_digest(row, metadata_override)
    if not image_digest:
        return _unsupported_command(
            "staging_digest_missing: production local deploy requires a successful staging image digest."
        )
    return [
        "bash",
        "scripts/local/promote_synapse_production.sh",
        "--project-key",
        _clean(row.project_key),
        "--service",
        service_key,
        "--ref",
        _clean(row.branch_name) or "main",
        "--commit-sha",
        _clean(metadata.get("resolvedCommitSha")),
        "--staging-image-digest",
        image_digest,
    ]


def _local_runner_command(
    row: ReleaseTaskRow,
    *,
    service_key: str,
    metadata_override: dict[str, Any] | None = None,
) -> list[str]:
    environment = _clean(row.environment).lower()
    project_key = _clean(row.project_key)
    if project_key == SYNAPSE_NETWORK_PROJECT_KEY and environment == "staging":
        return _synapse_network_staging_command(row, service_key=service_key)
    if project_key == SYNAPSE_PROVIDER_PROJECT_KEY and environment == "staging":
        return _synapse_provider_staging_command(row, service_key=service_key)
    if environment == "production":
        return _production_promote_command(
            row, service_key=service_key, metadata_override=metadata_override
        )
    return _unsupported_command(
        "Local deploy recipe is only configured for Synapse staging "
        "and production digest promotion."
    )


def _local_manifest_path(record_id: int) -> str:
    return f".local-runner/deployments/{int(record_id)}/manifest.json"


def _validate_local_recipe_scope(
    project_key: str, environment: str, service_key: str
) -> None:
    if environment == "production":
        return
    if (
        project_key == SYNAPSE_NETWORK_PROJECT_KEY
        and service_key in SYNAPSE_STAGING_LOCAL_SERVICES
    ):
        return
    if (
        project_key == SYNAPSE_PROVIDER_PROJECT_KEY
        and service_key in SYNAPSE_PROVIDER_STAGING_LOCAL_SERVICES
    ):
        return
    if service_key:
        raise ValueError("local_runner_recipe_missing")


def _build_local_runner_metadata(
    row: ReleaseTaskRow,
    *,
    record_id: int,
    service_key: str,
    repo_full_name: str,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {
        "release_task_id": int(row.id),
        "service_key": service_key,
        "deploy_repo_full_name": repo_full_name,
        "deploy_strategy": "local_deploy_runner",
        "deployScope": service_key,
        "environment": _clean(row.environment).lower(),
        "sourceRef": _clean(row.branch_name),
        "sourceRefType": "branch",
        "localDeployRunner": True,
        "localDeployRunnerVersion": "v1.1",
        "localManifestPath": _local_manifest_path(record_id),
    }
    task_metadata = _release_task_metadata(row)
    for key in (
        "prebuiltImageDigest",
        "promoteImageDigest",
        "stagingImageDigest",
        "imageSource",
        "sourceCommitSha",
        "buildService",
        "buildEvidence",
    ):
        if key in task_metadata:
            metadata[key] = task_metadata[key]
    metadata.update(extra_metadata or {})
    metadata["localRunnerCommand"] = _local_runner_command(
        row, service_key=service_key, metadata_override=metadata
    )
    return metadata


def _ensure_record_metadata(
    record: DeploymentRecordRow,
    row: ReleaseTaskRow,
    *,
    service_key: str,
    repo_full_name: str,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    metadata = _build_local_runner_metadata(
        row,
        record_id=int(record.id),
        service_key=service_key,
        repo_full_name=repo_full_name,
        extra_metadata=extra_metadata,
    )
    record.metadata_json = _json_dump(metadata)


def create_local_deploy_record_for_task(
    db: Session,
    row: ReleaseTaskRow,
    *,
    actor: str,
    note: str | None,
    pr_gate: ReleaseTaskPrGateOut | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> ReleaseTaskOut:
    service_key = _clean(getattr(row, "service_key", None)).lower()
    project_key = _clean(row.project_key)
    if _clean(row.status).lower() not in {"requested", "failed"}:
        raise ValueError(
            "Only requested or failed release tasks can be deployed locally."
        )
    if _clean(row.environment).lower() not in {"staging", "production"}:
        raise ValueError("Release task environment must be staging or production.")
    if service_key not in _valid_service_keys_for_project(project_key):
        raise ValueError(_service_key_error_for_project(project_key))
    if row.deployment_record_id is not None:
        raise ValueError("Release task already has a deployment record.")
    _validate_local_recipe_scope(
        project_key, _clean(row.environment).lower(), service_key
    )
    policy = _policy_for_project(db, project_key)
    repo_full_name = _release_task_deploy_repo(policy, project_key)
    record = DeploymentRecordRow(
        requirement_id=int(row.requirement_id)
        if row.requirement_id is not None
        else None,
        project_policy_id=int(policy.id) if policy is not None else None,
        project_key=project_key,
        environment=_clean(row.environment).lower(),
        action="deploy",
        status="requested",
        health_status="checking",
        branch_name=_clean(row.branch_name),
        workflow_file="local_deploy_runner",
        actor=actor,
        trigger_source="local_deploy_runner",
        notes=note,
        metadata_json="{}",
        started_at=utcnow(),
    )
    db.add(record)
    db.flush()
    _ensure_record_metadata(
        record,
        row,
        service_key=service_key,
        repo_full_name=repo_full_name,
        extra_metadata=extra_metadata,
    )
    deployment_task_events.record_requested(
        db,
        row,
        record,
        actor=actor,
        workflow_file="local_deploy_runner",
    )
    deployment_task_events.record_dispatched(
        db,
        record,
        actor=actor,
        inputs={"runner": "local_deploy_runner", "service_key": service_key},
    )
    row.deployment_record_id = int(record.id)
    row.status = "deploying"
    row.operator = actor
    row.note = note
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _release_task_to_out(row, db=db, pr_gate=pr_gate)


def deploy_release_task_locally(db: Session, task_id: int, body: Any) -> ReleaseTaskOut:
    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Release task not found.")
    actor = _clean(getattr(body, "actor", "operator")) or "operator"
    note = _clean(getattr(body, "note", None)) or _clean(row.note) or None
    environment = _clean(row.environment).lower()
    return create_local_deploy_record_for_task(
        db,
        row,
        actor=actor,
        note=note,
        pr_gate=ReleaseTaskPrGateOut(
            branch_exists=True,
            checks_status="local_runner",
            checks_summary=f"Local deploy runner will execute this {environment} deploy.",
            can_deploy_staging=environment == "staging",
            can_deploy_production=environment == "production",
            pr_state="production" if environment == "production" else None,
        ),
    )
