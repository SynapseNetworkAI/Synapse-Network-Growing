import json
import subprocess
import sys
from pathlib import Path

from scripts.growth.generate_ai_visibility_feed_diagnosis import diagnose_feed
from scripts.growth.record_ai_visibility_probe import parse_probe_file


def test_diagnosis_recommends_external_source_hosts_for_zero_citation_probe(
    tmp_path: Path,
):
    records = parse_probe_file(
        write_probe_jsonl(
            tmp_path,
            [
                probe_row(
                    platform="chatgpt",
                    query="MCP server for paid API calls",
                    competitors=["Stripe", "x402"],
                ),
                probe_row(
                    platform="claude",
                    query="Synapse Network MCP server",
                    competitors=["Project Synapse", "Sage Bionetworks"],
                ),
                probe_row(
                    platform="grok",
                    query="AI agent API monetization MCP",
                    competitors=["Stripe"],
                ),
                probe_row(
                    platform="gemini",
                    query="paid API calls MCP server",
                    competitors=["RapidAPI"],
                ),
            ],
        )
    )

    diagnosis = diagnose_feed(records, source_path="probe.jsonl").model_dump()

    assert diagnosis["status"] == "source_host_actions_required"
    assert diagnosis["target_platforms"] == ["chatgpt", "claude", "grok", "gemini"]
    assert diagnosis["external_mentioned_count"] == 0
    assert diagnosis["external_cited_count"] == 0
    issue_keys = {item["issue_key"] for item in diagnosis["issues"]}
    assert "platform_missing_official_identity" in issue_keys
    assert "brand_collision_returned" in issue_keys
    assert "api_monetization_competitors_returned" in issue_keys

    draft_types = {
        item["draft_type"] for item in diagnosis["recommended_source_host_executions"]
    }
    assert "mcp_directory_listing" in draft_types
    assert "github_readme_answer_block" in draft_types
    assert "social_citation_thread" in draft_types


def test_diagnosis_marks_validation_only_rows_as_no_external_evidence(tmp_path: Path):
    records = parse_probe_file(
        write_probe_jsonl(
            tmp_path,
            [
                {
                    **probe_row(platform="www_live_validation"),
                    "metadata": {"mode": "feed_validation"},
                }
            ],
        )
    )

    diagnosis = diagnose_feed(records, source_path="validation.jsonl").model_dump()

    assert diagnosis["status"] == "no_external_probe_evidence"
    assert diagnosis["external_probe_count"] == 0
    assert (
        diagnosis["recommended_source_host_executions"][0]["surface"] == "probe_rerun"
    )


def test_diagnosis_promotes_observed_source_host_actions(tmp_path: Path):
    records = parse_probe_file(
        write_probe_jsonl(
            tmp_path,
            [
                probe_row(
                    platform="chatgpt",
                    query="Synapse vs paid MCP alternatives",
                    metadata={
                        "mode": "api_probe",
                        "source_hosts": [
                            "aitoolnet.com",
                            "alternativeto.net",
                            "mcp.directory",
                            "mcpservers.org",
                            "lobehub.com",
                            "mcpfind.org",
                            "protodex.io",
                            "pulsemcp.com",
                            "mcp-marketplace.io",
                        ],
                    },
                )
            ],
        )
    )

    diagnosis = diagnose_feed(records, source_path="probe.jsonl").model_dump()

    recommendations = diagnosis["recommended_source_host_executions"]
    surfaces = [item["surface"] for item in recommendations]
    assert surfaces[:8] == [
        "aitoolnet",
        "alternativeto",
        "mcp_directory",
        "mcpservers",
        "lobehub",
        "mcpfind",
        "protodex",
        "pulsemcp",
    ]
    assert recommendations[0]["draft_type"] == "ai_tool_directory_listing"
    assert recommendations[1]["draft_type"] == "software_alternative_listing"
    assert recommendations[2]["draft_type"] == "mcp_directory_listing"
    assert recommendations[3]["draft_type"] == "mcp_directory_listing"
    assert recommendations[4]["draft_type"] == "mcp_directory_listing"
    assert recommendations[5]["draft_type"] == "mcp_directory_listing"
    assert recommendations[0]["target_queries"] == ["Synapse vs paid MCP alternatives"]
    assert "browser/form confirmation" in recommendations[0]["validation_command"]
    assert "MCP Directory" in recommendations[2]["rationale"]
    assert "MCPServers" in recommendations[3]["rationale"]
    assert "LobeHub" in recommendations[4]["rationale"]
    assert "MCPFind" in recommendations[5]["rationale"]
    assert "Protodex" in recommendations[6]["rationale"]
    assert "PulseMCP" in recommendations[7]["rationale"]
    assert "after-source-hosts" in recommendations[7]["next_probe_command"]


def test_diagnosis_promotes_synapse_org_brand_collision_source_host(tmp_path: Path):
    records = parse_probe_file(
        write_probe_jsonl(
            tmp_path,
            [
                probe_row(
                    platform="chatgpt",
                    query="SynapseNetwork MCP Server",
                    metadata={
                        "mode": "api_probe",
                        "source_hosts": ["python-docs.synapse.org"],
                    },
                )
            ],
        )
    )

    diagnosis = diagnose_feed(records, source_path="probe.jsonl").model_dump()

    recommendations = diagnosis["recommended_source_host_executions"]
    first = recommendations[0]
    assert first["surface"] == "docs_disambiguation_links"
    assert first["draft_type"] == "brand_disambiguation_answer_block"
    assert first["priority"] == "p0"
    assert first["target_queries"] == ["SynapseNetwork MCP Server"]
    assert "Synapse.org/Sage Bionetworks" in first["content_brief"]
    assert "exact identifier probes" in first["validation_command"]


