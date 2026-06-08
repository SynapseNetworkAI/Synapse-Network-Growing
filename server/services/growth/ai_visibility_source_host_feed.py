"""Source-host feed package for answer-engine presence work."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from server.schemas_growth import (
    GrowthAIVisibilitySourceHostExecutionChecklistOut,
    GrowthAIVisibilitySourceHostExecutionItemOut,
    GrowthAIVisibilitySourceHostDraftOut,
    GrowthAIVisibilitySourceHostFeedPackageOut,
)
from server.services.growth.ai_visibility_presence_plan import (
    DEFAULT_FEED_KEY,
    REMOTE_MCP_ENDPOINT,
    ai_visibility_presence_plan,
)

OFFICIAL_HOME = "https://www.synapse-network.ai/"
OFFICIAL_DOCS = "https://docs.synapse-network.ai/mcp/paid-api-calls"
COMPARISON_DOCS = "https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp"
COMPETITOR_LABELS = {
    "anythingmcp.com": "AnythingMCP",
    "docs.latchmcp.app": "Latch MCP",
    "docs.mcpay.tech": "MCPay",
    "docs.stripe.com": "Stripe",
    "mcp.magpie.im": "Magpie",
    "mcpsynapse.dev": "MCP Synapse",
    "teleport.ltd": "Teleport",
}


def ai_visibility_source_host_feed_package(
    db: Session,
    *,
    feed_key: str = DEFAULT_FEED_KEY,
    run_group: str | None = None,
) -> GrowthAIVisibilitySourceHostFeedPackageOut:
    plan = ai_visibility_presence_plan(db, feed_key=feed_key, run_group=run_group)
    drafts = [_draft_from_action(action) for action in plan.actions]
    blockers = list(plan.blockers)
    if not drafts:
        blockers.append("No source-host drafts were generated from the presence plan.")
    return GrowthAIVisibilitySourceHostFeedPackageOut(
        generated_at=datetime.now(timezone.utc),
        feed_key=plan.feed_key,
        run_group=plan.run_group,
        status="ready_for_operator_feed" if drafts else "blocked_until_source_hosts",
        source_hosts=plan.source_hosts,
        drafts=drafts,
        blockers=blockers,
        commands={
            "presence_plan": (
                "python scripts/growth/generate_ai_visibility_presence_plan.py "
                f"--feed-key {plan.feed_key}"
            ),
            "export_package": (
                "python scripts/growth/generate_ai_visibility_source_host_feed_package.py "
                f"--feed-key {plan.feed_key} "
                "--output docs/archive/evidence/growth/ai-visibility/"
                "YYYY-MM-DD-source-host-feed-package.json"
            ),
            "after_feed_probe": plan.next_probe_command,
            "compare": plan.compare_command,
        },
    )


def ai_visibility_source_host_execution_checklist(
    db: Session,
    *,
    feed_key: str = DEFAULT_FEED_KEY,
    run_group: str | None = None,
) -> GrowthAIVisibilitySourceHostExecutionChecklistOut:
    package = ai_visibility_source_host_feed_package(
        db,
        feed_key=feed_key,
        run_group=run_group,
    )
    items = [_execution_item(draft, package.commands) for draft in package.drafts]
    blockers = list(package.blockers)
    if not items:
        blockers.append("No source-host execution items are available.")
    return GrowthAIVisibilitySourceHostExecutionChecklistOut(
        generated_at=datetime.now(timezone.utc),
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


def _draft_from_action(action) -> GrowthAIVisibilitySourceHostDraftOut:
    if action.action_type == "directory_listing":
        return _directory_draft(action)
    if action.action_type == "comparison_presence":
        return _comparison_draft(action)
    if action.action_type == "brand_collision_disambiguation":
        return _brand_collision_draft(action)
    return _contextual_draft(action)


def _execution_item(
    draft: GrowthAIVisibilitySourceHostDraftOut,
    commands: dict[str, str],
) -> GrowthAIVisibilitySourceHostExecutionItemOut:
    return GrowthAIVisibilitySourceHostExecutionItemOut(
        key=f"{draft.priority:02d}-{draft.host}-{draft.draft_type}",
        host=draft.host,
        priority=draft.priority,
        draft_type=draft.draft_type,
        execution_status=_execution_status(draft),
        target_url=draft.submit_url or draft.target_url,
        action_required=_action_required(draft),
        required_evidence=_required_evidence(draft),
        validation_command=draft.validation_command,
        re_probe_command=commands.get("after_feed_probe", ""),
        completion_gate=(
            "Do not mark complete until operator evidence proves the listing, "
            "owned page, or partner mention is live; then rerun unchanged probes."
        ),
    )


def _execution_status(draft: GrowthAIVisibilitySourceHostDraftOut) -> str:
    if draft.status == "ready_to_submit":
        return "pending_submission"
    if draft.status == "ready_to_publish_on_owned_channels":
        return "pending_owned_publish"
    if draft.status == "operator_login_required":
        return "pending_operator_login"
    return "pending_operator_review"


def _action_required(draft: GrowthAIVisibilitySourceHostDraftOut) -> str:
    actions = {
        "directory_submission": "Submit the directory form using the non-secret payload.",
        "owned_comparison_refresh": "Publish the comparison draft on owned docs or GitHub surfaces.",
        "owned_brand_disambiguation_refresh": "Publish the disambiguation block on owned docs, llms.txt, and README surfaces.",
        "contextual_partner_or_guest_pitch": "Inspect the host and create a truthful partner, roundup, or guest-post opportunity.",
    }
    return actions.get(
        draft.draft_type, "Review the draft and decide the next safe action."
    )


def _required_evidence(draft: GrowthAIVisibilitySourceHostDraftOut) -> list[str]:
    if draft.draft_type == "directory_submission":
        return ["submission_url_or_receipt", "submitted_payload_summary", "screenshot"]
    if draft.draft_type == "owned_comparison_refresh":
        return ["published_url", "git_commit_or_pr", "live_curl_validation"]
    if draft.draft_type == "owned_brand_disambiguation_refresh":
        return [
            "published_url",
            "git_commit_or_pr",
            "llms_txt_validation",
            "unchanged_probe_rerun",
        ]
    return ["review_notes", "target_contact_or_surface", "decision_or_published_url"]


def _directory_draft(action) -> GrowthAIVisibilitySourceHostDraftOut:
    title = "Synapse Network MCP Server"
    return GrowthAIVisibilitySourceHostDraftOut(
        host=action.host,
        priority=action.priority,
        draft_type="directory_submission",
        status=_submission_status(action),
        target_url=action.submit_url or action.target_surface,
        submit_url=action.submit_url,
        title=title,
        summary=_directory_summary(action),
        body_markdown="\n".join(
            [
                f"# {title}",
                "",
                _directory_summary(action),
                "",
                f"- Remote MCP endpoint: {REMOTE_MCP_ENDPOINT}",
                "- Tools: discover_services, invoke_and_pay, get_receipt",
                f"- GitHub: {action.submission_payload.get('github_repository_url', '')}",
                f"- npm: {action.submission_payload.get('npm_package', '')}",
                f"- Docs: {OFFICIAL_DOCS}",
                "",
                "Synapse does not expose raw customer agent credentials to public listings.",
            ]
        ),
        source_reference_url=action.source_reference_url,
        submission_payload=action.submission_payload,
        validation_command=action.validation_command,
        probe_followup=action.probe_followup,
        operator_notes=action.operator_notes,
    )


def _comparison_draft(action) -> GrowthAIVisibilitySourceHostDraftOut:
    competitor = _competitor_label(action.host)
    title = f"Synapse Network vs {competitor} for paid MCP and agent payments"
    return GrowthAIVisibilitySourceHostDraftOut(
        host=action.host,
        priority=action.priority,
        draft_type="owned_comparison_refresh",
        status="ready_to_publish_on_owned_channels",
        target_url=COMPARISON_DOCS,
        title=title,
        summary=(
            "Publish or refresh an owned comparison block that names the cited "
            f"alternative `{action.host}` while keeping factual boundaries clear."
        ),
        body_markdown="\n".join(
            [
                f"# {title}",
                "",
                "Synapse Network combines Remote MCP discovery with scoped agent "
                "credentials, bounded paid API invocation, USDC settlement, and receipts.",
                "",
                f"The cited alternative surface is `{action.host}`. Compare on:",
                "",
                "- Remote MCP discovery for AI assistants",
                "- Spend limits and credential isolation",
                "- Payment receipts and provider settlement",
                "- Human confirmation for consequential paid actions",
                "",
                f"Official docs: {OFFICIAL_DOCS}",
            ]
        ),
        source_reference_url=action.source_reference_url,
        submission_payload=action.submission_payload,
        validation_command=action.validation_command,
        probe_followup=action.probe_followup,
        operator_notes=action.operator_notes,
    )


def _brand_collision_draft(action) -> GrowthAIVisibilitySourceHostDraftOut:
    collision_host = str(action.submission_payload.get("collision_host", action.host))
    title = f"Synapse Network official identity block for {collision_host}"
    answer_block = str(action.submission_payload.get("recommended_answer_block", ""))
    return GrowthAIVisibilitySourceHostDraftOut(
        host=action.host,
        priority=action.priority,
        draft_type="owned_brand_disambiguation_refresh",
        status="ready_to_publish_on_owned_channels",
        target_url=action.target_surface,
        title=title,
        summary=(
            "Publish an owned disambiguation block so answer engines do not map "
            f"SynapseNetworkAI MCP queries to `{collision_host}`."
        ),
        body_markdown="\n".join(
            [
                f"# {title}",
                "",
                "Answer-engine disambiguation block:",
                "",
                f"> {answer_block}",
                "",
                "Add this block to:",
                "",
                "- `docs.synapse-network.ai/mcp/synapse-vs-paid-mcp`",
                "- `www.synapse-network.ai/llms.txt` under official sources",
                "- SynapseNetworkAI MCP README / directory description",
                "",
                "Required official links:",
                "",
                *[
                    f"- {url}"
                    for url in action.submission_payload.get(
                        "required_official_links", []
                    )
                ],
            ]
        ),
        source_reference_url=action.source_reference_url,
        submission_payload=action.submission_payload,
        validation_command=action.validation_command,
        probe_followup=action.probe_followup,
        operator_notes=action.operator_notes,
    )


def _competitor_label(host: str) -> str:
    normalized = host.strip().lower()
    if normalized in COMPETITOR_LABELS:
        return COMPETITOR_LABELS[normalized]
    parts = [part for part in normalized.split(".") if part and part != "docs"]
    return parts[0] if parts else normalized


def _contextual_draft(action) -> GrowthAIVisibilitySourceHostDraftOut:
    title = f"Synapse Network contextual mention opportunity for {action.host}"
    return GrowthAIVisibilitySourceHostDraftOut(
        host=action.host,
        priority=action.priority,
        draft_type="contextual_partner_or_guest_pitch",
        status="needs_operator_review",
        target_url=action.target_surface,
        title=title,
        summary=(
            "Inspect this cited source host for a roundup, partner page, docs issue, "
            "guest post, or ecosystem listing that can truthfully mention Synapse."
        ),
        body_markdown="\n".join(
            [
                f"# {title}",
                "",
                "Pitch angle:",
                "",
                "Synapse Network is a settlement layer for AI agents that need to "
                "discover paid APIs, invoke approved tools with bounded spend, and "
                "retrieve receipts for each call.",
                "",
                "Suggested mention:",
                "",
                "> Synapse Network provides Remote MCP discovery and paid API "
                "settlement for AI agents, with scoped credentials, USDC settlement, "
                "and receipt evidence for each metered invocation.",
                "",
                f"Official source: {OFFICIAL_HOME}",
                f"MCP docs: {OFFICIAL_DOCS}",
            ]
        ),
        source_reference_url=action.source_reference_url,
        submission_payload=action.submission_payload,
        validation_command=action.validation_command,
        probe_followup=action.probe_followup,
        operator_notes=action.operator_notes,
    )


def _directory_summary(action) -> str:
    return str(
        action.submission_payload.get(
            "short_description",
            "Synapse Network Remote MCP lets AI agents discover payable APIs, invoke "
            "approved paid tools with bounded spend, and retrieve settlement receipts.",
        )
    )


def _submission_status(action) -> str:
    if action.submission_payload.get("login_required"):
        return "operator_login_required"
    if action.submit_url:
        return "ready_to_submit"
    return "needs_submit_surface_review"
