import json
import sys
from pathlib import Path

from scripts.growth import generate_ai_visibility_source_host_feed_package as feed_cli


def test_ai_visibility_source_host_feed_package_api_uses_presence_actions(
    synced_client,
):
    for host in ("mcpservers.org", "aws.amazon.com"):
        response = synced_client.post(
            "/api/growth/ai-visibility/checks",
            json={
                "query": "MCP server for paid API calls",
                "platform": "chatgpt",
                "answer_summary": f"ChatGPT cited {host}.",
                "synapse_mentioned": False,
                "synapse_cited": False,
                "metadata": {"source_hosts": [host]},
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-06-source-host-feed",
            },
        )
        assert response.status_code == 201

    package = synced_client.get(
        "/api/growth/ai-visibility/source-host-feed-package"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-06-source-host-feed"
    )

    assert package.status_code == 200
    payload = package.json()
    assert payload["status"] == "ready_for_operator_feed"
    draft_by_host = {item["host"]: item for item in payload["drafts"]}
    assert draft_by_host["mcpservers.org"]["draft_type"] == "directory_submission"
    assert draft_by_host["mcpservers.org"]["status"] == "ready_to_submit"
    assert draft_by_host["mcpservers.org"]["submit_url"] == (
        "https://mcpservers.org/submit"
    )
    assert "Synapse Network MCP Server" in draft_by_host["mcpservers.org"]["title"]
    assert draft_by_host["aws.amazon.com"]["draft_type"] == (
        "contextual_partner_or_guest_pitch"
    )
    assert draft_by_host["aws.amazon.com"]["status"] == "needs_operator_review"
    assert "after_feed_probe" in payload["commands"]

    checklist = synced_client.get(
        "/api/growth/ai-visibility/source-host-execution-checklist"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-06-source-host-feed"
    )

    assert checklist.status_code == 200
    checklist_payload = checklist.json()
    item_by_host = {item["host"]: item for item in checklist_payload["items"]}
    assert item_by_host["mcpservers.org"]["execution_status"] == "pending_submission"
    assert (
        "submission_url_or_receipt"
        in item_by_host["mcpservers.org"]["required_evidence"]
    )
    assert item_by_host["aws.amazon.com"]["execution_status"] == (
        "pending_operator_review"
    )
    assert "after_feed_probe" in checklist_payload["commands"]


def test_source_host_feed_package_handles_mcp_so_login_and_editorial_hosts(
    synced_client,
):
    for host in ("mcp.so", "chatforest.com", "coincodecap.com"):
        response = synced_client.post(
            "/api/growth/ai-visibility/checks",
            json={
                "query": "SynapseNetwork MCP vs paid MCP alternatives",
                "platform": "chatgpt",
                "answer_summary": f"ChatGPT cited {host}.",
                "synapse_mentioned": True,
                "synapse_cited": False,
                "metadata": {"source_hosts": [host]},
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-08-source-host-next",
            },
        )
        assert response.status_code == 201

    package = synced_client.get(
        "/api/growth/ai-visibility/source-host-feed-package"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-08-source-host-next"
    )

    assert package.status_code == 200
    payload = package.json()
    draft_by_host = {item["host"]: item for item in payload["drafts"]}
    assert draft_by_host["mcp.so"]["draft_type"] == "directory_submission"
    assert draft_by_host["mcp.so"]["status"] == "operator_login_required"
    assert draft_by_host["mcp.so"]["submit_url"] == "https://mcp.so/submit"
    assert draft_by_host["mcp.so"]["submission_payload"]["server_config"]
    assert draft_by_host["chatforest.com"]["draft_type"] == (
        "contextual_partner_or_guest_pitch"
    )
    assert draft_by_host["chatforest.com"]["submission_payload"]["pitch_subject"]
    assert draft_by_host["coincodecap.com"]["submission_payload"]["target_url"] == (
        "https://coincodecap.com/contact"
    )

    checklist = synced_client.get(
        "/api/growth/ai-visibility/source-host-execution-checklist"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-08-source-host-next"
    )

    assert checklist.status_code == 200
    item_by_host = {item["host"]: item for item in checklist.json()["items"]}
    assert item_by_host["mcp.so"]["execution_status"] == "pending_operator_login"
    assert item_by_host["chatforest.com"]["execution_status"] == (
        "pending_operator_review"
    )


