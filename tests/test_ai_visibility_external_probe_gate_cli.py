import json
import sys
from pathlib import Path

from scripts.growth import (
    generate_ai_visibility_external_probe_gate as external_gate_cli,
)


def test_generate_external_probe_gate_cli_writes_missing_key_evidence(
    monkeypatch,
    tmp_path: Path,
):
    output_path = tmp_path / "external-probe-gate.json"

    class FakeGate:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {
                "status": "blocked_until_api_keys",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-05-external-gate",
                "ready_to_execute": False,
                "missing_platforms": ["chatgpt", "claude", "grok", "gemini"],
                "blockers": [
                    "chatgpt missing OPENAI_API_KEY.",
                    "claude missing ANTHROPIC_API_KEY.",
                    "grok missing XAI_API_KEY.",
                    "gemini missing GEMINI_API_KEY.",
                ],
            }

    monkeypatch.setattr(
        external_gate_cli,
        "ai_visibility_external_probe_gate",
        lambda **_kwargs: FakeGate(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_external_probe_gate.py",
            "--feed-key",
            "mcp_paid_api_discovery",
            "--run-group",
            "2026-06-05-external-gate",
            "--output",
            str(output_path),
        ],
    )

    assert external_gate_cli.main() == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    rendered = json.dumps(payload)
    assert payload["feed_key"] == "mcp_paid_api_discovery"
    assert payload["run_group"] == "2026-06-05-external-gate"
    assert payload["ready_to_execute"] is False
    assert "chatgpt" in payload["missing_platforms"]
    assert "OPENAI_API_KEY" in rendered
    assert "ANTHROPIC_API_KEY" in rendered
    assert "XAI_API_KEY" in rendered
    assert "GEMINI_API_KEY" in rendered
    assert "sk-" not in rendered
