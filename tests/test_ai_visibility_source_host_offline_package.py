import json
from pathlib import Path


def test_source_host_cli_can_build_from_offline_diagnosis(tmp_path: Path):
    from server.services.growth.ai_visibility_source_host_offline import (
        source_host_execution_checklist_from_diagnosis,
        source_host_feed_package_from_diagnosis,
    )
    from server.services.growth.ai_visibility_source_host_offline_live import (
        source_host_live_spot_check_from_checklist,
    )

    diagnosis_path = tmp_path / "feed-diagnosis.json"
    diagnosis_path.write_text(
        json.dumps(
            {
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-09-offline",
                "recommended_source_host_executions": [
                    {
                        "surface": "alternativeto",
                        "rationale": "AlternativeTo appeared in answer sources.",
                        "validation_command": "Record browser confirmation.",
                        "next_probe_command": "python scripts/growth/run_ai_visibility_api_probe.py --execute",
                    },
                    {
                        "surface": "official_mcp_registry",
                        "rationale": "Official registry is a high-trust MCP source.",
                        "validation_command": "mcp-publisher publish",
                    },
                    {
                        "surface": "glama",
                        "rationale": "Glama is a visible MCP directory.",
                        "validation_command": "curl -fsS https://glama.ai/search?q=Synapse",
                    },
                    {
                        "surface": "mcpservers",
                        "rationale": "MCPServers appeared in answer sources.",
                        "validation_command": "Record MCPServers browser confirmation.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    package = source_host_feed_package_from_diagnosis(diagnosis_path)
    assert package.status == "ready_for_operator_feed"
    draft_by_host = {draft.host: draft for draft in package.drafts}
    assert draft_by_host["alternativeto.net"].draft_type == "directory_submission"
    assert draft_by_host["alternativeto.net"].validation_command == (
        "Record browser confirmation."
    )
    assert draft_by_host["registry.modelcontextprotocol.io"].draft_type == (
        "contextual_partner_or_guest_pitch"
    )
    assert draft_by_host["glama.ai"].submit_url == "https://glama.ai/mcp/servers"
    assert draft_by_host["mcpservers.org"].draft_type == "directory_submission"
    assert draft_by_host["mcpservers.org"].submit_url == "https://mcpservers.org/submit"
    assert draft_by_host["mcpservers.org"].submission_payload["category"] == "finance"
    assert draft_by_host["mcpservers.org"].submission_payload["plan"] == "free"

    checklist = source_host_execution_checklist_from_diagnosis(diagnosis_path)
    assert checklist.status == "ready_for_operator_execution"
    item_by_host = {item.host: item for item in checklist.items}
    assert item_by_host["alternativeto.net"].execution_status == "pending_submission"
    assert item_by_host["glama.ai"].live_listing_search_urls[0] == (
        "https://glama.ai/mcp/servers?query=Synapse%20Network%20MCP"
    )
    assert item_by_host["mcpservers.org"].execution_status == "pending_submission"
    assert any(
        field.label == "Category" and field.value == "finance"
        for field in item_by_host["mcpservers.org"].submission_fields
    )
    assert item_by_host["mcpservers.org"].live_listing_search_urls[0] == (
        "https://mcpservers.org/?q=Synapse%20Network"
    )

    checklist_path = tmp_path / "source-host-checklist.json"
    checklist_path.write_text(checklist.model_dump_json(), encoding="utf-8")
    spot_check = source_host_live_spot_check_from_checklist(checklist_path)
    assert spot_check.status == "ready_to_execute"
    assert any(
        item.host == "alternativeto.net"
        and item.search_url
        == "https://alternativeto.net/browse/search/?q=SynapseNetwork%20MCP%20Server"
        for item in spot_check.items
    )


def test_offline_source_host_package_normalizes_observed_surface_keys(tmp_path: Path):
    from server.services.growth.ai_visibility_source_host_offline import (
        source_host_execution_checklist_from_diagnosis,
        source_host_feed_package_from_diagnosis,
    )

    diagnosis_path = tmp_path / "feed-diagnosis.json"
    diagnosis_path.write_text(
        json.dumps(
            {
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-09-after-official-registry-live",
                "recommended_source_host_executions": [
                    {
                        "surface": "aitoolnet",
                        "draft_type": "ai_tool_directory_listing",
                        "rationale": "AIToolNet appeared in ChatGPT source hosts.",
                        "validation_command": "Record AIToolNet browser/form confirmation.",
                    },
                    {
                        "surface": "mcp_directory",
                        "draft_type": "mcp_directory_listing",
                        "rationale": "MCP Directory appeared in ChatGPT source hosts.",
                        "validation_command": "Record MCP Directory browser/form confirmation.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    package = source_host_feed_package_from_diagnosis(diagnosis_path)
    draft_by_host = {draft.host: draft for draft in package.drafts}

    assert "aitoolnet.com" in draft_by_host
    assert draft_by_host["aitoolnet.com"].draft_type == "directory_submission"
    assert draft_by_host["aitoolnet.com"].submit_url == (
        "https://www.aitoolnet.com/finish"
    )
    assert (
        "support@aitoolnet.com"
        in draft_by_host["aitoolnet.com"].submission_payload["submission_method"]
    )
    assert "mcp.directory" in draft_by_host
    assert draft_by_host["mcp.directory"].draft_type == "directory_submission"

    checklist = source_host_execution_checklist_from_diagnosis(diagnosis_path)
    item_by_host = {item.host: item for item in checklist.items}
    assert item_by_host["aitoolnet.com"].execution_status == "pending_submission"
    assert "YYYY-MM-DD-aitoolnet-submission-confirmation.json" in (
        item_by_host["aitoolnet.com"].submission_confirmation_command
    )
