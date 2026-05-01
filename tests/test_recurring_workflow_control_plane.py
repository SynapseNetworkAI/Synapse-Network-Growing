import json
from datetime import datetime, timedelta, timezone

from server.database import (
    HumanGateRequestRow,
    NotificationEventRow,
    PlanningGoalRow,
    RecurringWorkflowRow,
    RecurringWorkflowRunRow,
    ReleaseRecordRow,
    RequirementRow,
    WorkflowArtifactRow,
    WorkflowRunRow,
)
from server.services.scheduling.recurring_workflows import (
    _ci_status_sweep,
    _runner_stale_sweep,
    _next_run_at,
    list_recurring_workflow_runs,
    recurring_workflow_to_dict,
    run_recurring_workflow,
    sync_recurring_workflows,
)
from server.services.scheduling.locks import acquire_scheduler_lock
from server.services.planning.scheduler import goal_planner_sweep_due
from server.services.planning.lifecycle import ensure_active_manifest
from server.services.releases.deployment_status_scheduler import (
    ReleaseDeploymentStatusSweepScheduler,
)
from server.services.releases.service import sync_release_pr_statuses


def test_recurring_workflow_dry_run_records_history(db_session):
    sync_recurring_workflows(db_session)

    result = run_recurring_workflow(
        db_session,
        workflow_key="bug_log_sweep",
        dry_run=True,
        triggered_by="operator",
    )

    assert result["status"] == "completed"
    assert result["run_id"] is not None
    rows = list_recurring_workflow_runs(db_session, "bug_log_sweep")
    assert len(rows) == 1
    assert rows[0].status == "succeeded"
    assert rows[0].dry_run is True
    assert rows[0].duration_ms >= 0


def test_recurring_workflow_failed_run_records_error(db_session):
    sync_recurring_workflows(db_session)

    try:
        run_recurring_workflow(
            db_session, workflow_key="unsupported_workflow", dry_run=False
        )
    except ValueError:
        pass

    assert db_session.query(RecurringWorkflowRunRow).count() == 0

    db_session.add(
        RecurringWorkflowRow(
            workflow_key="unsupported_workflow",
            display_name="Unsupported",
            description="Unsupported test workflow",
            status="active",
            trigger_type="scheduled",
            owner_role="tester",
            schedule_json='{"cadence":"interval","interval_minutes":5}',
            input_query_json="{}",
            output_action_json="{}",
            escalation_rule_json="{}",
            validation_signal_json="{}",
            is_builtin=False,
        )
    )
    db_session.commit()

    try:
        run_recurring_workflow(
            db_session, workflow_key="unsupported_workflow", dry_run=False
        )
    except ValueError as exc:
        assert "Unsupported recurring workflow" in str(exc)

    history = (
        db_session.query(RecurringWorkflowRunRow)
        .filter(RecurringWorkflowRunRow.workflow_key == "unsupported_workflow")
        .one()
    )
    assert history.status == "failed"
    assert "Unsupported recurring workflow" in str(history.error_excerpt)


def test_recurring_workflows_health_endpoint(synced_client):
    response = synced_client.get("/api/recurring-workflows/health")

    assert response.status_code == 200
    payload = response.json()
    assert "bug_log_scheduler" in payload
    assert "lock" in payload["bug_log_scheduler"]
    assert "release_pr_status_scheduler" in payload
    assert "x_social_scheduler" in payload
    assert "notification_dispatcher" in payload
    assert payload["recurring_registry"]["total_count"] >= 7


def test_recurring_workflow_runs_endpoint(synced_client):
    run_response = synced_client.post(
        "/api/recurring-workflows/bug_log_sweep/run", json={"dry_run": True}
    )
    assert run_response.status_code == 200

    runs_response = synced_client.get(
        "/api/recurring-workflows/bug_log_sweep/runs?limit=5"
    )
    assert runs_response.status_code == 200
    runs = runs_response.json()
    assert runs
    assert runs[0]["workflow_key"] == "bug_log_sweep"
    assert runs[0]["dry_run"] is True


def test_recurring_workflow_projection_tolerates_legacy_string_last_result(
    db_session,
):
    sync_recurring_workflows(db_session)
    row = (
        db_session.query(RecurringWorkflowRow)
        .filter(RecurringWorkflowRow.workflow_key == "bug_log_sweep")
        .one()
    )
    row.last_result_json = '"legacy object wrapper string"'
    db_session.commit()

    payload = recurring_workflow_to_dict(row)

    assert payload["last_result"] == {}
    assert payload["health_status"] in {"healthy", "unknown", "failed"}


