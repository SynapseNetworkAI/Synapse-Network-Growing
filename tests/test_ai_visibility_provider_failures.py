import json
from pathlib import Path

from scripts.growth import summarize_ai_visibility_cycle as cycle_summary


def _provider_failure_row(platform: str) -> dict:
    return {
        "query": "MCP server for paid API calls",
        "platform": platform,
        "feed_key": "mcp_paid_api_discovery",
        "run_group": "2026-06-08-provider-failure",
        "answer_summary": f"{platform} provider failed.",
        "synapse_mentioned": False,
        "synapse_cited": False,
        "missing_facts": [f"{platform} API probe failed: provider credits unavailable"],
        "next_action": "Fix provider/API probe failure and rerun the same query.",
    }


def test_cycle_summary_marks_provider_failure_comparison_inconclusive(
    tmp_path: Path,
):
    previous_path = tmp_path / "previous-positive.jsonl"
    current_path = tmp_path / "current-provider-failure.jsonl"
    previous_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "query": "MCP server for paid API calls",
                    "platform": platform,
                    "feed_key": "mcp_paid_api_discovery",
                    "run_group": "2026-06-01-positive",
                    "answer_summary": f"{platform} cited Synapse.",
                    "synapse_mentioned": True,
                    "synapse_cited": platform == "chatgpt",
                    "cited_urls": ["https://www.synapse-network.ai/"]
                    if platform == "chatgpt"
                    else [],
                }
            )
            for platform in ("chatgpt", "claude", "grok")
        ),
        encoding="utf-8",
    )
    current_path.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {
                    "query": "MCP server for paid API calls",
                    "platform": "chatgpt",
                    "feed_key": "mcp_paid_api_discovery",
                    "run_group": "2026-06-08-provider-failure",
                    "answer_summary": "ChatGPT mentions SynapseNetwork.",
                    "synapse_mentioned": True,
                    "synapse_cited": False,
                },
                _provider_failure_row("claude"),
                _provider_failure_row("grok"),
            )
        ),
        encoding="utf-8",
    )

    payload = cycle_summary.summarize_cycle(
        cycle_summary.parse_probe_file(current_path),
        source_path=str(current_path),
        previous_records=cycle_summary.parse_probe_file(previous_path),
        previous_source_path=str(previous_path),
    )

    assert payload["provider_failure_count"] == 2
    assert payload["completed_external_probe_count"] == 1
    assert payload["comparison"]["comparison_status"] == "inconclusive_provider_failure"
    assert (
        "claude API probe failed: provider credits unavailable" in payload["blockers"]
    )
    assert "grok API probe failed: provider credits unavailable" in payload["blockers"]


def test_cycle_summary_marks_flat_provider_failure_run_inconclusive(
    tmp_path: Path,
):
    previous_path = tmp_path / "previous-no-mention.jsonl"
    current_path = tmp_path / "current-flat-provider-failure.jsonl"
    base_row = {
        "query": "MCP server for paid API calls",
        "platform": "chatgpt",
        "feed_key": "mcp_paid_api_discovery",
        "answer_summary": "ChatGPT did not mention SynapseNetwork.",
        "synapse_mentioned": False,
        "synapse_cited": False,
    }
    previous_path.write_text(
        json.dumps({**base_row, "run_group": "2026-06-01-no-mention"}),
        encoding="utf-8",
    )
    current_path.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {**base_row, "run_group": "2026-06-08-provider-failure"},
                _provider_failure_row("claude"),
                _provider_failure_row("grok"),
            )
        ),
        encoding="utf-8",
    )

    payload = cycle_summary.summarize_cycle(
        cycle_summary.parse_probe_file(current_path),
        source_path=str(current_path),
        previous_records=cycle_summary.parse_probe_file(previous_path),
        previous_source_path=str(previous_path),
    )

    assert payload["comparison"]["mentioned_delta"] == 0
    assert payload["comparison"]["cited_delta"] == 0
    assert payload["provider_failure_count"] == 2
    assert payload["comparison"]["comparison_status"] == "inconclusive_provider_failure"


def test_weekly_report_skips_provider_failure_for_stability_streak(synced_client):
    for platform in ("chatgpt", "claude"):
        response = synced_client.post(
            "/api/growth/ai-visibility/checks",
            json={
                "query": "AI agent payment API",
                "platform": platform,
                "answer_summary": "Synapse Network is cited by an official source.",
                "synapse_mentioned": True,
                "synapse_cited": True,
                "cited_urls": ["https://www.synapse-network.ai/"],
                "feed_key": "agent_payment_category_pages",
                "run_group": "2026-06-01-weekly-positive",
            },
        )
        assert response.status_code == 201

    for row in (
        {
            "query": "AI agent payment API",
            "platform": "chatgpt",
            "answer_summary": "Synapse Network was mentioned.",
            "synapse_mentioned": True,
            "synapse_cited": False,
            "feed_key": "agent_payment_category_pages",
            "run_group": "2026-06-08-provider-failure",
        },
        {
            **_provider_failure_row("claude"),
            "feed_key": "agent_payment_category_pages",
        },
        {
            **_provider_failure_row("grok"),
            "feed_key": "agent_payment_category_pages",
        },
    ):
        response = synced_client.post("/api/growth/ai-visibility/checks", json=row)
        assert response.status_code == 201

    report = synced_client.get("/api/growth/ai-visibility/weekly-report")

    assert report.status_code == 200
    payload = report.json()
    assert payload["stable_positive_runs"] == 1
    assert payload["latest_comparison_status"] == "inconclusive_provider_failure"
    assert any(
        "provider/API probe failure" in action for action in payload["next_actions"]
    )
