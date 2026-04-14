from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from server.database import RecurringWorkflowRow, utcnow
from server.services.bugs.log_scheduler import bug_log_sweep_due, maybe_run_bug_log_sweep_once


def test_bug_log_sweep_due_checks_interval():
    now = utcnow()
    assert bug_log_sweep_due(last_run_at=None, now=now, interval_minutes=5) is True
    assert bug_log_sweep_due(last_run_at=now - timedelta(minutes=6), now=now, interval_minutes=5) is True
    assert bug_log_sweep_due(last_run_at=now - timedelta(minutes=4), now=now, interval_minutes=5) is False


def test_maybe_run_bug_log_sweep_once_runs_only_when_due(db_session):
    row = RecurringWorkflowRow(
        workflow_key="bug_log_sweep",
        display_name="Bug Log Sweep",
        description="Sweep runtime logs",
        status="active",
        trigger_type="scheduled",
        owner_role="runtime_reliability_engineer",
        schedule_json='{"cadence":"interval","interval_minutes":5}',
        input_query_json="{}",
        output_action_json="{}",
        escalation_rule_json="{}",
        validation_signal_json="{}",
        is_builtin=True,
        last_run_at=utcnow() - timedelta(minutes=10),
    )
    db_session.add(row)
    db_session.commit()

    with patch(
        "server.services.bugs.log_scheduler.run_recurring_workflow",
        return_value={"workflow_key": "bug_log_sweep", "status": "completed", "result": {}},
    ) as mock_run:
        result = maybe_run_bug_log_sweep_once(db_session)
    assert result is not None
    assert mock_run.call_count == 1

    db_session.refresh(row)
    row.last_run_at = utcnow()
    db_session.add(row)
    db_session.commit()

    with patch("server.services.bugs.log_scheduler.run_recurring_workflow") as mock_run_recent:
        recent_result = maybe_run_bug_log_sweep_once(db_session)
    assert recent_result is None
    assert mock_run_recent.call_count == 0
