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
                    {
                        "surface": "mcpfind",
                        "rationale": "MCPFind appeared in public search results.",
                        "validation_command": "Record MCPFind browser confirmation.",
                    },
                    {
                        "surface": "protodex",
                        "rationale": "Protodex accepts MCP server submissions by GitHub issue.",
                        "validation_command": "Record Protodex issue URL.",
                    },
                    {
                        "surface": "docs_disambiguation_links",
                        "draft_type": "brand_disambiguation_answer_block",
                        "rationale": "Synapse.org appeared in exact identity answers.",
                        "validation_command": "Verify official docs disambiguation.",
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
    assert draft_by_host["alternativeto.net"].status == "operator_login_required"
    assert draft_by_host["alternativeto.net"].submit_url == "https://alternativeto.net/"
    assert (
        "authenticated/manual community submission path"
        in draft_by_host["alternativeto.net"].submission_payload["submission_blocker"]
    )
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
    assert draft_by_host["mcpfind.org"].draft_type == "directory_submission"
    assert draft_by_host["mcpfind.org"].submit_url == "https://mcpfind.org/submit"
    assert draft_by_host["mcpfind.org"].submission_payload["category"] == "payments"
    assert draft_by_host["protodex.io"].draft_type == "directory_submission"
    assert (
        "LuciferForge/mcp-directory/issues/new"
        in draft_by_host["protodex.io"].submit_url
    )
    assert (
        draft_by_host["protodex.io"].submission_payload["github_issue_repository"]
        == "LuciferForge/mcp-directory"
    )
    assert draft_by_host["docs.synapse-network.ai"].draft_type == (
        "owned_brand_disambiguation_refresh"
    )
    assert draft_by_host["docs.synapse-network.ai"].status == (
        "ready_to_publish_on_owned_channels"
    )
    assert (
        "SynapseNetworkAI/Synapse-Network-MCP-Server"
        in draft_by_host["docs.synapse-network.ai"].body_markdown
    )

    checklist = source_host_execution_checklist_from_diagnosis(diagnosis_path)
    assert checklist.status == "ready_for_operator_execution"
    item_by_host = {item.host: item for item in checklist.items}
    assert (
        item_by_host["alternativeto.net"].execution_status == "pending_operator_login"
    )
    assert item_by_host["glama.ai"].live_listing_search_urls[0] == (
        "https://glama.ai/mcp/servers?query=Synapse%20Network%20MCP"
    )
    assert item_by_host["mcpservers.org"].execution_status == "pending_submission"
    assert any(
        field.label == "Category" and field.value == "finance"
        for field in item_by_host["mcpservers.org"].submission_fields
    )
    assert item_by_host["docs.synapse-network.ai"].execution_status == (
        "pending_owned_publish"
    )
    assert item_by_host["mcpservers.org"].live_listing_search_urls[0] == (
        "https://mcpservers.org/?q=Synapse%20Network"
    )
    assert item_by_host["mcpfind.org"].execution_status == "pending_submission"
    assert item_by_host["mcpfind.org"].live_listing_search_urls[0] == (
        "https://mcpfind.org/?q=Synapse%20Network"
    )
    assert item_by_host["protodex.io"].execution_status == "pending_submission"
    assert item_by_host["protodex.io"].live_listing_search_urls[0] == (
        "https://protodex.io/?q=Synapse%20Network"
    )
    assert any(
        field.label == "GitHub repository URL"
        for field in item_by_host["protodex.io"].submission_fields
    )
    assert any(
        field.label == "Category" and field.value == "payments"
        for field in item_by_host["mcpfind.org"].submission_fields
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


def test_offline_source_host_package_supports_mcpfind_surface(tmp_path: Path):
    from server.services.growth.ai_visibility_source_host_offline import (
        source_host_execution_checklist_from_diagnosis,
        source_host_feed_package_from_diagnosis,
    )

    diagnosis_path = tmp_path / "feed-diagnosis.json"
    diagnosis_path.write_text(
        json.dumps(
            {
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-09-mcpfind",
                "recommended_source_host_executions": [
                    {
                        "surface": "mcpfind",
                        "draft_type": "mcp_directory_listing",
                        "rationale": "MCPFind appeared in public search results.",
                        "validation_command": "Record MCPFind browser confirmation.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    package = source_host_feed_package_from_diagnosis(diagnosis_path)
    draft = package.drafts[0]

    assert draft.host == "mcpfind.org"
    assert draft.submit_url == "https://mcpfind.org/submit"
    assert draft.submission_payload["listing_type"] == (
        "Remote MCP server directory listing"
    )
    assert "Remote MCP" in draft.submission_payload["tags"]

    checklist = source_host_execution_checklist_from_diagnosis(diagnosis_path)
    item = checklist.items[0]

    assert item.host == "mcpfind.org"
    assert item.execution_status == "pending_submission"
    assert "--surface mcpfind" in item.submission_confirmation_command
    assert item.live_listing_search_urls[0] == (
        "https://mcpfind.org/?q=Synapse%20Network"
    )
