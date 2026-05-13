"""Weekly repository hygiene review workflow helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from server.services.scheduling.repo_hygiene_scan import (
    _finding,
    scan_repo_hygiene_payload,
)


TERMINAL_STATUSES = (
    "completed succeeded done failed cancelled deleted superseded".split()
)


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _ops_findings(db: Any, *, now: datetime) -> list[dict[str, Any]]:
    from server.database import HumanGateRequestRow as HG
    from server.database import RecurringWorkflowRunRow as RR
    from server.database import WorkflowRunRow as WR

    stale_cutoff = now - timedelta(hours=24)
    stale_runs = (
        db.query(WR)
        .filter(WR.status == "running", WR.updated_at < stale_cutoff)
        .count()
    )
    pending_gate_cutoff = now - timedelta(hours=72)
    stale_gates = (
        db.query(HG)
        .filter(HG.status == "pending", HG.created_at < pending_gate_cutoff)
        .count()
    )
    failed_recurring = (
        db.query(RR)
        .filter(
            RR.status == "failed",
            RR.created_at >= now - timedelta(days=7),
        )
        .count()
    )
    findings: list[dict[str, Any]] = []
    if stale_runs:
        findings.append(
            _finding(
                finding_id="ops:stale-workflow-runs",
                category="ops_state",
                title="Stale workflow runs need operator review",
                description=(
                    f"{stale_runs} running workflow(s) have not updated for "
                    "more than 24 hours."
                ),
                severity="high",
                risk_level="high",
                recommended_action=(
                    "Inspect workflow evidence and recover, retry, or route "
                    "to a human gate."
                ),
            )
        )
    if stale_gates:
        findings.append(
            _finding(
                finding_id="ops:stale-human-gates",
                category="ops_state",
                title="Stale human gates need review",
                description=f"{stale_gates} pending human gate(s) are older than 72 hours.",
                severity="medium",
                risk_level="normal",
                recommended_action=(
                    "Review pending Human Gate decisions from the workflow detail page."
                ),
            )
        )
    if failed_recurring:
        findings.append(
            _finding(
                finding_id="ops:failed-recurring-runs",
                category="ops_state",
                title="Failed recurring runs need triage",
                description=(
                    f"{failed_recurring} recurring workflow run(s) failed in the last 7 days."
                ),
                severity="medium",
                risk_level="normal",
                recommended_action=(
                    "Open /schedules Attention Required and inspect failed run history."
                ),
            )
        )
    return findings


def _cleanup_week_key(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _can_auto_fix(item: dict[str, Any]) -> bool:
    risk = str(item.get("risk_level") or "normal")
    return bool(item.get("auto_fixable")) and risk in {"low", "normal"}


def _selected_auto_fix(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((item for item in items if _can_auto_fix(item)), None)


def _cleanup_plan_markdown(
    repo_findings: list[dict[str, Any]],
    ops_findings: list[dict[str, Any]],
    selected: dict[str, Any] | None,
) -> str:
    lines = [
        "# Weekly Repo Hygiene Review",
        "",
        f"- repo findings: `{len(repo_findings)}`",
        f"- ops findings: `{len(ops_findings)}`",
    ]
    if selected:
        lines.extend(
            [
                "",
                "## Selected Cleanup PR",
                f"- title: {selected.get('title')}",
                f"- path: `{selected.get('path') or '-'}`",
                f"- action: {selected.get('recommended_action')}",
            ]
        )
    else:
        lines.extend(["", "No low-risk auto-fixable cleanup item was selected."])
    if ops_findings:
        lines.append("")
        lines.append("## Operator Review Items")
        lines.extend(
            f"- {item.get('title')}: {item.get('description')}" for item in ops_findings
        )
    return "\n".join(lines)


def _active_cleanup_exists(db: Any, *, fingerprint: str, week_key: str) -> bool:
    from server.database import RequirementCandidateRow, RequirementRow

    existing_candidate = (
        db.query(RequirementCandidateRow)
        .filter(RequirementCandidateRow.candidate_fingerprint == fingerprint)
        .first()
    )
    if existing_candidate is not None:
        return True
    source_ref = f"weekly-repo-hygiene:{week_key}"
    return (
        db.query(RequirementRow)
        .filter(
            RequirementRow.source == "weekly_repo_hygiene_review",
            RequirementRow.source_ref == source_ref,
            RequirementRow.status.notin_(sorted(TERMINAL_STATUSES)),
        )
        .first()
        is not None
    )


def _acceptance_contract() -> dict[str, Any]:
    return {
        "acceptance_kind": "business",
        "expected_outcome": "code_delivery",
        "execution_acceptance_steps": [
            {
                "step_key": "hygiene_tests",
                "title": "Weekly hygiene tests pass",
                "expected_result": (
                    "The recurring workflow and schedules UI tests covering weekly "
                    "hygiene pass."
                ),
                "required_commands": [
                    "PYTHONPATH=. pytest -q tests/test_weekly_repo_hygiene_review.py",
                    "npm --prefix dashboard test -- --run SchedulesPage",
                ],
                "required_evidence_types": ["workflow_command_result"],
            },
            {
                "step_key": "diff_clean",
                "title": "Repository diff is whitespace-clean",
                "expected_result": "The cleanup PR diff has no whitespace errors.",
                "required_commands": ["git diff --check"],
                "required_evidence_types": ["git_diff_summary"],
            },
        ],
        "markdown": "## Weekly Repo Hygiene Acceptance\n- Keep the cleanup PR small and mechanical.\n- Do not merge automatically.\n- Do not touch production, auth, funds, external publishing, Docker volumes, or local machine cache.",
    }


def _select_goal(db: Any, manifest_id: int) -> Any:
    from server.database import PlanningGoalRow

    row = (
        db.query(PlanningGoalRow)
        .filter(
            PlanningGoalRow.manifest_id == manifest_id,
            PlanningGoalRow.goal_key == "operator_growth",
        )
        .first()
    )
    if row is not None:
        return row
    return (
        db.query(PlanningGoalRow)
        .filter(
            PlanningGoalRow.manifest_id == manifest_id,
            PlanningGoalRow.status == "active",
        )
        .order_by(PlanningGoalRow.id.asc())
        .one()
    )


def _candidate_fingerprint(*, manifest_id: int, week_key: str) -> str:
    raw = f"weekly_repo_hygiene_review:{manifest_id}:{week_key}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _create_cleanup_candidate(
    db: Any,
    *,
    week_key: str,
    selected: dict[str, Any],
    cleanup_plan: str,
    scan: dict[str, Any],
) -> Any:
    from server.database import ProjectRow, RequirementCandidateRow
    from server.services.planning.lifecycle import ensure_active_manifest
    from server.services.projects.project_center import ensure_projects_materialized

    ensure_projects_materialized(db)
    manifest = ensure_active_manifest(db)
    goal = _select_goal(db, int(manifest.id))
    project = (
        db.query(ProjectRow)
        .filter(ProjectRow.project_key == str(goal.project_key or ""))
        .first()
    )
    if project is None:
        project = db.query(ProjectRow).order_by(ProjectRow.id.asc()).first()
    project_id = int(project.id) if project is not None else None
    fingerprint = _candidate_fingerprint(
        manifest_id=int(manifest.id), week_key=week_key
    )
    if _active_cleanup_exists(db, fingerprint=fingerprint, week_key=week_key):
        raise ValueError("cleanup_requirement_already_exists_for_week")
    metadata = {
        "expected_outcome": "code_delivery",
        "acceptance_contract": _acceptance_contract(),
        "cleanup_week": week_key,
        "selected_finding": selected,
        "scan": scan,
    }
    row = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key=str(goal.goal_key or "operator_growth"),
        candidate_fingerprint=fingerprint,
        title=f"Weekly repo hygiene cleanup: {selected.get('title')}",
        description_markdown=cleanup_plan,
        project_id=project_id,
        project_key=str(goal.project_key or "synapse-network-growing"),
        workflow_key="agent_self_repair",
        priority="normal",
        risk_level="normal",
        confidence=0.82,
        rationale="Weekly Harness hygiene selected one low-risk mechanical cleanup item.",
        expected_evidence_json=_json_dumps(
            ["weekly hygiene tests", "git diff check", "cleanup PR"]
        ),
        status="pending",
        metadata_json=_json_dumps(metadata),
    )
    db.add(row)
    db.flush()
    return row


def _approve_and_run_cleanup(
    db: Any,
    candidate_id: int,
    approve_and_run: Callable[..., dict[str, Any]] | None,
) -> dict[str, Any]:
    if approve_and_run is None:
        from server.services.planning.lifecycle import (
            approve_and_run_candidate as approve_and_run,
        )

    return approve_and_run(db, candidate_id, operator="weekly_repo_hygiene_review")


def run_weekly_repo_hygiene_review_payload(
    db: Any,
    *,
    dry_run: bool = False,
    now: datetime | None = None,
    scanner: Callable[[], dict[str, Any]] | None = None,
    approve_and_run: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    scan_func = scanner or scan_repo_hygiene_payload
    scan = dict(scan_func())
    repo_findings = list(scan.get("repo_findings") or [])
    ops_findings = [
        *list(scan.get("ops_findings") or []),
        *_ops_findings(db, now=current),
    ]
    selected = _selected_auto_fix(repo_findings)
    cleanup_plan = _cleanup_plan_markdown(repo_findings, ops_findings, selected)
    result: dict[str, Any] = {
        "workflow_key": "weekly_repo_hygiene_review",
        "dry_run": bool(dry_run),
        "repo_findings": repo_findings,
        "ops_findings": ops_findings,
        "cleanup_plan_markdown": cleanup_plan,
        "created_candidate_id": None,
        "materialized_requirement_id": None,
        "started_workflow_run_id": None,
        "pr_expected": False,
        "blocked_reason": None,
    }
    if dry_run:
        return result
    if selected is None:
        result["blocked_reason"] = "no_low_risk_auto_fixable_findings"
        return result
    week_key = _cleanup_week_key(current)
    try:
        candidate = _create_cleanup_candidate(
            db,
            week_key=week_key,
            selected=selected,
            cleanup_plan=cleanup_plan,
            scan={"repo_findings": repo_findings, "ops_findings": ops_findings},
        )
    except ValueError as exc:
        result["blocked_reason"] = str(exc)
        return result
    auto_result = _approve_and_run_cleanup(db, int(candidate.id), approve_and_run)
    result["created_candidate_id"] = int(candidate.id)
    result["materialized_requirement_id"] = auto_result.get("requirement_id")
    result["started_workflow_run_id"] = auto_result.get("workflow_run_id")
    result["pr_expected"] = True
    return result