def test_x_social_recurring_workflows_are_registered_and_dry_runnable(synced_client):
    response = synced_client.get("/api/recurring-workflows")
    assert response.status_code == 200
    workflow_keys = {row["workflow_key"] for row in response.json()}
    assert {
        "product_planning_sweep",
        "x_social_daily_content_planner",
        "x_social_trend_radar_sweep",
        "x_social_repost_candidate_sweep",
        "x_social_reply_candidate_sweep",
        "x_social_post_observer_sweep",
    }.issubset(workflow_keys)

    product = synced_client.post(
        "/api/recurring-workflows/product_planning_sweep/run", json={"dry_run": True}
    )
    assert product.status_code == 200
    product_payload = product.json()
    assert product_payload["status"] == "completed"
    assert product_payload["result"]["auto_create_goal"] is False
    assert product_payload["result"]["created_opportunity_ids"] == []

    daily = synced_client.post(
        "/api/recurring-workflows/x_social_daily_content_planner/run",
        json={"dry_run": True},
    )
    assert daily.status_code == 200
    daily_payload = daily.json()
    assert daily_payload["status"] == "completed"
    assert daily_payload["result"]["idempotency"] == "top_up_to_three_active_drafts_per_operator_local_day"
    assert daily_payload["result"]["target_count"] == 3
    assert daily_payload["result"]["human_gate_required"] is True

    trends = synced_client.post(
        "/api/recurring-workflows/x_social_trend_radar_sweep/run",
        json={"dry_run": True},
    )
    assert trends.status_code == 200
    assert trends.json()["result"]["external_actions"] == []

    reposts = synced_client.post(
        "/api/recurring-workflows/x_social_repost_candidate_sweep/run",
        json={"dry_run": True},
    )
    assert reposts.status_code == 200
    assert reposts.json()["result"]["auto_repost"] is False

    replies = synced_client.post(
        "/api/recurring-workflows/x_social_reply_candidate_sweep/run",
        json={"dry_run": True},
    )
    assert replies.status_code == 200
    assert replies.json()["result"]["auto_reply"] is False
    assert replies.json()["result"]["max_created_per_run"] == 1

def test_product_planning_sweep_creates_opportunities_not_goals(db_session):
    sync_recurring_workflows(db_session)
    ensure_active_manifest(db_session)
    before_goals = db_session.query(PlanningGoalRow).count()

    result = run_recurring_workflow(
        db_session, workflow_key="product_planning_sweep", dry_run=False
    )

    assert result["status"] == "completed"
    assert result["result"]["created_count"] >= 1
    assert db_session.query(PlanningGoalRow).count() == before_goals


def test_x_social_reply_candidate_sweep_recurring_run_invokes_service(
    db_session, monkeypatch
):
    sync_recurring_workflows(db_session)

    def fake_reply_sweep(db):
        assert db is db_session
        return {
            "created_reply_ids": [41],
            "human_gate_required": True,
            "auto_publish": False,
        }

    monkeypatch.setattr(
        "server.services.scheduling.recurring_workflows.run_x_social_reply_candidate_sweep",
        fake_reply_sweep,
    )

    result = run_recurring_workflow(
        db_session, workflow_key="x_social_reply_candidate_sweep", dry_run=False
    )

    assert result["status"] == "completed"
    assert result["result"]["created_reply_ids"] == [41]


def _create_release_for_pr_sync(
    db_session,
    *,
    status="pr_opened",
    delivery_state="pr_open",
    pr_number=31,
    pr_url=None,
):
    requirement = RequirementRow(
        title=f"Release sync test {pr_number}",
        description_markdown="Release sync test",
        status="done",
        priority="normal",
        source="test",
        intake_metadata_json="{}",
    )
    db_session.add(requirement)
    db_session.flush()
    release = ReleaseRecordRow(
        requirement_id=int(requirement.id),
        status=status,
        delivery_state=delivery_state,
        pr_url=pr_url
        or f"https://github.com/SynapseNetworkAI/Synapse-Network-Growing/pull/{pr_number}",
        pr_number=pr_number,
        metadata_json='{"pr_sync_failure_summary":"old failure"}',
    )
    db_session.add(release)
    db_session.commit()
    db_session.refresh(release)
    return release


