"""Production release task gates and dispatch."""

from __future__ import annotations

import os
import subprocess
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server.database import DeploymentRecordRow, ReleaseTaskRow
from server.schemas import ReleaseTaskOut, ReleaseTaskPrGateOut
from server.services.releases.tasks import (
    E2E_BRANCH_OPTIONS,
    _clean,
    _json_load,
    _policy_for_project,
    _release_task_deploy_repo,
    _service_key_error_for_project,
    _valid_service_keys_for_project,
)
from server.services.releases.production_staging_evidence import (
    deployment_commit_sha as _deployment_commit_sha,
    latest_successful_staging_deployment as _latest_successful_staging_deployment,
    successful_staging_deployment_for_commit as _successful_staging_deployment_for_task,
)

PRODUCTION_GCP_PROJECT_ID = "synapse-network-prod"
PRODUCTION_CONFIRM_PHRASE = "YES"
PRODUCTION_DEPLOY_SERVICE_ACCOUNT = (
    "synapse-prod-github-deployer@synapse-network-prod.iam.gserviceaccount.com"
)
LOCAL_REPO_PATH_BY_PROJECT = {
    "synapse-network": "/Users/cliff/workspace/agent/Synapse-Network",
    "synapse-network-provider": "/Users/cliff/workspace/agent/Synapse-Network-Provider",
}
LOCAL_REPO_ENV_BY_PROJECT = {
    "synapse-network": "SYNAPSE_NETWORK_REPO",
    "synapse-network-provider": "SYNAPSE_NETWORK_PROVIDER_REPO",
}


def _local_repo_path_for_project(project_key: str) -> str:
    clean_project_key = _clean(project_key)
    env_key = LOCAL_REPO_ENV_BY_PROJECT.get(clean_project_key)
    if env_key:
        env_path = _clean(os.environ.get(env_key))
        if env_path:
            return env_path
    return _clean(LOCAL_REPO_PATH_BY_PROJECT.get(clean_project_key))


