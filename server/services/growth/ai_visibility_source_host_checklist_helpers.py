"""Shared source-host execution checklist helpers."""

from __future__ import annotations

from pathlib import Path

from server.schemas_growth import (
    GrowthAIVisibilitySourceHostDraftOut,
    GrowthAIVisibilitySourceHostExecutionItemOut,
    GrowthAIVisibilitySourceHostExecutionChecklistOut,
    GrowthAIVisibilitySourceHostFeedPackageOut,
    GrowthAIVisibilitySourceHostSubmissionFieldOut,
)
from server.services.growth.ai_visibility_source_host_live_listing import (
    live_listing_search_urls,
    live_listing_validation_steps,
)
from server.services.growth.ai_visibility_source_host_live_evidence import (
    latest_live_evidence,
)
from server.services.growth.ai_visibility_source_host_surfaces import (
    source_host_surface,
)

REMOTE_MCP_ENDPOINT = "https://mcp.synapse-network.ai/mcp"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
OFFICIAL_HOME = "https://www.synapse-network.ai/"
OFFICIAL_DOCS = "https://docs.synapse-network.ai/mcp/paid-api-calls"
CONTACT_EMAIL_NOTES = (
    "Operator-owned email only; required when the directory form asks for contact or "
    "account email; do not enter API keys or bearer tokens."
)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SUBMISSION_FIELD_KEYS = (
    "server_name",
    "website_url",
    "short_description",
    "github_repository_url",
    "npm_package",
    "remote_mcp_endpoint",
    "tools",
    "docs",
    "contact_email",
)
SUBMISSION_FIELD_KEYS_BY_HOST = {
    "mcpservers.org": (
        "server_name",
        "short_description",
        "link",
        "category",
        "contact_email",
        "plan",
        "remote_mcp_endpoint",
        "tools",
        "docs",
    ),
    "mcp.directory": (
        "github_repository_url",
        "npm_package",
        "pypi_package",
        "short_description",
        "contact_email",
        "remote_mcp_endpoint",
        "tools",
    ),
    "mcpfind.org": (
        "server_name",
        "short_description",
        "github_repository_url",
        "npm_package",
        "remote_mcp_endpoint",
        "tools",
        "docs",
        "contact_email",
        "category",
    ),
    "lobehub.com": (
        "server_name",
        "short_description",
        "github_repository_url",
        "npm_package",
        "remote_mcp_endpoint",
        "tools",
        "docs",
        "contact_email",
        "category",
    ),
    "protodex.io": (
        "github_repository_url",
        "category",
        "short_description",
        "remote_mcp_endpoint",
        "tools",
        "docs",
    ),
    "alternativeto.net": DEFAULT_SUBMISSION_FIELD_KEYS[:-1],
    "aitoolnet.com": (
        "server_name",
        "website_url",
        "short_description",
        "category",
        "pricing_or_plan",
        "listing_content",
        "github_repository_url",
        "npm_package",
        "remote_mcp_endpoint",
        "tools",
        "docs",
        "contact_email",
    ),
}


