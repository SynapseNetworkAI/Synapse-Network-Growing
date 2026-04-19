"""Release service backed by declarative workflow runs."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow, ProjectRow, ReleaseRecordRow, RequirementRow, WorkflowRunRow, utcnow
from server.schemas import ReleaseCandidateOut, ReleaseDetailOut, ValidationCheckResultOut, ValidationRecordSlimOut
from server.services.delivery.deployment_governance import list_requirement_deployment_records, trigger_requirement_deployment
from server.services.delivery.pull_request import sync_requirement_review_pr
from server.services.delivery.vcs import execute_requirement_delivery_vcs
from server.services.projects.project_center import project_to_dict
from server.services.requirements.service import _requirement_to_out, _target_projects_for_requirement, release_to_out


def _json_load(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _slug(value: str, *, limit: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-._")
    return (slug or "requirement")[:limit].strip("-._") or "requirement"


def _latest_workflow_run(db: Session, requirement_id: int) -> WorkflowRunRow | None:
    return (
        db.query(WorkflowRunRow)
        .filter(WorkflowRunRow.requirement_id == requirement_id)
        .order_by(WorkflowRunRow.id.desc())
        .first()
    )


def _active_or_latest_workflow_run(db: Session, requirement: RequirementRow) -> WorkflowRunRow | None:
    active_id = int(getattr(requirement, "active_workflow_run_id", 0) or 0)
    if active_id > 0:
        run = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == active_id).first()
        if run is not None:
            return run
    return _latest_workflow_run(db, int(requirement.id))


def _latest_release(db: Session, requirement_id: int) -> ReleaseRecordRow | None:
    return (
        db.query(ReleaseRecordRow)
        .filter(ReleaseRecordRow.requirement_id == requirement_id)
        .order_by(ReleaseRecordRow.id.desc())
        .first()
    )


def _project_for_requirement(requirement: RequirementRow) -> ProjectRow | None:
    return getattr(requirement, "project", None)


def _blackboard(run: WorkflowRunRow | None) -> dict[str, Any]:
    if run is None:
        return {}
    payload = _json_load(getattr(run, "blackboard_json", None), {})
    return payload if isinstance(payload, dict) else {}


def _workflow_validation_out(run: WorkflowRunRow | None, requirement_id: int) -> ValidationRecordSlimOut | None:
    if run is None:
        return None
    blackboard = _blackboard(run)
    verification = blackboard.get("verification") if isinstance(blackboard.get("verification"), dict) else {}
    gate = blackboard.get("gate") if isinstance(blackboard.get("gate"), dict) else {}
    status = "passed" if str(getattr(run, "status", "") or "") in {"succeeded", "awaiting_operator"} and str(verification.get("status") or "passed") == "passed" else "pending"
    checks = [
        ValidationCheckResultOut(
            label="Workflow verification",
            command=str(verification.get("command") or "").strip() or None,
            status=str(verification.get("status") or status),
        ),
        ValidationCheckResultOut(
            label="Risk evidence gate",
            status=str(gate.get("decision") or "not_applicable"),
        ),
    ]
    return ValidationRecordSlimOut(
        id=int(run.id),
        requirement_id=requirement_id,
        execution_run_id=0,
        profile=str(run.workflow_key or "declarative_workflow"),
        status=status,
        summary_markdown=f"Declarative workflow `{run.workflow_key}` reached `{run.current_state}` with status `{run.status}`.",
        checks=checks,
        reasoning_markdown="Validation is derived from workflow blackboard evidence.",
        suggested_next_action="open_pr" if status == "passed" else "wait_for_workflow",
        resolution_path=str(run.resolution or "").strip() or None,
        created_at=run.started_at or run.created_at,
        updated_at=run.updated_at,
    )


def _release_branch_name(requirement: RequirementRow) -> str:
    return f"ops/req-{int(requirement.id)}-{_slug(str(requirement.title or 'requirement'))}"


def _compare_url(remote_url: str | None, base_branch: str, branch_name: str) -> str | None:
    value = str(remote_url or "").strip()
    if value.startswith("git@github.com:"):
        path = value.split(":", 1)[1]
        if path.endswith(".git"):
            path = path[:-4]
        return f"https://github.com/{path}/compare/{base_branch}...{branch_name}"
    match = re.match(r"https?://github\.com/(?P<path>.+?)(?:\.git)?/?$", value)
    if match:
        return f"https://github.com/{match.group('path')}/compare/{base_branch}...{branch_name}"
    return None


def _release_record(db: Session, requirement: RequirementRow, run: WorkflowRunRow | None) -> ReleaseRecordRow:
    release = _latest_release(db, int(requirement.id))
    project = _project_for_requirement(requirement)
    workflow_run_id = int(run.id) if run is not None else None
    if release is None:
        release = ReleaseRecordRow(
            requirement_id=int(requirement.id),
            workflow_run_id=workflow_run_id,
            operating_manifest_id=int(getattr(requirement, "operating_manifest_id", 0) or 0) or None,
            goal_key=str(getattr(requirement, "goal_key", "") or "").strip() or None,
            project_id=int(project.id) if project is not None else getattr(requirement, "project_id", None),
            project_key=str(getattr(project, "project_key", "") or getattr(requirement, "project_key", "") or "").strip() or None,
            project_display_name=str(getattr(project, "display_name", "") or getattr(requirement, "project_display_name", "") or "").strip() or None,
            target_project_path=str(getattr(requirement, "target_project_path", "") or "").strip() or None,
            status="ready",
            delivery_state="pending",
            repairability="manual_only",
        )
        db.add(release)
        db.flush()
    else:
        release.workflow_run_id = workflow_run_id or getattr(release, "workflow_run_id", None)
        release.operating_manifest_id = int(getattr(requirement, "operating_manifest_id", 0) or 0) or None
        release.goal_key = str(getattr(requirement, "goal_key", "") or "").strip() or None
    return release


def _apply_pr_payload(release: ReleaseRecordRow, pr: dict[str, Any], *, note: str | None = None) -> None:
    sync = pr.get("sync") if isinstance(pr.get("sync"), dict) else {}
    vcs = pr.get("vcs") if isinstance(pr.get("vcs"), dict) else {}
    release.status = "pr_opened" if pr.get("created") else "release_blocked"
    release.delivery_state = "pr_open" if pr.get("created") else "blocked"
    release.branch_name = str(pr.get("branch_name") or sync.get("branch_name") or vcs.get("branch_name") or "").strip() or release.branch_name
    release.actual_branch_name = release.branch_name
    release.base_branch = str(pr.get("base_branch") or sync.get("base_branch") or vcs.get("base_branch") or "main").strip() or "main"
    release.commit_sha = str(vcs.get("latest_commit_sha") or vcs.get("commit_sha") or sync.get("latest_commit_sha") or "").strip() or release.commit_sha
    release.compare_url = str(pr.get("compare_url") or sync.get("compare_url") or "").strip() or release.compare_url
    release.pr_url = str(pr.get("url") or sync.get("pr_url") or "").strip() or release.pr_url
    release.pr_number = int(pr.get("number") or sync.get("pr_number")) if (pr.get("number") or sync.get("pr_number")) is not None else release.pr_number
    release.delivered_at = release.delivered_at or utcnow() if pr.get("created") else release.delivered_at
    release.notes = note
    release.metadata_json = _json_dump({"pr": pr})


def _pr_from_workflow(run: WorkflowRunRow | None) -> dict[str, Any]:
    blackboard = _blackboard(run)
    pr = blackboard.get("pr")
    return dict(pr) if isinstance(pr, dict) else {}


def list_release_candidates(db: Session) -> list[ReleaseCandidateOut]:
    rows = (
        db.query(RequirementRow)
        .filter(
            or_(
                RequirementRow.active_workflow_run_id.isnot(None),
                RequirementRow.workflow_state.in_(["completed", "ready_for_merge", "awaiting_operator"]),
                RequirementRow.status.in_(["completed", "done", "delivery_ready"]),
            )
        )
        .order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc())
        .all()
    )
    result: list[ReleaseCandidateOut] = []
    for requirement in rows:
        run = _active_or_latest_workflow_run(db, requirement)
        validation = _workflow_validation_out(run, int(requirement.id))
        if validation is None or validation.status != "passed":
            continue
        result.append(
            ReleaseCandidateOut(
                requirement=_requirement_to_out(db, requirement),
                validation=validation,
                release=release_to_out(_latest_release(db, int(requirement.id))),
            )
        )
    return result


def prepare_release(db: Session, requirement_id: int, *, actor: str, note: str | None = None) -> ReleaseDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    run = _active_or_latest_workflow_run(db, requirement)
    validation = _workflow_validation_out(run, requirement_id)
    if validation is None or validation.status != "passed":
        raise ValueError("Requirement must pass declarative workflow verification before release preparation.")
    release = _release_record(db, requirement, run)
    pr = _pr_from_workflow(run)
    if pr:
        _apply_pr_payload(release, pr, note=note)
    else:
        release.status = "ready"
        release.delivery_state = "pending"
        release.planned_branch_name = _release_branch_name(requirement)
        release.branch_name = release.branch_name or release.planned_branch_name
        release.base_branch = release.base_branch or "main"
        release.notes = note
    release.prepared_at = release.prepared_at or utcnow()
    release.metadata_json = _json_dump({"actor": actor, **(_json_load(release.metadata_json, {}) if release.metadata_json else {})})
    db.commit()
    return build_release_detail(db, requirement_id)

def open_release_pr(db: Session, requirement_id: int, *, actor: str, note: str | None = None) -> ReleaseDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    run = _active_or_latest_workflow_run(db, requirement)
    validation = _workflow_validation_out(run, requirement_id)
    if validation is None or validation.status != "passed":
        raise ValueError("Requirement must pass declarative workflow verification before opening a PR.")
    release = _release_record(db, requirement, run)
    pr = _pr_from_workflow(run)
    if pr and pr.get("created"):
        _apply_pr_payload(release, pr, note=note)
        db.commit()
        return build_release_detail(db, requirement_id)

    branch_name = release.branch_name or _release_branch_name(requirement)
    base_branch = release.base_branch or "main"
    target_paths = _target_projects_for_requirement(db, requirement)
    vcs_payload = execute_requirement_delivery_vcs(
        requirement_id=requirement_id,
        requirement_title=str(requirement.title or ""),
        delivery_contract={
            "branch_name": branch_name,
            "base_branch": base_branch,
            "remote_name": "origin",
            "commit_required": True,
            "push_required": True,
            "capability_matrix": {"git_write": True, "git_push": True},
            "changed_target_project_paths": target_paths,
        },
        fallback_target_path=target_paths[0] if target_paths else None,
    )
    blockers = [str(item).strip() for item in (vcs_payload.get("blockers") or []) if str(item).strip()]
    if blockers or vcs_payload.get("status") != "delivered":
        release.status = "release_blocked"
        release.delivery_state = "blocked"
        release.delivery_blocker_type = str(vcs_payload.get("delivery_blocker_type") or "repo_gate_failed")
        release.delivery_failure_excerpt = "; ".join(blockers) or "VCS delivery failed"
        release.delivery_failure_raw_output = json.dumps(vcs_payload, ensure_ascii=False, indent=2)
        release.next_action = "route_to_human"
        release.metadata_json = _json_dump({"actor": actor, "vcs": vcs_payload})
        db.commit()
        return build_release_detail(db, requirement_id)

    first_repo = next((item for item in (vcs_payload.get("repositories") or []) if isinstance(item, dict)), {})
    branch_name = str(vcs_payload.get("branch_name") or branch_name).strip()
    base_branch = str(vcs_payload.get("base_branch") or base_branch).strip()
    compare_url = _compare_url(first_repo.get("remote_url") if isinstance(first_repo, dict) else None, base_branch, branch_name)
    pr_sync = sync_requirement_review_pr(
        requirement_id=requirement_id,
        requirement_title=str(requirement.title or ""),
        branch_name=branch_name,
        base_branch=base_branch,
        compare_url=compare_url,
        latest_commit_sha=str(first_repo.get("commit_sha") or "").strip() or None if isinstance(first_repo, dict) else None,
        latest_remote_sha=str(first_repo.get("remote_sha") or "").strip() or None if isinstance(first_repo, dict) else None,
        last_pushed_at=None,
        review_surface_summary=validation.summary_markdown,
        promotion_checklist=[{"label": check.label, "status": check.status} for check in validation.checks],
        vcs_payload=vcs_payload,
    )
    _apply_pr_payload(
        release,
        {
            "created": pr_sync.get("status") == "synced" and bool(pr_sync.get("pr_url")),
            "number": pr_sync.get("pr_number"),
            "url": pr_sync.get("pr_url"),
            "branch_name": branch_name,
            "base_branch": base_branch,
            "compare_url": pr_sync.get("compare_url") or compare_url,
            "sync": pr_sync,
            "vcs": vcs_payload,
        },
        note=note,
    )
    requirement.workflow_state = "ready_for_merge"
    requirement.phase = "pr_opened"
    requirement.status = "delivery_ready"
    db.commit()
    return build_release_detail(db, requirement_id)


def build_release_detail(db: Session, requirement_id: int) -> ReleaseDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    run = _active_or_latest_workflow_run(db, requirement)
    return ReleaseDetailOut(
        requirement=_requirement_to_out(db, requirement),
        validation=_workflow_validation_out(run, requirement_id),
        release=release_to_out(_latest_release(db, requirement_id)),
        deployments=list_requirement_deployment_records(db, requirement_id),
    )


def deploy_release(
    db: Session,
    requirement_id: int,
    *,
    environment: str,
    actor: str,
    note: str | None = None,
) -> ReleaseDetailOut:
    release = _latest_release(db, requirement_id)
    if release is None or not str(release.commit_sha or "").strip():
        raise ValueError("Release must have a committed branch before deployment.")
    trigger_requirement_deployment(
        db,
        requirement_id,
        environment=environment,
        actor=actor,
        note=note,
        commit_sha=str(release.commit_sha),
    )
    return build_release_detail(db, requirement_id)


def rollback_release(
    db: Session,
    requirement_id: int,
    *,
    rollback_target_sha: str,
    actor: str,
    note: str | None = None,
) -> ReleaseDetailOut:
    trigger_requirement_deployment(
        db,
        requirement_id,
        environment="production",
        actor=actor,
        note=note,
        rollback_target_sha=rollback_target_sha,
        trigger_source="release_console",
    )
    release = _latest_release(db, requirement_id)
    if release is not None:
        release.status = "rolled_back"
        release.notes = note
        db.commit()
    return build_release_detail(db, requirement_id)
