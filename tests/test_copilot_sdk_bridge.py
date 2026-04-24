import json
from pathlib import Path
from unittest.mock import patch

import pytest

from server.services.runtime.copilot_sdk_bridge import CopilotSDKBridge


def _bridge(tmp_path: Path) -> CopilotSDKBridge:
    runner = tmp_path / "run_session.mjs"
    runner.write_text("// test runner\n", encoding="utf-8")
    return CopilotSDKBridge(runner_path=runner, cwd=tmp_path)


def test_bridge_appends_case_sensitive_model_hint(tmp_path):
    bridge = _bridge(tmp_path)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = json.dumps({
            "success": False,
            "error": 'Request session.create failed with message: Model "GPT-5.4" is not available.',
        })
        mock_run.return_value.stderr = ""

        with pytest.raises(RuntimeError, match='Try "gpt-5.4"'):
            bridge.run_session({"model": "GPT-5.4", "prompt": "hi"}, timeout=30)


def test_bridge_preserves_exact_model_guidance_for_lowercase_id(tmp_path):
    bridge = _bridge(tmp_path)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = json.dumps({
            "success": False,
            "error": 'Request session.create failed with message: Model "gpt-9" is not available.',
        })
        mock_run.return_value.stderr = ""

        with pytest.raises(RuntimeError, match="must match models.list exactly"):
            bridge.run_session({"model": "gpt-9", "prompt": "hi"}, timeout=30)


def test_bridge_uses_unbounded_subprocess_timeout_when_zero(tmp_path):
    bridge = _bridge(tmp_path)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = json.dumps({"success": True, "content": "ok", "events": []})
        mock_run.return_value.stderr = ""

        bridge.run_session({"model": "gpt-5.4", "prompt": "hi"}, timeout=0)

    assert mock_run.call_args.kwargs["timeout"] is None


def test_bridge_returns_success_payload_with_events(tmp_path):
    bridge = _bridge(tmp_path)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = json.dumps({
            "success": True,
            "content": "ok",
            "sessionId": "session-1",
            "selectedAgent": "planner",
            "tokensUsed": 12,
            "events": [{"type": "started", "detail": "running"}, {"detail": "done"}],
        })
        mock_run.return_value.stderr = ""

        result = bridge.run_session({"model": "gpt-5.4", "prompt": "hi"}, timeout=30)

    assert result.content == "ok"
    assert result.session_id == "session-1"
    assert result.selected_agent == "planner"
    assert result.tokens_used == 12
    assert [event.type for event in result.events] == ["started", "runtime_event"]


def test_bridge_rejects_empty_or_invalid_runner_output(tmp_path):
    bridge = _bridge(tmp_path)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = "no output"
        with pytest.raises(RuntimeError, match="no output"):
            bridge.run_session({"model": "gpt-5.4"}, timeout=30)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "not-json"
        mock_run.return_value.stderr = ""
        with pytest.raises(RuntimeError, match="invalid JSON"):
            bridge.run_session({"model": "gpt-5.4"}, timeout=30)


def test_bridge_requires_runner_file(tmp_path):
    bridge = CopilotSDKBridge(runner_path=tmp_path / "missing.mjs", cwd=tmp_path)

    with pytest.raises(RuntimeError, match="Copilot SDK runner not found"):
        bridge.run_session({"model": "gpt-5.4"}, timeout=30)


def test_bridge_spawns_detached_worker(tmp_path):
    bridge = _bridge(tmp_path)

    with patch("subprocess.Popen") as mock_popen:
        process = mock_popen.return_value
        process.pid = 4321
        process.stdin.write.return_value = None
        process.stdin.flush.return_value = None
        process.stdin.close.return_value = None

        pid = bridge.start_session({
            "sessionId": "session-123",
            "stdoutPath": str(tmp_path / "worker.stdout.log"),
            "stderrPath": str(tmp_path / "worker.stderr.log"),
        })

    assert pid == 4321
    assert mock_popen.call_args.kwargs["start_new_session"] is True


def test_bridge_writes_worker_pid_into_existing_state(tmp_path):
    bridge = _bridge(tmp_path)
    state_path = tmp_path / "state.json"
    state_path.write_text("{bad json", encoding="utf-8")

    with patch("subprocess.Popen") as mock_popen:
        process = mock_popen.return_value
        process.pid = 9876
        process.stdin.write.return_value = None
        process.stdin.flush.return_value = None
        process.stdin.close.return_value = None

        pid = bridge.resume_session({
            "sessionId": "session-456",
            "statePath": str(state_path),
        })

    assert pid == 9876
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["workerPid"] == 9876
    assert state["sessionId"] == "session-456"
    assert state["status"] == "starting"


def test_bridge_uses_auth_token_for_runner_env(tmp_path, monkeypatch):
    bridge = _bridge(tmp_path)
    monkeypatch.setattr("server.services.runtime.copilot_sdk_bridge.config.COPILOT_GITHUB_TOKEN", "")
    monkeypatch.setattr("server.services.runtime.copilot_sdk_bridge.config.GH_TOKEN", "")
    monkeypatch.setattr("server.services.runtime.copilot_sdk_bridge.config.COPILOT_OAUTH_TOKEN", "")
    monkeypatch.setattr("server.services.runtime.copilot_sdk_bridge.config.GITHUB_TOKEN", "")
    monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("COPILOT_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    class _Auth:
        token = "gho_from_auth"

    bridge.auth_service.resolve_stored_auth = lambda: _Auth()

    env = bridge._runner_env()

    assert env["COPILOT_GITHUB_TOKEN"] == "gho_from_auth"
