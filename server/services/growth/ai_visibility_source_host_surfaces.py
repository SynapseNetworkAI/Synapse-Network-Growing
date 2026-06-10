"""Canonical source-host surface keys for AI visibility evidence."""

from __future__ import annotations

from urllib.parse import urlparse

SOURCE_HOST_SURFACES = {
    "aitoolnet.com": "aitoolnet",
    "alternativeto.net": "alternativeto",
    "glama.ai": "glama",
    "glama_ai": "glama",
    "lobehub.com": "lobehub",
    "mcp.directory": "mcp_directory",
    "mcpfind.org": "mcpfind",
    "mcp-marketplace.io": "mcp_marketplace",
    "mcp.so": "mcp_so",
    "mcpservers.org": "mcpservers",
    "mysynap.com": "mysynap_com",
    "protodex.io": "protodex",
    "pulsemcp.com": "pulsemcp",
    "smithery.ai": "smithery",
    "smithery_ai": "smithery",
    "synapbus.dev": "synapbus_dev",
    "ubos.tech": "ubos_tech",
}


def source_host_surface(value: str) -> str:
    host = _host_value(value)
    if not host:
        return ""
    if host in SOURCE_HOST_SURFACES:
        return SOURCE_HOST_SURFACES[host]
    if host in SOURCE_HOST_SURFACES.values():
        return host
    return host.replace("-", "_").replace(".", "_")


def _host_value(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    parsed = urlparse(raw)
    host = parsed.netloc or parsed.path.split("/", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host
