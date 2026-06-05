import json
import subprocess
import sys
from pathlib import Path

from scripts.growth import ai_visibility_cli
from scripts.growth import (
    generate_ai_visibility_external_probe_gate as external_probe_gate_cli,
)
from scripts.growth import (
    generate_ai_visibility_probe_template as probe_template_cli,
)
from scripts.growth import generate_ai_visibility_live_readiness as live_readiness_cli
from scripts.growth import generate_ai_visibility_operator_brief as operator_brief
from scripts.growth import (
    generate_ai_visibility_release_unblock_plan as release_unblock_plan,
)
from scripts.growth import summarize_ai_visibility_cycle as cycle_summary
from server.services.growth import (
    ai_visibility_release_unblock as release_unblock_service,
)


def test_ai_visibility_cli_helpers_cover_payload_output_and_failure(
    tmp_path: Path,
    capsys,
):
    class ModelDumpPayload:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {"source": "model_dump"}

    class DictPayload:
        def dict(self):
            return {"source": "dict"}

    assert ai_visibility_cli.pydantic_payload(ModelDumpPayload()) == {
        "source": "model_dump"
    }
    assert ai_visibility_cli.pydantic_payload(DictPayload()) == {"source": "dict"}

    output_path = tmp_path / "nested" / "payload.json"
    ai_visibility_cli.write_json_payload({"status": "ok"}, str(output_path))
    assert json.loads(output_path.read_text(encoding="utf-8")) == {"status": "ok"}

    ai_visibility_cli.write_text_or_stdout("plain", output=None)
    assert capsys.readouterr().out.strip() == "plain"

    ai_visibility_cli.emit_failure(ValueError("bad input"))
    failure = json.loads(capsys.readouterr().err)
    assert failure == {
        "status": "failed",
        "error_type": "ValueError",
        "error_message": "bad input",
    }


def test_probe_template_includes_official_sources_and_collision_domains():
    rows = probe_template_cli.generate_records(
        feed_key="brand_disambiguation_www",
        run_group="2026-06-05-www-canonical-manual",
        platforms=["chatgpt"],
        queries=["What is Synapse Network for AI agents?"],
        mode="after-feed",
    )

    assert len(rows) == 1
    metadata = rows[0].metadata
    assert metadata["canonical_homepage"] == "https://www.synapse-network.ai/"
    assert "https://www.synapse-network.ai/" in metadata["official_source_urls"]
    assert "https://github.com/SynapseNetworkAI" in metadata["official_source_urls"]
    assert "https://www.synapse-network.ai/llms.txt" in metadata[
        "official_source_urls"
    ]
    assert "synapsenetwork.xyz" in metadata["known_collision_domains"]
    assert "synapse.network" in metadata["known_collision_domains"]
    assert "known collision domains" in metadata["evidence_capture"]
    assert "Success requires" in metadata["success_decision_rule"]


