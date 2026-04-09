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