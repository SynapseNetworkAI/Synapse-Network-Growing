"""MCP server release catalog constants."""

MCP_REPO_FULL_NAME = "SynapseNetworkAI/Synapse-Network-MCP-Server"
MCP_REPO_PATH_ENV = "SYNAPSE_MCP_SERVER_REPO_PATH"
MCP_RELEASE_CONFIRM_PREFIX = "PUBLISH_MCP_"
MCP_REMOTE_PROD_CONFIRM_PHRASE = "DEPLOY_MCP_REMOTE_PROD"
MCP_LOCAL_RUN_PREFIX = "local-mcp-run:"
MCP_REMOTE_ENDPOINT_URL = "https://mcp.synapse-network.ai/mcp"
MCP_REMOTE_GCP_PROJECT_ID = "synapse-network-prod"
MCP_REMOTE_CLOUD_RUN_REGION = "us-central1"
MCP_REMOTE_CLOUD_RUN_SERVICE = "synapse-prod-mcp-server"

MCP_RELEASE_STATUSES = {
    "planned",
    "readiness_running",
    "ready_to_publish",
    "npm_publishing",
    "npm_published",
    "registry_submitting",
    "registry_listed",
    "prod_smoke_running",
    "remote_prod_ready",
    "remote_prod_deploying",
    "remote_prod_deployed",
    "openai_smoke_running",
    "remote_prod_verified",
    "directories_pending",
    "completed",
    "failed",
    "cancelled",
}
MCP_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
MCP_RUNNER_ACTIVE_STATUSES = (
    "readiness_running",
    "npm_publishing",
    "registry_submitting",
    "prod_smoke_running",
    "remote_prod_deploying",
    "remote_prod_deployed",
    "openai_smoke_running",
)

DEFAULT_MCP_SERVER = {
    "server_key": "synapse-network-mcp-server",
    "server_name": "SynapseNetwork MCP Server",
    "package_name": "@synapse-network-ai/mcp-server",
    "package_registry": "npm",
    "registry_name": "io.github.SynapseNetworkAI/synapse-network-mcp-server",
    "install_command": "npx -y @synapse-network-ai/mcp-server",
    "package_url_template": "https://www.npmjs.com/package/{package_name}/v/{version}",
    "registry_url": "https://registry.modelcontextprotocol.io/servers/io.github.SynapseNetworkAI/synapse-network-mcp-server",
    "repo_full_name": MCP_REPO_FULL_NAME,
    "repo_url": f"https://github.com/{MCP_REPO_FULL_NAME}",
    "local_repo_path": "/Users/cliff/workspace/agent/Synapse-Network-MCP-Server",
    "transport_kind": "both",
    "remote_endpoint_url": MCP_REMOTE_ENDPOINT_URL,
    "tools": ["discover_services", "invoke_and_pay", "get_receipt"],
    "security_boundary": (
        "Uses SYNAPSE_AGENT_KEY only. It never requests owner private keys, "
        "seed phrases, admin credentials, deposits, withdrawals, refunds, "
        "settlement controls, or provider setup permissions."
    ),
}

DEFAULT_DISCOVERY_SURFACES: tuple[dict[str, object], ...] = (
    {
        "surface_key": "npm_registry",
        "surface_label": "npm Registry",
        "category": "artifact",
        "requires_npm": False,
        "requires_remote_http": False,
        "supports_auto_submit": True,
        "submission_url": "https://www.npmjs.com/package/@synapse-network-ai/mcp-server",
        "docs_url": "https://docs.npmjs.com/cli/v10/commands/npm-publish",
        "priority": 10,
    },
    {
        "surface_key": "official_mcp_registry",
        "surface_label": "Official MCP Registry",
        "category": "official_registry",
        "requires_npm": True,
        "requires_remote_http": False,
        "supports_auto_submit": True,
        "submission_url": "https://registry.modelcontextprotocol.io/",
        "docs_url": "https://modelcontextprotocol.io/registry/quickstart",
        "priority": 20,
    },
    {
        "surface_key": "smithery",
        "surface_label": "Smithery",
        "category": "directory",
        "requires_npm": True,
        "requires_remote_http": False,
        "supports_auto_submit": False,
        "submission_url": "https://smithery.ai/",
        "docs_url": "https://smithery.ai/",
        "priority": 30,
    },
    {
        "surface_key": "pulsemcp",
        "surface_label": "PulseMCP",
        "category": "directory",
        "requires_npm": True,
        "requires_remote_http": False,
        "supports_auto_submit": False,
        "submission_url": "https://www.pulsemcp.com/",
        "docs_url": "https://www.pulsemcp.com/api",
        "priority": 40,
    },
    {
        "surface_key": "glama",
        "surface_label": "Glama MCP Directory",
        "category": "directory",
        "requires_npm": True,
        "requires_remote_http": False,
        "supports_auto_submit": False,
        "submission_url": "https://glama.ai/mcp/servers",
        "docs_url": "https://glama.ai/",
        "priority": 50,
    },
    {
        "surface_key": "mcp_so",
        "surface_label": "mcp.so / MCP.so",
        "category": "directory",
        "requires_npm": True,
        "requires_remote_http": False,
        "supports_auto_submit": False,
        "submission_url": "https://mcp.so/",
        "docs_url": "https://mcp.so/",
        "priority": 60,
    },
    {
        "surface_key": "awesome_mcp_servers",
        "surface_label": "Awesome MCP servers",
        "category": "directory",
        "requires_npm": True,
        "requires_remote_http": False,
        "supports_auto_submit": False,
        "submission_url": "https://github.com/punkpeye/awesome-mcp-servers",
        "docs_url": "https://github.com/punkpeye/awesome-mcp-servers",
        "priority": 70,
    },
    {
        "surface_key": "openai_remote_mcp",
        "surface_label": "OpenAI Remote MCP / Apps",
        "category": "llm_platform",
        "requires_npm": False,
        "requires_remote_http": True,
        "supports_auto_submit": False,
        "submission_url": "https://platform.openai.com/docs/mcp",
        "docs_url": "https://platform.openai.com/docs/mcp",
        "priority": 80,
    },
    {
        "surface_key": "claude_remote_mcp",
        "surface_label": "Claude MCP Connector",
        "category": "llm_platform",
        "requires_npm": False,
        "requires_remote_http": True,
        "supports_auto_submit": False,
        "submission_url": "https://docs.anthropic.com/en/docs/agents-and-tools/mcp-connector",
        "docs_url": "https://docs.anthropic.com/en/docs/agents-and-tools/mcp-connector",
        "priority": 90,
    },
    {
        "surface_key": "cursor_config",
        "surface_label": "Cursor MCP Config",
        "category": "client_config",
        "requires_npm": True,
        "requires_remote_http": False,
        "supports_auto_submit": False,
        "submission_url": "https://docs.cursor.com/context/model-context-protocol",
        "docs_url": "https://docs.cursor.com/context/model-context-protocol",
        "priority": 100,
    },
    {
        "surface_key": "vscode_mcp_config",
        "surface_label": "VS Code MCP Config",
        "category": "client_config",
        "requires_npm": True,
        "requires_remote_http": False,
        "supports_auto_submit": False,
        "submission_url": "https://code.visualstudio.com/docs/copilot/chat/mcp-servers",
        "docs_url": "https://code.visualstudio.com/docs/copilot/chat/mcp-servers",
        "priority": 110,
    },
)