def _local_branch_commit_sha(
    project_key: str, branch_name: str
) -> tuple[str | None, str | None]:
    if config.E2E_MODE:
        if branch_name in E2E_BRANCH_OPTIONS:
            return f"e2e-commit-{branch_name.replace('/', '-')}", None
        return None, "分支不存在，请重新选择有效远端分支"
    repo_path = _local_repo_path_for_project(project_key)
    if not repo_path:
        return None, "Local production gate has no registered repository path."
    remote_ref = f"refs/remotes/origin/{branch_name}"
    try:
        fetch_result = subprocess.run(
            ["git", "-C", repo_path, "fetch", "--quiet", "origin", branch_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if fetch_result.returncode != 0:
            return None, (
                fetch_result.stderr
                or fetch_result.stdout
                or "Unable to refresh origin branch."
            ).strip()
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", f"{remote_ref}^{{commit}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"Unable to resolve local branch commit sha: {exc}"
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or "Local branch not found.").strip()
    sha = _clean(result.stdout)
    return sha or None, None if sha else "Local git did not return commit sha."


def _github_branch_commit_sha(
    project_key: str, branch_name: str
) -> tuple[str | None, str | None]:
    """Backward-compatible name for the local production gate resolver."""

    return _local_branch_commit_sha(project_key, branch_name)


def _task_target_commit_sha(row: ReleaseTaskRow) -> str:
    return _clean(getattr(row, "target_commit_sha", None))


def release_task_production_gate(
    db: Session, row: ReleaseTaskRow, repo_full_name: str
) -> ReleaseTaskPrGateOut:
    branch_name = _clean(row.branch_name)
    service_key = _clean(getattr(row, "service_key", None)).lower()
    project_key = _clean(row.project_key)
    gate = ReleaseTaskPrGateOut(
        branch_exists=False,
        pr_state="production",
        checks_status="unknown",
        environment_gate_summary="Production requires main plus a successful staging deployment for the same commit.",
        blocked_reason="Production gate pending.",
    )
    if branch_name != "main":
        gate.blocked_reason = "Production deploy only allows branch main."
        gate.environment_gate_summary = "Production cannot deploy feature branches."
        return gate
    if service_key not in _valid_service_keys_for_project(project_key):
        gate.blocked_reason = _service_key_error_for_project(project_key)
        return gate
    current_main_sha, commit_error = _github_branch_commit_sha(project_key, branch_name)
    gate.branch_exists = bool(current_main_sha)
    target_commit_sha = _task_target_commit_sha(row) or current_main_sha
    gate.resolved_commit_sha = target_commit_sha
    if not current_main_sha:
        gate.blocked_reason = commit_error or "Unable to resolve main commit sha."
        gate.environment_gate_summary = gate.blocked_reason
        return gate
    if target_commit_sha != current_main_sha:
        gate.blocked_reason = (
            "Production target commit is no longer the current origin/main commit."
        )
        gate.environment_gate_summary = "Redeploy the current main commit to staging before production."
        return gate
    staging_record = _successful_staging_deployment_for_task(
        db,
        project_key=project_key,
        service_key=service_key,
        commit_sha=target_commit_sha,
    )
    if staging_record is None and not _task_target_commit_sha(row):
        staging_record = _latest_successful_staging_deployment(
            db,
            project_key=project_key,
            service_key=service_key,
        )
        if (
            staging_record is not None
            and _deployment_commit_sha(staging_record) == current_main_sha
        ):
            target_commit_sha = _deployment_commit_sha(staging_record)
            gate.resolved_commit_sha = target_commit_sha
        else:
            staging_record = None
    if staging_record is None:
        gate.blocked_reason = (
            "No successful staging deployment exists for this service and main commit."
        )
        gate.environment_gate_summary = (
            "Deploy the same main commit to staging successfully before production."
        )
        return gate
    gate.staging_deployment_record_id = int(staging_record.id)
    gate.checks_status = "success"
    gate.checks_summary = (
        f"Staging deployment #{int(staging_record.id)} passed for {target_commit_sha[:12]}."
    )
    gate.environment_gate_summary = (
        "Production gate ready: selected main commit has passed staging."
    )
    gate.can_deploy_production = True
    gate.blocked_reason = None
    return gate


def _production_task_row(db: Session, task_id: int, body: Any) -> ReleaseTaskRow:
    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Release task not found.")
    task_status = _clean(row.status).lower()
    if task_status not in {"requested", "failed"}:
        raise ValueError(
            "Only requested or failed release tasks can be deployed to production."
        )
    if _clean(row.environment).lower() != "production":
        raise ValueError("Only production release tasks can use production deploy.")
    if _clean(getattr(body, "confirm_phrase", None)) != PRODUCTION_CONFIRM_PHRASE:
        raise ValueError("Production deploy requires confirm_phrase=YES.")
    if _clean(row.branch_name) != "main":
        raise ValueError("Production deploy only allows branch main.")
    service_key = _clean(getattr(row, "service_key", None)).lower()
    project_key = _clean(row.project_key)
    if service_key not in _valid_service_keys_for_project(project_key):
        raise ValueError(_service_key_error_for_project(project_key))
    if task_status == "requested" and row.deployment_record_id is not None:
        raise ValueError("Release task already has a deployment record.")
    if task_status == "failed" and row.deployment_record_id is not None:
        record = db.get(DeploymentRecordRow, int(row.deployment_record_id))
        if record is not None and _clean(record.status).lower() != "failed":
            raise ValueError(
                "Failed release task can only retry after a failed deployment record."
            )
        if record is not None and _clean(record.status).lower() == "failed":
            row.deployment_record_id = None
            db.flush()
    return row


def _production_staging_evidence(
    db: Session, gate: ReleaseTaskPrGateOut
) -> DeploymentRecordRow | None:
    if not (
        gate.can_deploy_production
        and gate.resolved_commit_sha
    ):
        raise ValueError(gate.blocked_reason or "Production gate is not ready.")
    if not gate.staging_deployment_record_id:
        return None
    staging_record = db.get(DeploymentRecordRow, int(gate.staging_deployment_record_id))
    if staging_record is None:
        raise ValueError("Source staging deployment record was not found.")
    return staging_record


def _staging_image_digest(staging_record: DeploymentRecordRow | None) -> str | None:
    if staging_record is None:
        return None
    metadata = _json_load(getattr(staging_record, "metadata_json", None), {})
    for key in (
        "imageDigest",
        "image_digest",
        "effectiveImage",
        "prebuiltImageDigest",
        "stagingImageDigest",
    ):
        value = _clean(metadata.get(key))
        if "@sha256:" in value:
            return value
    manifest = metadata.get("manifest")
    if isinstance(manifest, dict):
        for key in ("image_digest", "imageDigest", "effectiveImage"):
            value = _clean(manifest.get(key))
            if "@sha256:" in value:
                return value
    return None


def _deploy_release_task_to_production(
    db: Session, task_id: int, body: Any
) -> ReleaseTaskOut:
    row = _production_task_row(db, task_id, body)
    project_key = _clean(row.project_key)
    policy = _policy_for_project(db, project_key)
    repo_full_name = _release_task_deploy_repo(policy, project_key)
    gate = release_task_production_gate(db, row, repo_full_name)
    staging_record = _production_staging_evidence(db, gate)
    image_digest = _staging_image_digest(staging_record)
    if not image_digest:
        raise ValueError("staging_digest_missing")
    actor = _clean(getattr(body, "actor", "operator")) or "operator"
    note = _clean(getattr(body, "note", None)) or _clean(row.note) or None
    from server.services.releases.local_deploy_tasks import (
        create_local_deploy_record_for_task,
    )

    return create_local_deploy_record_for_task(
        db,
        row,
        actor=actor,
        note=note,
        pr_gate=gate,
        extra_metadata={
            "gcpProject": PRODUCTION_GCP_PROJECT_ID,
            "sourceRef": "main",
            "sourceRefType": "branch",
            "productionConfirmPhrase": PRODUCTION_CONFIRM_PHRASE,
            "deploy_repo_full_name": repo_full_name,
            "sourceStagingDeploymentRecordId": int(staging_record.id)
            if staging_record is not None
            else None,
            "stagingImageDigest": image_digest,
            "promoteImageDigest": image_digest,
            "resolvedCommitSha": gate.resolved_commit_sha,
            "environmentIsolationVersion": "v1",
            "impersonateServiceAccount": PRODUCTION_DEPLOY_SERVICE_ACCOUNT,
        },
    )


def deploy_release_task(db: Session, task_id: int, body: Any) -> ReleaseTaskOut:
    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Release task not found.")
    from server.services.releases.mcp_remote_tasks import is_mcp_remote_task, deploy_task as deploy_mcp_remote_task
    from server.services.releases.tasks import _release_task_to_out

    if is_mcp_remote_task(row):
        gate = deploy_mcp_remote_task(db, row, body)
        return _release_task_to_out(row, pr_gate=gate)
    environment = _clean(row.environment).lower()
    if environment == "staging":
        from server.services.releases.local_deploy_tasks import (
            create_local_deploy_record_for_task,
        )

        return create_local_deploy_record_for_task(
            db,
            row,
            actor=_clean(getattr(body, "actor", "operator")) or "operator",
            note=_clean(getattr(body, "note", None)) or _clean(row.note) or None,
            pr_gate=ReleaseTaskPrGateOut(
                branch_exists=True,
                checks_status="local_runner",
                checks_summary="Local deploy runner will execute this staging deploy.",
                can_deploy_staging=True,
            ),
        )
    if environment == "production":
        return _deploy_release_task_to_production(db, task_id, body)
    raise ValueError("Release task environment must be staging or production.")
