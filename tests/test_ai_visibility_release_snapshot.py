import json
import os
import sys

from scripts.growth import generate_ai_visibility_release_snapshot as snapshot_cli
from server.services.growth import ai_visibility_release_snapshot as snapshot
from server.services.growth.ai_visibility_remote_mcp_metadata import (
    RemoteMcpPublicMetadataCheckOut,
)


def test_release_snapshot_combines_live_gcloud_and_key_blockers(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GENIMI_API_KEY", raising=False)
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
    _mock_remote_mcp_metadata_ready(monkeypatch)

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
    assert "synapse-prod-user-front-00032-2z5" in rendered
    assert "gcloud auth login" in rendered
    assert "chatgpt external probe key missing: OPENAI_API_KEY." in rendered
    assert (
        "gemini external probe key missing: GEMINI_API_KEY or GENIMI_API_KEY."
        in rendered
    )
    assert "OPENAI_API_KEY=" not in rendered


def test_release_snapshot_does_not_keep_stale_live_blockers_when_feed_is_ready(
    monkeypatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GENIMI_API_KEY", raising=False)
    monkeypatch.setattr(
        snapshot,
        "ai_visibility_live_readiness",
        lambda **_: ReadyReadiness(),
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
    _mock_remote_mcp_metadata_ready(monkeypatch)

    payload = snapshot.build_snapshot(
        target_commit=snapshot.DEFAULT_TARGET_COMMIT,
        actor="codex/test",
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-snapshot",
    )

    rendered = json.dumps(payload)
    assert payload["live_readiness"]["status"] == "ready_for_external_probe"
    assert "Docs /mcp/paid-api-calls page must be live." not in rendered
    assert "does not expose the MCP paid API guide" not in rendered
    assert "gcloud auth login" in rendered
    assert "chatgpt external probe key missing: OPENAI_API_KEY." in rendered
    assert (
        "gemini external probe key missing: GEMINI_API_KEY or GENIMI_API_KEY."
        in rendered
    )


def test_release_snapshot_blocks_stale_remote_mcp_metadata(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic-secret")
    monkeypatch.setenv("XAI_API_KEY", "xai-test-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-secret")
    monkeypatch.setattr(
        snapshot,
        "ai_visibility_live_readiness",
        lambda **_: ReadyReadiness(),
    )
    monkeypatch.setattr(
        snapshot,
        "_gcloud_project_check",
        lambda project_id: {
            "project_id": project_id,
            "ok": True,
            "status": "ok",
            "summary": project_id,
        },
    )
    monkeypatch.setattr(
        snapshot,
        "remote_mcp_public_metadata_check",
        lambda: RemoteMcpPublicMetadataCheckOut(
            url="https://mcp.synapse-network.ai/.well-known/glama.json",
            ok=False,
            status="stale_or_incomplete",
            http_status=200,
            summary="Remote MCP public metadata is missing required AI directory fields.",
            missing_fields=[
                "name",
                "serverUrl",
                "repository",
                "tools.discover_services",
                "tools.invoke_and_pay",
                "tools.get_receipt",
            ],
            blocker=(
                "Remote MCP public metadata gate failed (stale or incomplete): "
                "https://mcp.synapse-network.ai/.well-known/glama.json missing "
                "name, serverUrl, repository, tools.discover_services, "
                "tools.invoke_and_pay, tools.get_receipt. Merge and deploy "
                "Synapse-Network-MCP-Server metadata refresh, then run "
                "npm run test:e2e:remote:metadata before rerunning AI visibility probes."
            ),
        ),
    )

    payload = snapshot.build_snapshot(
        target_commit=snapshot.DEFAULT_TARGET_COMMIT,
        actor="codex/test",
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-11-remote-metadata",
    )

    rendered = json.dumps(payload)
    assert payload["status"] == "blocked"
    assert payload["remote_mcp_public_metadata"]["status"] == "stale_or_incomplete"
    assert "Remote MCP public metadata gate failed" in rendered
    assert "tools.discover_services" in rendered
    assert "npm run test:e2e:remote:metadata" in rendered
    assert payload["next_actions"][0].startswith(
        "Merge and deploy the Remote MCP metadata refresh"
    )


def test_release_snapshot_accepts_genimi_alias(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic-secret")
    monkeypatch.setenv("XAI_API_KEY", "xai-test-secret")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GENIMI_API_KEY", "gemini-test-secret")
    monkeypatch.setattr(
        snapshot,
        "ai_visibility_live_readiness",
        lambda **_: ReadyReadiness(),
    )
    monkeypatch.setattr(
        snapshot,
        "_gcloud_project_check",
        lambda project_id: {
            "project_id": project_id,
            "ok": True,
            "status": "ok",
            "summary": project_id,
        },
    )
    _mock_remote_mcp_metadata_ready(monkeypatch)

    payload = snapshot.build_snapshot(
        target_commit=snapshot.DEFAULT_TARGET_COMMIT,
        actor="codex/test",
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-08-snapshot",
    )

    rendered = json.dumps(payload)
    assert payload["external_probe_keys"]["gemini"]["configured"] is True
    assert payload["external_probe_keys"]["gemini"]["env_key"] == (
        "GEMINI_API_KEY or GENIMI_API_KEY"
    )
    assert "gemini-test-secret" not in rendered


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


def test_release_snapshot_cli_loads_probe_env_file_without_printing_values(
    monkeypatch,
    tmp_path,
):
    output_path = tmp_path / "snapshot.json"
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "GENIMI_API_KEY=gemini-test-secret",
                "UNRELATED_SECRET=should-not-load",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("GENIMI_API_KEY", raising=False)
    monkeypatch.delenv("UNRELATED_SECRET", raising=False)

    def fake_snapshot(**_):
        return {
            "module_key": "ai_visibility",
            "snapshot_type": "release_blocker",
            "status": "blocked",
            "gemini_configured": bool(os.environ.get("GENIMI_API_KEY", "").strip()),
            "unrelated_configured": bool(
                os.environ.get("UNRELATED_SECRET", "").strip()
            ),
        }

    monkeypatch.setattr(snapshot_cli, "build_snapshot", fake_snapshot)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_release_snapshot.py",
            "--env-file",
            str(env_path),
            "--output",
            str(output_path),
        ],
    )

    assert snapshot_cli.main() == 0
    rendered = output_path.read_text(encoding="utf-8")
    payload = json.loads(rendered)
    assert payload["gemini_configured"] is True
    assert payload["unrelated_configured"] is False
    assert "gemini-test-secret" not in rendered
    assert "should-not-load" not in rendered


def test_release_snapshot_env_loader_handles_skip_and_invalid_lines(
    monkeypatch,
    tmp_path,
):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "",
                "# comment",
                "invalid_line",
                "OPENAI_API_KEY='dotenv-openai-key'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AI_VISIBILITY_SKIP_DOTENV", "1")

    snapshot_cli.load_probe_env_file(env_path)

    assert "OPENAI_API_KEY" not in os.environ

    monkeypatch.delenv("AI_VISIBILITY_SKIP_DOTENV", raising=False)
    snapshot_cli.load_probe_env_file(env_path)

    assert os.environ["OPENAI_API_KEY"] == "dotenv-openai-key"
    assert snapshot_cli.parse_env_line("invalid_line") is None
    assert snapshot_cli.unquote_env_value("plain-value") == "plain-value"


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


class ReadyReadiness:
    def model_dump(self, mode: str):  # noqa: ARG002
        return {
            "status": "ready_for_external_probe",
            "ready_count": 1,
            "blocked_count": 0,
            "items": [
                {
                    "feed_key": "mcp_paid_api_discovery",
                    "missing_facts": [],
                }
            ],
        }


def _mock_remote_mcp_metadata_ready(monkeypatch):
    monkeypatch.setattr(
        snapshot,
        "remote_mcp_public_metadata_check",
        lambda: RemoteMcpPublicMetadataCheckOut(
            url="https://mcp.synapse-network.ai/.well-known/glama.json",
            ok=True,
            status="ready",
            http_status=200,
            missing_fields=[],
            summary="Remote MCP public metadata has complete AI directory fields.",
        ),
    )
