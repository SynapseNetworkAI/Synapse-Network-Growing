import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


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
                        "surface": "chat_mcp_so",
                        "draft_type": "mcp_search_surface_review",
                        "rationale": "chat.mcp.so appeared in answer sources.",
                        "validation_command": "Record chat.mcp.so listing evidence.",
                    },
                    {
                        "surface": "dock0_dev",
                        "draft_type": "competitor_source_host_review",
                        "rationale": "dock0.dev appeared in answer sources.",
                        "validation_command": "Record dock0.dev competitor evidence.",
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
    assert draft_by_host["chat.mcp.so"].draft_type == "mcp_search_surface_review"
    assert draft_by_host["chat.mcp.so"].status == "operator_login_required"
    assert draft_by_host["chat.mcp.so"].validation_command == (
        "Record chat.mcp.so listing evidence."
    )
    assert draft_by_host["chat.mcp.so"].submit_url == "https://chat.mcp.so/submit"
    assert (
        draft_by_host["chat.mcp.so"].submission_payload["github_issue_repository"]
        == "chatmcp/mcpso"
    )
    assert draft_by_host["dock0.dev"].draft_type == "competitor_source_host_review"
    assert draft_by_host["dock0.dev"].status == "needs_operator_review"
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


def test_offline_source_host_package_marks_live_and_review_pending_items(
    tmp_path: Path,
):
    from server.services.growth.ai_visibility_source_host_offline import (
        source_host_execution_checklist_from_diagnosis,
        source_host_feed_package_from_diagnosis,
    )

    diagnosis_path = tmp_path / "feed-diagnosis.json"
    diagnosis_path.write_text(
        json.dumps(
            {
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-10-layered",
                "recommended_source_host_executions": [
                    {
                        "surface": "mcp_directory",
                        "draft_type": "mcp_directory_listing",
                        "rationale": "MCP Directory appeared in answer sources.",
                    },
                    {
                        "surface": "glama",
                        "draft_type": "mcp_directory_listing",
                        "rationale": "Glama has a partial Synapse candidate.",
                    },
                    {
                        "surface": "protodex",
                        "draft_type": "mcp_directory_listing",
                        "rationale": "Protodex appeared in public search.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    facts = SimpleNamespace(
        review_pending_surfaces=["mcp_directory"],
        metadata_refresh_surfaces=["glama"],
        live_surfaces=["protodex"],
    )

    package = source_host_feed_package_from_diagnosis(
        diagnosis_path,
        audit_facts=facts,
    )
    draft_by_host = {draft.host: draft for draft in package.drafts}
    assert draft_by_host["mcp.directory"].status == "review_pending_live_recheck"
    assert draft_by_host["protodex.io"].status == "already_live"
    assert (
        draft_by_host["mcp.directory"].submission_payload["source_host_audit_status"]
        == "review_pending_live_recheck"
    )
    assert draft_by_host["glama.ai"].status == "metadata_refresh_required"
    assert (
        draft_by_host["glama.ai"].submission_payload["source_host_audit_status"]
        == "metadata_refresh_required"
    )

    checklist = source_host_execution_checklist_from_diagnosis(
        diagnosis_path,
        audit_facts=facts,
    )
    item_by_host = {item.host: item for item in checklist.items}
    assert item_by_host["mcp.directory"].execution_status == (
        "review_pending_live_recheck"
    )
    assert item_by_host["mcp.directory"].submission_confirmation_command == ""
    assert "Do not resubmit" in item_by_host["mcp.directory"].action_required
    assert item_by_host["glama.ai"].execution_status == "metadata_refresh_required"
    assert (
        "Refresh the existing directory listing metadata"
        in item_by_host["glama.ai"].action_required
    )
    assert (
        "metadata_refresh_receipt_or_screenshot"
        in item_by_host["glama.ai"].required_evidence
    )
    assert (
        "Updated SynapseNetwork MCP Server"
        in item_by_host["glama.ai"].submission_confirmation_command
    )
    assert item_by_host["protodex.io"].execution_status == "already_live"
    assert item_by_host["protodex.io"].required_evidence == [
        "existing_live_source_host_evidence"
    ]


def test_source_host_audit_facts_collects_metadata_refresh_from_spot_check(
    tmp_path: Path,
):
    from server.services.growth.ai_visibility_source_host_audit import (
        source_host_audit_facts,
    )

    spot_check_path = tmp_path / "source-host-live-spot-check.json"
    spot_check_path.write_text(
        json.dumps(
            {
                "check_type": "source_host_live_spot_check",
                "generated_at": "2026-06-10T00:00:00Z",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-10-after-owned-source-live",
                "execute": True,
                "status": "candidate_incomplete_needs_metadata_refresh",
                "items": [
                    {
                        "host": "glama.ai",
                        "search_url": (
                            "https://glama.ai/mcp/servers?query=Synapse%20Network"
                        ),
                        "status": "candidate_incomplete",
                        "matched_terms": [
                            "synapse network",
                            "synapse-network-mcp-server",
                        ],
                        "missing_terms": ["mcp.synapse-network.ai"],
                    },
                    {
                        "host": "mcpservers.org",
                        "search_url": "https://mcpservers.org/?q=Synapse%20Network",
                        "status": "not_found",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    facts = source_host_audit_facts(evidence_dir=tmp_path)

    assert facts.metadata_refresh_surfaces == ["glama.ai"]
    assert "source-host-live-spot-check.json" in facts.evidence_files[0]


def test_source_host_metadata_refresh_evidence_can_override_older_live_status(
    tmp_path: Path,
):
    from server.services.growth.ai_visibility_source_host_audit import (
        source_host_audit_facts,
    )
    from server.services.growth.ai_visibility_source_host_offline import (
        source_host_execution_checklist_from_diagnosis,
        source_host_feed_package_from_diagnosis,
    )

    diagnosis_path = tmp_path / "feed-diagnosis.json"
    diagnosis_path.write_text(
        json.dumps(
            {
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-11-exact-query",
                "recommended_source_host_executions": [
                    {
                        "surface": "glama",
                        "draft_type": "mcp_directory_listing",
                        "rationale": "Glama has a partial exact-query candidate.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "2026-06-10-glama-live-source-host.json").write_text(
        json.dumps(
            {
                "module_key": "ai_visibility_source_host_execution",
                "status": "live_verified",
                "evidence_type": "live_source_host",
                "surface": "glama_ai",
                "checked_at": "2026-06-10T06:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "2026-06-11-glama-live-spot-check.json").write_text(
        json.dumps(
            {
                "check_type": "source_host_live_spot_check",
                "generated_at": "2026-06-10T16:00:00Z",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-11-exact-query",
                "execute": True,
                "status": "candidate_incomplete_needs_metadata_refresh",
                "items": [
                    {
                        "host": "glama.ai",
                        "status": "candidate_incomplete",
                        "matched_terms": [
                            "synapse network",
                            "synapse-network-mcp-server",
                        ],
                        "missing_terms": ["mcp.synapse-network.ai"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    facts = source_host_audit_facts(evidence_dir=tmp_path)
    package = source_host_feed_package_from_diagnosis(
        diagnosis_path,
        audit_facts=facts,
    )
    checklist = source_host_execution_checklist_from_diagnosis(
        diagnosis_path,
        audit_facts=facts,
    )

    assert facts.surface_statuses["glama"] == "metadata_refresh_required"
    assert package.drafts[0].host == "glama.ai"
    assert package.drafts[0].status == "metadata_refresh_required"
    assert checklist.items[0].host == "glama.ai"
    assert checklist.items[0].execution_status == "metadata_refresh_required"


def test_config_free_source_host_audit_tracks_latest_metadata_refresh_status(
    tmp_path: Path,
):
    from scripts.growth.ai_visibility_source_host_audit_cli import (
        offline_source_host_audit_facts,
    )

    (tmp_path / "2026-06-10-glama-live-source-host.json").write_text(
        json.dumps(
            {
                "module_key": "ai_visibility_source_host_execution",
                "status": "live_verified",
                "surface": "glama_ai",
                "checked_at": "2026-06-10T06:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "2026-06-11-glama-live-spot-check.json").write_text(
        json.dumps(
            {
                "check_type": "source_host_live_spot_check",
                "generated_at": "2026-06-10T16:00:00Z",
                "items": [
                    {
                        "host": "glama.ai",
                        "status": "candidate_incomplete",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    facts = offline_source_host_audit_facts(tmp_path)

    assert facts.live_surfaces == ["glama_ai"]
    assert facts.metadata_refresh_surfaces == ["glama.ai"]
    assert facts.surface_statuses["glama"] == "metadata_refresh_required"


def test_source_host_audit_cli_imports_without_pythonpath():
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from scripts.growth.ai_visibility_source_host_audit_cli "
                "import offline_source_host_audit_facts; "
                "print(offline_source_host_audit_facts().__class__.__name__)"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "OfflineSourceHostAuditFacts" in result.stdout


def test_offline_source_host_package_maps_exact_query_collision_surfaces(
    tmp_path: Path,
):
    from server.services.growth.ai_visibility_source_host_offline import (
        source_host_execution_checklist_from_diagnosis,
        source_host_feed_package_from_diagnosis,
    )

    diagnosis_path = tmp_path / "feed-diagnosis.json"
    diagnosis_path.write_text(
        json.dumps(
            {
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-10-exact",
                "recommended_source_host_executions": [
                    {
                        "surface": "mcp_so",
                        "draft_type": "mcp_directory_listing",
                        "rationale": "mcp.so appeared in exact SynapseNetwork answers.",
                    },
                    {
                        "surface": "ubos_tech",
                        "draft_type": "brand_collision_source_host_review",
                        "rationale": "UBOS returned unrelated Synapse MCP content.",
                    },
                    {
                        "surface": "mysynap_com",
                        "draft_type": "brand_collision_source_host_review",
                        "rationale": "mysynap.com appeared as a collision source.",
                    },
                    {
                        "surface": "synapbus_dev",
                        "draft_type": "brand_collision_source_host_review",
                        "rationale": "SynapBus appeared as a collision source.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    package = source_host_feed_package_from_diagnosis(diagnosis_path)
    draft_by_host = {draft.host: draft for draft in package.drafts}
    assert set(draft_by_host) == {
        "mcp.so",
        "ubos.tech",
        "mysynap.com",
        "synapbus.dev",
    }
    assert draft_by_host["mcp.so"].draft_type == "directory_submission"
    assert draft_by_host["mcp.so"].status == "operator_login_required"
    assert draft_by_host["mcp.so"].submit_url == "https://mcp.so/submit"
    assert (
        draft_by_host["mcp.so"].submission_payload["github_issue_repository"]
        == "chatmcp/mcpso"
    )
    assert draft_by_host["ubos.tech"].status == "needs_operator_review"

    checklist = source_host_execution_checklist_from_diagnosis(diagnosis_path)
    item_by_host = {item.host: item for item in checklist.items}
    assert item_by_host["mcp.so"].execution_status == "pending_operator_login"
    assert "truthful partner" in item_by_host["ubos.tech"].action_required