def test_source_host_feed_package_uses_readable_competitor_labels(
    synced_client,
):
    for host in ("docs.mcpay.tech", "mcp.magpie.im"):
        response = synced_client.post(
            "/api/growth/ai-visibility/checks",
            json={
                "query": "MCP server for paid API calls",
                "platform": "chatgpt",
                "answer_summary": f"ChatGPT cited {host}.",
                "synapse_mentioned": False,
                "synapse_cited": False,
                "metadata": {"source_hosts": [host]},
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-08-competitor-labels",
            },
        )
        assert response.status_code == 201

    package = synced_client.get(
        "/api/growth/ai-visibility/source-host-feed-package"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-08-competitor-labels"
    )

    assert package.status_code == 200
    draft_by_host = {item["host"]: item for item in package.json()["drafts"]}
    assert draft_by_host["docs.mcpay.tech"]["draft_type"] == (
        "owned_comparison_refresh"
    )
    assert draft_by_host["docs.mcpay.tech"]["title"] == (
        "Synapse Network vs MCPay for paid MCP and agent payments"
    )
    assert draft_by_host["mcp.magpie.im"]["title"] == (
        "Synapse Network vs Magpie for paid MCP and agent payments"
    )


def test_generate_ai_visibility_source_host_feed_package_cli_writes_json(
    monkeypatch, tmp_path: Path
):
    output_path = tmp_path / "source-host-feed.json"

    class FakePackage:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {
                "module_key": "ai_visibility",
                "package_type": "source_host_feed",
                "status": "ready_for_operator_feed",
                "feed_key": "mcp_paid_api_discovery",
                "drafts": [
                    {
                        "host": "mcpservers.org",
                        "draft_type": "directory_submission",
                    }
                ],
            }

    monkeypatch.setattr(
        feed_cli,
        "run_with_db",
        lambda callback: callback(object()),
    )
    monkeypatch.setattr(
        feed_cli,
        "_build_feed_package",
        lambda _db, **_kwargs: FakePackage(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_source_host_feed_package.py",
            "--feed-key",
            "mcp_paid_api_discovery",
            "--run-group",
            "2026-06-06-source-host-feed",
            "--output",
            str(output_path),
        ],
    )

    assert feed_cli.main() == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["package_type"] == "source_host_feed"
    assert payload["drafts"][0]["host"] == "mcpservers.org"


def test_generate_ai_visibility_source_host_execution_checklist_cli_writes_json(
    monkeypatch, tmp_path: Path
):
    from scripts.growth import (
        generate_ai_visibility_source_host_execution_checklist as checklist_cli,
    )

    output_path = tmp_path / "source-host-execution.json"

    class FakeChecklist:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {
                "module_key": "ai_visibility",
                "checklist_type": "source_host_feed_execution",
                "status": "ready_for_operator_execution",
                "items": [{"host": "mcpservers.org"}],
            }

    monkeypatch.setattr(
        checklist_cli,
        "run_with_db",
        lambda callback: callback(object()),
    )
    monkeypatch.setattr(
        checklist_cli,
        "_build_execution_checklist",
        lambda _db, **_kwargs: FakeChecklist(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_source_host_execution_checklist.py",
            "--feed-key",
            "mcp_paid_api_discovery",
            "--output",
            str(output_path),
        ],
    )

    assert checklist_cli.main() == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["checklist_type"] == "source_host_feed_execution"
    assert payload["items"][0]["host"] == "mcpservers.org"