def test_cycle_summary_marks_failed_feed_validation_blocked(tmp_path: Path):
    probe_path = tmp_path / "feed-validation.jsonl"
    probe_path.write_text(
        json.dumps(
            {
                "query": "Remote MCP live readiness",
                "platform": "mcp_live_validation",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-05-mcp-paid-api-prod-current",
                "synapse_mentioned": False,
                "synapse_cited": False,
                "missing_facts": [
                    "Docs /mcp/paid-api-calls page must be live.",
                    "www llms.txt must include the MCP paid API calls guide.",
                ],
                "next_action": "Publish /mcp/paid-api-calls before external probes.",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/summarize_ai_visibility_cycle.py",
            str(probe_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "feed_blocked"
    assert payload["feed_key"] == "mcp_paid_api_discovery"
    assert payload["local_validation_count"] == 1
    assert payload["external_probe_count"] == 0
    assert "Docs /mcp/paid-api-calls page must be live." in payload["blockers"]
    assert "Fix live feed blockers" in payload["next_actions"][-1]
    assert {strategy["platform"] for strategy in payload["platform_strategies"]} == {
        "chatgpt",
        "claude",
        "grok",
    }
    assert any(
        "Remote MCP custom app" in strategy["feed_focus"]
        for strategy in payload["platform_strategies"]
    )
    assert (
        "run_ai_visibility_feed_validation.py" in payload["commands"]["feed_validation"]
    )
    assert "--query" not in payload["commands"]["api_readiness"]


def test_cycle_summary_blocks_when_local_validation_has_missing_facts(tmp_path: Path):
    probe_path = tmp_path / "target-repo-ready-prod-blocked.jsonl"
    probe_path.write_text(
        json.dumps(
            {
                "query": "Synapse-Network target repo AI visibility implementation audit",
                "platform": "target_repo_validation",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-05-target-repo-ai-visibility-assets-ready",
                "answer_summary": "Source implementation is present, but prod is not live.",
                "synapse_mentioned": True,
                "synapse_cited": True,
                "cited_urls": [
                    "https://www.synapse-network.ai/",
                    "https://docs.synapse-network.ai/mcp/paid-api-calls",
                ],
                "missing_facts": [
                    "Production https://docs.synapse-network.ai/mcp/paid-api-calls is still 404.",
                    "GCloud auth still fails non-interactively.",
                ],
                "next_action": "Refresh GCloud auth and publish before external probes.",
            }
        ),
        encoding="utf-8",
    )

    records = cycle_summary.parse_probe_file(probe_path)
    payload = cycle_summary.summarize_cycle(records, source_path=str(probe_path))

    assert payload["status"] == "feed_blocked"
    assert payload["local_validation_count"] == 1
    assert payload["external_probe_count"] == 0
    assert (
        "Production https://docs.synapse-network.ai/mcp/paid-api-calls is still 404."
        in payload["blockers"]
    )
    assert "GCloud auth still fails non-interactively." in payload["blockers"]
    assert "Fix live feed blockers" in payload["next_actions"][-1]


def test_cycle_summary_detects_external_citation(tmp_path: Path):
    probe_path = tmp_path / "external.jsonl"
    probe_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "query": "MCP server for paid API calls",
                        "platform": platform,
                        "feed_key": "mcp_paid_api_discovery",
                        "run_group": "2026-06-18-after-registry-feed",
                        "answer_summary": f"{platform} result.",
                        "synapse_mentioned": True,
                        "synapse_cited": platform == "chatgpt",
                        "cited_urls": (
                            ["https://docs.synapse-network.ai/mcp/paid-api-calls"]
                            if platform == "chatgpt"
                            else []
                        ),
                    }
                )
                for platform in ("chatgpt", "claude", "grok")
            ]
        ),
        encoding="utf-8",
    )

    records = cycle_summary.parse_probe_file(probe_path)
    payload = cycle_summary.summarize_cycle(
        records,
        source_path=str(probe_path),
    )

    assert payload["status"] == "citation_observed"
    assert payload["covered_platforms"] == ["chatgpt", "claude", "grok"]
    assert payload["external_mentioned_count"] == 3
    assert payload["external_cited_count"] == 1
    assert payload["missing_platforms"] == []
    assert {strategy["platform"] for strategy in payload["platform_strategies"]} == {
        "chatgpt",
        "claude",
        "grok",
    }
    assert (
        "comparisons?feed_key=mcp_paid_api_discovery" in payload["commands"]["compare"]
    )
    assert "--query" not in payload["commands"]["api_readiness"]