def source_host_execution_item(
    draft: GrowthAIVisibilitySourceHostDraftOut,
    commands: dict[str, str],
) -> GrowthAIVisibilitySourceHostExecutionItemOut:
    latest_live = latest_live_evidence(draft.host)
    return GrowthAIVisibilitySourceHostExecutionItemOut(
        key=f"{draft.priority:02d}-{draft.host}-{draft.draft_type}",
        host=draft.host,
        priority=draft.priority,
        draft_type=draft.draft_type,
        execution_status=_execution_status(draft),
        target_url=draft.submit_url or draft.target_url,
        design_handoff_frame=str(
            draft.submission_payload.get("stitch_figma_frame") or ""
        ),
        action_required=_action_required(draft),
        submission_fields=_submission_fields(draft),
        submission_steps=_submission_steps(draft),
        evidence_recording_steps=_evidence_recording_steps(draft),
        live_listing_search_urls=live_listing_search_urls(
            host=draft.host,
            draft_type=draft.draft_type,
            target_url=draft.target_url,
        ),
        live_listing_validation_steps=live_listing_validation_steps(
            host=draft.host,
            draft_type=draft.draft_type,
        ),
        latest_live_evidence_status=latest_live.status,
        latest_live_missing_terms=latest_live.missing_terms,
        latest_live_evidence_url=latest_live.source_url,
        latest_live_validation_summary=latest_live.validation_summary,
        required_evidence=_required_evidence(draft),
        submission_confirmation_command=_submission_confirmation_command(draft),
        validation_command=draft.validation_command,
        re_probe_command=commands.get("after_feed_probe", ""),
        completion_gate=(
            "Do not mark complete until operator evidence proves the listing, "
            "owned page, or partner mention is live; then rerun unchanged probes."
        ),
    )


def source_host_execution_checklist_from_package(
    package: GrowthAIVisibilitySourceHostFeedPackageOut,
) -> GrowthAIVisibilitySourceHostExecutionChecklistOut:
    items = [
        source_host_execution_item(draft, package.commands) for draft in package.drafts
    ]
    blockers = list(package.blockers)
    if not items:
        blockers.append("No source-host execution items are available.")
    return GrowthAIVisibilitySourceHostExecutionChecklistOut(
        generated_at=package.generated_at,
        feed_key=package.feed_key,
        run_group=package.run_group,
        status="ready_for_operator_execution" if items else "blocked_until_drafts",
        items=items,
        blockers=blockers,
        commands={
            "export_feed_package": package.commands.get("export_package", ""),
            "after_feed_probe": package.commands.get("after_feed_probe", ""),
            "compare": package.commands.get("compare", ""),
        },
    )


def _execution_status(draft: GrowthAIVisibilitySourceHostDraftOut) -> str:
    if draft.status == "already_live":
        return "already_live"
    if draft.status == "review_pending_live_recheck":
        return "review_pending_live_recheck"
    if draft.status == "ready_to_submit":
        return "pending_submission"
    if draft.status == "ready_to_publish_on_owned_channels":
        return "pending_owned_publish"
    if draft.status == "operator_login_required":
        return "pending_operator_login"
    return "pending_operator_review"


def _action_required(draft: GrowthAIVisibilitySourceHostDraftOut) -> str:
    if draft.status == "already_live":
        return "No submission action required; source-host evidence is already live."
    if draft.status == "review_pending_live_recheck":
        return (
            "Do not resubmit; recheck the review-pending listing until the public "
            "source-host page includes the required Synapse terms."
        )
    if draft.status == "operator_login_required":
        return (
            "Use an operator-owned account or contact path to complete the "
            "directory submission; record a browser receipt, email/community "
            "confirmation, or public listing URL."
        )
    actions = {
        "directory_submission": "Submit the directory form using the non-secret payload.",
        "owned_comparison_refresh": "Publish the comparison draft on owned docs or GitHub surfaces.",
        "contextual_partner_or_guest_pitch": "Inspect the host and create a truthful partner, roundup, or guest-post opportunity.",
    }
    return actions.get(
        draft.draft_type, "Review the draft and decide the next safe action."
    )


def _submission_fields(
    draft: GrowthAIVisibilitySourceHostDraftOut,
) -> list[GrowthAIVisibilitySourceHostSubmissionFieldOut]:
    if draft.draft_type != "directory_submission":
        return []
    common = _common_submission_fields(draft)
    return [common[key] for key in _submission_field_keys(draft.host) if key in common]


