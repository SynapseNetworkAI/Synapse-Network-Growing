from __future__ import annotations

import subprocess
import sys
from pathlib import Path


RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "ci_runner.py"


def _run_runner(tmp_path: Path, command: list[str], *, timeout_seconds: int = 5) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    log_path = tmp_path / "ci.log"
    exit_code_path = tmp_path / "ci.exit_code"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--timeout-seconds",
            str(timeout_seconds),
            "--log-path",
            str(log_path),
            "--exit-code-path",
            str(exit_code_path),
            "--",
            *command,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    return completed, log_path, exit_code_path


def test_ci_runner_streams_large_stdout_to_log(tmp_path):
    completed, log_path, exit_code_path = _run_runner(
        tmp_path,
        [sys.executable, "-c", "print('x' * 200000)"],
    )

    assert completed.returncode == 0
    assert log_path.stat().st_size >= 200000
    assert exit_code_path.read_text(encoding="utf-8").strip() == "0"
    assert not (tmp_path / "ci.exit_code.tmp").exists()


def test_ci_runner_timeout_writes_marker_and_exit_code(tmp_path):
    completed, log_path, exit_code_path = _run_runner(
        tmp_path,
        [sys.executable, "-c", "import time; time.sleep(2)"],
        timeout_seconds=1,
    )

    assert completed.returncode == 124
    assert exit_code_path.read_text(encoding="utf-8").strip() == "124"
    assert "[CI RUNNER TIMEOUT] command exceeded 1 seconds" in log_path.read_text(encoding="utf-8")


def test_ci_runner_internal_error_writes_marker_and_exit_code(tmp_path):
    completed, log_path, exit_code_path = _run_runner(
        tmp_path,
        [str(tmp_path / "missing-command")],
    )

    assert completed.returncode == 125
    assert exit_code_path.read_text(encoding="utf-8").strip() == "125"
    assert "[CI RUNNER ERROR]" in log_path.read_text(encoding="utf-8")
