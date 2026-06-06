import json
import sys
from pathlib import Path

from scripts.growth import record_ai_visibility_probe as record_probe_cli
from scripts.growth import (
    import_ai_visibility_public_search_snapshot as public_search_cli,
)


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


def test_public_search_snapshot_import_outputs_diagnostic_probe_rows(
    tmp_path: Path,
):
    snapshot_path = tmp_path / "public-search.json"
    snapshot = {
        "snapshot_type": "public_web_search_visibility",
        "observed_at": "2026-06-06T01:02:03Z",
        "feed_key": "mcp_paid_api_discovery",
        "run_group": "2026-06-06-after-feed",
        "official_homepage": "https://www.synapse-network.ai/",
        "queries": [
            {
                "query": "MCP server for paid API calls Synapse",
                "synapse_found_in_returned_results": False,
                "observed_competitors_or_adjacent_results": [
                    {
                        "name": "MCPay",
                        "url": "https://docs.mcpay.tech/",
                    },
                    {
                        "name": "Hud Remote MCP Server",
                        "url": "https://docs.hud.io/docs/remote-mcp",
                    },
                ],
            },
            {
                "query": 'site:synapse-network.ai "MCP Server for Paid API Calls"',
                "synapse_found_in_returned_results": True,
                "observed_competitors_or_adjacent_results": [
                    {
                        "name": "Synapse MCP",
                        "url": "https://docs.synapse-network.ai/mcp/paid-api-calls",
                    }
                ],
            },
        ],
        "next_actions": ["Refresh IndexNow and rerun public web search."],
    }
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    records = public_search_cli.records_from_snapshot(
        snapshot,
        source_path=str(snapshot_path),
    )

    assert len(records) == 2
    assert records[0].platform == "public_web_search"
    assert records[0].synapse_mentioned is False
    assert records[0].synapse_cited is False
    assert records[0].competitor_mentions == [
        "MCPay",
        "Hud Remote MCP Server",
    ]
    assert records[0].missing_facts == [
        "Public web search returned no official Synapse result for query: MCP server for paid API calls Synapse"
    ]
    assert records[0].metadata["diagnostic_only"] is True
    assert records[1].synapse_mentioned is True
    assert records[1].result_rank == 1

    errors = record_probe_cli.validate_records(records)
    assert errors == []