DEFAULT_SURFACES: tuple[tuple[str, str], ...] = tuple(
    (str(surface["surface_key"]), str(surface["surface_label"]))
    for surface in DEFAULT_DISCOVERY_SURFACES
)

MCP_SURFACE_STATUSES = {
    "candidate",
    "blocked_missing_artifact",
    "blocked_requires_remote_mcp",
    "package_ready",
    "submitted",
    "registry_submitted",
    "under_review",
    "listed",
    "verified",
    "needs_fix",
    "failed",
}

MCP_SURFACE_CATEGORIES = {
    "artifact",
    "official_registry",
    "directory",
    "llm_platform",
    "client_config",
}

MCP_SERVER_TRANSPORT_KINDS = {"stdio", "remote_http", "both"}
MCP_SURFACE_CONFIG_STATUSES = {
    "not_configured",
    "configured",
    "verified",
    "expired",
    "blocked",
}
MCP_SURFACE_SUBMISSION_MODES = {"auto", "semi_auto", "manual", "readonly"}
MCP_SURFACE_AUTH_MODES = {
    "none",
    "env_token",
    "github-device",
    "github-oidc",
    "dns",
    "http",
    "oauth",
    "api_key",
    "manual",
}

DEFAULT_SURFACE_CONFIGS: dict[str, dict[str, object]] = {
    "npm_registry": {
        "submission_mode": "auto",
        "auth_mode": "env_token",
        "credential_ref": "env:NODE_AUTH_TOKEN|NPM_TOKEN",
        "required_env_vars": ["NODE_AUTH_TOKEN|NPM_TOKEN"],
    },
    "official_mcp_registry": {
        "submission_mode": "auto",
        "auth_mode": "github-device",
        "credential_ref": "local:mcp-publisher",
        "required_env_vars": [],
    },
    "smithery": {
        "submission_mode": "semi_auto",
        "auth_mode": "manual",
        "credential_ref": "",
        "required_env_vars": [],
    },
    "pulsemcp": {
        "submission_mode": "manual",
        "auth_mode": "manual",
        "credential_ref": "",
        "required_env_vars": [],
    },
    "glama": {
        "submission_mode": "semi_auto",
        "auth_mode": "manual",
        "credential_ref": "",
        "required_env_vars": [],
    },
    "mcp_so": {
        "submission_mode": "manual",
        "auth_mode": "manual",
        "credential_ref": "",
        "required_env_vars": [],
    },
    "awesome_mcp_servers": {
        "submission_mode": "semi_auto",
        "auth_mode": "env_token",
        "credential_ref": "env:GITHUB_TOKEN",
        "required_env_vars": ["GITHUB_TOKEN"],
    },
    "openai_remote_mcp": {
        "submission_mode": "readonly",
        "auth_mode": "none",
        "credential_ref": "",
        "required_env_vars": [],
    },
    "claude_remote_mcp": {
        "submission_mode": "readonly",
        "auth_mode": "none",
        "credential_ref": "",
        "required_env_vars": [],
    },
    "cursor_config": {
        "submission_mode": "readonly",
        "auth_mode": "none",
        "credential_ref": "",
        "required_env_vars": [],
    },
    "vscode_mcp_config": {
        "submission_mode": "readonly",
        "auth_mode": "none",
        "credential_ref": "",
        "required_env_vars": [],
    },
}
