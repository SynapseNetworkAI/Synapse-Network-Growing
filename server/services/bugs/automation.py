"""Automation helpers for bug claim-and-run and workflow projection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import BugFixAttemptRow, BugRecordRow, RequirementRow
from server.services.bugs.policy import requires_screenshot
from server.services.bugs.serializer import json_loads


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _workflow_summary(db: Session, workflow_run_id: int) -> dict[str, Any]:
    from server.services.workflows.declarative import workflow_run_detail

    return workflow_run_detail(db, workflow_run_id)


def _nested_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _update_attempt_text(
    attempt: BugFixAttemptRow, field_name: str, candidate: str
) -> bool:
    if not candidate:
        return False
    current = _clean_text(getattr(attempt, field_name, ""))
    if candidate == current:
        return False
    setattr(attempt, field_name, candidate)
    return True


def _sync_requirement_link(row: BugRecordRow, attempt: BugFixAttemptRow) -> bool:
    if attempt.requirement_id or row.converted_requirement_id is None:
        return False
    attempt.requirement_id = int(row.converted_requirement_id)
    return True


def _sync_command_results(attempt: BugFixAttemptRow, detail: dict[str, Any]) -> bool:
    command_results = (
        detail.get("command_results")
        if isinstance(detail.get("command_results"), list)
        else []
    )
    if not command_results:
        return False
    current = json_loads(attempt.verification_commands_json, [])
    if command_results == current:
        return False
    attempt.verification_commands_json = json_dumps(command_results)
    return True


def _sync_branch_name(
    attempt: BugFixAttemptRow,
    delivery: dict[str, Any],
    pr: dict[str, Any],
    sync: dict[str, Any],
) -> bool:
    return _update_attempt_text(
        attempt,
        "branch_name",
        _clean_text(
            delivery.get("branch_name")
            or pr.get("branch_name")
            or sync.get("branch_name")
            or sync.get("head_branch")
            or attempt.branch_name
        ),
    )


def _sync_pr_url(
    attempt: BugFixAttemptRow,
    delivery: dict[str, Any],
    pr: dict[str, Any],
    sync: dict[str, Any],
) -> bool:
    return _update_attempt_text(
        attempt,
        "pr_url",
        _clean_text(
            delivery.get("pr_url")
            or pr.get("url")
            or sync.get("pr_url")
            or attempt.pr_url
        ),
    )


def _sync_commit_sha(
    attempt: BugFixAttemptRow, sync: dict[str, Any], vcs: dict[str, Any]
) -> bool:
    return _update_attempt_text(
        attempt,
        "commit_sha",
        _clean_text(
            vcs.get("latest_commit_sha")
            or sync.get("latest_commit_sha")
            or attempt.commit_sha
        ),
    )


def _sync_attempt_delivery_fields(
    attempt: BugFixAttemptRow,
    row: BugRecordRow,
    detail: dict[str, Any],
    delivery: dict[str, Any],
    pr: dict[str, Any],
    sync: dict[str, Any],
    vcs: dict[str, Any],
) -> bool:
    changed = _sync_branch_name(attempt, delivery, pr, sync)
    changed = _sync_pr_url(attempt, delivery, pr, sync) or changed
    changed = _sync_commit_sha(attempt, sync, vcs) or changed
    changed = _sync_requirement_link(row, attempt) or changed
    changed = _sync_command_results(attempt, detail) or changed
    return changed


def _verification_context(
    blackboard: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    pr = _nested_dict(blackboard, "pr")
    return pr, _nested_dict(pr, "sync"), _nested_dict(blackboard, "verification")


def _mark_attempt_verified(row: BugRecordRow, attempt: BugFixAttemptRow) -> bool:
    changed = False
    if str(attempt.status or "") != "verified":
        attempt.status = "verified"
        attempt.verified_at = attempt.verified_at or _utcnow()
        changed = True
    summary = (
        "Workflow verification passed and review evidence is ready."
        if attempt.pr_url
        else "Workflow verification passed without repository changes."
    )
    if summary != str(attempt.verification_summary or ""):
        attempt.verification_summary = summary
        changed = True
    if str(row.status or "") != "verified":
        row.status = "verified"
        changed = True
    return changed


def _mark_attempt_failed(
    row: BugRecordRow, attempt: BugFixAttemptRow, failure_summary: str
) -> bool:
    changed = False
    if str(attempt.status or "") != "failed":
        attempt.status = "failed"
        changed = True
    if failure_summary and failure_summary != str(attempt.failure_reason or ""):
        attempt.failure_reason = failure_summary
        changed = True
    if str(row.status or "") != "failed":
        row.status = "failed"
        changed = True
    return changed


def _can_auto_verify(
    row: BugRecordRow,
    attempt: BugFixAttemptRow,
    verification_status: str,
    no_op_verified: bool,
) -> bool:
    if verification_status != "passed":
        return False
    has_delivery_evidence = bool(attempt.pr_url) or no_op_verified
    if not has_delivery_evidence:
        return False
    if not requires_screenshot(row):
        return True
    screenshots = json_loads(attempt.verification_screenshots_json, [])
    return bool(screenshots)


def _project_attempt_verification(
    row: BugRecordRow, attempt: BugFixAttemptRow, blackboard: dict[str, Any]
) -> bool:
    pr, sync, verification = _verification_context(blackboard)
    verification_status = _clean_text(verification.get("status")).lower()
    failure_summary = _clean_text(verification.get("failure_summary"))
    no_op_verified = (
        _clean_text(pr.get("status") or sync.get("status")) == "no_op_verified"
    )
    if _can_auto_verify(row, attempt, verification_status, no_op_verified):
        return _mark_attempt_verified(row, attempt)
    if verification_status == "failed":
        return _mark_attempt_failed(row, attempt, failure_summary)
    return False


def _sync_latest_fix_metadata(row: BugRecordRow, attempt: BugFixAttemptRow) -> bool:
    latest_fix = {
        "branch_name": attempt.branch_name,
        "commit_sha": attempt.commit_sha,
        "pr_url": attempt.pr_url,
        "workflow_run_id": attempt.workflow_run_id,
        "requirement_id": attempt.requirement_id,
    }
    metadata = json_loads(row.metadata_json, {})
    if latest_fix == metadata.get("latest_fix"):
        return False
    metadata["latest_fix"] = latest_fix
    row.metadata_json = json_dumps(metadata)
    return True


def project_attempt_from_workflow(
    db: Session, row: BugRecordRow, attempt: BugFixAttemptRow
) -> bool:
    workflow_run_id = int(getattr(attempt, "workflow_run_id", 0) or 0)
    if workflow_run_id <= 0:
        return False
    detail = _workflow_summary(db, workflow_run_id)
    blackboard = (
        detail.get("blackboard") if isinstance(detail.get("blackboard"), dict) else {}
    )
    delivery = (
        detail.get("delivery_summary")
        if isinstance(detail.get("delivery_summary"), dict)
        else {}
    )
    pr, sync, _verification = _verification_context(blackboard)
    vcs = _nested_dict(pr, "vcs")
    changed = _sync_attempt_delivery_fields(
        attempt, row, detail, delivery, pr, sync, vcs
    )
    changed = _project_attempt_verification(row, attempt, blackboard) or changed
    changed = _sync_latest_fix_metadata(row, attempt) or changed
    return changed


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def requirement_workflow_binding(
    db: Session, requirement_id: int | None
) -> tuple[int | None, RequirementRow | None]:
    if requirement_id is None:
        return None, None
    requirement = (
        db.query(RequirementRow)
        .filter(RequirementRow.id == int(requirement_id))
        .first()
    )
    if requirement is None:
        return None, None
    workflow_run_id = (
        int(getattr(requirement, "active_workflow_run_id", 0) or 0) or None
    )
    return workflow_run_id, requirement


def _preflight_missing(context: Any) -> list[str]:
    missing: list[str] = []
    if not context.target_project_path:
        missing.append("target_project_path")
    if not context.acceptance_checks:
        missing.append("acceptance_checks")
    return missing


def _fail_closed_preflight(
    db: Session,
    wb: Any,
    row: BugRecordRow,
    attempt: BugFixAttemptRow,
    agent_id: str,
    missing_preflight: list[str],
):
    attempt.status = "failed"
    attempt.failure_reason = (
        "claim-and-run failed closed because bug context is incomplete: "
        + ", ".join(missing_preflight)
    )
    row.status = "failed"
    wb._event(
        db,
        row,
        "automation_failed",
        actor=agent_id,
        from_status="fixing",
        to_status="failed",
        message=attempt.failure_reason,
        metadata={"missing_preflight": missing_preflight},
    )
    db.add(attempt)
    db.add(row)
    db.commit()
    return wb.bug_detail(db, int(row.id))


def _materialize_requirement_if_needed(
    db: Session, wb: Any, bug_id: int, row: BugRecordRow
) -> tuple[BugRecordRow, BugFixAttemptRow]:
    if row.converted_requirement_id is not None:
        attempt = wb.active_fix_attempt(db, int(row.id)) or wb.latest_fix_attempt(
            db, int(row.id)
        )
        if attempt is None:
            raise ValueError("bug fix attempt missing before workflow start")
        return row, attempt

    wb.materialize_bug_requirement(db, int(row.id))
    row = wb._bug_or_404(db, bug_id)
    attempt = wb.active_fix_attempt(db, int(row.id)) or wb.latest_fix_attempt(
        db, int(row.id)
    )
    if attempt is None:
        raise ValueError(
            "bug fix attempt disappeared during requirement materialization"
        )
    return row, attempt


def _ensure_workflow_binding(
    db: Session, wb: Any, row: BugRecordRow
) -> tuple[int | None, RequirementRow]:
    workflow_run_id, requirement = wb.requirement_workflow_binding(
        db, row.converted_requirement_id
    )
    if requirement is None:
        raise ValueError("bug requirement could not be resolved after materialization")
    if workflow_run_id is not None:
        return workflow_run_id, requirement
    workflow = wb.start_requirement_workflow(
        db,
        int(requirement.id),
        triggered_by="bug_claim_and_run",
        run_immediately=True,
    )
    workflow_run_id = (
        int(workflow.get("id") or workflow.get("workflow_run_id") or 0) or None
    )
    return workflow_run_id, requirement


def run_claim_and_run_bug(
    db: Session, bug_id: int, *, agent_id: str, lease_minutes: int = 120
):
    from server.services.bugs import workbench as wb

    row = wb._bug_or_404(db, bug_id)
    if wb.active_fix_attempt(db, int(row.id)) is not None:
        raise ValueError("bug already has an active fix attempt")
    wb.claim_bug(db, bug_id, agent_id=agent_id, lease_minutes=lease_minutes)
    row = wb._bug_or_404(db, bug_id)
    attempt = wb.active_fix_attempt(db, int(row.id))
    if attempt is None:
        raise ValueError("bug claim did not create an active fix attempt")

    context = wb.build_agent_context(
        db, row, allowed_next_actions=wb.allowed_next_actions(row, attempt)
    )
    missing_preflight = _preflight_missing(context)
    if missing_preflight:
        return _fail_closed_preflight(db, wb, row, attempt, agent_id, missing_preflight)

    row, attempt = _materialize_requirement_if_needed(db, wb, bug_id, row)
    workflow_run_id, requirement = _ensure_workflow_binding(db, wb, row)

    attempt.requirement_id = int(requirement.id)
    attempt.workflow_run_id = workflow_run_id
    attempt.status = "fixing"
    row.status = "fixing"
    metadata = json_loads(row.metadata_json, {})
    metadata["latest_fix"] = {
        "branch_name": attempt.branch_name,
        "commit_sha": attempt.commit_sha,
        "pr_url": attempt.pr_url,
        "workflow_run_id": attempt.workflow_run_id,
        "requirement_id": attempt.requirement_id,
    }
    row.metadata_json = json_dumps(metadata)
    wb._event(
        db,
        row,
        "workflow_started",
        actor=agent_id,
        from_status="fixing",
        to_status="fixing",
        metadata={
            "workflow_run_id": workflow_run_id,
            "requirement_id": int(requirement.id),
        },
    )
    db.add(attempt)
    db.add(row)
    db.commit()
    return wb.bug_detail(db, int(row.id))
