from __future__ import annotations

import json
from datetime import datetime, timezone

from server.services.runtime.copilot_sdk_state import (
    copilot_runtime_paths,
    load_runtime_events_after,
    load_runtime_state,
    parse_runtime_timestamp,
    read_text_if_exists,
    save_runtime_state,
    seconds_since_timestamp,
    task_output_dir,
)
from server.services.runtime.runtime_guards import is_openai_runtime_guard_error


def test_copilot_sdk_state_paths_and_json_round_trip(tmp_path):
    output_dir = task_output_dir(tmp_path, "agent-a", 42)
    assert output_dir == tmp_path / "roles" / "agent-a" / "outputs" / "task-42"

    paths = copilot_runtime_paths(output_dir)
    assert paths["state"].name == "copilot-session-state.json"
    assert paths["events"].name == "copilot-session-events.jsonl"

    save_runtime_state(paths["state"], {"status": "running"})
    assert load_runtime_state(paths["state"]) == {"status": "running"}
    assert read_text_if_exists(paths["state"]) == '{\n  "status": "running"\n}'
    assert read_text_if_exists(paths["stdout"]) is None


def test_load_runtime_state_tolerates_invalid_and_trailing_payloads(tmp_path):
    missing = tmp_path / "missing.json"
    assert load_runtime_state(missing) is None

    state_path = tmp_path / "state.json"
    state_path.write_text("{bad json", encoding="utf-8")
    assert load_runtime_state(state_path) is None

    state_path.write_text('{"status":"done"}}}', encoding="utf-8")
    assert load_runtime_state(state_path) == {"status": "done"}

    state_path.write_text('["not", "dict"]', encoding="utf-8")
    assert load_runtime_state(state_path) is None


def test_load_runtime_events_after_filters_and_sorts(tmp_path):
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        "\n".join([
            json.dumps({"seq": 3, "type": "done"}),
            "not-json",
            json.dumps({"seq": 1, "type": "start"}),
            json.dumps({"seq": 2, "type": "middle"}),
        ]),
        encoding="utf-8",
    )

    events = load_runtime_events_after(events_path, after_seq=1)

    assert [event["seq"] for event in events] == [2, 3]
    assert load_runtime_events_after(tmp_path / "missing.jsonl") == []


def test_runtime_timestamp_helpers():
    aware = parse_runtime_timestamp("2026-04-24T10:00:00Z")
    assert aware is not None
    assert aware.tzinfo is not None

    naive = parse_runtime_timestamp("2026-04-24T10:00:00")
    assert naive is not None
    assert naive.tzinfo == timezone.utc

    assert parse_runtime_timestamp("not-a-date") is None
    assert seconds_since_timestamp(None) is None
    assert seconds_since_timestamp(datetime.now(timezone.utc).isoformat()) is not None


def test_openai_runtime_guard_error_detection():
    assert is_openai_runtime_guard_error("insufficient_quota: billing details required")
    assert is_openai_runtime_guard_error("The requested model does not exist")
    assert is_openai_runtime_guard_error("Incorrect API key provided")
    assert not is_openai_runtime_guard_error("temporary network timeout")
