import json
import sys

from scripts.growth import generate_ai_visibility_release_snapshot as snapshot_cli
from server.services.growth import ai_visibility_release_snapshot as snapshot


def test_release_snapshot_combines_live_gcloud_and_key_blockers(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr(
        snapshot,
        "ai_visibility_live_readiness",
        lambda **_: FakeReadiness(),
    )
    monkeypatch.setattr(
        snapshot,
        "_gcloud_project_check",
        lambda project_id: {
            "project_id": project_id,
            "ok": False,
            "status": "failed",
            "summary": "Reauthentication failed. Please run gcloud auth login.",
        },
    )

    payload = snapshot.build_snapshot(
        target_commit=snapshot.DEFAULT_TARGET_COMMIT,
        actor="codex/test",
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-05-snapshot",
    )

    assert payload["snapshot_type"] == "release_blocker"
    assert payload["status"] == "blocked"
    assert payload["official_homepage"] == "https://www.synapse-network.ai/"
    assert payload["deploy_readiness_status"] == (
        "ready_for_release_runner_after_gcloud_auth"
    )
    assert any(
        fact == "Official homepage canonical is https://www.synapse-network.ai/."
        for fact in payload["confirmed_facts"]
    )
    rendered = json.dumps(payload)
    assert "Docs /mcp/paid-api-calls page must be live." in rendered
    assert "gcloud auth login" in rendered
    assert "chatgpt external probe key missing: OPENAI_API_KEY." in rendered
    assert "OPENAI_API_KEY=" not in rendered


def test_release_snapshot_cli_writes_json(monkeypatch, tmp_path):
    output_path = tmp_path / "snapshot.json"
    monkeypatch.setattr(
        snapshot_cli,
        "build_snapshot",
        lambda **_: {
            "module_key": "ai_visibility",
            "snapshot_type": "release_blocker",
            "status": "blocked",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_release_snapshot.py",
            "--output",
            str(output_path),
        ],
    )

    assert snapshot_cli.main() == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "blocked"


class FakeReadiness:
    def model_dump(self, mode: str):  # noqa: ARG002
        return {
            "status": "blocked",
            "ready_count": 0,
            "blocked_count": 1,
            "items": [
                {
                    "feed_key": "mcp_paid_api_discovery",
                    "missing_facts": [
                        "Docs /mcp/paid-api-calls page must be live.",
                    ],
                }
            ],
        }
