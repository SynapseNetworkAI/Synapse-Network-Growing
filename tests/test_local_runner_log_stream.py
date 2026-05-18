from server.services.local_runner.json_utils import _json_load_dict, json_dump
from server.services.local_runner.log_stream import run_command_with_chunked_logs
from server.services.local_runner.worker_loop import run_forever


def test_chunked_log_writer_reduces_event_count_for_log_storm():
    events = []

    def append_event(event_type, message, step_key):
        events.append((event_type, message, step_key))

    result = run_command_with_chunked_logs(
        [
            "python",
            "-c",
            "import sys\nfor i in range(10000): print(f'line-{i}')",
        ],
        append_event=append_event,
        step_key="storm",
        echo=False,
        flush_interval_ms=60000,
        flush_bytes=4096,
    )

    assert result.exit_code == 0
    stdout_events = [event for event in events if event[0] == "stdout"]
    assert 1 < len(stdout_events) < 10000
    assert "line-0" in "".join(event[1] for event in stdout_events)
    assert "line-9999" in "".join(event[1] for event in stdout_events)


def test_chunked_log_writer_preserves_middle_stderr_root_cause():
    events = []

    def append_event(event_type, message, step_key):
        events.append((event_type, message, step_key))

    result = run_command_with_chunked_logs(
        [
            "python",
            "-c",
            (
                "import sys\n"
                "sys.stderr.write('before\\n')\n"
                "sys.stderr.write('ROOT_CAUSE in middle\\n')\n"
                "sys.stderr.write('after\\n')\n"
                "sys.exit(3)\n"
            ),
        ],
        append_event=append_event,
        step_key="stderr",
        echo=False,
        flush_interval_ms=60000,
        flush_bytes=65536,
    )

    assert result.exit_code == 3
    stderr_text = "".join(event[1] for event in events if event[0] == "stderr")
    assert "ROOT_CAUSE in middle" in stderr_text


def test_json_helpers_and_worker_loop_sleep(monkeypatch):
    assert json_dump({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'
    assert _json_load_dict("") == {}
    assert _json_load_dict("{bad") == {}
    assert _json_load_dict("[1]") == {}
    assert _json_load_dict('{"ok": true}') == {"ok": True}

    calls = []

    def callback():
        calls.append("tick")
        raise KeyboardInterrupt

    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    try:
        run_forever(callback, sleep_seconds=0)
    except KeyboardInterrupt:
        pass
    assert calls == ["tick"]
