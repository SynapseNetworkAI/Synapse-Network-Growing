"""Directory submission payloads for AI visibility source-host work."""

from __future__ import annotations


def directory_submission_payload(
    host: str, base_payload: dict[str, object]
) -> dict[str, object]:
    if host == "aitoolnet.com":
        return _aitoolnet_payload(base_payload)
    if host == "alternativeto.net":
        return _alternativeto_payload(base_payload)
    if host == "glama.ai":
        return _glama_payload(base_payload)
    if host == "lobehub.com":
        return _lobehub_payload(base_payload)
    if host in {"chat.mcp.so", "mcp.so"}:
        return _mcp_so_payload(host, base_payload)
    if host == "mcp.directory":
        return {
            **base_payload,
            "pypi_package": "",
            "form_fields": [
                "GitHub Repository URL",
                "NPM package",
                "PyPI package",
                "Short description",
                "Email",
            ],
        }
    if host == "mcpservers.org":
        return {
            **base_payload,
            "link": base_payload.get("github_repository_url", ""),
            "category": "finance",
            "category_label": "Finance",
            "plan": "free",
            "form_fields": [
                "name",
                "description",
                "url",
                "category",
                "email",
                "plan",
            ],
            "submission_method": (
                "Submit the free MCPServers form at https://mcpservers.org/submit; "
                "use category=finance and include the Remote MCP endpoint plus tool "
                "names in the description when the form has no dedicated fields."
            ),
            "premium_listing": False,
        }
    if host == "mcpfind.org":
        return {
            **base_payload,
            "submission_method": (
                "Submit the open-source MCPFind server form at "
                "https://mcpfind.org/submit; include the GitHub repository, npm "
                "package, hosted Remote MCP endpoint, and tool names."
            ),
            "listing_type": "Remote MCP server directory listing",
            "category": "payments",
            "tags": [
                "Remote MCP",
                "AI agent payments",
                "paid API discovery",
                "USDC settlement",
                "discover_services",
                "invoke_and_pay",
                "get_receipt",
            ],
            "form_fields": [
                "Server name",
                "Description",
                "GitHub repository URL",
                "npm package",
                "Remote MCP endpoint",
                "Docs URL",
                "Contact email",
            ],
            "browser_submission_required": True,
        }
    if host == "protodex.io":
        return _protodex_payload(base_payload)
    return {
        **base_payload,
        "login_required": host == "mcp-marketplace.io",
    }


def _aitoolnet_payload(base_payload: dict[str, object]) -> dict[str, object]:
    return {
        **base_payload,
        "tool_name": "SynapseNetwork MCP Server",
        "website_url": "https://www.synapse-network.ai/",
        "category": "AI agents / Developer tools / Payments",
        "submission_method": (
            "Email support@aitoolnet.com from the Synapse support mailbox."
        ),
        "email_subject": "Friend link - Synapse Network Listing",
        "email_body": _aitoolnet_email_body(),
        "pricing_or_plan": (
            "Free review queue; paid fast-track requires explicit operator approval."
        ),
        "listing_content": (
            "Synapse Network MCP Server is a Remote MCP endpoint for AI agents to "
            "discover callable APIs, invoke paid services with spend controls, and "
            "retrieve receipts. Remote endpoint: https://mcp.synapse-network.ai/mcp. "
            "GitHub: https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server. "
            "npm: @synapse-network-ai/mcp-server. Tools: discover_services, "
            "invoke_and_pay, get_receipt. Docs: https://docs.synapse-network.ai/mcp."
        ),
        "contact_email_notes": (
            "Operator-owned email only; required by the AIToolNet form. Use a Synapse "
            "contact email; do not use API keys, bearer tokens, or personal secret values."
        ),
        "submission_blocker": (
            "AIToolNet submission requires an operator email send/draft receipt or "
            "browser confirmation. Do not mark submitted until that evidence exists."
        ),
        "acceptance_terms": [
            "Remote MCP",
            "MCP server for paid API calls",
            "ChatGPT MCP app for API payments",
            "AI agent API monetization",
            "discover_services",
            "invoke_and_pay",
            "get_receipt",
        ],
        "browser_submission_required": True,
    }


def _aitoolnet_email_body() -> str:
    return (
        "Hello AIToolNet team,\n\n"
        "Please review SynapseNetwork MCP Server for an AIToolNet listing.\n\n"
        "Website: https://www.synapse-network.ai/\n"
        "GitHub: https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server\n"
        "npm: @synapse-network-ai/mcp-server\n"
        "Remote MCP endpoint: https://mcp.synapse-network.ai/mcp\n"
        "Category: AI agents / Developer tools / Payments\n"
        "Tools: discover_services, invoke_and_pay, get_receipt\n\n"
        "Short description: Remote MCP for paid API discovery, API invocation, "
        "USDC agent payments, and receipts.\n\n"
        "Thanks,\nSynapse Network"
    )


def _glama_payload(base_payload: dict[str, object]) -> dict[str, object]:
    return {
        **base_payload,
        "submission_method": "Submit GitHub repository for Glama indexing.",
        "github_repository_url": base_payload.get("github_repository_url", ""),
        "listing_type": "open-source MCP server",
        "indexed_metadata": [
            "tools",
            "schemas",
            "annotations",
            "Remote MCP endpoint",
        ],
        "acceptance_terms": [
            "MCP server for paid API calls",
            "Remote MCP",
            "AgentPay",
            "discover_services",
            "invoke_and_pay",
            "get_receipt",
        ],
        "browser_submission_required": True,
    }


