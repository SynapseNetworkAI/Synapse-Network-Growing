from pathlib import Path
from types import SimpleNamespace

from scripts.growth import generate_ai_visibility_handoff_bundle as handoff_cli
from server.services.growth import ai_visibility_handoff_bundle as handoff_service
from server.routers import growth_ai_visibility as growth_ai_visibility_router


def test_generate_handoff_bundle_writes_all_operator_files(monkeypatch, tmp_path: Path):
    output_dir = tmp_path / "handoff"

    monkeypatch.setattr(
        handoff_service,
        "build_snapshot",
        lambda **_: {
            "status": "blocked",
            "blockers": ["GCloud auth fails non-interactively."],
            "next_actions": ["Run gcloud auth login."],
        },
    )
    monkeypatch.setattr(
        handoff_service,
        "ai_visibility_live_readiness",
        lambda **_: FakeLiveReadiness(),
    )
    monkeypatch.setattr(
        handoff_service,
        "ai_visibility_external_probe_gate",
        lambda **_: FakeExternalGate(),
    )
    monkeypatch.setattr(
        handoff_service,
        "ai_visibility_optimization_brief",
        lambda *_args, **_kwargs: SimpleNamespace(
            markdown="# Synapse AI Visibility Optimization Brief\n"
        ),
    )
    monkeypatch.setattr(
        handoff_service,
        "ai_visibility_next_cycle",
        lambda *_args, **_kwargs: FakeNextCycle(),
    )

    payloads = handoff_service.build_handoff_payloads(
        output_dir=output_dir,
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-05-handoff",
        target_commit="d8b5371e11fea2d962dcc656b9b8d08d0c1379d9",
        actor="codex/test",
        db=object(),
    )
    manifest = handoff_cli.write_handoff_payloads(payloads)

    assert manifest["bundle_type"] == "operator_handoff"
    assert manifest["status"] == "blocked"
    assert manifest["official_homepage"] == "https://www.synapse-network.ai/"
    assert manifest["ready_platforms"] == ["chatgpt", "claude"]
    assert manifest["missing_platforms"] == ["grok"]
    assert "GCloud auth fails non-interactively." in manifest["blockers"]
    assert "Docs /mcp/paid-api-calls page must be live." in manifest["blockers"]
    assert "--platforms chatgpt,claude" in manifest["commands"]["partial_api_readiness"]
    assert (
        "generate_ai_visibility_probe_matrix.py" in manifest["commands"]["probe_matrix"]
    )
    assert (
        "validate_ai_visibility_probe_matrix.py"
        in manifest["commands"]["validate_matrix"]
    )
    assert "summarize_ai_visibility_cycle.py" in manifest["commands"]["cycle_summary"]
    assert (
        "generate_ai_visibility_operator_brief.py"
        in manifest["commands"]["operator_brief"]
    )
    for filename in (
        "manifest.json",
        "release-snapshot.json",
        "live-readiness.json",
        "external-probe-gate.json",
        "next-cycle.json",
        "operator-brief.md",
    ):
        assert (output_dir / filename).exists()
    assert "# Synapse AI Visibility Optimization Brief" in (
        output_dir / "operator-brief.md"
    ).read_text(encoding="utf-8")


