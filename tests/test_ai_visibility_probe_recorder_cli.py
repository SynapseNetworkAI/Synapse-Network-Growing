import json
import sys
from pathlib import Path

from scripts.growth import record_ai_visibility_probe as record_probe_cli


def test_cli_db_apply_uses_database_writer(tmp_path: Path, monkeypatch, capsys):
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(
        json.dumps(
            {
                "query": "Remote MCP live readiness",
                "platform": "mcp_live_validation",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-05-goal-continuation",
                "answer_summary": "Live feed validation passed for the homepage.",
                "cited_urls": ["https://www.synapse-network.ai/"],
            }
        ),
        encoding="utf-8",
    )
    captured_records = []

    def fake_insert_records_with_db(records):
        captured_records.extend(records)
        return [{"id": 42}]

    monkeypatch.setattr(
        record_probe_cli,
        "insert_records_with_db",
        fake_insert_records_with_db,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "record_ai_visibility_probe.py",
            str(probe_path),
            "--allow-local-validation",
            "--db-apply",
        ],
    )

    assert record_probe_cli.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is False
    assert payload["target"] == "db"
    assert payload["created_ids"] == [42]
    assert [record.platform for record in captured_records] == ["mcp_live_validation"]


def test_cli_rejects_api_and_db_apply_together(tmp_path: Path, capsys, monkeypatch):
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(
        json.dumps(
            {
                "query": "MCP server for paid API calls",
                "platform": "grok",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-18-after-registry",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "record_ai_visibility_probe.py",
            str(probe_path),
            "--apply",
            "--db-apply",
        ],
    )

    assert record_probe_cli.main() == 2

    payload = json.loads(capsys.readouterr().err)
    assert payload["dry_run"] is False
    assert "--apply and --db-apply are mutually exclusive" in payload["errors"]
