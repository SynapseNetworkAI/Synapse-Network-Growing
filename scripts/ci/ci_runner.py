#!/usr/bin/env python3
"""Run a CI command with streaming logs and an atomic exit marker."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


TIMEOUT_EXIT_CODE = 124
RUNNER_ERROR_EXIT_CODE = 125


def _write_exit_code(path: Path, exit_code: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(f"{int(exit_code)}\n", encoding="utf-8")
    os.replace(tmp_path, path)


def _append_marker(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", errors="replace") as log:
        log.write("\n")
        log.write(message.rstrip())
        log.write("\n")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CI command with marker-file status.")
    parser.add_argument("--timeout-seconds", type=int, required=True)
    parser.add_argument("--log-path", required=True)
    parser.add_argument("--exit-code-path", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    log_path = Path(args.log_path)
    exit_code_path = Path(args.exit_code_path)
    timeout_seconds = max(1, int(args.timeout_seconds))
    command = [str(item) for item in args.command]
    exit_code = RUNNER_ERROR_EXIT_CODE

    try:
        if not command:
            raise ValueError("CI command must not be empty")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            completed = subprocess.run(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        exit_code = int(completed.returncode)
    except subprocess.TimeoutExpired:
        exit_code = TIMEOUT_EXIT_CODE
        _append_marker(log_path, f"[CI RUNNER TIMEOUT] command exceeded {timeout_seconds} seconds")
    except Exception as exc:  # Defensive: runner failures must produce a marker.
        exit_code = RUNNER_ERROR_EXIT_CODE
        _append_marker(log_path, f"[CI RUNNER ERROR] {exc.__class__.__name__}: {str(exc)[:500]}")
    finally:
        _write_exit_code(exit_code_path, exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
