import json
import sys
from pathlib import Path

from scripts.growth import generate_ai_visibility_presence_plan as presence_cli


def test_generate_ai_visibility_presence_plan_cli_writes_json(
    monkeypatch, tmp_path: Path
):
    output_path = tmp_path / "presence-plan.json"

    class FakePlan:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {
                "module_key": "ai_visibility",
                "status": "ready_for_presence_work",
                "feed_key": "mcp_paid_api_discovery",
                "actions": [
                    {
                        "host": "mcpservers.org",
                        "action_type": "directory_listing",
                    }
                ],
            }

    monkeypatch.setattr(
        presence_cli,
        "run_with_db",
        lambda callback: callback(object()),
    )
    monkeypatch.setattr(
        presence_cli,
        "_build_presence_plan",
        lambda _db, **_kwargs: FakePlan(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_presence_plan.py",
            "--feed-key",
            "mcp_paid_api_discovery",
            "--run-group",
            "2026-06-06-presence-cli",
            "--output",
            str(output_path),
        ],
    )

    assert presence_cli.main() == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "ready_for_presence_work"
    assert payload["actions"][0]["host"] == "mcpservers.org"
    assert payload["actions"][0]["action_type"] == "directory_listing"
