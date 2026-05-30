from datetime import datetime, timezone

from server.services.social import scheduler as social_scheduler


class FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeWorkflowRow:
    def __init__(self, workflow_key: str, *, last_run_at=None):
        self.workflow_key = workflow_key
        self.last_run_at = last_run_at


def test_x_social_scheduler_tick_runs_due_workflows_and_closes_session(monkeypatch):
    session = FakeSession()
    rows = [
        FakeWorkflowRow("x_social_daily_content_planner"),
        FakeWorkflowRow("x_social_trend_radar_sweep", last_run_at=datetime.now(timezone.utc)),
        FakeWorkflowRow("unrelated_workflow"),
    ]
    calls = []

    monkeypatch.setattr(social_scheduler, "sync_recurring_workflows", lambda db: rows)
    monkeypatch.setattr(social_scheduler, "recurring_workflow_to_dict", lambda row: {"is_due": row.workflow_key != "x_social_trend_radar_sweep"})

    def fake_run(_db, *, workflow_key: str, triggered_by: str):
        calls.append((workflow_key, triggered_by))
        return {"result": {"workflow_key": workflow_key, "ok": True}}

    monkeypatch.setattr(social_scheduler, "run_recurring_workflow", fake_run)

    scheduler = social_scheduler.XSocialSweepScheduler(session_factory=lambda: session, poll_seconds=1, startup_delay_seconds=0)
    scheduler._tick()

    assert calls == [("x_social_daily_content_planner", "scheduler")]
    assert scheduler.status_snapshot()["last_error"] is None
    assert scheduler.status_snapshot()["last_results"]["x_social_daily_content_planner"]["ok"] is True
    assert session.closed is True


def test_x_social_scheduler_tick_records_errors_and_closes_session(monkeypatch):
    session = FakeSession()

    def fail_sync(_db):
        raise RuntimeError("scheduler boom")

    monkeypatch.setattr(social_scheduler, "sync_recurring_workflows", fail_sync)

    scheduler = social_scheduler.XSocialSweepScheduler(session_factory=lambda: session, poll_seconds=1, startup_delay_seconds=0)
    scheduler._tick()

    assert scheduler.status_snapshot()["last_error"] == "scheduler boom"
    assert session.closed is True


def test_x_social_scheduler_tick_blocks_missing_x_client_config_without_error(
    monkeypatch,
):
    session = FakeSession()
    rows = [FakeWorkflowRow("x_social_post_observer_sweep")]

    monkeypatch.setattr(social_scheduler, "sync_recurring_workflows", lambda db: rows)
    monkeypatch.setattr(
        social_scheduler,
        "recurring_workflow_to_dict",
        lambda row: {"is_due": True},
    )

    def fail_run(_db, *, workflow_key: str, triggered_by: str):
        raise ValueError(
            "X_OAUTH_CLIENT_ID is required in local environment configuration."
        )

    monkeypatch.setattr(social_scheduler, "run_recurring_workflow", fail_run)

    scheduler = social_scheduler.XSocialSweepScheduler(
        session_factory=lambda: session,
        poll_seconds=1,
        startup_delay_seconds=0,
    )
    scheduler._tick()

    snapshot = scheduler.status_snapshot()
    assert snapshot["last_error"] is None
    assert snapshot["last_results"]["x_social_post_observer_sweep"]["status"] == "blocked"
    assert (
        snapshot["last_results"]["x_social_post_observer_sweep"][
            "requires_configuration"
        ]
        is True
    )
    assert session.closed is True


def test_x_social_scheduler_start_stop_without_duplicate_thread(monkeypatch):
    ran = {"count": 0}

    def fake_run_loop():
        ran["count"] += 1

    scheduler = social_scheduler.XSocialSweepScheduler(session_factory=FakeSession, poll_seconds=1, startup_delay_seconds=0)
    monkeypatch.setattr(scheduler, "_run_loop", fake_run_loop)

    scheduler.start()
    assert scheduler._thread is not None
    scheduler._thread.join(timeout=2)
    scheduler.start()
    scheduler.stop()

    assert ran["count"] == 2
    assert scheduler.status_snapshot()["running"] is False
