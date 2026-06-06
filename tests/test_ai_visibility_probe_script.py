import json
import subprocess
import sys
import urllib.error
from pathlib import Path

from scripts.growth.record_ai_visibility_probe import (
    parse_json_or_jsonl,
    parse_probe_file,
    validate_records,
)
from scripts.growth.generate_ai_visibility_probe_template import (
    CANONICAL_HOMEPAGE,
    default_queries_for_feed,
    generate_records,
    official_source_urls_for_feed,
    parse_platforms,
)
from scripts.growth.ai_visibility_api_probe_records import (
    api_readiness_blocker_records,
)
from scripts.growth import run_ai_visibility_api_probe as api_probe


def test_parse_json_array_and_validate_external_probe(tmp_path: Path):
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(
        json.dumps(
            [
                {
                    "query": "AI agent payment API",
                    "platform": "chatgpt",
                    "answer_summary": "Synapse is cited.",
                    "synapse_mentioned": True,
                    "synapse_cited": True,
                    "cited_urls": ["https://www.synapse-network.ai/ai-agent-payments"],
                    "feed_key": "agent_payment_category_pages",
                    "run_group": "2026-06-18-after-docs-launch",
                    "evidence_url": "docs/archive/evidence/growth/chatgpt.png",
                }
            ]
        ),
        encoding="utf-8",
    )

    records = parse_probe_file(probe_path)

    assert records[0].platform == "chatgpt"
    assert validate_records(records) == []


def test_parse_jsonl_rows():
    rows = parse_json_or_jsonl(
        "\n".join(
            [
                json.dumps({"query": "AI agent payment API"}),
                json.dumps({"query": "Synapse Network vs x402"}),
            ]
        )
    )

    assert [row["query"] for row in rows] == [
        "AI agent payment API",
        "Synapse Network vs x402",
    ]


