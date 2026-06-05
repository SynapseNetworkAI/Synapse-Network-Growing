import json
import sys
from pathlib import Path

from scripts.growth import export_ai_visibility_weekly_report as weekly_report_cli


def test_export_weekly_report_cli_writes_json(monkeypatch, tmp_path: Path):
    output_path = tmp_path / "weekly-report.json"

    class FakeReport:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {
                "module_key": "ai_visibility",
                "goal_status": "optimizing",
                "goal_achieved": False,
                "official_homepage": "https://www.synapse-network.ai/",
                "blockers": ["Run external probes."],
            }

    class FakeSession:
        def close(self):
            return None

    monkeypatch.setattr(weekly_report_cli, "init_db", lambda: None)
    monkeypatch.setattr(weekly_report_cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        weekly_report_cli,
        "ai_visibility_weekly_report",
        lambda _db: FakeReport(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_ai_visibility_weekly_report.py",
            "--output",
            str(output_path),
        ],
    )

    assert weekly_report_cli.main() == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["module_key"] == "ai_visibility"
    assert payload["goal_status"] == "optimizing"
    assert payload["official_homepage"] == "https://www.synapse-network.ai/"