def test_growth_ai_visibility_handoff_bundle_api(monkeypatch, synced_client):
    monkeypatch.setattr(
        growth_ai_visibility_router.ai_visibility_handoff_bundle,
        "build_handoff_payloads",
        lambda **_: {
            "manifest": {
                "module_key": "ai_visibility",
                "bundle_type": "operator_handoff",
                "generated_at": "2026-06-05T00:00:00Z",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-05-current",
                "target_commit_sha": "d8b5371e11fea2d962dcc656b9b8d08d0c1379d9",
                "official_homepage": "https://www.synapse-network.ai/",
                "status": "blocked",
                "release_status": "blocked",
                "live_readiness_status": "blocked",
                "external_probe_gate_status": "blocked_until_feed_ready",
                "ready_platforms": ["chatgpt", "claude"],
                "missing_platforms": ["grok"],
                "blockers": ["Docs /mcp/paid-api-calls page must be live."],
                "next_actions": ["Run gcloud auth login."],
                "files": {"manifest": "docs/archive/evidence/manifest.json"},
                "commands": {
                    "rerun_handoff": (
                        "python scripts/growth/generate_ai_visibility_handoff_bundle.py"
                    )
                },
            }
        },
    )

    response = synced_client.get(
        "/api/growth/ai-visibility/handoff-bundle"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-05-current"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["bundle_type"] == "operator_handoff"
    assert payload["official_homepage"] == "https://www.synapse-network.ai/"
    assert payload["external_probe_gate_status"] == "blocked_until_feed_ready"
    assert payload["ready_platforms"] == ["chatgpt", "claude"]
    assert payload["missing_platforms"] == ["grok"]


class FakeLiveReadiness:
    def model_dump(self, mode: str):  # noqa: ARG002
        return {
            "status": "blocked",
            "validation_command": (
                "python scripts/growth/run_ai_visibility_feed_validation.py "
                "--feed-key mcp_paid_api_discovery"
            ),
            "apply_command": (
                "python scripts/growth/record_ai_visibility_probe.py "
                "readiness.jsonl --allow-local-validation --apply"
            ),
            "items": [
                {
                    "feed_key": "mcp_paid_api_discovery",
                    "missing_facts": [
                        "Docs /mcp/paid-api-calls page must be live.",
                    ],
                }
            ],
        }


class FakeExternalGate:
    def model_dump(self, mode: str):  # noqa: ARG002
        return {
            "status": "ready_for_partial_external_probes",
            "ready_to_execute": False,
            "partial_ready_to_execute": True,
            "ready_platforms": ["chatgpt", "claude"],
            "missing_platforms": ["grok"],
            "blockers": ["grok missing XAI_API_KEY."],
            "api_readiness_command": (
                "python scripts/growth/run_ai_visibility_api_probe.py "
                "--platforms chatgpt,claude,grok"
            ),
            "partial_api_readiness_command": (
                "python scripts/growth/run_ai_visibility_api_probe.py "
                "--platforms chatgpt,claude"
            ),
            "api_execute_command": (
                "python scripts/growth/run_ai_visibility_api_probe.py "
                "--platforms chatgpt,claude,grok --execute"
            ),
            "record_probe_command": (
                "python scripts/growth/record_ai_visibility_probe.py probes.jsonl --apply"
            ),
            "compare_command": (
                "curl -fsS 'http://localhost:9700/api/growth/ai-visibility/comparisons'"
            ),
        }


class FakeNextCycle:
    def model_dump(self, mode: str):  # noqa: ARG002
        return {
            "feed_key": "mcp_paid_api_discovery",
            "run_group": "2026-06-05-mcp-weekly",
            "probe_matrix_command": (
                "python scripts/growth/generate_ai_visibility_probe_matrix.py "
                "--output docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-weekly-probe-matrix.json"
            ),
            "validate_matrix_command": (
                "python scripts/growth/validate_ai_visibility_probe_matrix.py "
                "docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-weekly.jsonl "
                "--matrix-file docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-weekly-probe-matrix.json"
            ),
            "cycle_summary_command": (
                "python scripts/growth/summarize_ai_visibility_cycle.py "
                "docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-weekly.jsonl "
                "--output docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-weekly-cycle-summary.json"
            ),
            "operator_brief_command": (
                "python scripts/growth/generate_ai_visibility_operator_brief.py "
                "--feed-key mcp_paid_api_discovery "
                "--cycle-summary docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-weekly-cycle-summary.json "
                "--output docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-weekly-operator-brief.md"
            ),
            "weekly_report_command": (
                "python scripts/growth/export_ai_visibility_weekly_report.py "
                "--output docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-weekly-weekly-report.json"
            ),
        }
