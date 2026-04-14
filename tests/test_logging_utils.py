from __future__ import annotations

import json
import logging
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

from server.logging_utils import (
    bind_context,
    clear_context,
    get_logger,
    log_event,
    setup_ops_logging,
    timed_operation,
    _reset_logging_for_tests,
)


def _flush_handlers() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_log_event_writes_structured_json_and_merges_context(tmp_path: Path):
    _reset_logging_for_tests()
    setup_ops_logging(
        log_level="INFO",
        log_dir=str(tmp_path),
        log_file="ops-dashboard.jsonl",
        backup_days=2,
        service_name="ops-dashboard",
        env="test",
    )
    logger = get_logger("ops-dashboard.test.logging")

    bind_context(request_id="req-123")
    log_event(logger, "requirement_created", requirement_id=7, execution_id=11, outcome="ok")
    clear_context()
    _flush_handlers()

    payload = json.loads((tmp_path / "ops-dashboard.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert payload["event"] == "requirement_created"
    assert payload["message"] == "requirement_created"
    assert payload["service"] == "ops-dashboard"
    assert payload["env"] == "test"
    assert payload["logger"] == "ops-dashboard.test.logging"
    assert payload["request_id"] == "req-123"
    assert payload["requirement_id"] == 7
    assert payload["execution_id"] == 11
    assert payload["outcome"] == "ok"


def test_timed_operation_logs_structured_traceback_on_error(capsys):
    _reset_logging_for_tests()
    setup_ops_logging(
        log_level="INFO",
        log_dir="/tmp",
        log_file="ops-dashboard-test.jsonl",
        backup_days=1,
        service_name="ops-dashboard",
        env="test",
    )
    logger = get_logger("ops-dashboard.test.logging")

    try:
        with timed_operation(logger, "failing_operation", workflow_key="demo"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    text = capsys.readouterr().err
    assert "failing_operation" in text
    assert "RuntimeError: boom" in text
    assert "\"workflow_key\": \"demo\"" in text


def test_setup_ops_logging_configures_daily_rotating_file_handler(tmp_path: Path):
    _reset_logging_for_tests()
    setup_ops_logging(
        log_level="INFO",
        log_dir=str(tmp_path),
        log_file="ops-dashboard.jsonl",
        backup_days=3,
        service_name="ops-dashboard",
        env="test",
    )
    logger = get_logger("ops-dashboard.test.rotation")
    log_event(logger, "rotation_smoke", task_id=1)
    _flush_handlers()

    root = logging.getLogger()
    file_handlers = [handler for handler in root.handlers if isinstance(handler, TimedRotatingFileHandler)]
    assert len(file_handlers) == 1
    handler = file_handlers[0]
    assert handler.when == "MIDNIGHT"
    assert handler.interval == 60 * 60 * 24
    assert handler.backupCount == 3

    handler.doRollover()
    log_event(logger, "rotation_after_rollover", task_id=2)
    _flush_handlers()

    base_file = tmp_path / "ops-dashboard.jsonl"
    rotated_files = list(tmp_path.glob("ops-dashboard.jsonl.*"))
    assert base_file.exists()
    assert rotated_files, "daily rotation should leave at least one timestamped backup"
