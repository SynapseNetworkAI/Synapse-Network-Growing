"""Source-host feed package for answer-engine presence work."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from server.schemas_growth import (
    GrowthAIVisibilitySourceHostExecutionChecklistOut,
    GrowthAIVisibilitySourceHostDraftOut,
    GrowthAIVisibilitySourceHostFeedPackageOut,
)
from server.services.growth.ai_visibility_source_host_checklist_helpers import (
    source_host_execution_checklist_from_package,
)
from server.services.growth.ai_visibility_presence_plan import (
    DEFAULT_FEED_KEY,
    REMOTE_MCP_ENDPOINT,
    ai_visibility_presence_plan,
)

OFFICIAL_HOME = "https://www.synapse-network.ai/"
OFFICIAL_DOCS = "https://docs.synapse-network.ai/mcp/paid-api-calls"
COMPARISON_DOCS = "https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp"


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
    return source_host_execution_checklist_from_package(package)


def _draft_from_action(action) -> GrowthAIVisibilitySourceHostDraftOut:
    if action.action_type == "directory_listing":
        return _directory_draft(action)
    if action.action_type == "comparison_presence":
        return _comparison_draft(action)
    return _contextual_draft(action)


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
                f"- Stitch/Figma frame: {action.submission_payload.get('stitch_figma_frame', 'Directory Source-Host Submission Pack')}",
                f"- Evidence status: {action.submission_payload.get('evidence_status', 'pending_submission_not_external_citation')}",
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
    competitor = action.host.split(".")[0]
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
