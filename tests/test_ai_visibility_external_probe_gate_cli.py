import json
import os
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
                    "gemini missing GEMINI_API_KEY or GENIMI_API_KEY.",
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
    assert "GENIMI_API_KEY" in rendered
    assert "sk-" not in rendered


def test_generate_external_probe_gate_cli_loads_env_file_without_printing_values(
    monkeypatch,
    tmp_path: Path,
):
    output_path = tmp_path / "external-probe-gate.json"
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY='dotenv-openai-secret'",
                "ANTHROPIC_API_KEY=dotenv-anthropic-secret",
                "XAI_API_KEY=xai-dotenv-secret",
                "GENIMI_API_KEY=gemini-dotenv-secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "XAI_API_KEY",
        "GEMINI_API_KEY",
        "GENIMI_API_KEY",
        "AI_VISIBILITY_ENV_FILE",
        "AI_VISIBILITY_SKIP_DOTENV",
    ):
        monkeypatch.delenv(key, raising=False)

    class EnvAwareGate:
        def model_dump(self, mode: str):  # noqa: ARG002
            ready = [
                platform
                for platform, key in [
                    ("chatgpt", "OPENAI_API_KEY"),
                    ("claude", "ANTHROPIC_API_KEY"),
                    ("grok", "XAI_API_KEY"),
                    ("gemini", "GENIMI_API_KEY"),
                ]
                if os.environ.get(key)
            ]
            return {
                "status": "ready_to_execute_external_probes",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-05-external-gate",
                "ready_to_execute": len(ready) == 4,
                "ready_platforms": ready,
                "missing_platforms": [],
                "blockers": [],
            }

    monkeypatch.setattr(
        external_gate_cli,
        "ai_visibility_external_probe_gate",
        lambda **_kwargs: EnvAwareGate(),
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
            "--env-file",
            str(env_path),
            "--output",
            str(output_path),
        ],
    )

    assert external_gate_cli.main() == 0
    rendered = output_path.read_text(encoding="utf-8")
    payload = json.loads(rendered)
    assert payload["ready_to_execute"] is True
    assert payload["ready_platforms"] == ["chatgpt", "claude", "grok", "gemini"]
    assert "dotenv-openai-secret" not in rendered
    assert "dotenv-anthropic-secret" not in rendered
    assert "xai-dotenv-secret" not in rendered
    assert "gemini-dotenv-secret" not in rendered