def test_cycle_summary_treats_api_readiness_rows_as_blockers(tmp_path: Path):
    probe_path = tmp_path / "api-blockers.jsonl"
    probe_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "query": "External API probe readiness",
                        "platform": platform,
                        "feed_key": "mcp_paid_api_discovery",
                        "run_group": "2026-06-06-api-blockers",
                        "answer_summary": f"{platform} API probe blocked.",
                        "synapse_mentioned": False,
                        "synapse_cited": False,
                        "missing_facts": [
                            f"{env_key} missing; no paid {platform} probe executed."
                        ],
                        "next_action": (
                            f"Configure {env_key} and rerun "
                            "run_ai_visibility_api_probe.py with --execute."
                        ),
                        "metadata": {
                            "mode": "api_probe_readiness_blocker",
                            "provider_env_key": env_key,
                        },
                    }
                )
                for platform, env_key in (
                    ("chatgpt", "OPENAI_API_KEY"),
                    ("claude", "ANTHROPIC_API_KEY"),
                    ("grok", "XAI_API_KEY"),
                )
            ]
        ),
        encoding="utf-8",
    )

    records = cycle_summary.parse_probe_file(probe_path)
    payload = cycle_summary.summarize_cycle(records, source_path=str(probe_path))

    assert payload["status"] == "external_probe_blocked"
    assert payload["external_probe_count"] == 0
    assert payload["api_probe_blocker_count"] == 3
    assert payload["external_mentioned_count"] == 0
    assert payload["external_cited_count"] == 0
    assert payload["covered_platforms"] == []
    assert payload["missing_platforms"] == ["chatgpt", "claude", "grok"]
    assert "OPENAI_API_KEY missing; no paid chatgpt probe executed." in payload[
        "blockers"
    ]
    assert (
        "External API probes are blocked by missing provider credentials."
        in payload["blockers"]
    )
    assert (
        "Configure missing answer-engine API keys" in payload["next_actions"][-1]
    )


def test_cycle_summary_surfaces_explicit_crawler_policy_improvement(tmp_path: Path):
    probe_path = tmp_path / "crawler-policy.jsonl"
    probe_path.write_text(
        json.dumps(
            {
                "query": "Brand disambiguation live feed readiness",
                "platform": "www_live_validation",
                "feed_key": "brand_disambiguation_www",
                "run_group": "2026-06-05-brand-crawler-policy",
                "answer_summary": "Live feed validation passed.",
                "synapse_mentioned": True,
                "synapse_cited": True,
                "cited_urls": ["https://www.synapse-network.ai/robots.txt"],
                "metadata": {
                    "ai_crawler_policy": {
                        "missing_explicit_crawlers": [
                            "OAI-SearchBot",
                            "Claude-SearchBot",
                        ],
                        "blocked_crawlers": [],
                        "wildcard_allows_public": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    records = cycle_summary.parse_probe_file(probe_path)
    payload = cycle_summary.summarize_cycle(records, source_path=str(probe_path))

    assert payload["status"] == "ready_for_external_probe"
    assert payload["feed_improvements"] == [
        "Make robots.txt crawler policy explicit for answer engines: OAI-SearchBot, Claude-SearchBot."
    ]
    assert payload["feed_improvements"][0] in payload["next_actions"]


def test_cycle_summary_compares_against_previous_probe_file(tmp_path: Path):
    previous_path = tmp_path / "baseline.jsonl"
    current_path = tmp_path / "after.jsonl"
    previous_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "query": "MCP server for paid API calls",
                        "platform": platform,
                        "feed_key": "mcp_paid_api_discovery",
                        "run_group": "2026-06-04-baseline",
                        "answer_summary": f"{platform} baseline.",
                        "synapse_mentioned": platform == "chatgpt",
                        "synapse_cited": False,
                    }
                )
                for platform in ("chatgpt", "claude", "grok")
            ]
        ),
        encoding="utf-8",
    )
    current_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "query": "MCP server for paid API calls",
                        "platform": platform,
                        "feed_key": "mcp_paid_api_discovery",
                        "run_group": "2026-06-18-after-feed",
                        "answer_summary": f"{platform} after.",
                        "synapse_mentioned": True,
                        "synapse_cited": platform in {"chatgpt", "claude"},
                        "cited_urls": (
                            ["https://docs.synapse-network.ai/mcp/paid-api-calls"]
                            if platform in {"chatgpt", "claude"}
                            else []
                        ),
                    }
                )
                for platform in ("chatgpt", "claude", "grok")
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/summarize_ai_visibility_cycle.py",
            str(current_path),
            "--previous",
            str(previous_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "citation_observed"
    assert payload["comparison"]["previous_external_probe_count"] == 3
    assert payload["comparison"]["previous_mentioned_count"] == 1
    assert payload["comparison"]["previous_cited_count"] == 0
    assert payload["comparison"]["mentioned_delta"] == 2
    assert payload["comparison"]["cited_delta"] == 2
    assert payload["comparison"]["comparison_status"] == "improved"


def test_operator_brief_renders_executable_mcp_package(tmp_path: Path):
    summary_path = tmp_path / "cycle-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "blockers": [
                    "Production docs page https://docs.synapse-network.ai/mcp/paid-api-calls is not live yet."
                ],
                "next_actions": ["Publish MCP paid API docs and www llms feed."],
                "commands": {
                    "api_readiness": (
                        "python scripts/growth/run_ai_visibility_api_probe.py "
                        "--feed-key mcp_paid_api_discovery "
                        "--run-group 2026-06-05-weekly "
                        "--platforms chatgpt,claude,grok"
                    )
                },
            }
        ),
        encoding="utf-8",
    )

    brief = operator_brief.render_operator_brief(
        feed_key="mcp_paid_api_discovery",
        cycle_summary_path=str(summary_path),
    )

    assert "# AI Visibility Operator Brief: mcp_paid_api_discovery" in brief
    assert (
        "Production docs page https://docs.synapse-network.ai/mcp/paid-api-calls"
        in brief
    )
    assert "AI Agent Payments Docs Landing" in brief
    assert "Synapse Network is a payment and settlement layer" in brief
    assert "### chatgpt" in brief
    assert "--platforms chatgpt,claude,grok" in brief
    assert "--query" not in brief
    assert (
        "python scripts/growth/run_ai_visibility_api_probe.py "
        "--feed-key mcp_paid_api_discovery "
        "--run-group 2026-06-05-weekly "
        "--platforms chatgpt,claude,grok --execute"
    ) in brief


