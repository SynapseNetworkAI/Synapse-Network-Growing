"""Production release task gates and dispatch."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from server import config
from server.database import DeploymentRecordRow, ReleaseTaskRow, utcnow
from server.schemas import ReleaseTaskOut, ReleaseTaskPrGateOut
from server.services.delivery.deployment_governance import (
    _callback_url,
    _dispatch_github_workflow,
    _json_dump,
)
from server.services.releases.github_cli import run_gh_json as _run_gh_json
from server.services.releases.tasks import (
    E2E_BRANCH_OPTIONS,
    _clean,
    _json_load,
    _policy_for_project,
    _release_task_deploy_repo,
    _release_task_to_out,
    _service_key_error_for_project,
    _valid_service_keys_for_project,
    deploy_release_task_to_staging,
)

PRODUCTION_GCP_PROJECT_ID = "synapse-network-prod"
PRODUCTION_CONFIRM_PHRASE = "DEPLOY_PRODUCTION"
PRODUCTION_WORKFLOW_FILE = "deploy-production.yml"
REQUIRED_GCP_PRODUCTION_DEPLOY_SECRETS = {
    "PROD_GCP_WORKLOAD_IDENTITY_PROVIDER",
    "PROD_GCP_DEPLOY_SERVICE_ACCOUNT",
    "PROD_GCP_PROJECT_ID",
    "PROD_GCP_REGION",
    "PROD_ARTIFACT_REGISTRY_REPOSITORY",
    "PROD_EVIDENCE_BUCKET",
}


def _missing_required_production_deploy_secrets(
    repo_full_name: str,
) -> tuple[list[str], str | None]:
    if config.E2E_MODE:
        return [], None
    status, payload, error = _run_gh_json(
        ["secret", "list", "--repo", repo_full_name, "--json", "name"],
        timeout=30,
    )
    if status != "ok":
        return sorted(
            REQUIRED_GCP_PRODUCTION_DEPLOY_SECRETS
        ), error or "Unable to verify GitHub production deployment secrets."
    if not isinstance(payload, list):
        return sorted(
            REQUIRED_GCP_PRODUCTION_DEPLOY_SECRETS
        ), "GitHub secret list response was not valid."
    present = {_clean(item.get("name")) for item in payload if isinstance(item, dict)}
    missing = sorted(
        secret
        for secret in REQUIRED_GCP_PRODUCTION_DEPLOY_SECRETS
        if secret not in present
    )
    return missing, None


def _github_branch_commit_sha(
    repo_full_name: str, branch_name: str
) -> tuple[str | None, str | None]:
    if config.E2E_MODE:
        if branch_name in E2E_BRANCH_OPTIONS:
            return f"e2e-commit-{branch_name.replace('/', '-')}", None
        return None, "分支不存在，请重新选择有效远端分支"
    status, payload, error = _run_gh_json(
        ["api", f"repos/{repo_full_name}/branches/{quote(branch_name, safe='')}"],
        timeout=30,
    )
    if status != "ok" or not isinstance(payload, dict):
        return None, error or "Unable to resolve branch commit sha."
    commit = payload.get("commit") if isinstance(payload.get("commit"), dict) else {}
    sha = _clean(commit.get("sha"))
    return (
        sha or None
    ), None if sha else "GitHub branch response did not include commit sha."


def _deployment_commit_sha(row: DeploymentRecordRow) -> str:
    metadata = _json_load(getattr(row, "metadata_json", None), {})
    return (
        _clean(getattr(row, "commit_sha", None))
        or _clean(metadata.get("resolvedCommitSha"))
        or _clean(metadata.get("githubHeadSha"))
    )


def _deployment_service_key(row: DeploymentRecordRow) -> str:
    metadata = _json_load(getattr(row, "metadata_json", None), {})
    return _clean(metadata.get("service_key") or metadata.get("deployScope"))


def _successful_staging_deployment_for_task(
    db: Session,
    *,
    project_key: str,
    service_key: str,
    commit_sha: str,
) -> DeploymentRecordRow | None:
    rows = (
        db.query(DeploymentRecordRow)
        .filter(
            DeploymentRecordRow.project_key == project_key,
            DeploymentRecordRow.environment == "staging",
            DeploymentRecordRow.status == "succeeded",
            DeploymentRecordRow.health_status.in_(
                ["passed", "healthy", "manual_verified"]
            ),
        )
        .order_by(DeploymentRecordRow.id.desc())
        .limit(50)
        .all()
    )
    for row in rows:
        if _deployment_service_key(row) != service_key:
            continue
        if _deployment_commit_sha(row) == commit_sha:
            return row
    return None


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
    commit_sha, commit_error = _github_branch_commit_sha(repo_full_name, branch_name)
    gate.branch_exists = bool(commit_sha)
    gate.resolved_commit_sha = commit_sha
    if not commit_sha:
        gate.blocked_reason = commit_error or "Unable to resolve main commit sha."
        gate.environment_gate_summary = gate.blocked_reason
        return gate
    staging_record = _successful_staging_deployment_for_task(
        db,
        project_key=project_key,
        service_key=service_key,
        commit_sha=commit_sha,
    )
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
        f"Staging deployment #{int(staging_record.id)} passed for {commit_sha[:12]}."
    )
    gate.environment_gate_summary = (
        "Production gate ready: main commit has passed staging."
    )
    gate.can_deploy_production = True
    gate.blocked_reason = None
    return gate


def _production_workflow_file(policy: Any) -> str:
    return (
        _clean(getattr(policy, "production_workflow_file", None))
        or PRODUCTION_WORKFLOW_FILE
    )


def _production_deployment_metadata(
    *,
    row: ReleaseTaskRow,
    repo_full_name: str,
    service_key: str,
    commit_sha: str,
    staging_record: DeploymentRecordRow,
) -> dict[str, Any]:
    return {
        "release_task_id": int(row.id),
        "service_key": service_key,
        "deploy_repo_full_name": repo_full_name,
        "deploy_strategy": "github_actions_wif_cloudrun",
        "sourceRefType": "branch",
        "sourceRef": "main",
        "deployScope": service_key,
        "gcpProject": PRODUCTION_GCP_PROJECT_ID,
        "region": "us-central1",
        "sourceStagingDeploymentRecordId": int(staging_record.id),
        "environmentIsolationVersion": "v1",
        "resolvedCommitSha": commit_sha,
        "controlledSteps": [
            "github_environment_gate",
            "wif_auth",
            "cloud_build",
            "artifact_push",
            "cloud_run_deploy",
            "prod_smoke",
            "callback",
        ],
    }


def _mark_release_task_dispatch_failed(
    db: Session,
    *,
    row: ReleaseTaskRow,
    record: DeploymentRecordRow,
    actor: str,
    error: Exception,
) -> ReleaseTaskOut:
    message = str(error)[:1000]
    record.status = "failed"
    record.health_status = "failed"
    record.notes = message
    record.finished_at = utcnow()
    row.status = "failed"
    row.operator = actor
    row.note = message
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _release_task_to_out(row, db=db)


def _production_task_row(db: Session, task_id: int, body: Any) -> ReleaseTaskRow:
    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Release task not found.")
    if _clean(row.status).lower() != "requested":
        raise ValueError("Only requested release tasks can be deployed to production.")
    if _clean(row.environment).lower() != "production":
        raise ValueError("Only production release tasks can use production deploy.")
    if _clean(getattr(body, "confirm_phrase", None)) != PRODUCTION_CONFIRM_PHRASE:
        raise ValueError("Production deploy requires confirm_phrase=DEPLOY_PRODUCTION.")
    if _clean(row.branch_name) != "main":
        raise ValueError("Production deploy only allows branch main.")
    service_key = _clean(getattr(row, "service_key", None)).lower()
    project_key = _clean(row.project_key)
    if service_key not in _valid_service_keys_for_project(project_key):
        raise ValueError(_service_key_error_for_project(project_key))
    if row.deployment_record_id is not None:
        raise ValueError("Release task already has a deployment record.")
    return row


def _production_staging_evidence(
    db: Session, gate: ReleaseTaskPrGateOut
) -> DeploymentRecordRow:
    if not (
        gate.can_deploy_production
        and gate.resolved_commit_sha
        and gate.staging_deployment_record_id
    ):
        raise ValueError(gate.blocked_reason or "Production gate is not ready.")
    staging_record = db.get(DeploymentRecordRow, int(gate.staging_deployment_record_id))
    if staging_record is None:
        raise ValueError("Source staging deployment record was not found.")
    return staging_record


def _assert_production_deploy_secrets(repo_full_name: str) -> None:
    missing_secrets, secret_error = _missing_required_production_deploy_secrets(
        repo_full_name
    )
    if missing_secrets:
        detail = ", ".join(missing_secrets)
        suffix = f" ({secret_error})" if secret_error else ""
        raise ValueError(
            f"Production deploy is blocked: missing GitHub secrets {detail}.{suffix}"
        )


def _production_gate_context(
    db: Session, task_id: int, body: Any
) -> tuple[ReleaseTaskRow, Any, str, ReleaseTaskPrGateOut, DeploymentRecordRow, str]:
    row = _production_task_row(db, task_id, body)
    project_key = _clean(row.project_key)
    policy = _policy_for_project(db, project_key)
    repo_full_name = _release_task_deploy_repo(policy, project_key)
    gate = release_task_production_gate(db, row, repo_full_name)
    staging_record = _production_staging_evidence(db, gate)
    _assert_production_deploy_secrets(repo_full_name)
    actor = _clean(getattr(body, "actor", "operator")) or "operator"
    return row, policy, repo_full_name, gate, staging_record, actor


def _create_production_deployment_record(
    db: Session,
    *,
    row: ReleaseTaskRow,
    policy: Any,
    repo_full_name: str,
    gate: ReleaseTaskPrGateOut,
    staging_record: DeploymentRecordRow,
    actor: str,
    note: str | None,
) -> DeploymentRecordRow:
    service_key = _clean(getattr(row, "service_key", None)).lower()
    project_key = _clean(row.project_key)
    workflow_file = _production_workflow_file(policy)
    record = DeploymentRecordRow(
        requirement_id=int(row.requirement_id)
        if row.requirement_id is not None
        else None,
        project_policy_id=int(policy.id) if policy is not None else None,
        project_key=project_key,
        environment="production",
        action="deploy",
        status="requested",
        health_status="checking",
        branch_name="main",
        commit_sha=gate.resolved_commit_sha,
        workflow_file=workflow_file,
        actor=actor,
        trigger_source="release_task",
        notes=note,
        metadata_json=_json_dump(
            _production_deployment_metadata(
                row=row,
                repo_full_name=repo_full_name,
                service_key=service_key,
                commit_sha=gate.resolved_commit_sha,
                staging_record=staging_record,
            )
        ),
        started_at=utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    row.deployment_record_id = int(record.id)
    row.status = "deploying"
    row.operator = actor
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return record


def _production_dispatch_inputs(
    *,
    row: ReleaseTaskRow,
    record: DeploymentRecordRow,
    commit_sha: str,
    service_key: str,
    actor: str,
) -> dict[str, str]:
    inputs = {
        "requirement_id": f"release-task-{int(row.id)}",
        "record_id": str(int(record.id)),
        "commit_sha": commit_sha,
        "source_ref_type": "branch",
        "source_ref": "main",
        "deploy_scope": service_key,
        "actor": actor,
        "trigger_source": "release_task",
    }
    callback_url = _callback_url(int(record.id))
    if callback_url:
        inputs["callback_url"] = callback_url
    if config.DEPLOY_WEBHOOK_TOKEN:
        inputs["callback_token"] = config.DEPLOY_WEBHOOK_TOKEN
    return inputs


def _deploy_release_task_to_production(
    db: Session, task_id: int, body: Any
) -> ReleaseTaskOut:
    row, policy, repo_full_name, gate, staging_record, actor = _production_gate_context(
        db, task_id, body
    )
    note = _clean(getattr(body, "note", None)) or _clean(row.note) or None
    service_key = _clean(getattr(row, "service_key", None)).lower()
    record = _create_production_deployment_record(
        db,
        row=row,
        policy=policy,
        repo_full_name=repo_full_name,
        gate=gate,
        staging_record=staging_record,
        actor=actor,
        note=note,
    )
    workflow_file = _production_workflow_file(policy)
    inputs = _production_dispatch_inputs(
        row=row,
        record=record,
        commit_sha=gate.resolved_commit_sha or "",
        service_key=service_key,
        actor=actor,
    )
    try:
        record.external_url = _dispatch_github_workflow(
            repo_full_name=repo_full_name,
            workflow_file=workflow_file,
            ref="main",
            inputs=inputs,
        )
        db.commit()
        db.refresh(row)
        return _release_task_to_out(row, db=db, pr_gate=gate)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        record = (
            db.get(DeploymentRecordRow, int(row.deployment_record_id))
            if row.deployment_record_id
            else record
        )
        return _mark_release_task_dispatch_failed(
            db, row=row, record=record, actor=actor, error=exc
        )


def deploy_release_task(db: Session, task_id: int, body: Any) -> ReleaseTaskOut:
    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Release task not found.")
    environment = _clean(row.environment).lower()
    if environment == "staging":
        return deploy_release_task_to_staging(db, task_id, body)
    if environment == "production":
        return _deploy_release_task_to_production(db, task_id, body)
    raise ValueError("Release task environment must be staging or production.")
