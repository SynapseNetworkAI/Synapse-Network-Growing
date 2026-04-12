from __future__ import annotations

import logging

from server.logging_utils import timed_operation


def test_timed_operation_logs_traceback_on_error(caplog):
    logger = logging.getLogger("ops-dashboard.test.logging")

    with caplog.at_level(logging.ERROR):
        try:
            with timed_operation(logger, "failing_operation", workflow_key="demo"):
                raise RuntimeError("boom")
        except RuntimeError:
            pass

    text = caplog.text
    assert "failing_operation" in text
    assert "Traceback" in text
    assert "RuntimeError: boom" in text
