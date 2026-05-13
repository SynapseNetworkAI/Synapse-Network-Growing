from datetime import datetime, timedelta, timezone

from server.database import (
    HumanGateRequestRow,
    RecurringWorkflowRunRow,
    RequirementCandidateRow,
    RequirementRow,
    WorkflowRunRow,
)
from server.services.scheduling import repo_hygiene
from server.services.scheduling import repo_hygiene_scan
from server.services.scheduling.recurring_workflows import (
    _next_run_at,
    run_recurring_workflow,
    sync_recurring_workflows,
)


def _finding(**overrides):
    payload = {
        "id": "docs:missing-frontmatter",
        "category": "docs_metadata",
        "severity": "low",
        "risk_level": "normal",
        "title": "Missing docs frontmatter",
        "description": "A docs file needs frontmatter.",
        "path": "docs/design-docs/example.md",
        "auto_fixable": True,
        "recommended_action": "Add standard frontmatter.",
    }
    payload.update(overrides)
    return payload


def _scan_with(findings):
    return {
        "workflow_key": "weekly_repo_hygiene_review",
        "repo_findings": findings,
        "ops_findings": [],
        "finding_count": len(findings),
        "auto_fixable_count": sum(1 for item in findings if item.get("auto_fixable")),
    }


def test_weekly_repo_hygiene_review_is_registered_for_sunday(db_session):
    rows = sync_recurring_workflows(db_session)
    row = next(
        item for item in rows if item.workflow_key == "weekly_repo_hygiene_review"
    )

    assert row.owner_role == "runtime_reliability_engineer"
    assert '"day":"SUN"' in row.schedule_json.replace(" ", "")
    next_run = _next_run_at(row, now=datetime(2026, 5, 13, 2, 0, tzinfo=timezone.utc))

    assert next_run is not None
    assert next_run.weekday() == 6


def test_weekly_repo_hygiene_dry_run_does_not_create_work(db_session, monkeypatch):
    sync_recurring_workflows(db_session)
    monkeypatch.setattr(
        repo_hygiene, "scan_repo_hygiene_payload", lambda: _scan_with([_finding()])
    )

    result = run_recurring_workflow(
        db_session, workflow_key="weekly_repo_hygiene_review", dry_run=True
    )

    assert result["status"] == "completed"
    assert result["result"]["dry_run"] is True
    assert result["result"]["repo_findings"][0]["id"] == "docs:missing-frontmatter"
    assert db_session.query(RequirementCandidateRow).count() == 0
    assert db_session.query(RequirementRow).count() == 0


def test_weekly_repo_hygiene_formal_run_dispatches_registered_workflow(
    db_session, monkeypatch
):
    sync_recurring_workflows(db_session)

    def fake_payload(db, *, dry_run):
        assert dry_run is False
        return {"workflow_key": "weekly_repo_hygiene_review", "pr_expected": False}

    monkeypatch.setattr(
        repo_hygiene, "run_weekly_repo_hygiene_review_payload", fake_payload
    )

    result = run_recurring_workflow(
        db_session, workflow_key="weekly_repo_hygiene_review", dry_run=False
    )

    assert result["status"] == "completed"
    assert result["result"]["workflow_key"] == "weekly_repo_hygiene_review"


def test_weekly_repo_hygiene_run_creates_candidate_and_starts_cleanup_workflow(
    db_session, monkeypatch
):
    sync_recurring_workflows(db_session)
    monkeypatch.setattr(
        repo_hygiene, "scan_repo_hygiene_payload", lambda: _scan_with([_finding()])
    )

    def fake_approve_and_run(db, candidate_id, *, operator):
        candidate = db.get(RequirementCandidateRow, candidate_id)
        candidate.status = "materialized"
        requirement = RequirementRow(
            title=candidate.title,
            description_markdown=candidate.description_markdown,
            status="in_progress",
            priority="normal",
            source="weekly_repo_hygiene_review",
            source_ref="weekly-repo-hygiene:2026-W20",
            intake_metadata_json="{}",
            operating_manifest_id=int(candidate.manifest_id),
            goal_key=str(candidate.goal_key),
            requirement_candidate_id=int(candidate.id),
            project_id=candidate.project_id,
            project_key=candidate.project_key,
            workflow_state="executing",
            phase="executing",
        )
        db.add(requirement)
        db.flush()
        candidate.materialized_requirement_id = int(requirement.id)
        return {"requirement_id": int(requirement.id), "workflow_run_id": 789}

    result = repo_hygiene.run_weekly_repo_hygiene_review_payload(
        db_session,
        now=datetime(2026, 5, 13, tzinfo=timezone.utc),
        approve_and_run=fake_approve_and_run,
    )

    assert result["pr_expected"] is True
    assert result["created_candidate_id"] is not None
    assert result["materialized_requirement_id"] is not None
    assert result["started_workflow_run_id"] == 789
    candidate = db_session.get(RequirementCandidateRow, result["created_candidate_id"])
    assert candidate.workflow_key == "agent_self_repair"
    assert candidate.risk_level == "normal"


