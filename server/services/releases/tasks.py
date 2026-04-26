"""Manual release task surface.

Release tasks represent release intent and human closure. Staging tasks may be
explicitly deployed only after an operator clicks the staging deploy action.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from server import config
from server.database import DeploymentRecordRow, ProjectPolicyRow, ReleaseTaskRow, RequirementRow, utcnow
from server.schemas import ReleaseBranchOptionOut, ReleaseTaskOut, ReleaseTaskPrGateOut
from server.services.delivery.deployment_governance import _callback_url, _dispatch_github_workflow, _json_dump
from server.services.delivery.pull_request import _gh_env
from server.services.projects.policy_registry import ensure_default_project_policies

VALID_SOURCE_TYPES = {"manual", "requirement_flow"}
VALID_ENVIRONMENTS = {"staging", "production"}
VALID_STATUSES = {"requested", "completed", "failed", "cancelled"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
SYNAPSE_NETWORK_SERVICE_KEYS = {"gateway", "gateway-admin", "admin-front", "user-front"}
PROJECT_SERVICE_KEYS = {
    "synapse-network": SYNAPSE_NETWORK_SERVICE_KEYS,
    "synapse-network-provider": {"provider-service"},
}
DIRECT_STAGING_BRANCHES = {"main"}
SYNAPSE_NETWORK_PROJECT_KEY = "synapse-network"
SYNAPSE_NETWORK_REPO = "cliff-personal/Synapse-Network"
SYNAPSE_NETWORK_PROVIDER_PROJECT_KEY = "synapse-network-provider"
STAGING_WORKFLOW_FILE = "deploy-staging.yml"
E2E_BRANCH_OPTIONS = [
    "main",
    "codex/e2e-staging-release-task",
    "codex/branch-based-staging-deploy",
]
SUCCESS_CHECK_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}
FAILED_CHECK_CONCLUSIONS = {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}
PENDING_CHECK_STATUSES = {"QUEUED", "IN_PROGRESS", "PENDING", "REQUESTED", "WAITING"}
REQUIRED_GCP_STAGING_DEPLOY_SECRETS = {"GCP_WORKLOAD_IDENTITY_PROVIDER", "GCP_DEPLOY_SERVICE_ACCOUNT"}
REQUIRED_PROVIDER_STAGING_DEPLOY_SECRETS = {
    "STAGING_DEPLOY_SSH_KEY",
    "STAGING_DEPLOY_HOST",
    "STAGING_DEPLOY_USER",
    "STAGING_REPO_DIR",
}


def _valid_service_keys_for_project(project_key: str) -> set[str]:
    return PROJECT_SERVICE_KEYS.get(_clean(project_key), SYNAPSE_NETWORK_SERVICE_KEYS)


def _service_key_error_for_project(project_key: str) -> str:
    allowed = ", ".join(sorted(_valid_service_keys_for_project(project_key)))
    return f"service_key must be one of: {allowed}"


def _deploy_strategy_for_project(project_key: str) -> str:
    if _clean(project_key) == SYNAPSE_NETWORK_PROVIDER_PROJECT_KEY:
        return "github_actions_ssh_gce"
    return "github_actions_gcp_cloudrun"


def _controlled_steps_for_project(project_key: str) -> list[str]:
    if _clean(project_key) == SYNAPSE_NETWORK_PROVIDER_PROJECT_KEY:
        return ["checkout", "resolve_ref", "ssh_deploy", "health_check"]
    return ["checkout", "preflight", "build", "push", "cloud_run_deploy", "health_check"]


def _required_staging_deploy_secrets_for_project(project_key: str | None) -> set[str]:
    if _clean(project_key) == SYNAPSE_NETWORK_PROVIDER_PROJECT_KEY:
        return REQUIRED_PROVIDER_STAGING_DEPLOY_SECRETS
    return REQUIRED_GCP_STAGING_DEPLOY_SECRETS


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _json_load(value: str | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not value:
        return fallback or {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return fallback or {}
    return payload if isinstance(payload, dict) else (fallback or {})


def _release_task_to_out(row: ReleaseTaskRow, *, db: Session | None = None, pr_gate: ReleaseTaskPrGateOut | None = None) -> ReleaseTaskOut:
    deployment = getattr(row, "deployment_record", None)
    if pr_gate is None and db is not None:
        pr_gate = _release_task_pr_gate(db, row)
    return ReleaseTaskOut(
        id=int(row.id),
        source_type=str(row.source_type or "manual"),
        requirement_id=int(row.requirement_id) if row.requirement_id is not None else None,
        deployment_record_id=int(row.deployment_record_id) if row.deployment_record_id is not None else None,
        project_key=str(row.project_key or ""),
        project_display_name=_clean(row.project_display_name) or None,
        service_key=_clean(getattr(row, "service_key", None)) or None,
        branch_name=str(row.branch_name or ""),
        environment=str(row.environment or ""),
        status=str(row.status or "requested"),
        actor=_clean(row.actor) or None,
        operator=_clean(row.operator) or None,
        note=_clean(row.note) or None,
        deployment_status=_clean(getattr(deployment, "status", None)) or None,
        deployment_external_run_id=_clean(getattr(deployment, "external_run_id", None)) or None,
        deployment_external_url=_clean(getattr(deployment, "external_url", None)) or None,
        deployment_failure_summary=_clean(getattr(deployment, "notes", None)) or None,
        deployment_health_status=_clean(getattr(deployment, "health_status", None)) or None,
        deployment_workflow_file=_clean(getattr(deployment, "workflow_file", None)) or None,
        deployment_commit_sha=_clean(getattr(deployment, "commit_sha", None)) or None,
        deployment_started_at=getattr(deployment, "started_at", None),
        deployment_finished_at=getattr(deployment, "finished_at", None),
        deployment_metadata=_json_load(getattr(deployment, "metadata_json", None), {}),
        pr_gate=pr_gate or ReleaseTaskPrGateOut(),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _copy_pr_gate(gate: ReleaseTaskPrGateOut) -> ReleaseTaskPrGateOut:
    payload = gate.model_dump() if hasattr(gate, "model_dump") else gate.dict()
    return ReleaseTaskPrGateOut(**payload)


def _release_task_pr_gate_with_row_actions(row: ReleaseTaskRow, gate: ReleaseTaskPrGateOut) -> ReleaseTaskPrGateOut:
    """Attach row-specific actions to a GitHub PR gate snapshot.

    GitHub branch/PR/check state is shared by branch, but create/deploy actions
    depend on the local task row. Keeping this split lets list endpoints cache
    expensive GitHub reads without reusing stale action booleans.
    """

    gate = _copy_pr_gate(gate)
    status = _clean(row.status).lower() or "requested"
    environment = _clean(row.environment).lower()
    has_deployment = row.deployment_record_id is not None
    is_open_pr_state = (gate.pr_state or "").lower() in {"open", "merged"}
    gate.can_create_pr = bool(
        status == "requested"
        and environment == "staging"
        and not has_deployment
        and gate.branch_exists
        and _clean(row.branch_name) not in DIRECT_STAGING_BRANCHES
        and not gate.pr_exists
    )
    gate.can_deploy_staging = bool(
        status == "requested"
        and environment == "staging"
        and not has_deployment
        and gate.branch_exists
        and (
            _clean(row.branch_name) in DIRECT_STAGING_BRANCHES
            or (
                gate.pr_exists
                and is_open_pr_state
                and gate.checks_status == "success"
            )
        )
    )
    return gate


def _project_display_name(db: Session, project_key: str, explicit: str | None) -> str | None:
    if _clean(explicit):
        return _clean(explicit)
    policy = (
        db.query(ProjectPolicyRow)
        .filter(ProjectPolicyRow.project_key == project_key)
        .order_by(ProjectPolicyRow.id.desc())
        .first()
    )
    return _clean(getattr(policy, "display_name", None)) or None


def _policy_for_project(db: Session, project_key: str) -> ProjectPolicyRow | None:
    ensure_default_project_policies(db)
    return (
        db.query(ProjectPolicyRow)
        .filter(ProjectPolicyRow.project_key == project_key)
        .order_by(ProjectPolicyRow.id.desc())
        .first()
    )


def _release_task_deploy_repo(policy: ProjectPolicyRow | None, project_key: str) -> str:
    configured = _clean(getattr(policy, "deploy_repo_full_name", None))
    if configured:
        return configured
    if project_key == SYNAPSE_NETWORK_PROJECT_KEY:
        return SYNAPSE_NETWORK_REPO
    raise ValueError("Release task project is missing deploy_repo_full_name.")


def _release_task_workflow_file(policy: ProjectPolicyRow | None) -> str:
    return _clean(getattr(policy, "staging_workflow_file", None)) or STAGING_WORKFLOW_FILE


def _bounded_error_excerpt(value: str, limit: int = 500) -> str:
    cleaned = _clean(value).replace("\r", "")
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}... [Truncated]"


def _merge_metadata(row: DeploymentRecordRow, updates: dict[str, Any]) -> None:
    metadata = _json_load(getattr(row, "metadata_json", None), {})
    metadata.update({key: value for key, value in updates.items() if value is not None})
    row.metadata_json = _json_dump(metadata)


def _manual_completion_deployment_record(row: ReleaseTaskRow, *, operator: str, note: str | None) -> DeploymentRecordRow:
    now = utcnow()
    metadata = {
        "release_task_id": int(row.id),
        "service_key": _clean(getattr(row, "service_key", None)) or None,
        "source_type": _clean(row.source_type) or "manual",
        "manual_completion": True,
        "manual_completion_note": note,
        "online_record_source": "release_task_manual_completion",
    }
    return DeploymentRecordRow(
        requirement_id=int(row.requirement_id) if row.requirement_id is not None else None,
        project_key=_clean(row.project_key),
        environment=_clean(row.environment).lower(),
        action="deploy",
        status="succeeded",
        branch_name=_clean(row.branch_name),
        actor=_clean(row.actor) or operator,
        trigger_source="release_task_manual_completion",
        health_status="manual_verified",
        notes=note or "Release task manually marked completed.",
        metadata_json=_json_dump(metadata),
        started_at=row.created_at or now,
        finished_at=now,
    )


def _run_gh_json(args: list[str], *, timeout: int = 30) -> tuple[str, Any | None, str]:
    """Run gh and classify the result without raising on GitHub domain states."""

    try:
        completed = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=_gh_env(),
        )
    except FileNotFoundError:
        return "transient_error", None, "GitHub CLI 'gh' is required."
    except subprocess.TimeoutExpired:
        return "transient_error", None, "GitHub CLI request timed out."
    stderr = _bounded_error_excerpt(completed.stderr or completed.stdout or "", 1000)
    lowered = stderr.lower()
    if completed.returncode != 0:
        if any(marker in lowered for marker in ("not found", "no pull requests found", "http 404", "could not resolve")):
            return "not_found", None, stderr or "GitHub resource was not found."
        if any(marker in lowered for marker in ("authentication", "not logged in", "permission", "http 401", "http 403")):
            return "auth_error", None, stderr or "GitHub authentication failed."
        return "transient_error", None, stderr or "GitHub CLI request failed."
    try:
        return "ok", json.loads(completed.stdout or "null"), ""
    except json.JSONDecodeError as exc:
        return "transient_error", None, f"GitHub response was not valid JSON: {exc}"


def _run_gh_text(args: list[str], *, timeout: int = 30) -> tuple[str, str | None, str]:
    try:
        completed = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=_gh_env(),
        )
    except FileNotFoundError:
        return "transient_error", None, "GitHub CLI 'gh' is required."
    except subprocess.TimeoutExpired:
        return "transient_error", None, "GitHub CLI request timed out."
    if completed.returncode != 0:
        return "transient_error", None, _bounded_error_excerpt(completed.stderr or completed.stdout or "", 1000)
    return "ok", completed.stdout or "", ""


def _github_branch_exists(repo_full_name: str, branch_name: str) -> tuple[bool, str | None]:
    if config.E2E_MODE:
        return branch_name in E2E_BRANCH_OPTIONS, None if branch_name in E2E_BRANCH_OPTIONS else "分支不存在，请重新选择有效远端分支"
    status, payload, error = _run_gh_json(
        ["api", f"repos/{repo_full_name}/branches/{quote(branch_name, safe='')}"]
    )
    if status == "ok" and isinstance(payload, dict) and _clean(payload.get("name")):
        return True, None
    if status == "not_found":
        return False, "分支不存在，请重新选择有效远端分支"
    return False, error or "无法确认分支状态，请稍后同步"


def _missing_required_staging_deploy_secrets(repo_full_name: str, project_key: str | None = None) -> tuple[list[str], str | None]:
    """Return missing GitHub secrets required before dispatching staging deploy.

    This is a fail-fast preflight. Without these secrets the GitHub workflow
    fails before build/deploy, so triggering it creates noisy failed runs rather
    than a useful release attempt.
    """

    if config.E2E_MODE:
        return [], None
    required_secrets = _required_staging_deploy_secrets_for_project(project_key)
    status, payload, error = _run_gh_json(
        ["secret", "list", "--repo", repo_full_name, "--json", "name"],
        timeout=30,
    )
    if status != "ok":
        return sorted(required_secrets), error or "Unable to verify GitHub deployment secrets."
    if not isinstance(payload, list):
        return sorted(required_secrets), "GitHub secret list response was not valid."
    present = {_clean(item.get("name")) for item in payload if isinstance(item, dict)}
    missing = sorted(secret for secret in required_secrets if secret not in present)
    return missing, None


def _checks_summary(status_rollup: list[Any]) -> tuple[str, str]:
    if not status_rollup:
        return "unknown", "PR checks 状态未知"
    passed = pending = failed = 0
    for item in status_rollup:
        if not isinstance(item, dict):
            continue
        conclusion = _clean(item.get("conclusion")).upper()
        status = _clean(item.get("status") or item.get("state")).upper()
        if conclusion in FAILED_CHECK_CONCLUSIONS or status in FAILED_CHECK_CONCLUSIONS:
            failed += 1
        elif conclusion in SUCCESS_CHECK_CONCLUSIONS or status == "SUCCESS":
            passed += 1
        elif status in PENDING_CHECK_STATUSES or not conclusion:
            pending += 1
        else:
            pending += 1
    if failed:
        return "failed", f"{failed} failed, {passed} passed, {pending} pending"
    if pending:
        return "pending", f"{pending} pending, {passed} passed"
    if passed:
        return "success", f"{passed} checks passed"
    return "unknown", "PR checks 状态未知"


def _github_pr_for_branch(repo_full_name: str, branch_name: str) -> tuple[dict[str, Any] | None, str | None]:
    if config.E2E_MODE:
        return None, None
    status, payload, error = _run_gh_json(
        [
            "pr",
            "list",
            "--repo",
            repo_full_name,
            "--head",
            branch_name,
            "--state",
            "all",
            "--json",
            "number,url,isDraft,state,headRefName,baseRefName,title,statusCheckRollup",
            "--limit",
            "10",
        ]
    )
    if status == "ok" and isinstance(payload, list) and payload:
        candidates = [item for item in payload if isinstance(item, dict)]
        # Prefer active review gates, then merged PRs with stable checks. Closed
        # unmerged PRs are still returned so the UI can explain the blocker.
        for desired_state in ("OPEN", "MERGED", "CLOSED"):
            for item in candidates:
                if _clean(item.get("state")).upper() == desired_state:
                    return item, None
        return candidates[0], None
    if status == "ok":
        return None, None
    return None, error or "无法读取 PR 状态"


def _release_task_pr_gate_for(row: ReleaseTaskRow, repo_full_name: str) -> ReleaseTaskPrGateOut:
    branch_name = _clean(row.branch_name)
    gate = ReleaseTaskPrGateOut(blocked_reason="等待 PR gate 同步")
    if not branch_name:
        gate.blocked_reason = "branch_name is required"
        return gate
    branch_exists, branch_error = _github_branch_exists(repo_full_name, branch_name)
    gate.branch_exists = branch_exists
    if not branch_exists:
        gate.blocked_reason = branch_error or "分支不存在，请重新选择有效远端分支"
        return gate
    if branch_name in DIRECT_STAGING_BRANCHES:
        gate.pr_state = "main"
        gate.checks_status = "success"
        gate.checks_summary = "main 分支可直接发布 staging，不需要 PR gate。"
        gate.blocked_reason = None
        return _release_task_pr_gate_with_row_actions(row, gate)
    pr_payload, pr_error = _github_pr_for_branch(repo_full_name, branch_name)
    if not pr_payload:
        gate.blocked_reason = pr_error or "未提交 PR"
        return _release_task_pr_gate_with_row_actions(row, gate)
    gate.pr_exists = True
    gate.pr_url = _clean(pr_payload.get("url")) or None
    gate.pr_number = int(pr_payload.get("number")) if pr_payload.get("number") is not None else None
    state = _clean(pr_payload.get("state")).lower() or "open"
    gate.pr_state = "draft" if bool(pr_payload.get("isDraft")) else state
    gate.checks_status, gate.checks_summary = _checks_summary(
        pr_payload.get("statusCheckRollup") if isinstance(pr_payload.get("statusCheckRollup"), list) else []
    )
    if gate.pr_state == "draft":
        gate.blocked_reason = "PR 仍是 Draft，请先在 GitHub 标记 Ready for review 后再发布 staging"
    elif state == "closed":
        gate.blocked_reason = "PR 已关闭且未合并，请重新提交 PR 或选择有效分支"
    elif gate.checks_status != "success":
        gate.blocked_reason = gate.checks_summary or "PR checks 未通过"
    else:
        gate.blocked_reason = None
    return _release_task_pr_gate_with_row_actions(row, gate)


def _release_task_pr_gate(db: Session, row: ReleaseTaskRow) -> ReleaseTaskPrGateOut:
    try:
        policy = _policy_for_project(db, _clean(row.project_key))
        repo_full_name = _release_task_deploy_repo(policy, _clean(row.project_key))
    except ValueError as exc:
        return ReleaseTaskPrGateOut(blocked_reason=str(exc))
    return _release_task_pr_gate_for(row, repo_full_name)


def _github_branch_options(repo_full_name: str, *, max_records: int = 100) -> list[ReleaseBranchOptionOut]:
    if config.E2E_MODE:
        return [
            ReleaseBranchOptionOut(
                name=name,
                commit_sha=f"e2e-{index}",
                protected=name == "main",
                is_default=name == "main",
                source="e2e",
            )
            for index, name in enumerate(E2E_BRANCH_OPTIONS, start=1)
        ]
    command = ["gh", "api", f"repos/{repo_full_name}/branches?per_page={int(max_records)}"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    except FileNotFoundError as exc:
        raise ValueError("GitHub CLI 'gh' is required to load release branch options.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Timed out while loading GitHub branch options.") from exc
    if completed.returncode != 0:
        excerpt = _bounded_error_excerpt(completed.stderr or completed.stdout)
        raise ValueError(f"Failed to load GitHub branch options: {excerpt or 'gh api failed'}")
    try:
        payload = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("GitHub branch response was not valid JSON.") from exc
    if not isinstance(payload, list):
        raise ValueError("GitHub branch response was not a list.")
    options: list[ReleaseBranchOptionOut] = []
    for item in payload[:max_records]:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        if not name:
            continue
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        options.append(
            ReleaseBranchOptionOut(
                name=name,
                commit_sha=_clean(commit.get("sha")) or None,
                protected=bool(item.get("protected")),
                is_default=name == "main",
                source="github",
            )
        )
    options.sort(key=lambda item: (0 if item.name == "main" else 1, item.name.lower()))
    return options


def list_release_task_branch_options(
    db: Session,
    *,
    project_key: str,
    service_key: str | None = None,
) -> list[ReleaseBranchOptionOut]:
    cleaned_project_key = _clean(project_key)
    if not cleaned_project_key:
        raise ValueError("project_key is required")
    cleaned_service_key = _clean(service_key).lower()
    if cleaned_service_key and cleaned_service_key not in _valid_service_keys_for_project(cleaned_project_key):
        raise ValueError(_service_key_error_for_project(cleaned_project_key))
    policy = _policy_for_project(db, cleaned_project_key)
    repo_full_name = _release_task_deploy_repo(policy, cleaned_project_key)
    options = _github_branch_options(repo_full_name)
    if not options:
        raise ValueError(f"No GitHub branches found for {repo_full_name}.")
    return options


def list_release_tasks(
    db: Session,
    *,
    project_key: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
) -> list[ReleaseTaskOut]:
    query = db.query(ReleaseTaskRow)
    if _clean(project_key):
        query = query.filter(ReleaseTaskRow.project_key == _clean(project_key))
    if _clean(environment):
        query = query.filter(ReleaseTaskRow.environment == _clean(environment).lower())
    if _clean(status):
        query = query.filter(ReleaseTaskRow.status == _clean(status).lower())
    if _clean(source_type):
        query = query.filter(ReleaseTaskRow.source_type == _clean(source_type).lower())
    rows = query.order_by(ReleaseTaskRow.updated_at.desc(), ReleaseTaskRow.id.desc()).all()
    repo_cache: dict[str, str] = {}
    gate_cache: dict[tuple[str, str], ReleaseTaskPrGateOut] = {}
    results: list[ReleaseTaskOut] = []
    for row in rows:
        pr_gate: ReleaseTaskPrGateOut | None = None
        project_key_value = _clean(row.project_key)
        branch_name = _clean(row.branch_name)
        if _clean(row.environment).lower() == "staging" and branch_name:
            try:
                repo_full_name = repo_cache.get(project_key_value)
                if repo_full_name is None:
                    policy = _policy_for_project(db, project_key_value)
                    repo_full_name = _release_task_deploy_repo(policy, project_key_value)
                    repo_cache[project_key_value] = repo_full_name
                cache_key = (repo_full_name, branch_name)
                cached_gate = gate_cache.get(cache_key)
                if cached_gate is None:
                    cached_gate = _release_task_pr_gate_for(row, repo_full_name)
                    gate_cache[cache_key] = cached_gate
                pr_gate = _release_task_pr_gate_with_row_actions(row, cached_gate)
            except ValueError as exc:
                pr_gate = ReleaseTaskPrGateOut(blocked_reason=str(exc))
        results.append(_release_task_to_out(row, pr_gate=pr_gate))
    return results


def create_release_task(db: Session, body: Any) -> ReleaseTaskOut:
    source_type = _clean(getattr(body, "source_type", "manual")).lower() or "manual"
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError("source_type must be manual or requirement_flow")
    environment = _clean(getattr(body, "environment", "")).lower()
    if environment not in VALID_ENVIRONMENTS:
        raise ValueError("environment must be staging or production")
    project_key = _clean(getattr(body, "project_key", ""))
    if not project_key:
        raise ValueError("project_key is required")
    branch_name = _clean(getattr(body, "branch_name", ""))
    if not branch_name:
        raise ValueError("branch_name is required")
    service_key = _clean(getattr(body, "service_key", "")).lower()
    if not service_key and project_key == SYNAPSE_NETWORK_PROJECT_KEY:
        service_key = "gateway"
    if service_key and service_key not in _valid_service_keys_for_project(project_key):
        raise ValueError(_service_key_error_for_project(project_key))
    requirement_id = int(getattr(body, "requirement_id", 0) or 0) or None
    if source_type == "manual":
        requirement_id = None
    elif requirement_id is not None and db.get(RequirementRow, requirement_id) is None:
        raise ValueError("Requirement not found.")
    row = ReleaseTaskRow(
        source_type=source_type,
        requirement_id=requirement_id,
        deployment_record_id=None,
        project_key=project_key,
        project_display_name=_project_display_name(db, project_key, getattr(body, "project_display_name", None)),
        service_key=service_key or None,
        branch_name=branch_name,
        environment=environment,
        status="requested",
        actor=_clean(getattr(body, "actor", "operator")) or "operator",
        operator=None,
        note=_clean(getattr(body, "note", None)) or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _release_task_to_out(row, db=db)


def update_release_task(db: Session, task_id: int, body: Any) -> ReleaseTaskOut:
    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Release task not found.")
    current_status = _clean(row.status).lower() or "requested"
    if current_status in TERMINAL_STATUSES:
        raise ValueError("Terminal release task cannot be changed.")
    next_status = _clean(getattr(body, "status", "")).lower()
    if next_status not in TERMINAL_STATUSES:
        raise ValueError("status must be completed, failed, or cancelled")
    row.status = next_status
    row.operator = _clean(getattr(body, "operator", "operator")) or "operator"
    if getattr(body, "note", None) is not None:
        row.note = _clean(getattr(body, "note", None)) or None
    deployment = db.get(DeploymentRecordRow, int(row.deployment_record_id)) if row.deployment_record_id else None
    if deployment is None and next_status == "completed":
        deployment = _manual_completion_deployment_record(row, operator=row.operator or "operator", note=row.note)
        db.add(deployment)
        db.flush()
        row.deployment_record_id = int(deployment.id)
    if deployment is not None:
        deployment.status = {
            "completed": "succeeded",
            "failed": "failed",
            "cancelled": "blocked",
        }[next_status]
        deployment.health_status = {
            "completed": "passed",
            "failed": "failed",
            "cancelled": "not_applicable",
        }[next_status]
        deployment.notes = row.note or f"Release task manually marked {next_status}."
        deployment.finished_at = utcnow()
        if next_status == "completed":
            _merge_metadata(
                deployment,
                {
                    "release_task_id": int(row.id),
                    "service_key": _clean(getattr(row, "service_key", None)) or None,
                    "manual_completion": deployment.trigger_source == "release_task_manual_completion",
                    "online_record_source": deployment.trigger_source,
                },
            )
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _release_task_to_out(
        row,
        pr_gate=ReleaseTaskPrGateOut(blocked_reason=f"Release task manually marked {next_status}."),
    )


def create_release_task_pr(db: Session, task_id: int, body: Any) -> ReleaseTaskOut:
    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Release task not found.")
    if _clean(row.status).lower() != "requested":
        raise ValueError("Only requested release tasks can create staging PR gates.")
    branch_name = _clean(row.branch_name)
    if not branch_name:
        raise ValueError("branch_name is required before PR creation.")
    policy = _policy_for_project(db, _clean(row.project_key))
    repo_full_name = _release_task_deploy_repo(policy, _clean(row.project_key))
    gate = _release_task_pr_gate_for(row, repo_full_name)
    if not gate.branch_exists:
        raise ValueError(gate.blocked_reason or "Release task branch does not exist on GitHub.")
    if gate.pr_exists:
        return _release_task_to_out(row, db=db, pr_gate=gate)

    service_key = _clean(getattr(row, "service_key", None)) or "service"
    environment = _clean(row.environment) or "staging"
    title = f"Release {service_key} {branch_name} to {environment}"
    note = _clean(getattr(body, "note", None)) or _clean(row.note) or None
    body_markdown = "\n".join(
        [
            f"# Release Task #{int(row.id)}",
            "",
            f"- Project: `{_clean(row.project_key)}`",
            f"- Service: `{service_key}`",
            f"- Branch: `{branch_name}`",
            f"- Environment: `{environment}`",
            "",
            "> This PR is a staging release gate. It does not merge automatically and does not trigger production deploy.",
            "",
            "## Operator note",
            note or "No additional note.",
        ]
    )
    if config.E2E_MODE:
        return _release_task_to_out(
            row,
            pr_gate=ReleaseTaskPrGateOut(
                branch_exists=True,
                pr_exists=True,
                pr_url=f"https://github.com/{repo_full_name}/pull/1",
                pr_number=1,
                pr_state="open",
                checks_status="pending",
                checks_summary="PR checks 运行中",
                blocked_reason="PR checks 运行中",
            ),
        )
    command = [
        "gh",
        "pr",
        "create",
        "--repo",
        repo_full_name,
        "--head",
        branch_name,
        "--base",
        "main",
        "--title",
        title,
        "--body",
        body_markdown,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=_gh_env(),
        )
    except FileNotFoundError as exc:
        raise ValueError("GitHub CLI 'gh' is required to create release PRs.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Timed out while creating GitHub PR.") from exc
    if completed.returncode != 0:
        excerpt = _bounded_error_excerpt(completed.stderr or completed.stdout, 1000)
        raise ValueError(f"Failed to create GitHub PR: {excerpt or 'gh pr create failed'}")
    pr_url = _clean(completed.stdout).splitlines()[-1] if _clean(completed.stdout) else None
    return _release_task_to_out(
        row,
        pr_gate=ReleaseTaskPrGateOut(
            branch_exists=True,
            pr_exists=True,
            pr_url=pr_url,
            pr_state="open",
            checks_status="pending",
            checks_summary="PR checks 运行中",
            blocked_reason="PR checks 运行中",
        ),
    )


def _github_actions_run_id_from_url(url: str | None) -> str | None:
    match = re.search(r"/actions/runs/(\d+)", _clean(url))
    return match.group(1) if match else None


def _parse_github_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _find_recent_actions_run_id(repo_full_name: str, record: DeploymentRecordRow, metadata: dict[str, Any]) -> str | None:
    workflow_file = _clean(record.workflow_file) or STAGING_WORKFLOW_FILE
    status, payload, _error = _run_gh_json(
        [
            "run",
            "list",
            "--repo",
            repo_full_name,
            "--workflow",
            workflow_file,
            "--event",
            "workflow_dispatch",
            "--limit",
            "20",
            "--json",
            "databaseId,status,conclusion,createdAt,updatedAt,url,headSha",
        ],
        timeout=30,
    )
    if status != "ok" or not isinstance(payload, list):
        return None
    started_at = _as_utc(record.started_at) or datetime.now(timezone.utc)
    earliest = started_at - timedelta(minutes=5)
    branch = _clean(record.branch_name)
    for item in payload:
        if not isinstance(item, dict):
            continue
        created_at = _parse_github_timestamp(item.get("createdAt"))
        if created_at is not None and created_at < earliest:
            continue
        run_id = item.get("databaseId")
        if run_id is None:
            continue
        # If several release tasks are dispatched close together, prefer a log
        # match on the branch/service inputs. If logs are unavailable, use the
        # newest plausible workflow_dispatch run and reconcile again later.
        log_status, log_payload, _ = _run_gh_text(
            ["run", "view", str(run_id), "--repo", repo_full_name, "--log"],
            timeout=30,
        )
        if log_status == "ok" and isinstance(log_payload, str):
            service_key = _clean(metadata.get("service_key") or metadata.get("deployScope"))
            has_branch = not branch or branch in log_payload
            has_service = not service_key or service_key in log_payload
            if has_branch and has_service:
                return str(run_id)
            continue
        return str(run_id)
    return None


def _github_actions_run_view(repo_full_name: str, run_id: str) -> tuple[dict[str, Any] | None, str | None]:
    status, payload, error = _run_gh_json(
        [
            "run",
            "view",
            str(run_id),
            "--repo",
            repo_full_name,
            "--json",
            "databaseId,status,conclusion,createdAt,updatedAt,url,headSha",
        ],
        timeout=30,
    )
    if status == "ok" and isinstance(payload, dict):
        return payload, None
    return None, error or "Unable to read GitHub Actions run."


def _apply_github_run_to_deployment(
    db: Session,
    record: DeploymentRecordRow,
    *,
    run_payload: dict[str, Any],
    run_id: str,
) -> str:
    now = utcnow()
    status = _clean(run_payload.get("status")).lower()
    conclusion = _clean(run_payload.get("conclusion")).lower()
    run_url = _clean(run_payload.get("url")) or record.external_url
    head_sha = _clean(run_payload.get("headSha")) or None
    record.external_run_id = str(run_id)
    record.external_url = run_url
    _merge_metadata(
        record,
        {
            "githubRunId": str(run_id),
            "githubRunUrl": run_url,
            "githubRunStatus": status,
            "githubRunConclusion": conclusion or None,
            "githubHeadSha": head_sha,
            "lastDeploymentStatusSyncedAt": now.isoformat(),
        },
    )
    task = (
        db.query(ReleaseTaskRow)
        .filter(ReleaseTaskRow.deployment_record_id == int(record.id))
        .order_by(ReleaseTaskRow.id.desc())
        .first()
    )
    if status and status != "completed":
        record.status = "running"
        record.notes = f"GitHub Actions run {status}."
        return "running"
    if conclusion == "success":
        record.status = "succeeded"
        record.health_status = "healthy"
        record.commit_sha = head_sha or record.commit_sha
        record.notes = "staging deploy succeeded; GitHub Actions run passed."
        record.finished_at = now
        if task is not None:
            task.status = "completed"
            task.operator = task.operator or "github_actions_sync"
            task.updated_at = now
        return "succeeded"
    if conclusion in {"failure", "cancelled", "timed_out", "startup_failure", "action_required"}:
        record.status = "failed"
        record.health_status = "failed"
        record.notes = f"GitHub Actions staging deploy {conclusion}."
        record.finished_at = now
        if task is not None:
            task.status = "failed"
            task.operator = task.operator or "github_actions_sync"
            task.note = task.note or record.notes
            task.updated_at = now
        return "failed"
    record.notes = "GitHub Actions run result is not terminal yet."
    return "pending"


def sync_release_task_deployment_statuses(db: Session, *, max_records: int = 50) -> dict[str, Any]:
    bounded_limit = max(1, min(int(max_records or 50), 50))
    rows = (
        db.query(DeploymentRecordRow)
        .filter(
            DeploymentRecordRow.trigger_source == "release_task",
            DeploymentRecordRow.status.in_(["requested", "running", "pending"]),
        )
        .order_by(DeploymentRecordRow.id.asc())
        .limit(bounded_limit)
        .all()
    )
    result: dict[str, Any] = {
        "processed_count": 0,
        "succeeded_ids": [],
        "failed_ids": [],
        "running_ids": [],
        "pending_ids": [],
        "error_ids": [],
    }
    for record in rows:
        result["processed_count"] += 1
        metadata = _json_load(record.metadata_json, {})
        repo_full_name = _clean(metadata.get("deploy_repo_full_name"))
        if not repo_full_name:
            result["error_ids"].append(int(record.id))
            record.notes = "Deployment sync skipped: missing deploy_repo_full_name."
            continue
        run_id = _clean(record.external_run_id) or _github_actions_run_id_from_url(record.external_url)
        if not run_id:
            run_id = _find_recent_actions_run_id(repo_full_name, record, metadata)
        if not run_id:
            result["pending_ids"].append(int(record.id))
            _merge_metadata(record, {"lastDeploymentStatusSyncedAt": utcnow().isoformat(), "deploymentSyncPendingReason": "GitHub Actions run id not found yet"})
            continue
        run_payload, error = _github_actions_run_view(repo_full_name, run_id)
        if run_payload is None:
            result["error_ids"].append(int(record.id))
            record.notes = f"Deployment sync failed: {error}"
            _merge_metadata(record, {"lastDeploymentStatusSyncedAt": utcnow().isoformat(), "deploymentSyncError": error})
            continue
        state = _apply_github_run_to_deployment(db, record, run_payload=run_payload, run_id=run_id)
        key = {
            "succeeded": "succeeded_ids",
            "failed": "failed_ids",
            "running": "running_ids",
            "pending": "pending_ids",
        }.get(state, "pending_ids")
        result[key].append(int(record.id))
    db.commit()
    return result


def deploy_release_task_to_staging(db: Session, task_id: int, body: Any) -> ReleaseTaskOut:
    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Release task not found.")
    if _clean(row.status).lower() != "requested":
        raise ValueError("Only requested release tasks can be deployed to staging.")
    if _clean(row.environment).lower() != "staging":
        raise ValueError("Only staging release tasks can be deployed automatically.")
    branch_name = _clean(row.branch_name)
    if not branch_name:
        raise ValueError("branch_name is required before staging deploy.")
    service_key = _clean(getattr(row, "service_key", None)).lower()
    project_key = _clean(row.project_key)
    if service_key not in _valid_service_keys_for_project(project_key):
        raise ValueError(_service_key_error_for_project(project_key))
    if row.deployment_record_id is not None:
        raise ValueError("Release task already has a deployment record.")

    policy = _policy_for_project(db, project_key)
    repo_full_name = _release_task_deploy_repo(policy, project_key)
    gate = _release_task_pr_gate_for(row, repo_full_name)
    if not gate.can_deploy_staging:
        raise ValueError(gate.blocked_reason or "PR checks must pass before staging deploy.")
    missing_secrets, secret_error = _missing_required_staging_deploy_secrets(repo_full_name, project_key=project_key)
    if missing_secrets:
        detail = ", ".join(missing_secrets)
        suffix = f" ({secret_error})" if secret_error else ""
        raise ValueError(f"Staging deploy is blocked: missing GitHub secrets {detail}.{suffix}")
    workflow_file = _release_task_workflow_file(policy)
    actor = _clean(getattr(body, "actor", "operator")) or "operator"
    note = _clean(getattr(body, "note", None)) or _clean(row.note) or None
    deploy_strategy = _deploy_strategy_for_project(project_key)
    controlled_steps = _controlled_steps_for_project(project_key)
    deployment_metadata = {
        "release_task_id": int(row.id),
        "service_key": service_key,
        "deploy_repo_full_name": repo_full_name,
        "deploy_strategy": deploy_strategy,
        "sourceRefType": "branch",
        "sourceRef": branch_name,
        "deployScope": service_key,
        "controlledSteps": controlled_steps,
    }
    if deploy_strategy == "github_actions_gcp_cloudrun":
        deployment_metadata.update(
            {
                "gcpProject": "engineering-staging-svc-1442",
                "region": "us-central1",
            }
        )
    record = DeploymentRecordRow(
        requirement_id=int(row.requirement_id) if row.requirement_id is not None else None,
        project_policy_id=int(policy.id) if policy is not None else None,
        project_key=project_key,
        environment="staging",
        action="deploy",
        status="requested",
        branch_name=branch_name,
        workflow_file=workflow_file,
        actor=actor,
        trigger_source="release_task",
        notes=note,
        metadata_json=_json_dump(deployment_metadata),
        started_at=utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    row.deployment_record_id = int(record.id)
    row.operator = actor
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    inputs = {
        "requirement_id": f"release-task-{int(row.id)}",
        "record_id": str(int(record.id)),
        "commit_sha": "",
        "source_ref_type": "branch",
        "source_ref": branch_name,
        "deploy_scope": service_key,
        "actor": actor,
        "trigger_source": "release_task",
    }
    callback_url = _callback_url(int(record.id))
    if callback_url:
        inputs["callback_url"] = callback_url
    if config.DEPLOY_WEBHOOK_TOKEN:
        inputs["callback_token"] = config.DEPLOY_WEBHOOK_TOKEN

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
        record = db.get(DeploymentRecordRow, int(row.deployment_record_id)) if row.deployment_record_id else None
        if record is None:
            record = DeploymentRecordRow(
                requirement_id=int(row.requirement_id) if row.requirement_id is not None else None,
                project_policy_id=int(policy.id) if policy is not None else None,
                project_key=project_key,
                environment="staging",
                action="deploy",
                status="failed",
                branch_name=branch_name,
                workflow_file=workflow_file,
                actor=actor,
                trigger_source="release_task",
                notes=str(exc)[:1000],
                metadata_json=_json_dump(
                    {
                        "release_task_id": int(row.id),
                        "service_key": service_key,
                        "deploy_repo_full_name": repo_full_name,
                        "deploy_strategy": deploy_strategy,
                        "dispatch_failed_before_record_commit": True,
                    }
                ),
                started_at=utcnow(),
            )
            db.add(record)
            db.flush()
            row.deployment_record_id = int(record.id)
        record.status = "failed"
        record.health_status = "failed"
        record.notes = str(exc)[:1000]
        record.finished_at = utcnow()
        row.status = "failed"
        row.operator = actor
        row.note = str(exc)[:1000]
        row.updated_at = utcnow()
        db.commit()
        db.refresh(row)
        return _release_task_to_out(row, db=db, pr_gate=gate)
