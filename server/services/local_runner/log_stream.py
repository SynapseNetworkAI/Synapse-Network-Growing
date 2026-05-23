"""Chunked subprocess log streaming for local runners."""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

DEFAULT_FLUSH_INTERVAL_MS = 2000
DEFAULT_FLUSH_BYTES = 65536


@dataclass(frozen=True)
class ChunkedCommandResult:
    exit_code: int
    duration_seconds: float
    failure_summary: str | None = None


class _StreamBuffer:
    def __init__(
        self,
        *,
        event_type: str,
        step_key: str,
        flush_interval_seconds: float,
        flush_bytes: int,
        append_event: Callable[[str, str, str], None],
        echo: bool,
    ) -> None:
        self.event_type = event_type
        self.step_key = step_key
        self.flush_interval_seconds = flush_interval_seconds
        self.flush_bytes = flush_bytes
        self.append_event = append_event
        self.echo = echo
        self._parts: list[str] = []
        self._byte_count = 0
        self._last_flush = time.monotonic()
        self._lock = threading.Lock()

    def append(self, text: str) -> None:
        if not text:
            return
        if self.echo:
            stream = sys.stderr if self.event_type == "stderr" else sys.stdout
            print(text, end="", file=stream, flush=True)
        with self._lock:
            self._parts.append(text)
            self._byte_count += len(text.encode("utf-8", errors="replace"))
            if self._should_flush_locked():
                self._flush_locked()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def maybe_flush_by_time(self) -> None:
        with self._lock:
            if (
                self._parts
                and (time.monotonic() - self._last_flush) >= self.flush_interval_seconds
            ):
                self._flush_locked()

    def _should_flush_locked(self) -> bool:
        if self._byte_count >= self.flush_bytes:
            return True
        return (time.monotonic() - self._last_flush) >= self.flush_interval_seconds

    def _flush_locked(self) -> None:
        if not self._parts:
            self._last_flush = time.monotonic()
            return
        message = "".join(self._parts)
        self._parts.clear()
        self._byte_count = 0
        self._last_flush = time.monotonic()
        self.append_event(self.event_type, message, self.step_key)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _reader_thread(pipe, buffer: _StreamBuffer) -> None:
    try:
        while True:
            chunk = pipe.readline()
            if not chunk:
                break
            buffer.append(chunk)
    finally:
        pipe.close()


def run_command_with_chunked_logs(
    command: Sequence[str],
    *,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    step_key: str = "run",
    append_event: Callable[[str, str, str], None],
    echo: bool = True,
    flush_interval_ms: int | None = None,
    flush_bytes: int | None = None,
) -> ChunkedCommandResult:
    """Run a command and write stdout/stderr to append-only chunk events.

    The function never inserts one DB row per log line. It flushes by time window,
    by byte size, and at process exit.
    """

    interval_ms = flush_interval_ms or _env_int(
        "RUNNER_LOG_FLUSH_INTERVAL_MS", DEFAULT_FLUSH_INTERVAL_MS
    )
    max_bytes = flush_bytes or _env_int("RUNNER_LOG_FLUSH_BYTES", DEFAULT_FLUSH_BYTES)
    interval_seconds = max(0.1, interval_ms / 1000.0)
    stdout_buffer = _StreamBuffer(
        event_type="stdout",
        step_key=step_key,
        flush_interval_seconds=interval_seconds,
        flush_bytes=max_bytes,
        append_event=append_event,
        echo=echo,
    )
    stderr_buffer = _StreamBuffer(
        event_type="stderr",
        step_key=step_key,
        flush_interval_seconds=interval_seconds,
        flush_bytes=max_bytes,
        append_event=append_event,
        echo=echo,
    )
    started = time.perf_counter()
    append_event("step_started", f"$ {' '.join(command)}\n", step_key)
    # Command list is supplied by deterministic runner policy, never shell-expanded here.
    process = subprocess.Popen(  # nosec B603
        list(command),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stdout_thread = threading.Thread(
        target=_reader_thread, args=(process.stdout, stdout_buffer), daemon=True
    )
    stderr_thread = threading.Thread(
        target=_reader_thread, args=(process.stderr, stderr_buffer), daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()
    while process.poll() is None:
        stdout_buffer.maybe_flush_by_time()
        stderr_buffer.maybe_flush_by_time()
        time.sleep(min(0.2, interval_seconds))
    stdout_thread.join()
    stderr_thread.join()
    stdout_buffer.flush()
    stderr_buffer.flush()
    duration = time.perf_counter() - started
    exit_code = int(process.returncode or 0)
    append_event(
        "step_finished",
        f"Command exited with code {exit_code} after {duration:.2f}s.\n",
        step_key,
    )
    summary = None
    if exit_code != 0:
        summary = f"Command exited with code {exit_code}: {' '.join(command)}"
    return ChunkedCommandResult(
        exit_code=exit_code,
        duration_seconds=duration,
        failure_summary=summary,
    )