def _lobehub_payload(base_payload: dict[str, object]) -> dict[str, object]:
    return {
        **base_payload,
        "submission_method": (
            "Verify or refresh the LobeHub MCP marketplace listing at "
            "https://lobehub.com/mcp. Use the public SynapseNetworkAI GitHub "
            "repository, npm package, Remote MCP endpoint, docs URL, and tool "
            "names; record the public listing URL as live evidence."
        ),
        "listing_type": "MCP marketplace listing",
        "category": "AI agents / Developer tools / Payments",
        "tags": [
            "Remote MCP",
            "AI agent payments",
            "paid API discovery",
            "AgentPay",
            "discover_services",
            "invoke_and_pay",
            "get_receipt",
        ],
        "form_fields": [
            "Server name",
            "Description",
            "GitHub repository URL",
            "npm package",
            "Remote MCP endpoint",
            "Docs URL",
            "Tools",
            "Contact email",
        ],
        "public_listing_url": (
            "https://lobehub.com/mcp/synapsenetworkai-synapse-network-mcp-server"
        ),
        "acceptance_terms": [
            "SynapseNetworkAI",
            "synapse-network-mcp-server",
            "Remote MCP",
            "discover_services",
            "invoke_and_pay",
            "get_receipt",
        ],
        "browser_submission_required": True,
    }


def _mcp_so_payload(host: str, base_payload: dict[str, object]) -> dict[str, object]:
    issue_url = "https://github.com/chatmcp/mcpso/issues/1"
    return {
        **base_payload,
        "submission_method": (
            f"Use the public {host}/submit form when an operator is signed in. "
            "If browser login is unavailable, add a listing comment to "
            "chatmcp/mcpso issue #1 and record the comment URL."
        ),
        "listing_type": "MCP directory listing",
        "submit_url": f"https://{host}/submit",
        "github_issue_repository": "chatmcp/mcpso",
        "github_issue_url": issue_url,
        "github_issue_comment_url": issue_url,
        "login_required": True,
        "submission_blocker": (
            f"{host} submit form requires site sign-in. GitHub issue #1 is the "
            "public fallback path for server links when no site session is "
            "available."
        ),
        "form_fields": [
            "Type",
            "Name",
            "URL",
            "Server Config",
        ],
        "server_config": {
            "mcpServers": {
                "synapse-network": {
                    "type": "streamable-http",
                    "url": "https://mcp.synapse-network.ai/mcp",
                    "headers": {
                        "Authorization": "Bearer <Synapse Agent Credential>",
                    },
                }
            }
        },
        "tags": [
            "Remote MCP",
            "paid API discovery",
            "agent payments",
            "AgentPay",
            "USDC settlement",
            "discover_services",
            "invoke_and_pay",
            "get_receipt",
        ],
        "acceptance_terms": [
            "Synapse Network",
            "SynapseNetworkAI",
            "synapse-network-mcp-server",
            "https://mcp.synapse-network.ai/mcp",
            "discover_services",
            "invoke_and_pay",
            "get_receipt",
        ],
    }


def _alternativeto_payload(base_payload: dict[str, object]) -> dict[str, object]:
    return {
        **base_payload,
        "software_name": "SynapseNetwork MCP Server",
        "website_url": "https://www.synapse-network.ai/",
        "login_required": True,
        "browser_submission_required": True,
        "manual_submission_required": True,
        "submission_method": (
            "Sign in to AlternativeTo and use the community add/suggest app "
            "flow from the live site. The previously generated direct submit "
            "URL returned HTTP 404 on 2026-06-10; if the UI does not expose "
            "an add-app path, contact hello@alternativeto.net or the public "
            "community channels from the AlternativeTo site and record that "
            "operator-owned confirmation."
        ),
        "submission_blocker": (
            "AlternativeTo requires an authenticated/manual community "
            "submission path; do not mark submitted until a browser receipt, "
            "email/community confirmation, or public listing URL exists."
        ),
        "categories": [
            "Developer Tools",
            "API",
            "Payment Processing",
            "AI Tools",
        ],
        "acceptance_terms": [
            "Remote MCP",
            "paid API discovery",
            "AI agent payments",
            "API monetization",
            "discover_services",
            "invoke_and_pay",
            "get_receipt",
        ],
    }


def _protodex_payload(base_payload: dict[str, object]) -> dict[str, object]:
    return {
        **base_payload,
        "submission_method": (
            "Open the Protodex GitHub issue prefill, submit the public "
            "SynapseNetworkAI MCP repository, category, and brief description, "
            "then record the issue URL as source-host submission evidence."
        ),
        "listing_type": "MCP server index listing",
        "category": "API Integration",
        "github_issue_repository": "LuciferForge/mcp-directory",
        "review_sla": "Protodex states submissions are reviewed and added within 7 days.",
        "form_fields": [
            "Repository URL",
            "Category",
            "Brief description",
        ],
        "tags": [
            "Remote MCP",
            "paid API discovery",
            "AI agent payments",
            "USDC settlement",
            "discover_services",
            "invoke_and_pay",
            "get_receipt",
        ],
        "browser_submission_required": False,
    }
