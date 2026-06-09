"""Source-host driven presence plan for answer-engine visibility."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from server.schemas_growth import (
    GrowthAIVisibilityPresenceActionOut,
    GrowthAIVisibilityPresencePlanOut,
)
from server.services.growth import ai_visibility_discovery
from server.services.growth.ai_visibility_directory_submission_payloads import (
    directory_submission_payload,
)
from server.services.growth.ai_visibility_source_host_directory_config import (
    DIRECTORY_SUBMIT_URLS,
)
from server.services.growth.ai_visibility_text import unique_strings

DEFAULT_FEED_KEY = "mcp_paid_api_discovery"
DEFAULT_RUN_GROUP = "latest"

DIRECTORY_HOSTS = {
    "aitoolnet.com",
    "alternativeto.net",
    "glama.ai",
    "mcpservers.org",
    "mcp.directory",
    "mcpfind.org",
    "mcp-marketplace.io",
    "lobehub.com",
    "protodex.io",
    "pulsemcp.com",
}
CONTROLLED_HOSTS = {
    "github.com",
    "registry.modelcontextprotocol.io",
    "smithery.ai",
}
COMPETITOR_HOSTS = {
    "docs.mcpay.tech",
    "docs.latchmcp.app",
    "mcp.magpie.im",
    "teleport.ltd",
    "docs.stripe.com",
    "anythingmcp.com",
    "mcpsynapse.dev",
}
BRAND_COLLISION_HOSTS = {
    "python-docs.synapse.org",
    "synapse.org",
}
OFFICIAL_GITHUB_REPOSITORY = (
    "https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server"
)
OFFICIAL_NPM_PACKAGE = "@synapse-network-ai/mcp-server"
REMOTE_MCP_ENDPOINT = "https://mcp.synapse-network.ai/mcp"
OFFICIAL_CONTACT_EMAIL = "support@synapse-network.ai"
LISTING_DESCRIPTION = (
    "Synapse Network Remote MCP lets AI agents discover payable APIs, invoke "
    "approved paid tools with bounded USDC spend, and retrieve settlement receipts."
)
OFFICIAL_DOCS_URL = "https://docs.synapse-network.ai/mcp/paid-api-calls"
COMPARISON_DOCS_URL = "https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp"


def ai_visibility_presence_plan(
    db: Session,
    *,
    feed_key: str = DEFAULT_FEED_KEY,
    run_group: str | None = None,
) -> GrowthAIVisibilityPresencePlanOut:
    safe_feed_key = (feed_key or DEFAULT_FEED_KEY).strip()
    comparison = _latest_comparison(db, feed_key=safe_feed_key, run_group=run_group)
    safe_run_group = comparison.run_group if comparison else (run_group or "")
    source_hosts = comparison.source_hosts if comparison else []
    actions = _presence_actions(source_hosts)
    blockers = _blockers(source_hosts, actions)
    return GrowthAIVisibilityPresencePlanOut(
        generated_at=datetime.now(timezone.utc),
        feed_key=safe_feed_key,
        run_group=safe_run_group,
        status="ready_for_presence_work" if actions else "blocked_until_source_hosts",
        source_hosts=source_hosts,
        actions=actions,
        blockers=blockers,
        validation_commands=_validation_commands(safe_feed_key, safe_run_group),
        next_probe_command=_next_probe_command(safe_feed_key),
        compare_command=(
            'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons'
            f'?feed_key={safe_feed_key}"'
        ),
    )


def _latest_comparison(db: Session, *, feed_key: str, run_group: str | None):
    comparisons = ai_visibility_discovery.list_ai_comparisons(
        db,
        feed_key=feed_key,
        run_group=run_group,
        limit=20,
    ).items
    if not comparisons:
        return None
    if run_group:
        return comparisons[0]
    return max(comparisons, key=lambda item: item.latest_run_at or datetime.min)


def _presence_actions(
    source_hosts: list[str],
) -> list[GrowthAIVisibilityPresenceActionOut]:
    actions = [
        _action_for_host(host, index=index)
        for index, host in enumerate(source_hosts[:10], start=1)
    ]
    return [action for action in actions if action is not None]


def _action_for_host(
    host: str, *, index: int
) -> GrowthAIVisibilityPresenceActionOut | None:
    normalized = host.strip().lower()
    if not normalized:
        return None
    if normalized in DIRECTORY_HOSTS:
        return _directory_action(normalized, index)
    if normalized in CONTROLLED_HOSTS:
        return _controlled_action(normalized, index)
    if normalized in COMPETITOR_HOSTS:
        return _competitor_action(normalized, index)
    if normalized in BRAND_COLLISION_HOSTS:
        return _brand_collision_action(normalized, index)
    return _monitor_action(normalized, index)


def _directory_action(host: str, index: int) -> GrowthAIVisibilityPresenceActionOut:
    submit_url = DIRECTORY_SUBMIT_URLS.get(host, "")
    operator_notes = []
    if host == "mcp-marketplace.io":
        operator_notes.append(
            "Login appears required before submission; use the operator-owned directory account."
        )
    if host in {"aitoolnet.com", "alternativeto.net", "glama.ai"}:
        operator_notes.extend(
            [
                "Use the Directory Source-Host Submission Pack Stitch/Figma frame before filling the browser form.",
                "CLI probes can receive site-level 403; verify through browser/form confirmation or a public listing URL.",
            ]
        )
    if host == "aitoolnet.com":
        operator_notes.extend(
            [
                "AIToolNet finish page asks listings to email support@aitoolnet.com; "
                "send from support@synapse-network.ai or another operator-owned "
                "Synapse mailbox.",
                "Do not mark AIToolNet submitted from CLI reachability alone; "
                "require an email draft/send receipt, browser confirmation screen, "
                "or screenshot.",
            ]
        )
    return _action(
        host=host,
        priority=index,
        action_type="directory_listing",
        ownership="submittable",
        rationale=(
            "ChatGPT cited this MCP directory or marketplace for paid MCP queries; "
            "a Synapse listing or update can become a candidate source."
        ),
        target_surface=f"https://{host}/",
        asset="Synapse Remote MCP listing metadata with endpoint, tools, GitHub, npm, and docs links.",
        validation_command=f'curl -fsS "https://{host}/" | grep -i "synapse"',
        submit_url=submit_url,
        source_reference_url=submit_url or f"https://{host}/",
        submission_payload=_directory_payload(host),
        operator_notes=operator_notes,
    )


def _controlled_action(host: str, index: int) -> GrowthAIVisibilityPresenceActionOut:
    return _action(
        host=host,
        priority=index,
        action_type="owned_or_partner_listing",
        ownership="controlled_or_authorized",
        rationale=(
            "This host can carry official Synapse facts through GitHub, registry, "
            "or directory metadata controlled by SynapseNetworkAI."
        ),
        target_surface=f"https://{host}/",
        asset="Official SynapseNetwork MCP README/listing with Remote MCP endpoint and payment-tool facts.",
        validation_command=f'curl -fsS "https://{host}/" >/dev/null',
        source_reference_url=f"https://{host}/",
        submission_payload=_controlled_payload(host),
    )


def _competitor_action(host: str, index: int) -> GrowthAIVisibilityPresenceActionOut:
    return _action(
        host=host,
        priority=index,
        action_type="comparison_presence",
        ownership="not_directly_editable",
        rationale=(
            "ChatGPT cited this competitor or alternative surface; Synapse should "
            "strengthen equivalent comparison pages and third-party mentions."
        ),
        target_surface=f"https://{host}/",
        asset="Synapse-vs-paid-MCP comparison block plus social/GitHub references naming this alternative.",
        validation_command=(
            "curl -fsS https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp "
            f'| grep -i "{host.split(".")[0]}"'
        ),
        source_reference_url=f"https://{host}/",
        submission_payload=_comparison_payload(host),
        operator_notes=[
            "Do not submit to competitor-owned docs; publish equivalent comparison evidence on owned channels."
        ],
    )


def _brand_collision_action(
    host: str, index: int
) -> GrowthAIVisibilityPresenceActionOut:
    return _action(
        host=host,
        priority=index,
        action_type="brand_disambiguation",
        ownership="owned_content_required",
        rationale=(
            "Answer engines are using this non-Synapse-Network source for exact "
            "SynapseNetwork MCP queries; official source hosts need stronger "
            "identity and disambiguation language."
        ),
        target_surface=COMPARISON_DOCS_URL,
        asset=(
            "Owned docs/README/registry disambiguation block naming Synapse Network, "
            "SynapseNetworkAI/Synapse-Network-MCP-Server, the hosted Remote MCP "
            "endpoint, and the Synapse.org/Sage Bionetworks distinction."
        ),
        validation_command=(
            "curl -fsS https://docs.synapse-network.ai/mcp/paid-api-calls "
            "| grep -i 'Sage Bionetworks'"
        ),
        source_reference_url=f"https://{host}/",
        submission_payload={
            "collision_host": host,
            "owned_docs_url": OFFICIAL_DOCS_URL,
            "owned_comparison_url": COMPARISON_DOCS_URL,
            "github_repository_url": OFFICIAL_GITHUB_REPOSITORY,
            "official_registry_query": (
                "io.github.SynapseNetworkAI/synapse-network-mcp-server"
            ),
            "exact_identifier_queries": [
                "SynapseNetwork MCP Server",
                "SynapseNetworkAI Synapse-Network-MCP-Server",
                "io.github.SynapseNetworkAI/synapse-network-mcp-server",
                "https://mcp.synapse-network.ai/mcp discover_services",
            ],
            "recommended_copy": (
                "Synapse Network MCP Server is the Remote MCP endpoint for AI "
                "agents buying paid APIs through Synapse Network at "
                "synapse-network.ai. It is separate from Synapse.org and Sage "
                "Bionetworks biomedical data infrastructure."
            ),
            "evidence_status": "pending_owned_disambiguation_publication",
        },
        operator_notes=[
            "Publish on owned docs and GitHub first; do not request edits to the unrelated Synapse.org site.",
            "After publication, rerun exact identifier probes before changing directory priorities.",
        ],
    )


def _monitor_action(host: str, index: int) -> GrowthAIVisibilityPresenceActionOut:
    return _action(
        host=host,
        priority=index,
        action_type="monitor_and_contextual_feed",
        ownership="unknown",
        rationale=(
            "The host appeared in ChatGPT source evidence; inspect whether it has "
            "a directory, comparison, or roundup surface that can mention Synapse."
        ),
        target_surface=f"https://{host}/",
        asset="Contextual mention opportunity or evidence-only monitor entry.",
        validation_command=f'curl -I -sS "https://{host}/" | head -5',
        source_reference_url=f"https://{host}/",
        submission_payload={
            "inspection_goal": (
                "Find a directory, marketplace, roundup, guest post, or comparison "
                "surface where Synapse can be listed without misrepresenting ownership."
            ),
            "official_facts_url": OFFICIAL_DOCS_URL,
            "remote_mcp_endpoint": REMOTE_MCP_ENDPOINT,
        },
    )


def _action(
    *,
    host: str,
    priority: int,
    action_type: str,
    ownership: str,
    rationale: str,
    target_surface: str,
    asset: str,
    validation_command: str,
    submit_url: str = "",
    source_reference_url: str = "",
    submission_payload: dict[str, object] | None = None,
    operator_notes: list[str] | None = None,
) -> GrowthAIVisibilityPresenceActionOut:
    return GrowthAIVisibilityPresenceActionOut(
        host=host,
        priority=priority,
        action_type=action_type,
        ownership=ownership,
        rationale=rationale,
        target_surface=target_surface,
        asset=asset,
        copy_points=[
            "Synapse Network is the settlement layer for AI agents buying paid APIs.",
            f"Remote MCP endpoint: {REMOTE_MCP_ENDPOINT}",
            "Tools: discover_services, invoke_and_pay, get_receipt",
            f"Official docs: {OFFICIAL_DOCS_URL}",
            f"Comparison: {COMPARISON_DOCS_URL}",
        ],
        validation_command=validation_command,
        probe_followup=(
            "Rerun the unchanged ChatGPT/Claude/Grok/Gemini probe matrix after the listing "
            "or comparison asset is live and indexed."
        ),
        submit_url=submit_url,
        source_reference_url=source_reference_url,
        submission_payload=submission_payload or {},
        operator_notes=operator_notes or [],
    )


def _directory_payload(host: str) -> dict[str, object]:
    return directory_submission_payload(
        host,
        {
            "server_name": "Synapse Network MCP Server",
            "short_description": LISTING_DESCRIPTION,
            "github_repository_url": OFFICIAL_GITHUB_REPOSITORY,
            "npm_package": OFFICIAL_NPM_PACKAGE,
            "remote_mcp_endpoint": REMOTE_MCP_ENDPOINT,
            "tools": ["discover_services", "invoke_and_pay", "get_receipt"],
            "website": "https://www.synapse-network.ai/",
            "docs": OFFICIAL_DOCS_URL,
            "contact_email": OFFICIAL_CONTACT_EMAIL,
            "stitch_figma_frame": "Directory Source-Host Submission Pack",
            "evidence_status": "pending_submission_not_external_citation",
        },
    )


def _controlled_payload(host: str) -> dict[str, object]:
    return {
        "host": host,
        "github_repository_url": OFFICIAL_GITHUB_REPOSITORY,
        "npm_package": OFFICIAL_NPM_PACKAGE,
        "remote_mcp_endpoint": REMOTE_MCP_ENDPOINT,
        "metadata_updates": [
            "Remote MCP endpoint",
            "OAuth/BYOK auth boundary",
            "discover_services/invoke_and_pay/get_receipt tools",
            "paid API settlement and receipt facts",
        ],
    }


def _comparison_payload(host: str) -> dict[str, object]:
    return {
        "competitor_host": host,
        "owned_comparison_url": COMPARISON_DOCS_URL,
        "recommended_copy_angle": (
            "Explain how Synapse differs from paid MCP alternatives by combining "
            "Remote MCP discovery, bounded agent spend, USDC settlement, and receipts."
        ),
        "source_hosts_to_monitor": [host],
    }


def _blockers(
    source_hosts: list[str], actions: list[GrowthAIVisibilityPresenceActionOut]
) -> list[str]:
    blockers = []
    if not source_hosts:
        blockers.append(
            "No source_hosts metadata has been recorded; rerun API probes before planning third-party presence."
        )
    if not actions:
        blockers.append("No actionable source-host presence targets were generated.")
    return unique_strings(blockers)


def _validation_commands(feed_key: str, run_group: str) -> list[str]:
    safe_run_group = run_group or "YYYY-MM-DD-after-presence-feed"
    return [
        (
            "python scripts/growth/run_ai_visibility_feed_validation.py "
            f"--feed-key {feed_key}"
        ),
        (
            "python scripts/growth/generate_ai_visibility_probe_matrix.py "
            f"--feed-key {feed_key}"
        ),
        (
            "python scripts/growth/run_ai_visibility_api_probe.py "
            f"--feed-key {feed_key} --run-group {safe_run_group} "
            "--platforms chatgpt --execute"
        ),
    ]


def _next_probe_command(feed_key: str) -> str:
    return (
        "python scripts/growth/run_ai_visibility_api_probe.py "
        f"--feed-key {feed_key} "
        "--run-group YYYY-MM-DD-after-presence-feed "
        "--platforms chatgpt,claude,grok,gemini "
        "--output docs/archive/evidence/growth/ai-visibility/"
        "YYYY-MM-DD-after-presence-feed-external-probes.jsonl "
        "--execute"
    )
