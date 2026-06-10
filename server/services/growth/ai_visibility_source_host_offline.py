"""Offline source-host handoff helpers for AI visibility evidence files."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from server.schemas_growth import (
    GrowthAIVisibilitySourceHostDraftOut,
    GrowthAIVisibilitySourceHostExecutionChecklistOut,
    GrowthAIVisibilitySourceHostFeedPackageOut,
)
from server.services.growth.ai_visibility_directory_submission_payloads import (
    directory_submission_payload,
)
from server.services.growth.ai_visibility_source_host_checklist_helpers import (
    source_host_execution_checklist_from_package,
)
from server.services.growth.ai_visibility_source_host_directory_config import (
    DIRECTORY_SUBMIT_URLS,
)
from server.services.growth.ai_visibility_source_host_surfaces import (
    source_host_surface,
)

DEFAULT_FEED_KEY = "mcp_paid_api_discovery"
REMOTE_MCP_ENDPOINT = "https://mcp.synapse-network.ai/mcp"
OFFICIAL_HOME = "https://www.synapse-network.ai/"
OFFICIAL_DOCS = "https://docs.synapse-network.ai/mcp/paid-api-calls"
OFFICIAL_GITHUB_REPOSITORY = (
    "https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server"
)
OFFICIAL_NPM_PACKAGE = "@synapse-network-ai/mcp-server"
SURFACE_HOSTS = {
    "aitoolnet": "aitoolnet.com",
    "alternativeto": "alternativeto.net",
    "mcp_directory": "mcp.directory",
    "mcpfind": "mcpfind.org",
    "official_mcp_registry": "registry.modelcontextprotocol.io",
    "github_readme": "github.com",
    "smithery": "smithery.ai",
    "glama": "glama.ai",
    "lobehub": "lobehub.com",
    "mcpservers": "mcpservers.org",
    "mcp_marketplace": "mcp-marketplace.io",
    "protodex": "protodex.io",
    "pulsemcp": "pulsemcp.com",
    "x_citation_thread": "x.com",
    "docs_disambiguation_links": "docs.synapse-network.ai",
}


def source_host_feed_package_from_diagnosis(
    diagnosis_path: str | Path,
    *,
    feed_key: str | None = None,
    run_group: str | None = None,
    audit_facts: object | None = None,
) -> GrowthAIVisibilitySourceHostFeedPackageOut:
    payload = _read_json(diagnosis_path)
    safe_feed_key = feed_key or str(payload.get("feed_key") or DEFAULT_FEED_KEY)
    safe_run_group = run_group or str(payload.get("run_group") or "")
    drafts = [
        _draft_from_recommendation(rec, i, audit_facts=audit_facts)
        for i, rec in _recommendations(payload)
    ]
    blockers: list[str] = []
    if not drafts:
        blockers.append(
            "No source-host drafts were generated from diagnosis recommendations."
        )
    return GrowthAIVisibilitySourceHostFeedPackageOut(
        generated_at=datetime.now(timezone.utc),
        feed_key=safe_feed_key,
        run_group=safe_run_group,
        status="ready_for_operator_feed" if drafts else "blocked_until_source_hosts",
        source_hosts=[draft.host for draft in drafts],
        drafts=drafts,
        blockers=blockers,
        commands=_commands(safe_feed_key, safe_run_group),
    )


def source_host_execution_checklist_from_diagnosis(
    diagnosis_path: str | Path,
    *,
    feed_key: str | None = None,
    run_group: str | None = None,
    audit_facts: object | None = None,
) -> GrowthAIVisibilitySourceHostExecutionChecklistOut:
    package = source_host_feed_package_from_diagnosis(
        diagnosis_path,
        feed_key=feed_key,
        run_group=run_group,
        audit_facts=audit_facts,
    )
    return source_host_execution_checklist_from_package(package)


def _recommendations(payload: dict[str, object]) -> list[tuple[int, dict[str, object]]]:
    raw = payload.get("recommended_source_host_executions")
    if not isinstance(raw, list):
        return []
    return [
        (index, item)
        for index, item in enumerate(raw, start=1)
        if isinstance(item, dict)
    ]


def _draft_from_recommendation(
    recommendation: dict[str, object],
    index: int,
    *,
    audit_facts: object | None,
) -> GrowthAIVisibilitySourceHostDraftOut:
    host = _host_for_surface(recommendation)
    draft_type = _draft_type_for_recommendation(recommendation, host)
    submit_url = DIRECTORY_SUBMIT_URLS.get(host, "")
    summary = _summary(recommendation)
    payload = _submission_payload(host)
    status = _status_for_draft(draft_type, submit_url, payload)
    status = _audit_status_override(host=host, status=status, audit_facts=audit_facts)
    if audit_facts:
        payload["source_host_audit_status"] = status
    return GrowthAIVisibilitySourceHostDraftOut(
        host=host,
        priority=index,
        draft_type=draft_type,
        status=status,
        target_url=submit_url or f"https://{host}/",
        submit_url=submit_url,
        title=_title_for_draft(host, draft_type),
        summary=summary,
        body_markdown=_body_markdown(host, draft_type, summary, payload),
        source_reference_url=submit_url or f"https://{host}/",
        submission_payload=payload,
        validation_command=str(
            recommendation.get("validation_command")
            or f'curl -fsS "https://{host}/" | grep -i "synapse"'
        ),
        probe_followup=str(recommendation.get("next_probe_command") or ""),
        operator_notes=_operator_notes(host, draft_type),
    )


def _audit_status_override(
    *,
    host: str,
    status: str,
    audit_facts: object | None,
) -> str:
    if not audit_facts:
        return status
    surface = source_host_surface(host)
    if surface in {source_host_surface(item) for item in audit_facts.live_surfaces}:
        return "already_live"
    if surface in {
        source_host_surface(item) for item in audit_facts.review_pending_surfaces
    }:
        return "review_pending_live_recheck"
    return status


def _host_for_surface(recommendation: dict[str, object]) -> str:
    surface = str(recommendation.get("surface") or "").strip().lower()
    if "." in surface:
        return surface
    return SURFACE_HOSTS.get(surface, surface or "unknown-source-host")


def _draft_type_for_recommendation(recommendation: dict[str, object], host: str) -> str:
    source_draft_type = str(recommendation.get("draft_type") or "")
    if source_draft_type == "brand_disambiguation_answer_block":
        return "owned_brand_disambiguation_refresh"
    if host in DIRECTORY_SUBMIT_URLS:
        return "directory_submission"
    return "contextual_partner_or_guest_pitch"


def _status_for_draft(
    draft_type: str, submit_url: str, payload: dict[str, object]
) -> str:
    if draft_type == "owned_brand_disambiguation_refresh":
        return "ready_to_publish_on_owned_channels"
    if payload.get("login_required"):
        return "operator_login_required"
    if submit_url:
        return "ready_to_submit"
    return "needs_operator_review"


def _title_for_draft(host: str, draft_type: str) -> str:
    if draft_type == "directory_submission":
        return "Synapse Network MCP Server"
    if draft_type == "owned_brand_disambiguation_refresh":
        return "Synapse Network MCP brand disambiguation block"
    return f"Synapse Network source-host opportunity for {host}"


def _summary(recommendation: dict[str, object]) -> str:
    return str(
        recommendation.get("content_brief")
        or recommendation.get("rationale")
        or "Create public, truthful source-host evidence for Synapse Network."
    )


def _submission_payload(host: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "server_name": "Synapse Network MCP Server",
        "short_description": (
            "Synapse Network Remote MCP lets AI agents discover payable APIs, "
            "invoke approved paid tools with bounded USDC spend, and retrieve receipts."
        ),
        "website_url": OFFICIAL_HOME,
        "github_repository_url": OFFICIAL_GITHUB_REPOSITORY,
        "npm_package": OFFICIAL_NPM_PACKAGE,
        "remote_mcp_endpoint": REMOTE_MCP_ENDPOINT,
        "tools": ["discover_services", "invoke_and_pay", "get_receipt"],
        "docs": OFFICIAL_DOCS,
        "contact_email": "support@synapse-network.ai",
        "stitch_figma_frame": "Directory Source-Host Submission Pack",
        "evidence_status": "pending_submission_not_external_citation",
    }
    return directory_submission_payload(host, payload)


def _body_markdown(
    host: str, draft_type: str, summary: str, payload: dict[str, object]
) -> str:
    if draft_type == "directory_submission":
        return "\n".join(
            [
                "# Synapse Network MCP Server",
                "",
                summary,
                "",
                f"- Remote MCP endpoint: {REMOTE_MCP_ENDPOINT}",
                "- Tools: discover_services, invoke_and_pay, get_receipt",
                f"- GitHub: {payload.get('github_repository_url', '')}",
                f"- npm: {payload.get('npm_package', '')}",
                f"- Docs: {OFFICIAL_DOCS}",
            ]
        )
    if draft_type == "owned_brand_disambiguation_refresh":
        return "\n".join(
            [
                "# Synapse Network MCP brand disambiguation block",
                "",
                summary,
                "",
                "Use these exact identity strings in public source hosts:",
                "",
                "1. SynapseNetwork MCP Server",
                "2. SynapseNetworkAI/Synapse-Network-MCP-Server",
                "3. io.github.SynapseNetworkAI/synapse-network-mcp-server",
                f"4. Hosted Remote MCP URL: {REMOTE_MCP_ENDPOINT}",
                "",
                "Owned publication targets:",
                f"Official source: {OFFICIAL_HOME}",
                f"MCP docs: {OFFICIAL_DOCS}",
                f"GitHub: {OFFICIAL_GITHUB_REPOSITORY}",
            ]
        )
    return "\n".join(
        [
            f"# Synapse Network source-host opportunity for {host}",
            "",
            summary,
            "",
            f"Official source: {OFFICIAL_HOME}",
            f"MCP docs: {OFFICIAL_DOCS}",
            f"Remote MCP endpoint: {REMOTE_MCP_ENDPOINT}",
        ]
    )


def _operator_notes(host: str, draft_type: str) -> list[str]:
    if draft_type != "directory_submission":
        return ["Review the source host and choose a truthful public mention path."]
    notes = [
        "Use the Directory Source-Host Submission Pack Stitch/Figma frame before filling the form.",
        "CLI probes can receive site-level blocks; verify through browser/form confirmation or a public listing URL.",
    ]
    if host == "aitoolnet.com":
        notes.append(
            "AIToolNet uses email submission to support@aitoolnet.com; record a send/draft receipt or screenshot."
        )
    if host == "alternativeto.net":
        notes.append(
            "AlternativeTo uses an authenticated community submission path; record browser, email, or community confirmation before marking submitted."
        )
    return notes


def _commands(feed_key: str, run_group: str) -> dict[str, str]:
    safe_run_group = run_group or "YYYY-MM-DD-after-presence-feed"
    return {
        "export_package": (
            "python scripts/growth/generate_ai_visibility_source_host_feed_package.py "
            f"--feed-key {feed_key} --run-group {safe_run_group}"
        ),
        "after_feed_probe": (
            "python scripts/growth/run_ai_visibility_api_probe.py "
            f"--feed-key {feed_key} --run-group {safe_run_group}-after-source-hosts "
            "--platforms chatgpt,claude,grok,gemini --execute"
        ),
        "compare": (
            'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons'
            f'?feed_key={feed_key}&run_group={safe_run_group}"'
        ),
    }


def _read_json(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload
