import json
import subprocess
import sys
from pathlib import Path

from scripts.growth.record_ai_visibility_source_host_execution import (
    build_source_host_evidence,
)


def test_source_host_execution_evidence_marks_live_verified():
    evidence = build_source_host_evidence(
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-after-github-source-host-main",
        surface="github_readme",
        source_url="https://raw.githubusercontent.com/example/repo/main/README.md",
        content=(
            "Answer Engine Source Block for SynapseNetwork MCP Server. "
            "Includes RapidAPI, Project Synapse, discover_services, "
            "invoke_and_pay, and get_receipt."
        ),
        required_terms=[
            "Answer Engine Source Block",
            "RapidAPI",
            "Project Synapse",
            "discover_services",
            "invoke_and_pay",
            "get_receipt",
        ],
        target_platforms=["chatgpt", "claude", "grok", "gemini"],
        target_queries=["MCP server for paid API calls"],
    )

    assert evidence.status == "live_verified"
    assert evidence.evidence_role == "source_host_live_evidence_not_external_citation"
    assert evidence.missing_terms == []
    assert "after-source-host" in evidence.next_probe_command


def test_source_host_execution_evidence_fails_closed_on_missing_terms():
    evidence = build_source_host_evidence(
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-after-github-source-host-main",
        surface="github_readme",
        source_url="https://raw.githubusercontent.com/example/repo/main/README.md",
        content="SynapseNetwork MCP Server",
        required_terms=["RapidAPI", "Project Synapse"],
        target_platforms=["chatgpt"],
        target_queries=[],
    )

    assert evidence.status == "missing_required_terms"
    assert evidence.matched_terms == []
    assert evidence.missing_terms == ["RapidAPI", "Project Synapse"]


def test_source_host_execution_cli_writes_json(tmp_path: Path):
    source_path = tmp_path / "README.md"
    source_path.write_text(
        "SynapseNetwork MCP Server with Answer Engine Source Block and RapidAPI.",
        encoding="utf-8",
    )
    output_path = tmp_path / "evidence.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/record_ai_visibility_source_host_execution.py",
            "--feed-key",
            "mcp_paid_api_discovery",
            "--run-group",
            "2026-06-06-after-github-source-host-main",
            "--surface",
            "github_readme",
            "--source-url",
            source_path.as_uri(),
            "--required-term",
            "Answer Engine Source Block",
            "--required-term",
            "RapidAPI",
            "--target-platform",
            "chatgpt",
            "--target-query",
            "MCP server for paid API calls",
            "--output",
            str(output_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["module_key"] == "ai_visibility_source_host_execution"
    assert payload["status"] == "live_verified"
    assert payload["surface"] == "github_readme"