def test_validation_rejects_validation_platforms_and_missing_citation_evidence(
    tmp_path: Path,
):
    probe_path = tmp_path / "probe.jsonl"
    probe_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "query": "How can AI agents pay for APIs locally?",
                        "platform": "www_local_validation",
                        "feed_key": "agent_payment_category_pages",
                        "run_group": "2026-06-04-local",
                    }
                ),
                json.dumps(
                    {
                        "query": "AI agent payment API live crawl",
                        "platform": "www_live_validation",
                        "feed_key": "agent_payment_category_pages",
                        "run_group": "2026-06-04-live-predeploy",
                    }
                ),
                json.dumps(
                    {
                        "query": "Synapse Network vs x402",
                        "platform": "claude",
                        "synapse_mentioned": True,
                        "synapse_cited": True,
                        "feed_key": "agent_payment_category_pages",
                        "run_group": "2026-06-18-after-docs-launch",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    records = parse_probe_file(probe_path)
    errors = validate_records(records)

    assert "record 0: validation platform is not external probe evidence" in errors
    assert "record 1: validation platform is not external probe evidence" in errors
    assert "record 2: synapse_cited=true requires cited_urls or evidence_url" in errors


def test_validation_rejects_collision_domain_as_synapse_citation(tmp_path: Path):
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(
        json.dumps(
            {
                "query": "What is Synapse Network for AI agents?",
                "platform": "chatgpt",
                "answer_summary": "A result cites a brand-collision domain.",
                "synapse_mentioned": True,
                "synapse_cited": True,
                "cited_urls": ["https://www.synapsenetwork.xyz/"],
                "competitor_mentions": ["synapsenetwork.xyz"],
                "feed_key": "brand_disambiguation_www",
                "run_group": "2026-06-05-brand-collision",
            }
        ),
        encoding="utf-8",
    )

    records = parse_probe_file(probe_path)
    errors = validate_records(records)

    assert (
        "record 0: synapse_cited=true requires at least one official Synapse cited_url"
        in errors
    )


def test_cli_dry_run_outputs_summary(tmp_path: Path):
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(
        json.dumps(
            {
                "query": "MCP server for paid API calls",
                "platform": "grok",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-18-after-registry",
                "answer_summary": "No Synapse citation yet.",
                "synapse_mentioned": False,
                "synapse_cited": False,
                "next_action": "Feed registry listing evidence.",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/record_ai_visibility_probe.py",
            str(probe_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["target"] == "dry_run"
    assert payload["platforms"] == ["grok"]
    assert payload["feed_keys"] == ["mcp_paid_api_discovery"]


def test_generate_probe_template_defaults_validate(tmp_path: Path):
    records = generate_records(
        feed_key="agent_payment_category_pages",
        run_group="2026-06-18-baseline",
        platforms=["chatgpt", "claude", "grok"],
        queries=[
            "What is Synapse Network for AI agents?",
            "AI agent payment API",
            "How can AI agents pay for APIs?",
            "MCP server for paid API calls",
            "AI agent USDC settlement layer",
            "Synapse Network vs x402",
            "How can API providers earn from AI agents?",
        ],
        mode="baseline",
    )

    assert len(records) == 21
    probe_records = parse_probe_file(
        write_probe_jsonl(tmp_path, [record.__dict__ for record in records])
    )

    assert validate_records(probe_records) == []
    assert records[0].metadata["canonical_homepage"] == CANONICAL_HOMEPAGE
    assert records[0].metadata["platform_entry_url"] == "https://chatgpt.com/"
    assert records[0].metadata["question_to_ask"] == records[0].query
    assert "Capture a screenshot" in records[0].metadata["evidence_capture"]
    assert records[0].evidence_url.endswith(
        "2026-06-18-baseline/chatgpt-what-is-synapse-network-for-ai-agents.png"
    )


def test_generate_probe_template_custom_platform_and_query(tmp_path: Path):
    records = generate_records(
        feed_key="brand_disambiguation_www",
        run_group="2026-06-18-after-homepage",
        platforms=parse_platforms("chatgpt"),
        queries=["SynapseNetwork settlement layer for AI agents"],
        mode="after-feed",
    )
    probe_path = write_probe_jsonl(tmp_path, [record.__dict__ for record in records])

    parsed = parse_probe_file(probe_path)

    assert len(parsed) == 1
    assert parsed[0].platform == "chatgpt"
    assert parsed[0].feed_key == "brand_disambiguation_www"
    assert parsed[0].metadata["platform_entry_url"] == "https://chatgpt.com/"
    assert "compare against the previous run group" in parsed[0].next_action
    assert validate_records(parsed) == []


def test_generate_probe_template_defaults_to_feed_queries_and_sources(tmp_path: Path):
    records = generate_records(
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-18-after-registry",
        platforms=["chatgpt"],
        queries=default_queries_for_feed("mcp_paid_api_discovery"),
        mode="after-feed",
    )
    probe_path = write_probe_jsonl(tmp_path, [record.__dict__ for record in records])

    parsed = parse_probe_file(probe_path)

    assert [record.query for record in parsed] == [
        "MCP server for paid API calls",
        "ChatGPT MCP app for API payments",
        "Synapse vs paid MCP alternatives",
    ]
    source_urls = official_source_urls_for_feed("mcp_paid_api_discovery")
    assert "https://www.synapse-network.ai/" in source_urls
    assert "https://mcp.synapse-network.ai/mcp" in source_urls
    assert "https://docs.synapse-network.ai/mcp/paid-api-calls" in source_urls
    assert parsed[0].metadata["official_source_urls"] == source_urls
    assert validate_records(parsed) == []


def test_generate_probe_template_cli_writes_jsonl(tmp_path: Path):
    output_path = tmp_path / "probe-template.jsonl"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/generate_ai_visibility_probe_template.py",
            "--feed-key",
            "mcp_paid_api_discovery",
            "--run-group",
            "2026-06-18-after-registry",
            "--platforms",
            "grok",
            "--query",
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
    records = parse_probe_file(output_path)
    assert len(records) == 1
    assert records[0].platform == "grok"
    assert records[0].metadata["canonical_homepage"] == CANONICAL_HOMEPAGE
    assert validate_records(records) == []


def test_generate_probe_template_cli_defaults_to_feed_queries(tmp_path: Path):
    output_path = tmp_path / "probe-template.jsonl"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/generate_ai_visibility_probe_template.py",
            "--feed-key",
            "mcp_paid_api_discovery",
            "--run-group",
            "2026-06-18-after-registry",
            "--platforms",
            "chatgpt",
            "--output",
            str(output_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    records = parse_probe_file(output_path)
    assert [record.query for record in records] == [
        "MCP server for paid API calls",
        "ChatGPT MCP app for API payments",
        "Synapse vs paid MCP alternatives",
    ]
    assert records[0].metadata["official_source_urls"] == official_source_urls_for_feed(
        "mcp_paid_api_discovery"
    )
    assert validate_records(records) == []


def test_generate_probe_matrix_cli_writes_json(tmp_path: Path):
    output_path = tmp_path / "probe-matrix.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/generate_ai_visibility_probe_matrix.py",
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
    assert payload["module_key"] == "ai_visibility"
    assert payload["target_platforms"] == ["chatgpt", "claude", "grok"]
    assert payload["total"] == 9
    mcp_rows = [
        row for row in payload["rows"] if row["feed_key"] == "mcp_paid_api_discovery"
    ]
    assert {row["platform"] for row in mcp_rows} == {
        "chatgpt",
        "claude",
        "grok",
    }
    assert all(
        "record_ai_visibility_probe.py" in row["record_probe_command"]
        for row in mcp_rows
    )
    assert any(
        "https://mcp.synapse-network.ai/mcp" in row["official_source_urls"]
        for row in mcp_rows
    )


def test_validate_probe_matrix_cli_accepts_complete_scope(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    probe_path = tmp_path / "probe.jsonl"
    subprocess.run(
        [
            sys.executable,
            "scripts/growth/generate_ai_visibility_probe_matrix.py",
            "--output",
            str(matrix_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    row = next(
        item for item in matrix["rows"] if item["feed_key"] == "mcp_paid_api_discovery"
    )
    scoped_rows = [
        item
        for item in matrix["rows"]
        if item["feed_key"] == "mcp_paid_api_discovery"
        and item["run_group"] == row["run_group"]
    ]
    rows = [
        {
            "query": query,
            "platform": matrix_row["platform"],
            "feed_key": matrix_row["feed_key"],
            "run_group": matrix_row["run_group"],
            "answer_summary": "No Synapse citation yet.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "evidence_url": (
                f"{matrix_row['evidence_directory']}/"
                f"{matrix_row['platform']}-{query_index}.png"
            ),
        }
        for matrix_row in scoped_rows
        for query_index, query in enumerate(matrix_row["queries"])
    ]
    probe_path.write_text(
        "\n".join(json.dumps(item) for item in rows),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/validate_ai_visibility_probe_matrix.py",
            str(probe_path),
            "--matrix-file",
            str(matrix_path),
            "--feed-key",
            "mcp_paid_api_discovery",
            "--run-group",
            row["run_group"],
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["matched_count"] == sum(len(item["queries"]) for item in scoped_rows)
    assert payload["platforms"] == ["chatgpt", "claude", "grok"]


def test_validate_probe_matrix_cli_rejects_missing_matrix_rows(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    probe_path = tmp_path / "probe.jsonl"
    matrix = {
        "rows": [
            {
                "feed_key": "mcp_paid_api_discovery",
                "platform": "chatgpt",
                "status": "ready_to_probe",
                "run_group": "2026-06-18-mcp",
                "queries": [
                    "MCP server for paid API calls",
                    "ChatGPT MCP app for API payments",
                ],
                "blockers": [],
            }
        ]
    }
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    probe_path.write_text(
        json.dumps(
            {
                "query": "MCP server for paid API calls",
                "platform": "chatgpt",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-18-mcp",
                "answer_summary": "No Synapse citation yet.",
                "evidence_url": "docs/archive/evidence/growth/ai-visibility/chatgpt.png",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/validate_ai_visibility_probe_matrix.py",
            str(probe_path),
            "--matrix-file",
            str(matrix_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["missing_count"] == 1
    assert "ChatGPT MCP app for API payments" in payload["errors"][0]


def test_validate_probe_matrix_cli_requires_evidence_url(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    probe_path = tmp_path / "probe.json"
    matrix_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "feed_key": "mcp_paid_api_discovery",
                        "platform": "chatgpt",
                        "status": "ready_to_probe",
                        "run_group": "2026-06-18-mcp",
                        "queries": ["MCP server for paid API calls"],
                        "blockers": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    probe_path.write_text(
        json.dumps(
            {
                "query": "MCP server for paid API calls",
                "platform": "chatgpt",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-18-mcp",
                "answer_summary": "No Synapse citation yet.",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/validate_ai_visibility_probe_matrix.py",
            str(probe_path),
            "--matrix-file",
            str(matrix_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert (
        "record 0: evidence_url is required for matrix validation" in payload["errors"]
    )


def test_generate_feed_package_cli_writes_json(tmp_path: Path):
    output_path = tmp_path / "feed-package.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/generate_ai_visibility_feed_package.py",
            "--feed-key",
            "agent_payment_category_pages",
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
    assert payload["total"] == 1
    package = payload["items"][0]
    assert package["feed_key"] == "agent_payment_category_pages"
    assert package["canonical_domain"] == CANONICAL_HOMEPAGE
    assert (
        "--feed-key agent_payment_category_pages" in package["probe_template_command"]
    )
    assert {asset["surface"] for asset in package["publish_assets"]} >= {
        "www",
        "docs",
        "github",
    }


def test_generate_mcp_feed_package_includes_paid_api_docs(tmp_path: Path):
    output_path = tmp_path / "feed-package.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/generate_ai_visibility_feed_package.py",
            "--feed-key",
            "mcp_paid_api_discovery",
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
    package = payload["items"][0]
    assert package["feed_key"] == "mcp_paid_api_discovery"
    assert "https://docs.synapse-network.ai/mcp/paid-api-calls" in {
        asset["target"] for asset in package["publish_assets"]
    }
    assert CANONICAL_HOMEPAGE in {
        asset["target"] for asset in package["publish_assets"]
    }
    assert (
        "curl -fsS https://docs.synapse-network.ai/mcp/paid-api-calls"
        in (package["validation_commands"])
    )
    assert any(
        "https://www.synapse-network.ai/" in command
        for command in package["validation_commands"]
    )
    assert any(
        "MCP Server for Paid API Calls" in action
        for action in package["validation_commands"]
    )
    assert {strategy["platform"] for strategy in package["platform_strategies"]} == {
        "chatgpt",
        "claude",
        "grok",
    }
    chatgpt_strategy = next(
        strategy
        for strategy in package["platform_strategies"]
        if strategy["platform"] == "chatgpt"
    )
    assert "mcp_registry" in chatgpt_strategy["preferred_surfaces"]
    assert "ChatGPT MCP app for API payments" in chatgpt_strategy["probe_queries"]


def test_generate_docs_blueprint_cli_writes_json(tmp_path: Path):
    output_path = tmp_path / "docs-blueprint.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/generate_ai_visibility_docs_blueprint.py",
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
    assert payload["category"] == "AI Agent Payments"
    assert payload["canonical_domain"] == CANONICAL_HOMEPAGE
    assert payload["implementation_root"] == (
        "services/docs-front/content/docs/ai-agent-payments"
    )
    assert len(payload["pages"]) == 7
    assert payload["pages"][0]["slug"] == "index"
    assert "# AI Agent Payments" in payload["pages"][0]["mdx_skeleton"]


def test_generate_design_handoff_cli_writes_json(tmp_path: Path):
    output_path = tmp_path / "design-handoff.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/generate_ai_visibility_design_handoff.py",
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
    assert (
        payload["figma_file_name"] == "Synapse AI Agent Payments Docs - AI Visibility"
    )
    assert payload["source_tool"] == "Stitch"
    assert payload["target_tool"] == "Figma"
    assert len(payload["frames"]) == 3
    assert payload["frames"][0]["source_page_slug"] == "index"
    assert payload["canonical_domain"] == CANONICAL_HOMEPAGE


def test_api_probe_cli_readiness_does_not_require_execute(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/run_ai_visibility_api_probe.py",
            "--platforms",
            "chatgpt",
            "--query",
            "AI agent payment API",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
        env={"OPENAI_API_KEY": "test-openai-key"},
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["execute"] is False
    assert payload["platforms"] == ["chatgpt"]
    assert "test-openai-key" not in result.stdout


def test_api_probe_chatgpt_default_uses_broad_responses_model():
    assert api_probe.DEFAULT_MODELS["chatgpt"] == "gpt-4o-mini"


def test_api_probe_execute_missing_keys_fails_closed(tmp_path: Path):
    output_path = tmp_path / "probe.jsonl"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/run_ai_visibility_api_probe.py",
            "--platforms",
            "chatgpt,claude,grok",
            "--query",
            "AI agent payment API",
            "--output",
            str(output_path),
            "--execute",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
        env={},
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert {item["missing_env"] for item in payload["missing"]} == {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "XAI_API_KEY",
    }
    assert payload["record_count"] == 3
    assert output_path.exists()
    records = parse_probe_file(output_path)
    assert validate_records(records) == []
    assert {record.platform for record in records} == {"chatgpt", "claude", "grok"}
    assert all(record.metadata["mode"] == "api_probe_readiness_blocker" for record in records)
    assert all(record.synapse_mentioned is False for record in records)
    assert all(record.synapse_cited is False for record in records)
    assert "OPENAI_API_KEY" in records[0].missing_facts[0]


def test_api_readiness_blocker_records_are_valid():
    records = api_readiness_blocker_records(
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-www-homepage-live",
        missing=[
            {"platform": "chatgpt", "missing_env": "OPENAI_API_KEY"},
            {"platform": "claude", "missing_env": "ANTHROPIC_API_KEY"},
        ],
        query_count=2,
    )

    assert validate_records(records) == []
    assert [record.platform for record in records] == ["chatgpt", "claude"]
    assert records[0].query == "ChatGPT Claude Grok API probe readiness"
    assert records[0].metadata["mode"] == "api_probe_readiness_blocker"
    assert records[0].metadata["blocked_query_count"] == "2"
    assert "OPENAI_API_KEY" in records[0].answer_summary
    assert "https://www.synapse-network.ai/" in records[0].metadata[
        "official_source_urls"
    ]


def test_run_api_probes_generates_valid_records(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")

    def fake_call_platform(platform: str, query: str):
        assert query == "AI agent payment API"
        return {
            "summary": f"{platform} mentions Synapse Network and cites docs.",
            "synapse_mentioned": True,
            "synapse_cited": True,
            "cited_urls": ["https://www.synapse-network.ai/ai-agent-payments"],
            "source_urls": [
                "https://www.synapse-network.ai/ai-agent-payments",
                "https://docs.synapse-network.ai/ai-agent-payments",
            ],
            "competitor_mentions": ["x402"],
            "missing_facts": [],
            "next_action": "Compare against previous run group.",
            "result_rank": 1,
            "model": f"{platform}-model",
            "request_id": f"{platform}-request",
        }

    monkeypatch.setattr(api_probe, "call_platform", fake_call_platform)

    records = api_probe.run_api_probes(
        feed_key="agent_payment_category_pages",
        run_group="2026-06-18-api-probe",
        platforms=["chatgpt", "claude", "grok"],
        queries=["AI agent payment API"],
    )

    assert len(records) == 3
    assert validate_records(records) == []
    assert records[0].evidence_url == ""
    assert records[0].metadata["mode"] == "api_probe"
    assert "api_request_id" in records[0].metadata["evidence_capture"]
    assert records[0].metadata["source_url_count"] == "2"
    assert records[0].metadata["synapse_cited_url_count"] == "1"


def test_post_json_redacts_secret_values_on_http_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai-value")

    class FakeError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                "https://api.openai.com/v1/responses",
                401,
                "Unauthorized",
                hdrs=None,
                fp=None,
            )

        def read(self):
            return b'{"error":"bad key secret-openai-value"}'

    def fake_urlopen(*_args, **_kwargs):
        raise FakeError()

    monkeypatch.setattr(api_probe.urllib.request, "urlopen", fake_urlopen)

    try:
        api_probe.post_json(
            api_probe.OPENAI_RESPONSES_URL,
            {"model": "test"},
            {"Authorization": "Bearer secret-openai-value"},
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("HTTPError should raise RuntimeError")

    assert "secret-openai-value" not in message
    assert "[REDACTED]" in message


def write_probe_jsonl(tmp_path: Path, payloads: list[dict]) -> Path:
    probe_path = tmp_path / "generated.jsonl"
    probe_path.write_text(
        "\n".join(json.dumps(payload) for payload in payloads),
        encoding="utf-8",
    )
    return probe_path