def test_release_unblock_plan_generates_safe_release_commands():
    payload = release_unblock_plan.build_release_unblock_plan(
        target_commit=release_unblock_plan.DEFAULT_TARGET_COMMIT,
        actor="codex/test-ai-visibility",
    )
    rendered = json.dumps(payload)

    assert payload["status"] == "blocked_until_gcloud_auth"
    assert payload["official_homepage"] == "https://www.synapse-network.ai/"
    assert payload["target_commit_sha"] == release_unblock_plan.DEFAULT_TARGET_COMMIT
    assert payload["source_pr"]["number"] == 214
    assert payload["source_pr"]["state"] == "MERGED"
    assert {item["number"] for item in payload["source_prs"]} == {
        203,
        204,
        212,
        213,
        214,
    }
    assert payload["deployment_gaps"][0]["service_key"] == "docs-front"
    assert payload["predeploy_evidence"]["status"] == (
        "target_branch_ready_live_prod_blocked"
    )
    assert payload["deploy_readiness_status"] == (
        "ready_for_release_runner_after_gcloud_auth"
    )
    assert any(
        fact == "Official homepage canonical is https://www.synapse-network.ai/."
        for fact in payload["confirmed_facts"]
    )
    assert payload["known_blockers"] == [
        "GCloud auth fails non-interactively until a human runs gcloud auth login.",
    ]
    assert set(payload["services"]) == {"docs-front", "user-front"}
    assert "gcloud auth login" in rendered
    assert "X-Growing-Agent-Deploy-Token" in rendered
    assert "scripts/local/run_deploy_worker.py" in rendered
    assert "/api/releases/tasks" in rendered
    assert "deploy-staging" in rendered
    assert "confirm_phrase" in rendered
    assert "YES" in rendered
    assert "https://www.synapse-network.ai/llms.txt" in rendered
    assert "https://docs.synapse-network.ai/mcp/paid-api-calls" in rendered
    commands = [
        command
        for group in payload["command_groups"]
        for command in group.get("commands", [])
    ]
    assert not any(
        command.strip().startswith("gcloud run deploy") for command in commands
    )
    assert "OPS_AGENT_DEPLOY_API_TOKEN=" not in rendered


