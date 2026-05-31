"""MCP server release catalog constants."""

MCP_REPO_FULL_NAME = "SynapseNetworkAI/Synapse-Network-MCP-Server"
MCP_REPO_PATH_ENV = "SYNAPSE_MCP_SERVER_REPO_PATH"
MCP_RELEASE_CONFIRM_PREFIX = "PUBLISH_MCP_"
MCP_LOCAL_RUN_PREFIX = "local-mcp-run:"

MCP_RELEASE_STATUSES = {
    "planned",
    "readiness_running",
    "ready_to_publish",
    "npm_publishing",
    "npm_published",
    "registry_submitting",
    "registry_listed",
    "prod_smoke_running",
    "directories_pending",
    "completed",
    "failed",
    "cancelled",
}
MCP_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

DEFAULT_MCP_SERVER = {
    "server_key": "synapse-network-mcp-server",
    "server_name": "SynapseNetwork MCP Server",
    "package_name": "@synapse-network-ai/mcp-server",
    "package_registry": "npm",
    "registry_name": "io.github.synapsenetworkai/synapse-network-mcp-server",
    "install_command": "npx -y @synapse-network-ai/mcp-server",
    "package_url_template": "https://www.npmjs.com/package/{package_name}/v/{version}",
    "registry_url": "https://registry.modelcontextprotocol.io/servers/io.github.synapsenetworkai/synapse-network-mcp-server",
}

DEFAULT_SURFACES: tuple[tuple[str, str], ...] = (
    ("official_mcp_registry", "Official MCP Registry"),
    ("smithery", "Smithery"),
    ("pulsemcp", "PulseMCP"),
    ("glama", "Glama MCP Directory"),
    ("mcp_so", "mcp.so / MCP.so"),
    ("awesome_mcp_servers", "Awesome MCP servers"),
)

MCP_SURFACE_STATUSES = {
    "candidate",
    "package_ready",
    "registry_submitted",
    "listed",
    "verified",
    "needs_fix",
}