def test_release_pr_status_sweep_maps_merged_pr(db_session):
    release = _create_release_for_pr_sync(db_session)

    result = sync_release_pr_statuses(
        db_session,
        query_status=lambda **_: {
            "result": "ok",
            "payload": {
                "state": "MERGED",
                "isDraft": False,
                "mergedAt": "2026-04-21T11:19:24Z",
                "closedAt": "2026-04-21T11:19:24Z",
                "mergeCommit": {"oid": "abc123"},
            },
        },
        sleep=lambda _: None,
    )

    db_session.refresh(release)
    metadata = json.loads(release.metadata_json)
    assert result["merged_ids"] == [release.id]
    assert release.status == "merged"
    assert release.delivery_state == "merged"
    assert release.commit_sha == "abc123"
    assert metadata["pr_status"] == "merged"
    assert metadata["merge_commit_sha"] == "abc123"
    assert "pr_sync_failure_summary" not in metadata


def test_release_pr_status_sweep_maps_closed_and_missing_prs(db_session):
    closed_release = _create_release_for_pr_sync(db_session, pr_number=32)
    missing_release = _create_release_for_pr_sync(db_session, pr_number=33)

    def query_status(*, pr_ref, **_):
        if str(pr_ref).endswith("/32"):
            return {
                "result": "ok",
                "payload": {
                    "state": "CLOSED",
                    "isDraft": False,
                    "closedAt": "2026-04-21T12:00:00Z",
                },
            }
        return {"result": "not_found", "error_excerpt": "HTTP 404: Not Found"}

    result = sync_release_pr_statuses(
        db_session, query_status=query_status, sleep=lambda _: None
    )

    db_session.refresh(closed_release)
    db_session.refresh(missing_release)
    missing_metadata = json.loads(missing_release.metadata_json)
    assert result["closed_ids"] == [closed_release.id]
    assert result["missing_ids"] == [missing_release.id]
    assert closed_release.status == "pr_closed"
    assert closed_release.delivery_state == "abandoned"
    assert closed_release.next_action == "review_closed_pr"
    assert missing_release.status == "pr_closed"
    assert missing_release.delivery_state == "abandoned"
    assert missing_release.next_action == "review_missing_pr"
    assert (
        missing_metadata["pr_sync_failure_summary"]
        == "PR removed from GitHub or no longer accessible"
    )


def test_release_pr_status_sweep_keeps_state_on_transient_error_and_limits_calls(
    db_session,
):
    first = _create_release_for_pr_sync(db_session, pr_number=34)
    second = _create_release_for_pr_sync(db_session, pr_number=35)
    calls: list[str] = []
    sleeps: list[float] = []

    def query_status(*, pr_ref, **_):
        calls.append(str(pr_ref))
        return {"result": "transient_error", "error_excerpt": "GitHub timeout"}

    result = sync_release_pr_statuses(
        db_session,
        max_records=1,
        query_status=query_status,
        sleep=lambda seconds: sleeps.append(seconds),
    )

    db_session.refresh(first)
    db_session.refresh(second)
    assert len(calls) == 1
    assert sleeps == []
    assert result["scanned_count"] == 1
    assert result["processed_count"] == 0
    assert result["failed_ids"] == [first.id]
    assert first.status == "pr_opened"
    assert second.status == "pr_opened"


def test_release_pr_status_sweep_rate_limits_between_queries(db_session):
    _create_release_for_pr_sync(db_session, pr_number=36)
    _create_release_for_pr_sync(db_session, pr_number=37)
    sleeps: list[float] = []

    result = sync_release_pr_statuses(
        db_session,
        query_status=lambda **_: {
            "result": "ok",
            "payload": {"state": "OPEN", "isDraft": False},
        },
        sleep=lambda seconds: sleeps.append(seconds),
    )

    assert result["processed_count"] == 2
    assert sleeps == [1.0]


