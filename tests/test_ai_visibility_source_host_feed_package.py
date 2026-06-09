import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.growth import generate_ai_visibility_source_host_feed_package as feed_cli


def test_ai_visibility_source_host_feed_package_api_uses_presence_actions(
    synced_client,
):
    for host in (
        "mcpservers.org",
        "aitoolnet.com",
        "alternativeto.net",
        "mcp.directory",
        "glama.ai",
        "aws.amazon.com",
    ):
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
    assert draft_by_host["aitoolnet.com"]["draft_type"] == "directory_submission"
    assert draft_by_host["aitoolnet.com"]["status"] == "ready_to_submit"
    assert draft_by_host["aitoolnet.com"]["submit_url"] == (
        "https://www.aitoolnet.com/finish"
    )
    assert (
        draft_by_host["aitoolnet.com"]["submission_payload"]["stitch_figma_frame"]
        == "Directory Source-Host Submission Pack"
    )
    assert "browser/form confirmation" in " ".join(
        draft_by_host["alternativeto.net"]["operator_notes"]
    )
    assert draft_by_host["alternativeto.net"]["submit_url"] == (
        "https://alternativeto.net/software/submit/"
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
    assert item_by_host["aitoolnet.com"]["execution_status"] == "pending_submission"
    assert item_by_host["mcp.directory"]["execution_status"] == "pending_submission"
    assert (
        "--surface mcp_directory"
        in item_by_host["mcp.directory"]["submission_confirmation_command"]
    )
    mcp_directory_fields = item_by_host["mcp.directory"]["submission_fields"]
    assert {
        "GitHub repository URL",
        "NPM package",
        "PyPI package",
        "Short description",
        "Contact email",
    }.issubset({field["label"] for field in mcp_directory_fields})
    assert any(
        field["value"]
        == "https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server"
        for field in mcp_directory_fields
    )
    assert any(
        "Remote MCP endpoint" in field["label"]
        and field["value"] == "https://mcp.synapse-network.ai/mcp"
        for field in mcp_directory_fields
    )
    assert (
        "operator-owned browser session"
        in item_by_host["mcp.directory"]["submission_steps"][0]
    )
    assert (
        "--surface mcp_directory"
        in item_by_host["mcp.directory"]["evidence_recording_steps"][0]
    )
    assert item_by_host["mcp.directory"]["live_listing_search_urls"][0] == (
        "https://mcp.directory/?q=Synapse%20Network"
    )
    assert (
        "--evidence-mode live-listing"
        in item_by_host["mcp.directory"]["live_listing_validation_steps"][2]
    )
    assert (
        "YYYY-MM-DD-mcp_directory-submission-confirmation.json"
        in item_by_host["mcp.directory"]["submission_confirmation_command"]
    )
    assert item_by_host["aitoolnet.com"]["design_handoff_frame"] == (
        "Directory Source-Host Submission Pack"
    )
    assert (
        "--evidence-mode submission-confirmation"
        in item_by_host["aitoolnet.com"]["submission_confirmation_command"]
    )
    assert (
        "YYYY-MM-DD-aitoolnet-submission-confirmation.json"
        in item_by_host["aitoolnet.com"]["submission_confirmation_command"]
    )
    assert item_by_host["glama.ai"]["execution_status"] == "pending_submission"
    assert item_by_host["glama.ai"]["target_url"] == "https://glama.ai/mcp/servers"
    assert item_by_host["glama.ai"]["design_handoff_frame"] == (
        "Directory Source-Host Submission Pack"
    )
    assert item_by_host["glama.ai"]["live_listing_search_urls"][0] == (
        "https://glama.ai/mcp/servers?query=Synapse%20Network%20MCP"
    )
    assert item_by_host["alternativeto.net"]["execution_status"] == "pending_submission"
    assert any(
        field["label"] == "Website URL"
        and field["value"] == "https://www.synapse-network.ai/"
        for field in item_by_host["alternativeto.net"]["submission_fields"]
    )
    assert item_by_host["alternativeto.net"]["live_listing_search_urls"][0] == (
        "https://alternativeto.net/browse/search/?q=SynapseNetwork%20MCP%20Server"
    )
    assert (
        "submission_url_or_receipt"
        in item_by_host["mcpservers.org"]["required_evidence"]
    )
    assert item_by_host["aws.amazon.com"]["execution_status"] == (
        "pending_operator_review"
    )
    assert "after_feed_probe" in checklist_payload["commands"]

    spot_check = synced_client.get(
        "/api/growth/ai-visibility/source-host-live-spot-check"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-06-source-host-feed"
    )
    assert spot_check.status_code == 200
    spot_payload = spot_check.json()
    assert spot_payload["status"] == "ready_to_execute"
    assert any(
        item["host"] == "mcp.directory"
        and item["search_url"] == "https://mcp.directory/?q=Synapse%20Network"
        and item["status"] == "pending_execute"
        for item in spot_payload["items"]
    )


def test_ai_visibility_source_host_live_spot_check_detects_candidate(
    db_session,
):
    from server.services.growth.ai_visibility_source_host_live_spot_check import (
        ai_visibility_source_host_live_spot_check,
    )
    from server.services.growth.ai_visibility_discovery import create_ai_check
    from server.schemas_growth import GrowthAIVisibilityCheckCreate

    create_ai_check(
        db_session,
        GrowthAIVisibilityCheckCreate(
            query="Synapse vs paid MCP alternatives",
            platform="chatgpt",
            answer_summary="ChatGPT cited mcp.directory.",
            synapse_mentioned=False,
            synapse_cited=False,
            metadata={"source_hosts": ["mcp.directory"]},
            feed_key="mcp_paid_api_discovery",
            run_group="2026-06-06-source-host-live",
        ),
    )

    def fake_fetcher(url: str):  # noqa: ARG001
        return (
            200,
            "Directory result for Synapse Network MCP Server at "
            "https://mcp.synapse-network.ai/mcp",
        )

    result = ai_visibility_source_host_live_spot_check(
        db_session,
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-source-host-live",
        execute=True,
        fetcher=fake_fetcher,
    )

    assert result.status == "candidate_found_needs_live_listing_evidence"
    assert result.items[0].status == "candidate_found"
    assert "synapse network" in result.items[0].matched_terms
    assert (
        "record_ai_visibility_source_host_execution.py"
        in result.commands["record_live_listing"]
    )


def test_ai_visibility_source_host_checklist_keeps_reserved_mcp_directories(
    db_session,
):
    from server.services.growth.ai_visibility_discovery import create_ai_check
    from server.services.growth.ai_visibility_source_host_feed import (
        ai_visibility_source_host_execution_checklist,
    )
    from server.schemas_growth import GrowthAIVisibilityCheckCreate

    create_ai_check(
        db_session,
        GrowthAIVisibilityCheckCreate(
            query="MCP server for paid API calls",
            platform="chatgpt",
            answer_summary="ChatGPT cited several MCP directory and competitor hosts.",
            synapse_mentioned=False,
            synapse_cited=False,
            metadata={
                "source_hosts": [
                    "docs.mcpay.tech",
                    "mcp.directory",
                    "agent402.dev",
                    "cloud.tencent.com",
                    "crowcrowcrow.com",
                    "developer.paddle.com",
                    "docs.opensearch.org",
                    "anythingmcp.com",
                    "glama.ai",
                ]
            },
            feed_key="mcp_paid_api_discovery",
            run_group="2026-06-06-reserved-source-hosts",
        ),
    )

    checklist = ai_visibility_source_host_execution_checklist(
        db_session,
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-reserved-source-hosts",
    )

    item_by_host = {item.host: item for item in checklist.items}
    assert item_by_host["glama.ai"].draft_type == "directory_submission"
    assert item_by_host["glama.ai"].target_url == "https://glama.ai/mcp/servers"
    assert item_by_host["glama.ai"].priority == 9


def test_ai_visibility_source_host_live_spot_check_blocks_without_search_urls(
    monkeypatch,
    db_session,
):
    from server.schemas_growth import GrowthAIVisibilitySourceHostExecutionChecklistOut
    from server.services.growth import ai_visibility_source_host_live_spot_check as svc

    monkeypatch.setattr(
        svc,
        "ai_visibility_source_host_execution_checklist",
        lambda _db, **_kwargs: GrowthAIVisibilitySourceHostExecutionChecklistOut(
            generated_at=datetime.now(timezone.utc),
            feed_key="mcp_paid_api_discovery",
            status="ready_for_operator_execution",
            items=[],
        ),
    )

    result = svc.ai_visibility_source_host_live_spot_check(
        db_session,
        feed_key="mcp_paid_api_discovery",
        execute=True,
    )

    assert result.status == "blocked_until_search_urls"
    assert "No source-host live listing search URLs are available." in result.blockers


def test_ai_visibility_source_host_live_spot_check_reports_fetch_failure(
    monkeypatch,
    db_session,
):
    from server.schemas_growth import (
        GrowthAIVisibilitySourceHostExecutionChecklistOut,
        GrowthAIVisibilitySourceHostExecutionItemOut,
    )
    from server.services.growth import ai_visibility_source_host_live_spot_check as svc

    monkeypatch.setattr(
        svc,
        "ai_visibility_source_host_execution_checklist",
        lambda _db, **_kwargs: GrowthAIVisibilitySourceHostExecutionChecklistOut(
            generated_at=datetime.now(timezone.utc),
            feed_key="mcp_paid_api_discovery",
            status="ready_for_operator_execution",
            items=[
                GrowthAIVisibilitySourceHostExecutionItemOut(
                    key="mcp_directory",
                    host="mcp.directory",
                    draft_type="directory_submission",
                    execution_status="pending_submission",
                    target_url="https://mcp.directory/",
                    action_required="Submit listing.",
                    live_listing_search_urls=["https://mcp.directory/?q=Synapse"],
                    validation_command="python scripts/growth/probe.py",
                    re_probe_command="python scripts/growth/probe.py",
                    completion_gate="Live listing evidence recorded.",
                )
            ],
        ),
    )

    result = svc.ai_visibility_source_host_live_spot_check(
        db_session,
        feed_key="mcp_paid_api_discovery",
        execute=True,
        fetcher=lambda _url: (_ for _ in ()).throw(RuntimeError("host unavailable")),
    )

    assert result.status == "partial_fetch_failure"
    assert result.items[0].status == "fetch_failed"
    assert result.items[0].evidence_excerpt == "host unavailable"
    assert "No Synapse source-host listing candidate was found" in result.blockers[-1]


def test_ai_visibility_source_host_live_spot_check_reports_no_candidate(
    db_session,
):
    from server.services.growth.ai_visibility_source_host_live_spot_check import (
        ai_visibility_source_host_live_spot_check,
    )
    from server.services.growth.ai_visibility_discovery import create_ai_check
    from server.schemas_growth import GrowthAIVisibilityCheckCreate

    create_ai_check(
        db_session,
        GrowthAIVisibilityCheckCreate(
            query="Synapse vs paid MCP alternatives",
            platform="chatgpt",
            answer_summary="ChatGPT cited mcp.directory.",
            synapse_mentioned=False,
            synapse_cited=False,
            metadata={"source_hosts": ["mcp.directory"]},
            feed_key="mcp_paid_api_discovery",
            run_group="2026-06-06-source-host-none",
        ),
    )

    result = ai_visibility_source_host_live_spot_check(
        db_session,
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-source-host-none",
        execute=True,
        fetcher=lambda _url: (200, "Search result only echoed SynapseNetwork."),
    )

    assert result.status == "no_candidate_found"
    assert result.items[0].status == "not_found"


def test_ai_visibility_source_host_live_spot_check_fetch_url_handles_http(
    monkeypatch,
):
    import io
    import urllib.error

    from server.services.growth import ai_visibility_source_host_live_spot_check as svc

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit: int):
            return b"Synapse Network MCP result"

    monkeypatch.setattr(
        svc.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse()
    )
    assert svc._fetch_url("https://example.com/search") == (
        200,
        "Synapse Network MCP result",
    )

    def raise_http_error(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://example.com/search",
            429,
            "Too Many Requests",
            hdrs=None,
            fp=io.BytesIO(b"rate limited"),
        )

    monkeypatch.setattr(svc.urllib.request, "urlopen", raise_http_error)
    assert svc._fetch_url("https://example.com/search") == (429, "rate limited")


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


