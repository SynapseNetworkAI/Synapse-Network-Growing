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
    _json_dump,
)
from server.services.releases.github_cli import run_gh_json as _run_gh_json
from server.services.releases.tasks import (
    E2E_BRANCH_OPTIONS,
    _clean,
    _policy_for_project,
    _release_task_deploy_repo,
    _release_task_to_out,
    _service_key_error_for_project,
    _valid_service_keys_for_project,
    deploy_release_task_to_staging,
)
from server.services.releases.production_workflows import (
    production_workflow_file_for_service,
)
from server.services.releases.production_staging_evidence import (
    deployment_commit_sha as _deployment_commit_sha,
    latest_successful_staging_deployment as _latest_successful_staging_deployment,
    successful_staging_deployment_for_commit as _successful_staging_deployment_for_task,
)

PRODUCTION_GCP_PROJECT_ID = "synapse-network-prod"
PRODUCTION_CONFIRM_PHRASE = "YES"
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
    current_main_sha, commit_error = _github_branch_commit_sha(repo_full_name, branch_name)
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
        gate.environment_gate_summary = (
            "Redeploy the current main commit to staging before production."
        )
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


def _production_workflow_file(
    policy: Any, *, project_key: str, service_key: str
) -> str:
    return production_workflow_file_for_service(
        configured_workflow_file=getattr(policy, "production_workflow_file", None),
        project_key=project_key,
        service_key=service_key,
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


def _pending_production_deployment_metadata(
    *,
    row: ReleaseTaskRow,
    repo_full_name: str,
    service_key: str,
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
        "environmentIsolationVersion": "v1",
        "dispatchPending": True,
        "dispatchStatus": "pending",
    }


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


def _create_pending_production_deployment_record(
    db: Session,
    *,
    row: ReleaseTaskRow,
    policy: Any,
    repo_full_name: str,
    actor: str,
    note: str | None,
) -> DeploymentRecordRow:
    service_key = _clean(getattr(row, "service_key", None)).lower()
    project_key = _clean(row.project_key)
    workflow_file = _production_workflow_file(
        policy, project_key=project_key, service_key=service_key
    )
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
        workflow_file=workflow_file,
        actor=actor,
        trigger_source="release_task",
        notes=note or "Production dispatch pending; sync will verify gate before dispatch.",
        metadata_json=_json_dump(
            _pending_production_deployment_metadata(
                row=row,
                repo_full_name=repo_full_name,
                service_key=service_key,
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
    row.note = note
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
        "actor": actor,
        "trigger_source": "release_task",
    }
    if _clean(getattr(record, "workflow_file", None)) == "deploy-production-frontends.yml":
        inputs["deploy_scope"] = service_key
    callback_url = _callback_url(int(record.id))
    if callback_url:
        inputs["callback_url"] = callback_url
    if config.DEPLOY_WEBHOOK_TOKEN:
        inputs["callback_token"] = config.DEPLOY_WEBHOOK_TOKEN
    return inputs


def _deploy_release_task_to_production(
    db: Session, task_id: int, body: Any
) -> ReleaseTaskOut:
    row = _production_task_row(db, task_id, body)
    project_key = _clean(row.project_key)
    policy = _policy_for_project(db, project_key)
    repo_full_name = _release_task_deploy_repo(policy, project_key)
    actor = _clean(getattr(body, "actor", "operator")) or "operator"
    note = _clean(getattr(body, "note", None)) or _clean(row.note) or None
    _create_pending_production_deployment_record(
        db,
        row=row,
        policy=policy,
        repo_full_name=repo_full_name,
        actor=actor,
        note=note,
    )
    queued_gate = ReleaseTaskPrGateOut(
        branch_exists=True,
        pr_state="production",
        checks_status="pending",
        checks_summary="Production dispatch queued.",
        environment_gate_summary="Production dispatch queued; sync will verify gate before dispatch.",
        blocked_reason=None,
    )
    return _release_task_to_out(row, db=db, pr_gate=queued_gate)


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