def _common_submission_fields(
    draft: GrowthAIVisibilitySourceHostDraftOut,
) -> dict[str, GrowthAIVisibilitySourceHostSubmissionFieldOut]:
    payload = draft.submission_payload
    return {
        "server_name": _field(
            "Server or product name",
            _payload_text(payload, "server_name", default=draft.title),
            "Use this for name/title fields.",
        ),
        "short_description": _field(
            "Short description",
            _payload_text(payload, "short_description", default=draft.summary),
            "Include Remote MCP, paid API discovery, spend bounds, USDC settlement, and receipts.",
        ),
        "link": _field(
            "Link",
            _payload_text(payload, "link", "github_repository_url"),
            "Use this for MCPServers' required GitHub or docs URL field.",
        ),
        "github_repository_url": _field(
            "GitHub repository URL",
            _payload_text(payload, "github_repository_url"),
            "Use the public SynapseNetworkAI MCP repository.",
        ),
        "npm_package": _field(
            "NPM package",
            _payload_text(payload, "npm_package"),
            "Leave unchanged unless the published package name changes.",
        ),
        "pypi_package": _field(
            "PyPI package",
            _payload_text(payload, "pypi_package"),
            "Use blank or not applicable if the form supports it.",
        ),
        "contact_email": _field(
            "Contact email",
            _payload_text(payload, "contact_email", default="<operator email>"),
            _payload_text(payload, "contact_email_notes", default=CONTACT_EMAIL_NOTES),
        ),
        "category": _field(
            "Category",
            _payload_text(
                payload,
                "category",
                default="AI agents / Developer tools / Payments",
            ),
            "Use the closest directory taxonomy if the exact category is unavailable.",
        ),
        "pricing_or_plan": _field(
            "Pricing or plan",
            _payload_text(payload, "pricing_or_plan", default="Free review queue"),
            "Choose the free/manual review queue unless the operator explicitly approves a paid listing or fast-track.",
        ),
        "plan": _field(
            "Plan",
            _payload_text(payload, "plan", default="free"),
            "Use the free listing path unless the operator explicitly approves a paid listing.",
        ),
        "listing_content": _field(
            "Listing content",
            _payload_text(
                payload,
                "listing_content",
                "short_description",
                default=draft.summary,
            ),
            "Paste only public product facts. Include Remote MCP endpoint, GitHub, npm, docs, and tool names; never include raw credentials.",
        ),
        "website_url": _field(
            "Website URL",
            _payload_text(payload, "website_url", "website", default=OFFICIAL_HOME),
            "Prefer the canonical www homepage.",
        ),
        "remote_mcp_endpoint": _field(
            "Remote MCP endpoint",
            _payload_text(
                payload,
                "remote_mcp_endpoint",
                default=REMOTE_MCP_ENDPOINT,
            ),
            "If the form lacks this field, include it in the description.",
        ),
        "tools": _field(
            "Tools",
            _payload_tools(payload),
            "If the form lacks this field, include these in the description.",
        ),
        "docs": _field(
            "Docs URL",
            _payload_text(payload, "docs", default=OFFICIAL_DOCS),
            "Use as the documentation/reference URL when available.",
        ),
    }


def _submission_field_keys(host: str) -> tuple[str, ...]:
    return SUBMISSION_FIELD_KEYS_BY_HOST.get(host, DEFAULT_SUBMISSION_FIELD_KEYS)


def _payload_text(
    payload: dict[str, object],
    *keys: str,
    default: str = "",
) -> str:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    return default


def _payload_tools(payload: dict[str, object]) -> str:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return ""
    return ", ".join(str(tool) for tool in tools)


def _field(
    label: str,
    value: str,
    notes: str = "",
) -> GrowthAIVisibilitySourceHostSubmissionFieldOut:
    return GrowthAIVisibilitySourceHostSubmissionFieldOut(
        label=label,
        value=value,
        notes=notes,
    )