def test_generate_ai_visibility_source_host_live_spot_check_cli_writes_json(
    monkeypatch, tmp_path: Path
):
    from scripts.growth import (
        generate_ai_visibility_source_host_live_spot_check as spot_cli,
    )

    output_path = tmp_path / "source-host-live.json"

    class FakeSpotCheck:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {
                "module_key": "ai_visibility",
                "check_type": "source_host_live_spot_check",
                "status": "ready_to_execute",
                "items": [{"host": "mcp.directory"}],
            }

    monkeypatch.setattr(
        spot_cli,
        "run_with_db",
        lambda callback: callback(object()),
    )
    monkeypatch.setattr(
        spot_cli,
        "_build_spot_check",
        lambda _db, **_kwargs: FakeSpotCheck(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_source_host_live_spot_check.py",
            "--feed-key",
            "mcp_paid_api_discovery",
            "--execute",
            "--output",
            str(output_path),
        ],
    )

    assert spot_cli.main() == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["check_type"] == "source_host_live_spot_check"
    assert payload["items"][0]["host"] == "mcp.directory"


def test_generate_ai_visibility_source_host_live_spot_check_builds_from_service(
    monkeypatch,
):
    from scripts.growth import (
        generate_ai_visibility_source_host_live_spot_check as spot_cli,
    )
    from server.services.growth import ai_visibility_source_host_live_spot_check as svc

    class FakeSpotCheck:
        feed_key = "mcp_paid_api_discovery"

    monkeypatch.setattr(
        svc,
        "ai_visibility_source_host_live_spot_check",
        lambda db, **kwargs: (db, kwargs, FakeSpotCheck()),
    )

    db = object()
    result = spot_cli._build_spot_check(
        db,
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-source-host-feed",
        execute=True,
    )

    assert result[0] is db
    assert result[1]["execute"] is True
    assert result[1]["run_group"] == "2026-06-06-source-host-feed"
