"""Release service backed by declarative workflow runs."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database import ProjectRow, ReleaseRecordRow, RequirementRow, WorkflowRunRow, utcnow
from server.schemas import ReleaseCandidateOut, ReleaseDetailOut, ValidationCheckResultOut, ValidationRecordSlimOut
from server.services.delivery.deployment_governance import list_requirement_deployment_records, mark_requirement_no_deploy, trigger_requirement_deployment
from server.services.delivery.pull_request import query_review_pr_status, sync_requirement_review_pr
from server.services.delivery.vcs import execute_requirement_delivery_vcs
from server.services.requirements.service import _requirement_to_out, _target_projects_for_requirement, release_to_out
from server.services.result_objects import ServiceObjectResult

def _json_load(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _metadata(release: ReleaseRecordRow | None) -> dict[str, Any]:
    payload = _json_load(getattr(release, "metadata_json", None), {}) if release is not None else {}
    return payload if isinstance(payload, dict) else {}


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
        workflow_run_id=int(run.id),
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


def _github_repo_slug_from_url(value: str | None) -> str | None:
    text = str(value or "").strip()
    match = re.match(r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)(?:/.*)?$", text)
    if not match:
        return None
    repo = match.group("repo")
    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"{match.group('owner')}/{repo}"


def _release_pr_ref_and_repo(release: ReleaseRecordRow) -> tuple[str | None, str | None]:
    pr_url = str(getattr(release, "pr_url", "") or "").strip()
    if pr_url:
        return pr_url, _github_repo_slug_from_url(pr_url)
    pr_number = getattr(release, "pr_number", None)
    repo_slug = _github_repo_slug_from_url(getattr(release, "compare_url", None))
    if pr_number is not None and repo_slug:
        return str(int(pr_number)), repo_slug
    return None, repo_slug


def _merge_release_metadata(release: ReleaseRecordRow, updates: dict[str, Any]) -> None:
    metadata = _metadata(release)
    for key, value in updates.items():
        if value is None:
            metadata.pop(key, None)
        else:
            metadata[key] = value
    release.metadata_json = _json_dump(metadata)


def _sync_release_from_pr_payload(release: ReleaseRecordRow, payload: dict[str, Any], *, synced_at: str) -> str:
    state = str(payload.get("state") or "").strip().upper()
    merged_at = str(payload.get("mergedAt") or "").strip() or None
    closed_at = str(payload.get("closedAt") or "").strip() or None
    merge_commit = payload.get("mergeCommit") if isinstance(payload.get("mergeCommit"), dict) else {}
    merge_commit_sha = str(merge_commit.get("oid") or "").strip() or None
    pr_status = "merged" if state == "MERGED" or merged_at else "closed" if state == "CLOSED" else "draft" if bool(payload.get("isDraft")) else "open"
    updates = {
        "pr_status": pr_status,
        "github_pr_state": state,
        "is_draft": bool(payload.get("isDraft")),
        "merged_at": merged_at,
        "closed_at": closed_at,
        "merge_commit_sha": merge_commit_sha,
        "last_pr_status_synced_at": synced_at,
        "pr_sync_failure_summary": None,
    }
    if state == "MERGED" or merged_at:
        release.status = "merged"
        release.delivery_state = "merged"
        release.commit_sha = merge_commit_sha or str(getattr(release, "commit_sha", "") or "").strip() or None
        release.delivered_at = release.delivered_at or utcnow()
        release.next_action = None
    elif state == "CLOSED":
        release.status = "pr_closed"
        release.delivery_state = "abandoned"
        release.next_action = "review_closed_pr"
    else:
        release.status = "pr_opened"
        release.delivery_state = "pr_open"
    release.updated_at = utcnow()
    _merge_release_metadata(release, updates)
    return pr_status


def _mark_release_pr_missing(release: ReleaseRecordRow, *, error_excerpt: str | None, synced_at: str) -> None:
    failure_summary = "PR removed from GitHub or no longer accessible"
    release.status = "pr_closed"
    release.delivery_state = "abandoned"
    release.next_action = "review_missing_pr"
    release.updated_at = utcnow()
    _merge_release_metadata(
        release,
        {
            "pr_status": "not_found",
            "github_pr_state": "NOT_FOUND",
            "failure_summary": failure_summary,
            "pr_sync_failure_summary": failure_summary,
            "pr_sync_error_excerpt": str(error_excerpt or "").strip()[:1000] or None,
            "last_pr_status_synced_at": synced_at,
        },
    )


def sync_release_pr_statuses(
    db: Session,
    *,
    max_records: int = 50,
    per_record_sleep_seconds: float = 1.0,
    query_status: Callable[..., dict[str, Any]] = query_review_pr_status,
    sleep: Callable[[float], None] | None = None,
) -> ServiceObjectResult:
    """Synchronize local release records with GitHub PR state.

    This is read-only against GitHub. It never merges, closes, deploys, or
    deletes branches.
    """

    limit = max(1, min(int(max_records or 50), 100))
    rows = (
        db.query(ReleaseRecordRow)
        .filter(
            or_(
                ReleaseRecordRow.pr_url.isnot(None),
                ReleaseRecordRow.pr_number.isnot(None),
            ),
            or_(
                ReleaseRecordRow.status.in_(("pr_opened", "ready_for_merge")),
                ReleaseRecordRow.delivery_state.in_(("pr_open", "ready_for_merge")),
            ),
        )
        .order_by(ReleaseRecordRow.updated_at.asc(), ReleaseRecordRow.id.asc())
        .limit(limit)
        .all()
    )
    sleeper = sleep
    if sleeper is None:
        import time

        sleeper = time.sleep
    merged_ids: list[int] = []
    closed_ids: list[int] = []
    missing_ids: list[int] = []
    open_ids: list[int] = []
    failed_items: list[dict[str, Any]] = []
    synced_at = utcnow().isoformat()
    processed = 0
    for index, release in enumerate(rows):
        release_id = int(release.id)
        pr_ref, repo_slug = _release_pr_ref_and_repo(release)
        if not pr_ref:
            failed_items.append(
                {
                    "release_id": release_id,
                    "result": "transient_error",
                    "error": "release has no pr_url and no resolvable GitHub repo for pr_number",
                }
            )
        else:
            result = query_status(pr_ref=pr_ref, repo_slug=repo_slug)
            kind = str(result.get("result") or "")
            if kind == "ok":
                pr_status = _sync_release_from_pr_payload(release, dict(result.get("payload") or {}), synced_at=synced_at)
                if pr_status == "merged":
                    merged_ids.append(release_id)
                elif pr_status == "closed":
                    closed_ids.append(release_id)
                else:
                    open_ids.append(release_id)
                processed += 1
            elif kind == "not_found":
                _mark_release_pr_missing(release, error_excerpt=str(result.get("error_excerpt") or ""), synced_at=synced_at)
                missing_ids.append(release_id)
                processed += 1
            else:
                failed_items.append(
                    {
                        "release_id": release_id,
                        "result": kind or "transient_error",
                        "error": str(result.get("error_excerpt") or "GitHub PR status query failed")[:1000],
                    }
                )
        if index < len(rows) - 1 and per_record_sleep_seconds > 0:
            sleeper(float(per_record_sleep_seconds))
    db.commit()
    return ServiceObjectResult({
        "status": "completed",
        "processed_count": int(processed),
        "scanned_count": len(rows),
        "max_records": limit,
        "merged_ids": merged_ids,
        "closed_ids": closed_ids,
        "missing_ids": missing_ids,
        "open_ids": open_ids,
        "failed_ids": [int(item["release_id"]) for item in failed_items],
        "failed_items": failed_items,
        "rate_limit_sleep_seconds": float(per_record_sleep_seconds),
    })


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
    source_ref_type: str = "branch",
    source_ref: str | None = None,
    deploy_scope: str = "auto",
) -> ReleaseDetailOut:
    release = _latest_release(db, requirement_id)
    if release is None:
        raise ValueError("Release must be prepared before deployment.")
    resolved_source_ref = (source_ref or "").strip() or str(release.actual_branch_name or release.branch_name or release.commit_sha or "").strip()
    if not resolved_source_ref:
        raise ValueError("Release must have a branch, tag, or commit before deployment.")
    if environment == "production" and not str(release.commit_sha or "").strip():
        raise ValueError("Production deployment requires a resolved committed SHA.")
    trigger_requirement_deployment(
        db,
        requirement_id,
        environment=environment,
        actor=actor,
        note=note,
        commit_sha=str(release.commit_sha or "").strip() or None,
        source_ref_type=source_ref_type,
        source_ref=resolved_source_ref,
        deploy_scope=deploy_scope,
    )
    return build_release_detail(db, requirement_id)


def mark_release_no_deploy(
    db: Session,
    requirement_id: int,
    *,
    actor: str,
    note: str | None = None,
    source_ref_type: str = "branch",
    source_ref: str | None = None,
    deploy_scope: str = "auto",
) -> ReleaseDetailOut:
    release = _latest_release(db, requirement_id)
    if release is None:
        raise ValueError("Release must be prepared before marking no-deploy.")
    effective_source_ref = (source_ref or "").strip() or str(release.actual_branch_name or release.branch_name or release.commit_sha or "").strip()
    mark_requirement_no_deploy(
        db,
        requirement_id,
        actor=actor,
        note=note,
        source_ref_type=source_ref_type,
        source_ref=effective_source_ref,
        commit_sha=str(release.commit_sha or "").strip() or None,
        reason=f"manual no-deploy; requested scope={deploy_scope}",
    )
    release.status = "no_deploy"
    release.delivery_state = "no_deploy"
    release.notes = note
    db.commit()
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