def _submission_steps(draft: GrowthAIVisibilitySourceHostDraftOut) -> list[str]:
    if draft.status == "already_live":
        return []
    if draft.status == "review_pending_live_recheck":
        return [
            "Do not submit the form again while the directory review is pending.",
            "Open the live listing search URLs on a fixed cadence.",
            "Record live-listing evidence only after a public page includes the required Synapse terms.",
        ]
    if draft.draft_type != "directory_submission":
        return []
    return [
        f"Open {draft.submit_url or draft.target_url} in an operator-owned browser session.",
        "Fill only the non-secret submission fields from this checklist.",
        "Add the Remote MCP endpoint and tool list to the description if the form has no dedicated fields.",
        "Submit or save draft only after the browser preview matches the Synapse Remote MCP facts.",
        "Capture a screenshot or public receipt URL before marking the item submitted.",
    ]


def _evidence_recording_steps(draft: GrowthAIVisibilitySourceHostDraftOut) -> list[str]:
    if draft.status == "already_live":
        return [
            "Keep the existing live source-host evidence; rerun unchanged probes after the next new feed asset is live."
        ]
    if draft.status == "review_pending_live_recheck":
        return [
            "Use evidence-mode live-listing only after the public listing URL is accessible.",
            "Rerun unchanged ChatGPT/Claude/Grok/Gemini probes after live listing evidence exists.",
        ]
    if draft.draft_type != "directory_submission":
        return []
    surface = source_host_surface(draft.host)
    steps = [
        f"Record submission confirmation with --surface {surface}.",
        "Use evidence-mode submission-confirmation for a submitted-but-not-listed form receipt.",
        "Use evidence-mode live-listing only after the public listing URL is accessible.",
        "Rerun unchanged ChatGPT/Claude/Grok/Gemini probes after live listing evidence exists.",
    ]
    latest_live = latest_live_evidence(draft.host)
    if latest_live.status == "missing_required_terms":
        missing = ", ".join(latest_live.missing_terms) or "required terms"
        steps.insert(
            0,
            (
                "Latest live check failed for this source host; missing terms: "
                f"{missing}. Treat this as an operator submission/update blocker."
            ),
        )
    return steps


def _required_evidence(draft: GrowthAIVisibilitySourceHostDraftOut) -> list[str]:
    if draft.status == "already_live":
        return ["existing_live_source_host_evidence"]
    if draft.status == "review_pending_live_recheck":
        return ["public_listing_url", "live_curl_or_browser_validation"]
    if draft.draft_type == "directory_submission":
        return ["submission_url_or_receipt", "submitted_payload_summary", "screenshot"]
    if draft.draft_type == "owned_comparison_refresh":
        return ["published_url", "git_commit_or_pr", "live_curl_validation"]
    return ["review_notes", "target_contact_or_surface", "decision_or_published_url"]


def _submission_confirmation_command(
    draft: GrowthAIVisibilitySourceHostDraftOut,
) -> str:
    if draft.status in {"already_live", "review_pending_live_recheck"}:
        return ""
    if draft.draft_type != "directory_submission":
        return ""
    surface = source_host_surface(draft.host)
    return (
        "python scripts/growth/record_ai_visibility_source_host_execution.py "
        "--feed-key mcp_paid_api_discovery "
        "--run-group YYYY-MM-DD-after-directory-submission "
        f"--surface {surface} "
        f"--source-url {draft.submit_url or draft.target_url} "
        "--evidence-mode submission-confirmation "
        '--submitted-payload-summary "Submitted SynapseNetwork MCP Server with '
        "Remote MCP endpoint, GitHub, npm package, discover_services, "
        'invoke_and_pay, and get_receipt." '
        "--screenshot-url docs/archive/evidence/growth/ai-visibility/"
        f"YYYY-MM-DD-{surface}-submission.png "
        f'--design-handoff-frame "{draft.submission_payload.get("stitch_figma_frame", "")}" '
        "--target-platform chatgpt "
        "--target-platform claude "
        '--target-query "Synapse vs paid MCP alternatives" '
        "--output docs/archive/evidence/growth/ai-visibility/"
        f"YYYY-MM-DD-{surface}-submission-confirmation.json"
    )
