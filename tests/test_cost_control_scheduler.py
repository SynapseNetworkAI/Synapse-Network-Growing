import json
from datetime import datetime, timezone
from types import SimpleNamespace

from server.database import SessionLocal
from server.services.scheduling.cost_control_scheduler import (
    CostControlScheduler,
    _ensure_utc,
    _json_object,
    _operator_zone,
    _parse_local_time,
    _should_run_cost_control_workflow,
)
from server.services.scheduling.recurring_workflows import sync_recurring_workflows


def test_cost_control_scheduler_runs_due_allowlisted_workflows(db_session, monkeypatch):
    sync_recurring_workflows(db_session)
    db_session.close()
    ran: list[tuple[str, str]] = []

    def fake_run_recurring_workflow(db, *, workflow_key: str, triggered_by: str, **_):
        ran.append((workflow_key, triggered_by))
        return {"result": {"workflow_key": workflow_key}}

    monkeypatch.setattr(
        "server.services.scheduling.cost_control_scheduler.run_recurring_workflow",
        fake_run_recurring_workflow,
    )
    monkeypatch.setattr(
        "server.services.scheduling.cost_control_scheduler._should_run_cost_control_workflow",
        lambda row, *, now=None: True,
    )

    scheduler = CostControlScheduler(
        session_factory=SessionLocal,
        poll_seconds=300,
        startup_delay_seconds=0,
    )
    scheduler._tick()

    assert ran == [
        ("artifact_registry_cleanup_sweep", "scheduler"),
        ("secret_manager_version_cleanup_sweep", "scheduler"),
        ("staging_environment_shutdown_sweep", "scheduler"),
    ]
    snapshot = scheduler.status_snapshot()
    assert snapshot["last_run_at"] is not None


def test_cost_control_scheduler_skips_not_due_workflows(db_session, monkeypatch):
    rows = sync_recurring_workflows(db_session)
    now = datetime.now(timezone.utc)
    for row in rows:
        if row.workflow_key in CostControlScheduler.WORKFLOW_KEYS:
            row.last_run_at = now
    db_session.commit()
    db_session.close()
    ran: list[str] = []

    monkeypatch.setattr(
        "server.services.scheduling.cost_control_scheduler.run_recurring_workflow",
        lambda db, *, workflow_key, **_: ran.append(workflow_key),
    )
    monkeypatch.setattr(
        "server.services.scheduling.cost_control_scheduler._should_run_cost_control_workflow",
        lambda row, *, now=None: False,
    )

    scheduler = CostControlScheduler(
        session_factory=SessionLocal,
        poll_seconds=300,
        startup_delay_seconds=0,
    )
    scheduler._tick()

    assert ran == []


def test_cost_control_scheduler_daily_shutdown_waits_until_local_time(db_session):
    rows = sync_recurring_workflows(db_session)
    row = next(
        item
        for item in rows
        if item.workflow_key == "staging_environment_shutdown_sweep"
    )
    row.schedule_json = json.dumps(
        {"cadence": "daily", "suggested_local_time": "23:00", "timezone": "UTC"}
    )
    row.last_run_at = None

    assert (
        _should_run_cost_control_workflow(
            row, now=datetime(2026, 5, 30, 14, 59, tzinfo=timezone.utc)
        )
        is False
    )
    assert (
        _should_run_cost_control_workflow(
            row, now=datetime(2026, 5, 30, 15, 1, tzinfo=timezone.utc)
        )
        is True
    )


def test_cost_control_scheduler_status_start_stop_and_loop_branches(monkeypatch):
    class FakeThread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False
            self.joined = False

        def start(self):
            self.started = True

        def is_alive(self):
            return self.started and not self.joined

        def join(self, timeout=None):
            self.joined = True

    monkeypatch.setattr(
        "server.services.scheduling.cost_control_scheduler.threading.Thread",
        lambda **kwargs: FakeThread(**kwargs),
    )

    scheduler = CostControlScheduler(
        session_factory=lambda: None,
        poll_seconds=1,
        startup_delay_seconds=1,
    )
    assert scheduler.status_snapshot()["running"] is False
    scheduler.start()
    first_thread = scheduler._thread
    scheduler.start()
    assert scheduler._thread is first_thread
    assert scheduler.status_snapshot()["running"] is True
    scheduler.stop()
    assert scheduler.status_snapshot()["running"] is False

    scheduler._stop_event.set()
    scheduler._run_loop()


def test_cost_control_scheduler_tick_handles_missing_rows_and_errors(monkeypatch):
    closed = []

    class FakeDb:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(
        "server.services.scheduling.cost_control_scheduler.sync_recurring_workflows",
        lambda db: [SimpleNamespace(workflow_key="unrelated", status="active")],
    )
    scheduler = CostControlScheduler(session_factory=FakeDb, startup_delay_seconds=0)
    scheduler._tick()
    assert scheduler._last_error is None
    assert closed == [True]

    monkeypatch.setattr(
        "server.services.scheduling.cost_control_scheduler.sync_recurring_workflows",
        lambda db: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    scheduler._tick()
    assert scheduler._last_error == "boom"


def test_cost_control_scheduler_due_helpers_are_deterministic(monkeypatch):
    row = SimpleNamespace(status="paused", schedule_json="{}")
    assert _should_run_cost_control_workflow(row) is False

    interval_row = SimpleNamespace(
        status="active",
        schedule_json=json.dumps({"cadence": "interval", "interval_minutes": 30}),
        last_run_at=None,
    )
    monkeypatch.setattr(
        "server.services.scheduling.cost_control_scheduler.recurring_workflow_to_dict",
        lambda row: {"is_due": False},
    )
    assert _should_run_cost_control_workflow(interval_row) is True

    daily_row = SimpleNamespace(
        status="active",
        schedule_json=json.dumps({"cadence": "daily", "suggested_local_time": "23:00"}),
        last_run_at=datetime(2026, 5, 29, 12, 0),
    )
    monkeypatch.setattr(
        "server.services.scheduling.cost_control_scheduler.config.OPERATOR_TIMEZONE",
        "UTC",
    )
    assert (
        _should_run_cost_control_workflow(
            daily_row, now=datetime(2026, 5, 30, 23, 1, tzinfo=timezone.utc)
        )
        is True
    )

    assert _parse_local_time("bad") == (23, 0)
    assert _parse_local_time("99:-1") == (23, 0)
    monkeypatch.setattr(
        "server.services.scheduling.cost_control_scheduler.config.OPERATOR_TIMEZONE",
        "Invalid/Zone",
    )
    assert _operator_zone().key == "UTC"
    assert _ensure_utc(datetime(2026, 1, 1)).tzinfo is not None
    assert _json_object("{") == {}
    assert _json_object("[]") == {}
