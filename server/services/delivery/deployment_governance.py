from __future__ import annotations

"""Deployment governance helpers for staging/prod release records and triggers."""

import json
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from server import config
from server.database import DeploymentRecordRow, ProjectPolicyRow, ReleaseRecordRow, RequirementRow, utcnow
from server.schemas import (
    DeliveryStateOut,
    DeploymentOverviewOut,
    DeploymentProjectOverviewOut,
    DeploymentRecordOut,
    DeploymentRequirementCandidateOut,
    EnvironmentStatusOut,
)
from server.services.projects.policy import (
    list_project_policies,
    project_policy_to_dict,
    resolve_project_policies_for_target,
)


def _json_load(raw: str | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not raw:
        return dict(fallback or {})
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return dict(fallback or {})
    if not isinstance(data, dict):
        return dict(fallback or {})
    return dict(data)


def _json_dump(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _github_token() -> str:
    return (
        config.GH_TOKEN.strip()
        or config.GITHUB_TOKEN.strip()
        or config.COPILOT_GITHUB_TOKEN.strip()
        or config.COPILOT_OAUTH_TOKEN.strip()
    )


def _github_headers() -> dict[str, str]:
    token = _github_token()
    if not token:
        raise ValueError("GitHub token is not configured for deployment dispatch.")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _workflow_page_url(repo_full_name: str, workflow_file: str) -> str:
    return f"https://github.com/{repo_full_name}/actions/workflows/{workflow_file}"


def _deployment_record_to_dict(row: DeploymentRecordRow) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "requirement_id": int(row.requirement_id),
        "project_policy_id": int(row.project_policy_id) if row.project_policy_id is not None else None,
        "project_key": str(row.project_key or ""),
        "environment": str(row.environment or ""),
        "action": str(row.action or "deploy"),
        "status": str(row.status or "requested"),
        "commit_sha": str(row.commit_sha or "").strip() or None,
        "branch_name": str(row.branch_name or "").strip() or None,
        "workflow_file": str(row.workflow_file or "").strip() or None,
        "external_run_id": str(row.external_run_id or "").strip() or None,
        "external_url": str(row.external_url or "").strip() or None,
        "actor": str(row.actor or "").strip() or None,
        "trigger_source": str(row.trigger_source or "ops_console"),
        "rollback_target_sha": str(row.rollback_target_sha or "").strip() or None,
        "health_status": str(row.health_status or "").strip() or None,
        "notes": str(row.notes or "").strip() or None,
        "metadata": _json_load(getattr(row, "metadata_json", None), {}),
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_requirement_deployment_records(db: Session, requirement_id: int) -> list[DeploymentRecordOut]:
    rows = (
        db.query(DeploymentRecordRow)
        .filter(DeploymentRecordRow.requirement_id == requirement_id)
        .order_by(DeploymentRecordRow.id.desc())
        .all()
    )
    return [DeploymentRecordOut(**_deployment_record_to_dict(row)) for row in rows]


def _list_project_deployment_records(
    db: Session,
    project_key: str,
    *,
    limit: int = 6,
) -> list[DeploymentRecordOut]:
    rows = (
        db.query(DeploymentRecordRow)
        .filter(DeploymentRecordRow.project_key == project_key)
        .order_by(DeploymentRecordRow.id.desc())
        .limit(max(1, limit))
        .all()
    )
    return [DeploymentRecordOut(**_deployment_record_to_dict(row)) for row in rows]


def _environment_host_label(policy: ProjectPolicyRow, environment: str) -> str | None:
    if environment == "production":
        return str(getattr(policy, "production_host_label", "") or "").strip() or None
    return str(getattr(policy, "staging_host_label", "") or "").strip() or None


def _latest_environment_row(db: Session, project_key: str, environment: str) -> DeploymentRecordRow | None:
    return (
        db.query(DeploymentRecordRow)
        .filter(
            DeploymentRecordRow.project_key == project_key,
            DeploymentRecordRow.environment == environment,
        )
        .order_by(DeploymentRecordRow.id.desc())
        .first()
    )


def _latest_success_row(
    db: Session,
    project_key: str,
    environment: str,
    *,
    commit_sha: str | None = None,
) -> DeploymentRecordRow | None:
    query = db.query(DeploymentRecordRow).filter(
        DeploymentRecordRow.project_key == project_key,
        DeploymentRecordRow.environment == environment,
        DeploymentRecordRow.status == "succeeded",
    )
    if commit_sha:
        query = query.filter(DeploymentRecordRow.commit_sha == commit_sha)
    return query.order_by(DeploymentRecordRow.id.desc()).first()


def build_project_environment_statuses(db: Session, policy: ProjectPolicyRow) -> list[EnvironmentStatusOut]:
    data = project_policy_to_dict(policy)
    statuses: list[EnvironmentStatusOut] = []
    for environment in ("staging", "production"):
        row = _latest_environment_row(db, data["project_key"], environment)
        statuses.append(
            EnvironmentStatusOut(
                environment=environment,
                project_key=data["project_key"],
                deploy_repo_full_name=data.get("deploy_repo_full_name"),
                host_label=_environment_host_label(policy, environment),
                deploy_strategy=data.get("deploy_strategy") or "github_actions_ssh",
                trigger_enabled=bool(data.get("deploy_trigger_enabled")),
                current_commit_sha=str(getattr(row, "commit_sha", "") or "").strip() or None,
                current_branch=str(getattr(row, "branch_name", "") or "").strip() or None,
                last_success_at=(row.finished_at or row.started_at).isoformat() if row and row.status == "succeeded" else None,
                health_status=str(getattr(row, "health_status", "") or "").strip() or None,
                last_trigger_source=str(getattr(row, "trigger_source", "") or "").strip() or None,
                last_external_url=str(getattr(row, "external_url", "") or "").strip() or None,
                last_record_id=int(row.id) if row is not None else None,
            )
        )
    return statuses


def _requirement_delivery_payload(db: Session, requirement_id: int) -> dict[str, Any]:
    release = (
        db.query(ReleaseRecordRow)
        .filter(ReleaseRecordRow.requirement_id == requirement_id)
        .order_by(ReleaseRecordRow.id.desc())
        .first()
    )
    if release is None:
        return {}
    metadata = _json_load(getattr(release, "metadata_json", None), {})
    return {
        **metadata,
        "latest_remote_sha": str(getattr(release, "commit_sha", "") or "").strip() or None,
        "latest_commit_sha": str(getattr(release, "commit_sha", "") or "").strip() or None,
        "head_branch": str(getattr(release, "actual_branch_name", "") or getattr(release, "branch_name", "") or "").strip() or None,
        "branch_name": str(getattr(release, "branch_name", "") or "").strip() or None,
    }


def _resolve_commit_sha(db: Session, requirement: RequirementRow, explicit_commit_sha: str | None = None) -> str:
    if explicit_commit_sha and explicit_commit_sha.strip():
        return explicit_commit_sha.strip()
    payload = _requirement_delivery_payload(db, int(requirement.id))
    commit_sha = (
        str(payload.get("latest_remote_sha") or "").strip()
        or str(payload.get("latest_commit_sha") or "").strip()
    )
    if commit_sha:
        return commit_sha
    raise ValueError("Requirement is missing a deliverable commit SHA. Sync branch delivery before deploy.")


def _callback_url(record_id: int) -> str | None:
    base = config.DEPLOY_PUBLIC_BASE_URL.strip()
    if not base:
        return None
    return f"{base.rstrip('/')}/api/deployments/{record_id}/report"


def _dispatch_github_workflow(
    *,
    repo_full_name: str,
    workflow_file: str,
    ref: str,
    inputs: dict[str, str],
) -> str:
    url = f"{config.DEPLOY_GITHUB_API_BASE_URL.rstrip('/')}/repos/{repo_full_name}/actions/workflows/{workflow_file}/dispatches"
    response = httpx.post(
        url,
        headers=_github_headers(),
        json={"ref": ref, "inputs": inputs},
        timeout=max(1, config.DEPLOY_TIMEOUT_SECONDS),
    )
    if response.status_code >= 400:
        detail = response.text.strip() or f"HTTP {response.status_code}"
        raise ValueError(f"GitHub workflow dispatch failed: {detail}")
    return _workflow_page_url(repo_full_name, workflow_file)


def _require_policy_for_requirement(db: Session, requirement: RequirementRow) -> ProjectPolicyRow:
    policies = resolve_project_policies_for_target(
        db,
        getattr(requirement, "target_project_path", None),
        require_active=True,
    )
    if not policies:
        raise ValueError("Requirement target project is not governed by an active project policy.")
    return policies[0]


def trigger_requirement_deployment(
    db: Session,
    requirement_id: int,
    *,
    environment: str,
    actor: str = "operator",
    note: str | None = None,
    commit_sha: str | None = None,
    rollback_target_sha: str | None = None,
    trigger_source: str = "ops_console",
) -> DeploymentRecordOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    policy = _require_policy_for_requirement(db, requirement)
    policy_data = project_policy_to_dict(policy)
    if not bool(policy_data.get("deploy_trigger_enabled")):
        raise ValueError("Deploy trigger is disabled by project policy.")
    repo_full_name = str(policy_data.get("deploy_repo_full_name") or "").strip()
    if not repo_full_name:
        raise ValueError("Project policy is missing deploy_repo_full_name.")
    env_name = str(environment or "").strip().lower()
    if env_name not in {"staging", "production"}:
        raise ValueError("environment must be staging or production")

    action = "rollback" if rollback_target_sha else ("promote" if env_name == "production" else "deploy")
    effective_commit_sha = _resolve_commit_sha(db, requirement, rollback_target_sha or commit_sha)
    if env_name == "production" and not rollback_target_sha:
        staging_success = _latest_success_row(db, policy_data["project_key"], "staging", commit_sha=effective_commit_sha)
        if staging_success is None:
            raise ValueError("Production promotion requires a successful staging deployment for the same commit.")

    workflow_file = (
        str(policy_data.get("production_workflow_file") or "deploy-production.yml")
        if env_name == "production"
        else str(policy_data.get("staging_workflow_file") or "deploy-staging.yml")
    )
    delivery_payload = _requirement_delivery_payload(db, requirement_id)
    branch_name = str(delivery_payload.get("head_branch") or delivery_payload.get("branch_name") or "").strip() or None

    record = DeploymentRecordRow(
        requirement_id=requirement_id,
        project_policy_id=int(policy.id),
        project_key=str(policy_data["project_key"]),
        environment=env_name,
        action=action,
        status="requested",
        commit_sha=effective_commit_sha,
        branch_name=branch_name,
        workflow_file=workflow_file,
        actor=(actor or "operator").strip() or "operator",
        trigger_source=(trigger_source or "ops_console").strip() or "ops_console",
        rollback_target_sha=(rollback_target_sha or "").strip() or None,
        notes=(note or "").strip() or None,
        metadata_json=_json_dump(
            {
                "deploy_repo_full_name": repo_full_name,
                "deploy_strategy": str(policy_data.get("deploy_strategy") or "github_actions_ssh"),
                "host_label": _environment_host_label(policy, env_name),
            }
        ),
        started_at=utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    inputs = {
        "requirement_id": str(requirement_id),
        "commit_sha": effective_commit_sha,
        "actor": record.actor or "operator",
        "trigger_source": record.trigger_source or "ops_console",
        "record_id": str(record.id),
    }
    callback_url = _callback_url(int(record.id))
    if callback_url:
        inputs["callback_url"] = callback_url
    if config.DEPLOY_WEBHOOK_TOKEN:
        inputs["callback_token"] = config.DEPLOY_WEBHOOK_TOKEN
    if rollback_target_sha:
        inputs["rollback_target_sha"] = rollback_target_sha.strip()

    try:
        record.external_url = _dispatch_github_workflow(
            repo_full_name=repo_full_name,
            workflow_file=workflow_file,
            ref="main",
            inputs=inputs,
        )
        db.commit()
        db.refresh(record)
    except Exception as exc:  # noqa: BLE001
        record.status = "blocked"
        record.notes = str(exc)
        record.finished_at = utcnow()
        db.commit()
        db.refresh(record)
        raise

    return DeploymentRecordOut(**_deployment_record_to_dict(record))


def report_deployment_result(
    db: Session,
    record_id: int,
    *,
    status: str,
    external_run_id: str | None = None,
    external_url: str | None = None,
    health_status: str | None = None,
    branch_name: str | None = None,
    commit_sha: str | None = None,
    notes: str | None = None,
) -> DeploymentRecordOut:
    row = db.query(DeploymentRecordRow).filter(DeploymentRecordRow.id == record_id).first()
    if row is None:
        raise ValueError("Deployment record not found.")
    row.status = (status or "").strip() or row.status
    if external_run_id is not None:
        row.external_run_id = external_run_id.strip() or None
    if external_url is not None:
        row.external_url = external_url.strip() or row.external_url
    if health_status is not None:
        row.health_status = health_status.strip() or None
    if branch_name is not None:
        row.branch_name = branch_name.strip() or None
    if commit_sha is not None:
        row.commit_sha = commit_sha.strip() or row.commit_sha
    if notes is not None:
        row.notes = notes.strip() or None
    row.finished_at = utcnow() if row.status in {"succeeded", "failed", "rolled_back", "blocked"} else row.finished_at
    db.commit()
    db.refresh(row)
    return DeploymentRecordOut(**_deployment_record_to_dict(row))


def build_requirement_deployment_summary(db: Session, requirement: RequirementRow) -> dict[str, Any]:
    try:
        policy = _require_policy_for_requirement(db, requirement)
    except Exception:
        return {
            "staging_status": None,
            "production_status": None,
            "last_deployed_sha": None,
            "last_deployed_at": None,
            "deploy_readiness": {
                "ready": False,
                "blockers": ["No active project policy with deploy governance is configured."],
            },
        }
    policy_data = project_policy_to_dict(policy)
    statuses = build_project_environment_statuses(db, policy)
    latest_success = (
        db.query(DeploymentRecordRow)
        .filter(
            DeploymentRecordRow.project_key == policy_data["project_key"],
            DeploymentRecordRow.status == "succeeded",
        )
        .order_by(DeploymentRecordRow.id.desc())
        .first()
    )
    requirement_payload = _requirement_delivery_payload(db, int(requirement.id))
    deliverable_commit = (
        str(requirement_payload.get("latest_remote_sha") or "").strip()
        or str(requirement_payload.get("latest_commit_sha") or "").strip()
        or None
    )
    blockers: list[str] = []
    if not policy_data.get("deploy_trigger_enabled"):
        blockers.append("deploy trigger disabled by project policy")
    if not policy_data.get("deploy_repo_full_name"):
        blockers.append("deploy repo mapping missing")
    if not deliverable_commit:
        blockers.append("deliverable commit SHA missing")
    return {
        "staging_status": statuses[0].model_dump(),
        "production_status": statuses[1].model_dump(),
        "last_deployed_sha": str(getattr(latest_success, "commit_sha", "") or "").strip() or None,
        "last_deployed_at": (
            (latest_success.finished_at or latest_success.started_at).isoformat()
            if latest_success is not None and (latest_success.finished_at or latest_success.started_at) is not None
            else None
        ),
        "deploy_readiness": {
            "ready": len(blockers) == 0,
            "blockers": blockers,
            "project_key": policy_data["project_key"],
            "deploy_repo_full_name": policy_data.get("deploy_repo_full_name"),
            "deliverable_commit_sha": deliverable_commit,
        },
    }


def build_deployment_overview(
    db: Session,
    *,
    candidate_limit: int = 20,
    record_limit: int = 6,
) -> DeploymentOverviewOut:
    project_overviews: list[DeploymentProjectOverviewOut] = []
    policies = list_project_policies(db)
    for policy in policies:
        policy_data = project_policy_to_dict(policy)
        recent_records = _list_project_deployment_records(db, policy_data["project_key"], limit=record_limit)
        has_deploy_governance = bool(policy_data.get("deploy_repo_full_name")) or bool(policy_data.get("deploy_trigger_enabled"))
        if not has_deploy_governance and not recent_records:
            continue
        project_overviews.append(
            DeploymentProjectOverviewOut(
                project_policy_id=int(policy.id),
                project_key=policy_data["project_key"],
                display_name=policy_data["display_name"],
                deploy_repo_full_name=policy_data.get("deploy_repo_full_name"),
                deploy_strategy=str(policy_data.get("deploy_strategy") or "github_actions_ssh"),
                deploy_trigger_enabled=bool(policy_data.get("deploy_trigger_enabled")),
                staging_host_label=policy_data.get("staging_host_label"),
                production_host_label=policy_data.get("production_host_label"),
                environment_statuses=build_project_environment_statuses(db, policy),
                recent_records=recent_records,
            )
        )

    release_candidates: list[DeploymentRequirementCandidateOut] = []
    requirements = (
        db.query(RequirementRow)
        .filter(RequirementRow.status == "done")
        .order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc())
        .limit(max(1, candidate_limit))
        .all()
    )
    for requirement in requirements:
        records = list_requirement_deployment_records(db, int(requirement.id))
        project_key = None
        project_display_name = None
        has_deploy_governance = False
        try:
            policy = _require_policy_for_requirement(db, requirement)
            policy_data = project_policy_to_dict(policy)
            project_key = str(policy_data.get("project_key") or "").strip() or None
            project_display_name = str(policy_data.get("display_name") or "").strip() or None
            has_deploy_governance = bool(policy_data.get("deploy_repo_full_name")) or bool(policy_data.get("deploy_trigger_enabled"))
        except Exception:
            policy = None
        if not has_deploy_governance and not records:
            continue
        deploy_summary = build_requirement_deployment_summary(db, requirement)
        release_candidates.append(
            DeploymentRequirementCandidateOut(
                requirement_id=int(requirement.id),
                title=str(requirement.title or ""),
                status=str(requirement.status or "draft"),
                priority=str(requirement.priority or "normal"),
                source=str(requirement.source or "manual"),
                source_ref=str(requirement.source_ref or "").strip() or None,
                project_key=project_key,
                project_display_name=project_display_name,
                target_project_path=str(requirement.target_project_path or "").strip() or None,
                updated_at=requirement.updated_at,
                delivery_state=DeliveryStateOut(**deploy_summary),
                deployment_records=records[:record_limit],
            )
        )

    return DeploymentOverviewOut(
        project_overviews=project_overviews,
        release_candidates=release_candidates,
    )
