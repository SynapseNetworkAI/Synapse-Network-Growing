import json
from pathlib import Path

from scripts.growth import generate_ai_visibility_operator_brief as operator_brief
from scripts.growth import summarize_ai_visibility_cycle as cycle_summary


def test_cycle_summary_surfaces_source_host_effectiveness_inputs(tmp_path: Path):
    probe_path = _write_source_host_probe(tmp_path)

    records = cycle_summary.parse_probe_file(probe_path)
    payload = cycle_summary.summarize_cycle(records, source_path=str(probe_path))

    assert [item["platform"] for item in payload["platform_results"]] == [
        "chatgpt",
        "claude",
        "grok",
        "gemini",
    ]
    assert payload["top_source_hosts"][0] == {
        "value": "mcp.directory",
        "count": 2,
        "surface": "mcp_directory",
    }
    assert payload["top_competitors"][0] == {"value": "MCPay", "count": 1}
    chatgpt = next(
        item for item in payload["platform_results"] if item["platform"] == "chatgpt"
    )
    assert chatgpt["status"] == "not_visible_yet"
    assert chatgpt["source_hosts"][0]["value"] == "mcp.directory"
    assert "mcp.directory" in chatgpt["next_action"]


def test_operator_brief_renders_observed_outcomes(tmp_path: Path):
    summary_path = tmp_path / "cycle-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "blockers": [
                    "Production docs page https://docs.synapse-network.ai/mcp/paid-api-calls is not live yet."
                ],
                "platform_results": [
                    {
                        "platform": "chatgpt",
                        "status": "not_visible_yet",
                        "mentioned_count": 0,
                        "cited_count": 0,
                        "next_action": "Feed or refresh source hosts observed by chatgpt: mcp.directory.",
                    }
                ],
                "top_source_hosts": [
                    {
                        "value": "mcp.directory",
                        "surface": "mcp_directory",
                        "count": 2,
                    }
                ],
                "top_competitors": [{"value": "MCPay", "count": 1}],
                "next_actions": ["Publish MCP paid API docs and www llms feed."],
            }
        ),
        encoding="utf-8",
    )

    brief = operator_brief.render_operator_brief(
        feed_key="mcp_paid_api_discovery",
        cycle_summary_path=str(summary_path),
    )

    assert "## Observed Search Outcome" in brief
    assert "chatgpt: not_visible_yet (0 mentions / 0 citations)" in brief
    assert "## Next Feed Targets" in brief
    assert "mcp_directory: mcp.directory appeared 2 time(s)." in brief
    assert "MCPay: 1" in brief


def _write_source_host_probe(tmp_path: Path) -> Path:
    probe_path = tmp_path / "source-host-cycle.jsonl"
    probe_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "query": "MCP server for paid API calls",
                        "platform": "chatgpt",
                        "feed_key": "mcp_paid_api_discovery",
                        "run_group": "2026-06-18-source-host-cycle",
                        "answer_summary": "ChatGPT cited MCP directories.",
                        "synapse_mentioned": False,
                        "synapse_cited": False,
                        "competitor_mentions": ["MCPay", "x402"],
                        "metadata": {
                            "source_hosts": [
                                "mcp.directory",
                                "mcpservers.org",
                                "mcp.directory",
                            ]
                        },
                    }
                ),
                json.dumps(
                    {
                        "query": "ChatGPT MCP app for API payments",
                        "platform": "gemini",
                        "feed_key": "mcp_paid_api_discovery",
                        "run_group": "2026-06-18-source-host-cycle",
                        "answer_summary": "Gemini returned no source hosts.",
                        "synapse_mentioned": False,
                        "synapse_cited": False,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    return probe_path
