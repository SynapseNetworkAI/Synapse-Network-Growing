"""Public Remote MCP metadata checks for AI visibility release gates."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

from pydantic import BaseModel, Field

from server.services.growth.ai_visibility_text import unique_strings

REMOTE_MCP_METADATA_URL = "https://mcp.synapse-network.ai/.well-known/glama.json"
EXPECTED_SCHEMA = "https://glama.ai/mcp/schemas/connector.json"
EXPECTED_NAME = "Synapse Network MCP Server"
EXPECTED_SERVER_URL = "https://mcp.synapse-network.ai/mcp"
EXPECTED_REPOSITORY = "https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server"
EXPECTED_TOOLS = ["discover_services", "invoke_and_pay", "get_receipt"]

MetadataFetcher = Callable[[str], tuple[int, str]]


class RemoteMcpPublicMetadataCheckOut(BaseModel):
    url: str
    ok: bool
    status: str
    http_status: int
    summary: str
    missing_fields: list[str] = Field(default_factory=list)
    observed: dict[str, Any] = Field(default_factory=dict)
    blocker: str = ""


def remote_mcp_public_metadata_check(
    *,
    url: str = REMOTE_MCP_METADATA_URL,
    fetcher: MetadataFetcher | None = None,
) -> RemoteMcpPublicMetadataCheckOut:
    try:
        status, body = (fetcher or _fetch_url)(url)
    except Exception as exc:  # noqa: BLE001 - bounded public diagnostic
        return RemoteMcpPublicMetadataCheckOut(
            url=url,
            ok=False,
            status="fetch_failed",
            http_status=0,
            summary=str(exc)[:300],
            missing_fields=[
                "name",
                "serverUrl",
                "repository",
                "tools.discover_services",
                "tools.invoke_and_pay",
                "tools.get_receipt",
            ],
            blocker=_blocker_summary(
                "fetch failed",
                [
                    "name",
                    "serverUrl",
                    "repository",
                    "tools.discover_services",
                    "tools.invoke_and_pay",
                    "tools.get_receipt",
                ],
            ),
        )
    if status < 200 or status >= 300:
        return RemoteMcpPublicMetadataCheckOut(
            url=url,
            ok=False,
            status="http_failed",
            http_status=status,
            summary=f"metadata endpoint returned HTTP {status}",
            missing_fields=["metadata_http_2xx"],
            blocker=_blocker_summary(f"HTTP {status}", ["metadata_http_2xx"]),
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return RemoteMcpPublicMetadataCheckOut(
            url=url,
            ok=False,
            status="invalid_json",
            http_status=status,
            summary=f"metadata endpoint returned invalid JSON: {exc}",
            missing_fields=["valid_json"],
            blocker=_blocker_summary("invalid JSON", ["valid_json"]),
        )
    missing = _missing_metadata_fields(payload)
    ok = not missing
    return RemoteMcpPublicMetadataCheckOut(
        url=url,
        ok=ok,
        status="ready" if ok else "stale_or_incomplete",
        http_status=status,
        summary=(
            "Remote MCP public metadata has complete AI directory fields."
            if ok
            else "Remote MCP public metadata is missing required AI directory fields."
        ),
        missing_fields=missing,
        observed=_observed_fields(payload),
        blocker="" if ok else _blocker_summary("stale or incomplete", missing),
    )


def _fetch_url(url: str) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Synapse-Growing-AI-Visibility-MetadataGate/1.0",
            "Accept": "application/json, text/plain;q=0.8",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310
            return response.status, response.read(100_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read(20_000).decode("utf-8", "replace")
        return exc.code, body


def _missing_metadata_fields(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return [
            "metadata_object",
            "name",
            "serverUrl",
            "repository",
            "tools.discover_services",
            "tools.invoke_and_pay",
            "tools.get_receipt",
        ]
    missing: list[str] = []
    if payload.get("$schema") != EXPECTED_SCHEMA:
        missing.append("$schema")
    if payload.get("name") != EXPECTED_NAME:
        missing.append("name")
    if payload.get("serverUrl") != EXPECTED_SERVER_URL:
        missing.append("serverUrl")
    if payload.get("repository") != EXPECTED_REPOSITORY:
        missing.append("repository")
    tools = _tool_names(payload.get("tools"))
    for tool in EXPECTED_TOOLS:
        if tool not in tools:
            missing.append(f"tools.{tool}")
    return missing


def _tool_names(raw_tools: Any) -> list[str]:
    if not isinstance(raw_tools, list):
        return []
    names: list[str] = []
    for item in raw_tools:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            names.append(str(item.get("name") or item.get("id") or "").strip())
    return unique_strings([name for name in names if name])


def _observed_fields(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"type": type(payload).__name__}
    return {
        "$schema": payload.get("$schema"),
        "name": payload.get("name"),
        "serverUrl": payload.get("serverUrl"),
        "repository": payload.get("repository"),
        "tools": _tool_names(payload.get("tools")),
    }


def _blocker_summary(reason: str, missing: list[str]) -> str:
    joined = ", ".join(missing)
    return (
        "Remote MCP public metadata gate failed "
        f"({reason}): {REMOTE_MCP_METADATA_URL} missing {joined}. "
        "Merge and deploy Synapse-Network-MCP-Server metadata refresh, then run "
        "npm run test:e2e:remote:metadata before rerunning AI visibility probes."
    )
