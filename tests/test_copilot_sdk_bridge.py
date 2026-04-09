import json
from pathlib import Path
from unittest.mock import patch

import pytest

from server.services.copilot_sdk_bridge import CopilotSDKBridge


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