"""Canonical source-host surface keys for AI visibility evidence."""

from __future__ import annotations

from urllib.parse import urlparse

SOURCE_HOST_SURFACES = {
    "aitoolnet.com": "aitoolnet",
    "alternativeto.net": "alternativeto",
    "mcp.directory": "mcp_directory",
    "mcpfind.org": "mcpfind",
    "mcp-marketplace.io": "mcp_marketplace",
    "mcpservers.org": "mcpservers",
    "protodex.io": "protodex",
    "pulsemcp.com": "pulsemcp",
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