def test_weekly_repo_hygiene_records_ops_review_findings(db_session):
    now = datetime(2026, 5, 13, tzinfo=timezone.utc)
    requirement = RequirementRow(
        title="Stale workflow",
        description_markdown="Needs review",
        status="in_progress",
        priority="normal",
        source="test",
        source_ref="test",
        intake_metadata_json="{}",
        goal_key="operator_growth",
        project_key="synapse-network-growing",
    )
    db_session.add(requirement)
    db_session.flush()
    stale_run = WorkflowRunRow(
        requirement_id=int(requirement.id),
        workflow_key="agent_self_repair",
        current_state="verify",
        status="running",
        triggered_by="test",
        updated_at=now - timedelta(hours=25),
    )
    failed_recurring = RecurringWorkflowRunRow(
        workflow_key="daily_health_check",
        status="failed",
        triggered_by="test",
        created_at=now - timedelta(days=1),
    )
    db_session.add_all([stale_run, failed_recurring])
    db_session.flush()
    db_session.add(
        HumanGateRequestRow(
            workflow_run_id=int(stale_run.id),
            state_key="review",
            gate_type="operator_review",
            status="pending",
            created_at=now - timedelta(hours=73),
        )
    )
    db_session.flush()

    result = repo_hygiene.run_weekly_repo_hygiene_review_payload(
        db_session,
        dry_run=True,
        now=now,
        scanner=lambda: _scan_with([]),
    )

    ids = {item["id"] for item in result["ops_findings"]}
    assert ids == {
        "ops:stale-workflow-runs",
        "ops:stale-human-gates",
        "ops:failed-recurring-runs",
    }
    assert "Operator Review Items" in result["cleanup_plan_markdown"]


def test_weekly_repo_hygiene_scanner_detects_repo_entropy(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_hygiene_scan.config, "PROJECT_ROOT", tmp_path)
    (tmp_path / "AGENTS.md").write_text("ok\n", encoding="utf-8")
    (tmp_path / "stray-plan.md").write_text("move me\n", encoding="utf-8")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "pull_request_template.md").write_text(
        "## Summary\n", encoding="utf-8"
    )
    design_docs = tmp_path / "docs" / "design-docs"
    design_docs.mkdir(parents=True)
    (design_docs / "missing.md").write_text("# Missing\n", encoding="utf-8")
    (design_docs / "ok.md").write_text("---\nid: ok\n---\n# OK\n", encoding="utf-8")
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    (server_dir / "todo.py").write_text("# TODO: review this\n", encoding="utf-8")

    payload = repo_hygiene_scan.scan_repo_hygiene_payload(root=tmp_path)

    ids = {item["id"] for item in payload["repo_findings"]}
    assert "root-markdown:stray-plan.md" in ids
    assert "missing-frontmatter:docs/design-docs/missing.md" in ids
    assert "pr-template:literal-newline-hygiene" in ids
    assert "todo:server/todo.py" in ids
    assert repo_hygiene_scan._repo_rel(tmp_path.parent / "outside.md").endswith(
        "outside.md"
    )
    assert payload["auto_fixable_count"] == 2


def test_weekly_repo_hygiene_high_risk_or_duplicate_noops(db_session):
    high_risk = _finding(id="auth:secret-cleanup", risk_level="high", auto_fixable=True)

    high_result = repo_hygiene.run_weekly_repo_hygiene_review_payload(
        db_session,
        now=datetime(2026, 5, 13, tzinfo=timezone.utc),
        scanner=lambda: _scan_with([high_risk]),
    )

    assert high_result["pr_expected"] is False
    assert high_result["blocked_reason"] == "no_low_risk_auto_fixable_findings"

    first = repo_hygiene.run_weekly_repo_hygiene_review_payload(
        db_session,
        now=datetime(2026, 5, 13, tzinfo=timezone.utc),
        scanner=lambda: _scan_with([_finding()]),
        approve_and_run=lambda _db, candidate_id, *, operator: {
            "requirement_id": 1,
            "workflow_run_id": 2,
        },
    )
    second = repo_hygiene.run_weekly_repo_hygiene_review_payload(
        db_session,
        now=datetime(2026, 5, 13, tzinfo=timezone.utc),
        scanner=lambda: _scan_with([_finding()]),
        approve_and_run=lambda _db, candidate_id, *, operator: {
            "requirement_id": 1,
            "workflow_run_id": 2,
        },
    )

    assert first["pr_expected"] is True
    assert second["pr_expected"] is False
    assert second["blocked_reason"] == "cleanup_requirement_already_exists_for_week"