def test_release_pr_status_recurring_workflow_records_history(db_session, monkeypatch):
    sync_recurring_workflows(db_session)

    monkeypatch.setattr(
        "server.services.scheduling.recurring_workflows.sync_release_pr_statuses",
        lambda db, **kwargs: {
            "status": "completed",
            "processed_count": 1,
            "merged_ids": [1],
            "closed_ids": [],
            "missing_ids": [],
            "failed_ids": [],
        },
    )

    result = run_recurring_workflow(
        db_session, workflow_key="release_pr_status_sweep", dry_run=False
    )

    assert result["status"] == "completed"
    assert result["result"]["processed_count"] == 1
    history = list_recurring_workflow_runs(db_session, "release_pr_status_sweep")
    assert history
    assert history[0].status == "succeeded"


def test_release_deployment_status_recurring_workflow_records_history(
    db_session, monkeypatch
):
    rows = sync_recurring_workflows(db_session)
    assert any(row.workflow_key == "release_deployment_status_sweep" for row in rows)

    monkeypatch.setattr(
        "server.services.scheduling.recurring_workflows.sync_release_task_deployment_statuses",
        lambda db, **kwargs: {
            "processed_count": 1,
            "succeeded_ids": [19],
            "failed_ids": [],
            "running_ids": [],
            "pending_ids": [],
        },
    )

    result = run_recurring_workflow(
        db_session, workflow_key="release_deployment_status_sweep", dry_run=False
    )

    assert result["status"] == "completed"
    assert result["result"]["processed_count"] == 1
    assert result["result"]["succeeded_ids"] == [19]
    history = list_recurring_workflow_runs(
        db_session, "release_deployment_status_sweep"
    )
    assert history
    assert history[0].status == "succeeded"


def test_release_deployment_status_recurring_workflow_dry_run_counts_candidates(
    db_session,
):
    from server.database import DeploymentRecordRow

    db_session.add(
        DeploymentRecordRow(
            project_key="synapse-network",
            environment="staging",
            action="deploy",
            status="requested",
            trigger_source="release_task",
            metadata_json="{}",
        )
    )
    db_session.add(
        DeploymentRecordRow(
            project_key="synapse-network",
            environment="staging",
            action="deploy",
            status="succeeded",
            trigger_source="release_task",
            metadata_json="{}",
        )
    )
    db_session.commit()
    sync_recurring_workflows(db_session)

    result = run_recurring_workflow(
        db_session, workflow_key="release_deployment_status_sweep", dry_run=True
    )

    assert result["status"] == "completed"
    assert result["result"]["candidate_deployment_count"] == 1
    assert result["result"]["read_only_github"] is True


def test_release_deployment_status_scheduler_runs_once_and_stops(monkeypatch):
    import time

    calls: list[str] = []

    class FakeSession:
        def close(self):
            calls.append("close")

    def fake_sync(db):
        calls.append("sync")

    def fake_run(db, *, workflow_key, triggered_by):
        calls.append(f"{workflow_key}:{triggered_by}")
        return {
            "result": {
                "processed_count": 1,
                "succeeded_ids": [19],
                "failed_ids": [],
                "running_ids": [],
                "pending_ids": [],
            }
        }

    monkeypatch.setattr(
        "server.services.releases.deployment_status_scheduler.sync_recurring_workflows",
        fake_sync,
    )
    monkeypatch.setattr(
        "server.services.releases.deployment_status_scheduler.run_recurring_workflow",
        fake_run,
    )

    scheduler = ReleaseDeploymentStatusSweepScheduler(
        session_factory=FakeSession,
        interval_seconds=60,
        startup_delay_seconds=0,
    )
    assert scheduler.status_snapshot()["running"] is False

    scheduler.start()
    for _ in range(20):
        if "release_deployment_status_sweep:scheduler" in calls:
            break
        time.sleep(0.01)
    scheduler.stop()

    snapshot = scheduler.status_snapshot()
    assert snapshot["enabled"] is True
    assert "sync" in calls
    assert "release_deployment_status_sweep:scheduler" in calls
    assert "close" in calls


def test_goal_planner_sweep_due_after_daily_slot_without_prior_run():
    from datetime import datetime, timezone

    assert goal_planner_sweep_due(
        last_run_at=None,
        now=datetime(2026, 4, 20, 9, 1, tzinfo=timezone.utc),
        local_time="09:00",
    )


