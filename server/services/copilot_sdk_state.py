"""Shared state helpers for detached Copilot SDK task execution."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


STATE_FILE_NAME = "copilot-session-state.json"
EVENTS_FILE_NAME = "copilot-session-events.jsonl"
STDOUT_FILE_NAME = "copilot-session.stdout.log"
STDERR_FILE_NAME = "copilot-session.stderr.log"


def task_output_dir(project_root: Path, agent_id: str, task_id: int) -> Path:
    return project_root / "roles" / agent_id / "outputs" / f"task-{task_id}"


def copilot_runtime_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "state": output_dir / STATE_FILE_NAME,
        "events": output_dir / EVENTS_FILE_NAME,
        "stdout": output_dir / STDOUT_FILE_NAME,
        "stderr": output_dir / STDERR_FILE_NAME,
        "output": output_dir / "output.md",
        "metadata": output_dir / "metadata.json",
        "runtime_events": output_dir / "runtime-events.json",
    }


def load_runtime_state(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_runtime_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_runtime_events_after(path: Path, after_seq: int = 0) -> list[dict]:
    if not path.exists():
        return []

    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        seq = int(item.get("seq", 0) or 0)
        if seq > after_seq:
            events.append(item)
    events.sort(key=lambda item: int(item.get("seq", 0) or 0))
    return events


def parse_runtime_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds_since_timestamp(value: str | None) -> float | None:
    dt = parse_runtime_timestamp(value)
    if dt is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def read_text_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None