def test_release_unblock_plan_blocks_stale_target_commit():
    payload = release_unblock_plan.build_release_unblock_plan(
        target_commit="d8b5371e11fea2d962dcc656b9b8d08d0c1379d9",
        actor="codex/test-ai-visibility",
    )

    assert payload["status"] == "blocked_until_target_commit_matches"
    assert payload["deploy_readiness_status"] == "blocked_until_target_commit_matches"
    assert any(
        "does not match current predeploy evidence commit" in blocker
        for blocker in payload["known_blockers"]
    )


def test_release_unblock_plan_predeploy_evidence_fail_closed(monkeypatch, tmp_path: Path):
    missing_path = tmp_path / "missing-predeploy.json"
    monkeypatch.setattr(
        release_unblock_service,
        "PREDEPLOY_EVIDENCE_PATH",
        str(missing_path),
    )

    missing = release_unblock_service._load_predeploy_evidence()

    assert missing["status"] == "missing"
    assert "has not been generated" in missing["summary"]


def test_release_unblock_plan_invalid_predeploy_evidence_fail_closed(
    monkeypatch, tmp_path: Path
):
    invalid_path = tmp_path / "invalid-predeploy.json"
    invalid_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(
        release_unblock_service,
        "PREDEPLOY_EVIDENCE_PATH",
        str(invalid_path),
    )

    invalid = release_unblock_service._load_predeploy_evidence()

    assert invalid["status"] == "invalid_json"
    assert "invalid" in invalid["summary"].lower()


def test_release_unblock_plan_cli_writes_json(tmp_path: Path):
    output_path = tmp_path / "release-unblock-plan.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/generate_ai_visibility_release_unblock_plan.py",
            "--target-commit",
            release_unblock_plan.DEFAULT_TARGET_COMMIT,
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
    assert payload["environment_defaults"]["ops_base_url"] == "http://localhost:9700"
    assert payload["source_pr"]["number"] == 214
    assert {item["number"] for item in payload["source_prs"]} == {
        203,
        204,
        212,
        213,
        214,
    }
    assert payload["predeploy_evidence"]["status"] == (
        "target_branch_ready_live_prod_blocked"
    )
    assert payload["deploy_readiness_status"] == (
        "ready_for_release_runner_after_gcloud_auth"
    )
    assert any(
        group["key"] == "production_validation" for group in payload["command_groups"]
    )


def test_live_readiness_cli_writes_json(monkeypatch, tmp_path: Path):
    output_path = tmp_path / "live-readiness.json"

    class FakeReadiness:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {
                "module_key": "ai_visibility",
                "status": "blocked",
                "run_group": "2026-06-05-live-readiness",
                "canonical_homepage": "https://www.synapse-network.ai/",
                "ready_count": 0,
                "blocked_count": 1,
                "validation_command": (
                    "python scripts/growth/run_ai_visibility_feed_validation.py "
                    "--feed-key mcp_paid_api_discovery"
                ),
                "apply_command": (
                    "python scripts/growth/record_ai_visibility_probe.py "
                    "docs/archive/evidence/growth/ai-visibility/live.jsonl "
                    "--allow-local-validation --apply"
                ),
                "items": [
                    {
                        "feed_key": "mcp_paid_api_discovery",
                        "status": "blocked",
                        "missing_facts": [
                            "Docs /mcp/paid-api-calls page must be live."
                        ],
                    }
                ],
                "total": 1,
            }

    monkeypatch.setattr(
        live_readiness_cli,
        "ai_visibility_live_readiness",
        lambda **_: FakeReadiness(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_live_readiness.py",
            "--feed-key",
            "mcp_paid_api_discovery",
            "--output",
            str(output_path),
        ],
    )

    assert live_readiness_cli.main() == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["canonical_homepage"] == "https://www.synapse-network.ai/"
    assert "run_ai_visibility_feed_validation.py" in payload["validation_command"]
    assert payload["items"][0]["feed_key"] == "mcp_paid_api_discovery"