def test_goal_planner_sweep_due_uses_operator_timezone():
    from datetime import datetime, timezone

    assert not goal_planner_sweep_due(
        last_run_at=None,
        now=datetime(2026, 4, 20, 0, 59, tzinfo=timezone.utc),
        local_time="09:00",
        timezone_name="Asia/Kuala_Lumpur",
    )
    assert goal_planner_sweep_due(
        last_run_at=None,
        now=datetime(2026, 4, 20, 1, 1, tzinfo=timezone.utc),
        local_time="09:00",
        timezone_name="Asia/Kuala_Lumpur",
    )
    assert not goal_planner_sweep_due(
        last_run_at=datetime(2026, 4, 20, 1, 1, tzinfo=timezone.utc),
        now=datetime(2026, 4, 20, 2, 0, tzinfo=timezone.utc),
        local_time="09:00",
        timezone_name="Asia/Kuala_Lumpur",
    )
    assert not goal_planner_sweep_due(
        last_run_at=datetime(2026, 4, 20, 9, 1, tzinfo=timezone.utc),
        now=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        local_time="09:00",
    )


def test_recurring_daily_next_run_uses_operator_timezone(monkeypatch):
    monkeypatch.setattr("server.config.OPERATOR_TIMEZONE", "Asia/Kuala_Lumpur")
    row = RecurringWorkflowRow(
        workflow_key="goal_planner_sweep",
        display_name="Goal Planner Sweep",
        description="Daily planner",
        status="active",
        trigger_type="scheduled",
        owner_role="portfolio_planner",
        schedule_json='{"cadence":"daily","suggested_local_time":"09:00"}',
        input_query_json="{}",
        output_action_json="{}",
        escalation_rule_json="{}",
        validation_signal_json="{}",
    )

    next_run = _next_run_at(row, now=datetime(2026, 4, 21, 10, 30, tzinfo=timezone.utc))

    assert next_run == datetime(2026, 4, 22, 1, 0, tzinfo=timezone.utc)


def test_goal_planner_recurring_workflow_runs_real_planner_dry_run(
    db_session, monkeypatch
):
    from server.services.planning.planner_agent import PlannerAgentCandidate

    monkeypatch.setattr(
        "server.services.planning.lifecycle.synthesize_candidate_for_goal",
        lambda **kwargs: PlannerAgentCandidate(
            title=f"Advance goal: {kwargs['goal'].title}",
            description_markdown="## Goal\nDry-run candidate",
            workflow_key=str(kwargs["goal"].workflow_key or "agent_self_repair"),
            priority="normal",
            risk_level="normal",
            confidence=0.7,
            rationale="Dry-run planner test.",
            acceptance_contract=kwargs.get("acceptance_contract")
            or {
                "execution_acceptance_steps": [
                    {
                        "step_key": "dry_run",
                        "title": "Dry-run evidence",
                        "expected_result": "Dry-run candidate has safe evidence.",
                        "required_commands": ["python -m pytest -q"],
                    }
                ]
            },
            metadata={"generated_by": "planner_agent_v1", "planner_repair_attempts": 0},
        ),
    )
    sync_recurring_workflows(db_session)

    result = run_recurring_workflow(
        db_session, workflow_key="goal_planner_sweep", dry_run=True
    )

    assert result["status"] == "completed"
    assert result["result"]["dry_run"] is True
    assert "routing_results" in result["result"]
    rows = list_recurring_workflow_runs(db_session, "goal_planner_sweep")
    assert rows


def test_bug_log_sweep_skips_when_scheduler_lock_is_held(db_session):
    sync_recurring_workflows(db_session)
    lock = acquire_scheduler_lock(
        db_session,
        lock_key="scheduler:bug_log_sweep",
        owner_id="test-owner",
        ttl_seconds=300,
        metadata={"test": True},
    )
    assert lock is not None

    result = run_recurring_workflow(
        db_session, workflow_key="bug_log_sweep", dry_run=True
    )

    assert result["status"] == "skipped_locked"
    rows = list_recurring_workflow_runs(db_session, "bug_log_sweep")
    assert len(rows) == 1
    assert rows[0].status == "skipped_locked"