def test_diagnosis_promotes_exact_query_collision_source_hosts(tmp_path: Path):
    records = parse_probe_file(
        write_probe_jsonl(
            tmp_path,
            [
                probe_row(
                    platform="chatgpt",
                    query="SynapseNetworkAI/Synapse-Network-MCP-Server",
                    metadata={
                        "mode": "api_probe",
                        "source_hosts": [
                            "mcp.so",
                            "ubos.tech",
                            "mysynap.com",
                            "synapbus.dev",
                        ],
                    },
                )
            ],
        )
    )

    diagnosis = diagnose_feed(records, source_path="probe.jsonl").model_dump()

    recommendations = diagnosis["recommended_source_host_executions"]
    by_surface = {item["surface"]: item for item in recommendations}
    assert by_surface["mcp_so"]["draft_type"] == "mcp_directory_listing"
    assert by_surface["ubos_tech"]["draft_type"] == (
        "brand_collision_source_host_review"
    )
    assert by_surface["mysynap_com"]["priority"] == "p0"
    assert by_surface["synapbus_dev"]["priority"] == "p0"
    assert "exact SynapseNetwork MCP" in by_surface["mcp_so"]["rationale"]
    assert "collision evidence" in by_surface["ubos_tech"]["validation_command"]


def test_diagnosis_keeps_new_observed_source_hosts_actionable(tmp_path: Path):
    records = parse_probe_file(
        write_probe_jsonl(
            tmp_path,
            [
                probe_row(
                    platform="chatgpt",
                    query="How can AI agents pay for APIs?",
                    metadata={
                        "mode": "api_probe",
                        "source_hosts": [
                            "apiosk.com",
                            "synapsenetwork.xyz",
                            "apnews.com",
                        ],
                    },
                ),
                probe_row(
                    platform="chatgpt",
                    query="How can API providers earn from AI agents?",
                    metadata={
                        "mode": "api_probe",
                        "source_hosts": ["apiosk.com", "apnews.com"],
                    },
                ),
            ],
        )
    )

    diagnosis = diagnose_feed(records, source_path="probe.jsonl").model_dump()

    recommendations = diagnosis["recommended_source_host_executions"]
    by_surface = {item["surface"]: item for item in recommendations}
    assert by_surface["apiosk_com"]["draft_type"] == (
        "api_monetization_source_host_review"
    )
    assert by_surface["apiosk_com"]["priority"] == "p0"
    assert by_surface["apiosk_com"]["target_queries"] == [
        "How can AI agents pay for APIs?",
        "How can API providers earn from AI agents?",
    ]
    assert by_surface["synapsenetwork_xyz"]["draft_type"] == (
        "brand_collision_source_host_review"
    )
    assert "non-official Synapse collision" in by_surface["synapsenetwork_xyz"][
        "content_brief"
    ]
    assert by_surface["apnews.com"]["draft_type"] == "observed_source_host_review"
    assert by_surface["apnews.com"]["priority"] == "p0"
    assert "no dedicated playbook" in by_surface["apnews.com"]["rationale"]


def test_diagnosis_cli_writes_json_and_recommendations_jsonl(tmp_path: Path):
    probe_path = write_probe_jsonl(
        tmp_path,
        [
            probe_row(
                platform="chatgpt",
                query="ChatGPT MCP app for API payments",
                competitors=["x402"],
            ),
            probe_row(
                platform="gemini",
                query="AI agent paid API calls",
                competitors=["RapidAPI"],
            ),
        ],
    )
    output_path = tmp_path / "diagnosis.json"
    recommendations_path = tmp_path / "recommendations.jsonl"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/generate_ai_visibility_feed_diagnosis.py",
            str(probe_path),
            "--output",
            str(output_path),
            "--recommendations-output",
            str(recommendations_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["module_key"] == "ai_visibility_feed_diagnosis"
    assert payload["covered_platforms"] == ["chatgpt", "gemini"]
    rows = [
        json.loads(line)
        for line in recommendations_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows[0]["surface"] == "official_mcp_registry"
    assert rows[0]["evidence_role"] == "source_host_intent_not_external_citation"


def probe_row(
    *,
    platform: str,
    query: str = "MCP server for paid API calls",
    competitors: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    return {
        "query": query,
        "platform": platform,
        "feed_key": "mcp_paid_api_discovery",
        "run_group": "2026-06-06-after-prod",
        "answer_summary": "The answer did not mention Synapse Network.",
        "synapse_mentioned": False,
        "synapse_cited": False,
        "cited_urls": [],
        "competitor_mentions": competitors or [],
        "missing_facts": ["Synapse Network was not cited."],
        "next_action": "Add independent source-host citation evidence.",
        "metadata": metadata or {},
    }


def write_probe_jsonl(tmp_path: Path, payloads: list[dict]) -> Path:
    probe_path = tmp_path / "probe.jsonl"
    probe_path.write_text(
        "\n".join(json.dumps(payload) for payload in payloads),
        encoding="utf-8",
    )
    return probe_path