def test_external_probe_gate_cli_writes_redacted_json(monkeypatch, tmp_path: Path):
    output_path = tmp_path / "external-probe-gate.json"

    class FakeGate:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {
                "module_key": "ai_visibility",
                "feed_key": "brand_disambiguation_www",
                "run_group": "2026-06-05-brand-external",
                "status": "ready_for_partial_external_probes",
                "ready_to_execute": False,
                "partial_ready_to_execute": True,
                "manual_ready_to_execute": True,
                "feed_ready": True,
                "api_keys_ready": False,
                "target_platforms": ["chatgpt", "claude", "grok"],
                "ready_platforms": ["chatgpt"],
                "missing_platforms": ["claude", "grok"],
                "provider_readiness": [
                    {
                        "platform": "chatgpt",
                        "env_key": "OPENAI_API_KEY",
                        "configured": True,
                    },
                    {
                        "platform": "claude",
                        "env_key": "ANTHROPIC_API_KEY",
                        "configured": False,
                    },
                ],
                "blockers": ["claude missing ANTHROPIC_API_KEY."],
                "feed_validation_command": (
                    "python scripts/growth/run_ai_visibility_feed_validation.py"
                ),
                "record_readiness_command": (
                    "python scripts/growth/record_ai_visibility_probe.py "
                    "docs/archive/evidence/growth/ai-visibility/live.jsonl "
                    "--allow-local-validation --apply"
                ),
                "manual_probe_template_command": (
                    "python scripts/growth/generate_ai_visibility_probe_template.py "
                    "--feed-key brand_disambiguation_www "
                    "--platforms chatgpt,claude,grok --mode after-feed"
                ),
                "api_readiness_command": (
                    "python scripts/growth/run_ai_visibility_api_probe.py "
                    "--feed-key brand_disambiguation_www "
                    "--platforms chatgpt,claude,grok"
                ),
                "api_execute_command": (
                    "python scripts/growth/run_ai_visibility_api_probe.py "
                    "--feed-key brand_disambiguation_www "
                    "--platforms chatgpt,claude,grok --execute"
                ),
                "partial_api_readiness_command": (
                    "python scripts/growth/run_ai_visibility_api_probe.py "
                    "--feed-key brand_disambiguation_www --platforms chatgpt"
                ),
                "partial_api_execute_command": (
                    "python scripts/growth/run_ai_visibility_api_probe.py "
                    "--feed-key brand_disambiguation_www --platforms chatgpt "
                    "--execute"
                ),
                "record_probe_command": (
                    "python scripts/growth/record_ai_visibility_probe.py "
                    "docs/archive/evidence/growth/ai-visibility/external.jsonl --apply"
                ),
                "compare_command": (
                    "curl -fsS 'http://localhost:9700/api/growth/ai-visibility/"
                    "comparisons?feed_key=brand_disambiguation_www' | python -m json.tool"
                ),
            }

    monkeypatch.setattr(
        external_probe_gate_cli,
        "ai_visibility_external_probe_gate",
        lambda **_: FakeGate(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_external_probe_gate.py",
            "--feed-key",
            "brand_disambiguation_www",
            "--run-group",
            "2026-06-05-brand-external",
            "--output",
            str(output_path),
        ],
    )

    assert external_probe_gate_cli.main() == 0
    rendered = output_path.read_text(encoding="utf-8")
    payload = json.loads(rendered)
    assert payload["status"] == "ready_for_partial_external_probes"
    assert payload["ready_platforms"] == ["chatgpt"]
    assert payload["manual_ready_to_execute"] is True
    assert (
        "generate_ai_visibility_probe_template.py"
        in payload["manual_probe_template_command"]
    )
    assert "OPENAI_API_KEY" in rendered
    assert "run_ai_visibility_api_probe.py" in payload["api_readiness_command"]
    assert "sk-test" not in rendered


def test_generate_optimization_brief_cli_writes_markdown(tmp_path: Path):
    output_path = tmp_path / "optimization-brief.md"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/generate_ai_visibility_optimization_brief.py",
            "--run-group",
            "2026-06-05-operator-brief",
            "--output",
            str(output_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    body = output_path.read_text(encoding="utf-8")
    assert "# Synapse AI Visibility Optimization Brief" in body
    assert "Official homepage: https://www.synapse-network.ai/" in body
    assert "## Feed Cycle Matrix" in body
    assert "mcp_paid_api_discovery" in body