def _create_awaiting_ci_run(
    db_session, tmp_path, *, exit_code: int | None = None, log_body: str = ""
):
    requirement = RequirementRow(
        title="CI final regression",
        description_markdown="Run final regression before PR handoff.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        status="in_progress",
    )
    db_session.add(requirement)
    db_session.flush()
    log_path = tmp_path / f"run-{requirement.id}.log"
    exit_code_path = tmp_path / f"run-{requirement.id}.exit_code"
    log_path.write_text(log_body, encoding="utf-8")
    if exit_code is not None:
        exit_code_path.write_text(f"{exit_code}\n", encoding="utf-8")
    blackboard = {
        "workflow_key": "agent_self_repair",
        "current_state": "awaiting_ci",
        "ci": {
            "status": "in_progress",
            "ci_backend": "local_marker",
            "ci_command": ["python", "-m", "pytest", "-q"],
            "ci_log_path": str(log_path),
            "ci_exit_code_path": str(exit_code_path),
            "ci_timeout_at": (
                datetime.now(timezone.utc) + timedelta(minutes=5)
            ).isoformat(),
        },
    }
    run = WorkflowRunRow(
        requirement_id=int(requirement.id),
        workflow_key="agent_self_repair",
        current_state="awaiting_ci",
        status="awaiting_ci",
        triggered_by="test",
        blackboard_json=json.dumps(blackboard),
    )
    db_session.add(run)
    db_session.flush()
    return run, log_path, exit_code_path


def test_ci_status_sweep_failed_ci_records_bounded_tail_and_human_gate(
    db_session, tmp_path
):
    long_log = "\n".join(f"line {index}" for index in range(2000))
    run, _log_path, _exit_path = _create_awaiting_ci_run(
        db_session, tmp_path, exit_code=1, log_body=long_log
    )

    result = _ci_status_sweep(db_session, runtime_cap_seconds=60)

    assert result["processed_count"] == 1
    db_session.refresh(run)
    assert run.current_state == "awaiting_operator"
    assert run.status == "awaiting_operator"
    assert run.resolution == "ci_failed_needs_human"
    artifact = (
        db_session.query(WorkflowArtifactRow)
        .filter(WorkflowArtifactRow.workflow_run_id == run.id)
        .one()
    )
    assert "line 1999" in artifact.human_readable_body
    assert "line 0" not in artifact.human_readable_body
    assert len(artifact.human_readable_body.encode("utf-8")) <= 8192
    gate = (
        db_session.query(HumanGateRequestRow)
        .filter(HumanGateRequestRow.workflow_run_id == run.id)
        .one()
    )
    assert gate.gate_type == "ci_final_regression_failed"


def test_ci_status_sweep_uses_latest_blackboard_after_bulk_claim(db_session, tmp_path):
    run, _old_log_path, _old_exit_path = _create_awaiting_ci_run(
        db_session,
        tmp_path,
        exit_code=1,
        log_body="old failed marker",
    )
    old_blackboard = json.loads(str(run.blackboard_json))
    new_log_path = tmp_path / "retry.log"
    new_exit_path = tmp_path / "retry.exit_code"
    new_log_path.write_text("new failed marker", encoding="utf-8")
    new_exit_path.write_text("1\n", encoding="utf-8")
    new_blackboard = dict(old_blackboard)
    new_blackboard["ci"] = {
        **dict(old_blackboard["ci"]),
        "ci_log_path": str(new_log_path),
        "ci_exit_code_path": str(new_exit_path),
    }
    db_session.query(WorkflowRunRow).filter(WorkflowRunRow.id == run.id).update(
        {WorkflowRunRow.blackboard_json: json.dumps(new_blackboard)},
        synchronize_session=False,
    )
    db_session.commit()

    result = _ci_status_sweep(db_session, runtime_cap_seconds=60)

    assert result["processed_count"] == 1
    artifact = (
        db_session.query(WorkflowArtifactRow)
        .filter(WorkflowArtifactRow.workflow_run_id == run.id)
        .one()
    )
    assert "new failed marker" in artifact.human_readable_body
    assert "old failed marker" not in artifact.human_readable_body


def test_ci_status_sweep_in_progress_does_not_read_log(
    db_session, tmp_path, monkeypatch
):
    run, _log_path, _exit_path = _create_awaiting_ci_run(
        db_session, tmp_path, exit_code=None, log_body="still running"
    )

    def fail_if_read(*args, **kwargs):
        raise AssertionError("in-progress CI must not read log tail")

    monkeypatch.setattr(
        "server.services.scheduling.recurring_workflows._bounded_log_tail", fail_if_read
    )
    result = _ci_status_sweep(db_session, runtime_cap_seconds=60)

    assert result["processed_count"] == 0
    db_session.refresh(run)
    assert run.current_state == "awaiting_ci"


