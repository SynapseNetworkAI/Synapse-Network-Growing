import json
import sys
from pathlib import Path

from scripts.growth import generate_ai_visibility_goal_audit as goal_audit_cli


def test_generate_goal_audit_cli_writes_fail_closed_evidence(
    monkeypatch, tmp_path: Path
):
    output_path = tmp_path / "goal-audit.json"

    class FakeAudit:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {
                "module_key": "ai_visibility",
                "status": "incomplete",
                "goal_achieved": False,
                "target_platforms": ["chatgpt", "claude", "grok", "gemini"],
                "completed_count": 5,
                "total_required": 8,
                "blockers": ["Missing real external GPT/Claude/Grok/Gemini evidence."],
                "export_command": "python scripts/growth/generate_ai_visibility_goal_audit.py",
            }

    class FakeSession:
        def close(self):
            return None

    monkeypatch.setattr(goal_audit_cli, "init_db", lambda: None)
    monkeypatch.setattr(goal_audit_cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        goal_audit_cli,
        "ai_visibility_goal_audit",
        lambda _db: FakeAudit(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_goal_audit.py",
            "--output",
            str(output_path),
        ],
    )

    assert goal_audit_cli.main() == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "incomplete"
    assert payload["goal_achieved"] is False
    assert payload["target_platforms"] == ["chatgpt", "claude", "grok", "gemini"]
    assert payload["completed_count"] < payload["total_required"]
    assert "Missing real external GPT/Claude/Grok/Gemini evidence." in payload["blockers"]