def test_ci_status_sweep_recovers_stale_processing_lock(db_session, tmp_path):
    run, _log_path, _exit_path = _create_awaiting_ci_run(
        db_session, tmp_path, exit_code=None
    )
    run.current_state = "processing_ci_result"
    run.status = "awaiting_ci"
    run.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.commit()

    result = _ci_status_sweep(
        db_session, runtime_cap_seconds=60, stale_lock_seconds=300
    )

    assert result["stale_processing_locks_recovered"] == 1
    db_session.refresh(run)
    assert run.current_state == "awaiting_ci"


def test_ci_status_sweep_runtime_cap_stops_before_next_workflow(
    db_session, tmp_path, monkeypatch
):
    _create_awaiting_ci_run(db_session, tmp_path, exit_code=None)
    _create_awaiting_ci_run(db_session, tmp_path, exit_code=None)
    ticks = iter([0.0, 61.0])
    monkeypatch.setattr(
        "server.services.scheduling.recurring_workflows.time.monotonic",
        lambda: next(ticks, 61.0),
    )

    result = _ci_status_sweep(db_session, runtime_cap_seconds=60)

    assert result["sweep_runtime_cap_reached"] is True
    assert result["processed_count"] == 0
    assert result["remaining_count"] == 2


def test_ci_status_sweep_is_registered(db_session):
    rows = sync_recurring_workflows(db_session)

    assert any(row.workflow_key == "ci_status_sweep" for row in rows)


def test_runner_stale_sweep_alerts_only_stale_running_workflows(
    db_session, monkeypatch
):
    monkeypatch.setattr(
        "server.config.WORKFLOW_RUNNER_STALE_AGENT_SELF_REPAIR_SECONDS", 900
    )
    monkeypatch.setattr("server.config.OPS_BASE_URL", "http://localhost:9700")
    now = datetime(2026, 4, 22, 1, 0, tzinfo=timezone.utc)
    stale_requirement = RequirementRow(
        title="Stale self repair",
        description_markdown="Runner has not progressed.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        status="in_progress",
        project_key="synapse-network-growing",
    )
    fresh_requirement = RequirementRow(
        title="Fresh self repair",
        description_markdown="Runner recently progressed.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        status="in_progress",
        project_key="synapse-network-growing",
    )
    db_session.add_all([stale_requirement, fresh_requirement])
    db_session.flush()
    stale_run = WorkflowRunRow(
        requirement_id=int(stale_requirement.id),
        workflow_key="agent_self_repair",
        current_state="verify",
        status="running",
        triggered_by="test",
        updated_at=now - timedelta(minutes=20),
    )
    fresh_run = WorkflowRunRow(
        requirement_id=int(fresh_requirement.id),
        workflow_key="agent_self_repair",
        current_state="verify",
        status="running",
        triggered_by="test",
        updated_at=now - timedelta(minutes=5),
    )
    done_run = WorkflowRunRow(
        requirement_id=int(fresh_requirement.id),
        workflow_key="agent_self_repair",
        current_state="done",
        status="succeeded",
        triggered_by="test",
        updated_at=now - timedelta(hours=2),
    )
    db_session.add_all([stale_run, fresh_run, done_run])
    db_session.commit()

    result = _runner_stale_sweep(db_session, now=now)
    second_result = _runner_stale_sweep(db_session, now=now + timedelta(minutes=1))

    assert result["stale_workflow_run_ids"] == [int(stale_run.id)]
    assert second_result["stale_workflow_run_ids"] == [int(stale_run.id)]
    events = (
        db_session.query(NotificationEventRow)
        .filter(NotificationEventRow.event_type == "runner_stale")
        .order_by(NotificationEventRow.id.asc())
        .all()
    )
    assert [event.status for event in events] == ["delivered", "suppressed"]
    event = events[0]
    assert event.channel == "alert"
    payload = json.loads(event.payload_json)
    assert payload["object_refs"]["workflow_run_id"] == int(stale_run.id)
    assert payload["object_refs"]["current_state"] == "verify"
    assert payload["object_refs"]["root_cause_kind"] == "runner_stale"
    assert payload["links"]["工作流"].endswith(f"/workflows/{int(stale_run.id)}")
