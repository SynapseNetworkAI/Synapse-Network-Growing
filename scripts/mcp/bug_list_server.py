#!/usr/bin/env python3
"""Local-only MCP adapter for Synapse Bug List APIs.

The server speaks stdio JSON-RPC and intentionally wraps only allowlisted
`/api/bugs/*` routes. It does not execute shell commands, proxy arbitrary HTTP
paths, or connect to the database.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from scripts.mcp.bug_list_tool_catalog import (
    BUG_LIST_TOOL_DEFINITIONS,
    WRITE_TOOLS,
)

DEFAULT_BASE_URL = "http://127.0.0.1:9700"
AGENT_TOKEN_HEADER = "X-Growing-Agent-Bug-Token"  # nosec B105
JSON_RPC_PARSE_ERROR = -32700
JSON_RPC_METHOD_NOT_FOUND = -32601
JSON_RPC_INVALID_PARAMS = -32602
JSON_RPC_TOOL_ERROR = -32000


@dataclass
class McpToolError(Exception):
    code: str
    message: str
    status: int | None = None
    detail: Any = None


def _base_url() -> str:
    return os.getenv("OPS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _agent_token() -> str:
    return os.getenv("OPS_AGENT_BUG_API_TOKEN", "").strip()


def _require_fields(arguments: dict[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if arguments.get(field) in (None, "")]
    if missing:
        raise McpToolError(
            "validation_required",
            f"Missing required argument(s): {', '.join(missing)}",
            status=400,
            detail={"missing": missing},
        )


def _query_path(path: str, params: dict[str, Any]) -> str:
    clean_params = {
        key: value for key, value in params.items() if value not in (None, "")
    }
    query = parse.urlencode(clean_params)
    return f"{path}?{query}" if query else path


def _json_bytes(payload: dict[str, Any] | None) -> bytes | None:
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _request_api(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    token_required: bool = False,
) -> dict[str, Any]:
    token = _agent_token()
    if token_required and not token:
        raise McpToolError(
            "auth_required",
            "OPS_AGENT_BUG_API_TOKEN is required for Bug List write tools.",
            status=401,
        )
    url = f"{_base_url()}{path}"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers[AGENT_TOKEN_HEADER] = token
    req = request.Request(
        url, data=_json_bytes(payload), headers=headers, method=method
    )
    try:
        with request.urlopen(req, timeout=30) as response:  # nosec B310
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = _read_http_error_detail(exc)
        raise _map_http_error(exc.code, detail) from exc
    except OSError as exc:
        raise McpToolError(
            "ops_api_unavailable",
            f"Unable to reach Ops API at {_base_url()}: {exc}",
            status=None,
            detail=str(exc),
        ) from exc
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise McpToolError(
            "ops_api_unavailable",
            "Ops API returned non-JSON response.",
            detail=raw[:500],
        ) from exc
    if not isinstance(parsed, dict):
        return {"value": parsed}
    return parsed


def _read_http_error_detail(exc: error.HTTPError) -> Any:
    raw = exc.read().decode("utf-8", errors="replace")
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _detail_text(detail: Any) -> str:
    if isinstance(detail, dict):
        value = detail.get("detail", detail)
        return (
            json.dumps(value, ensure_ascii=False)
            if not isinstance(value, str)
            else value
        )
    return str(detail)


def _map_http_error(status: int, detail: Any) -> McpToolError:
    text = _detail_text(detail).lower()
    if status == 404:
        code = "not_found"
    elif status in (401, 403):
        code = "auth_required"
    elif status == 409:
        code = "already_claimed"
    elif status == 400 and (
        "screenshot" in text or "evidence" in text or "verification" in text
    ):
        code = "missing_evidence"
    elif status == 400:
        code = "validation_required"
    else:
        code = "ops_api_unavailable"
    return McpToolError(code, _detail_text(detail), status=status, detail=detail)


def _bugs_list(arguments: dict[str, Any]) -> dict[str, Any]:
    path = _query_path(
        "/api/bugs",
        {
            "project_key": arguments.get("project_key"),
            "status": arguments.get("status"),
            "severity": arguments.get("severity"),
            "source_key": arguments.get("source_key"),
            "q": arguments.get("q"),
            "limit": arguments.get("limit"),
            "offset": arguments.get("offset"),
        },
    )
    return _request_api("GET", path)


def _bugs_get(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_fields(arguments, ("bug_id",))
    return _request_api("GET", f"/api/bugs/{arguments['bug_id']}")


def _bugs_agent_queue(arguments: dict[str, Any]) -> dict[str, Any]:
    path = _query_path(
        "/api/bugs/agent-queue",
        {"limit": arguments.get("limit"), "offset": arguments.get("offset")},
    )
    return _request_api("GET", path)


def _bugs_intake(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_fields(arguments, ("project_key", "title", "summary", "severity"))
    payload = {
        "source_key": arguments.get("source_key") or "manual_bug_report",
        "project_key": arguments["project_key"],
        "project_root_path": arguments.get("project_root_path"),
        "title": arguments["title"],
        "summary": arguments["summary"],
        "severity": arguments["severity"],
        "fingerprint": arguments.get("fingerprint"),
        "source_ref": arguments.get("source_ref"),
        "environment": arguments.get("environment"),
        "log_excerpt": arguments.get("log_excerpt"),
        "stack_trace": arguments.get("stack_trace"),
        "metadata": arguments.get("metadata") or {},
    }
    if arguments.get("evidence"):
        payload["metadata"]["mcp_evidence"] = arguments["evidence"]
    return _request_api(
        "POST", "/api/bugs/agent-actions/intake", payload, token_required=True
    )


def _bugs_claim(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_fields(arguments, ("bug_id", "agent_id"))
    payload = {
        "agent_id": arguments["agent_id"],
        "lease_minutes": arguments.get("lease_minutes", 120),
    }
    return _request_api(
        "POST",
        f"/api/bugs/agent-actions/{arguments['bug_id']}/claim",
        payload,
        token_required=True,
    )


def _bugs_materialize_requirement(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_fields(arguments, ("bug_id",))
    return _request_api(
        "POST",
        f"/api/bugs/agent-actions/{arguments['bug_id']}/materialize-requirement",
        {},
        token_required=True,
    )


def _bugs_link_fix(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_fields(arguments, ("bug_id", "agent_id"))
    payload = {
        "agent_id": arguments["agent_id"],
        "branch_name": arguments.get("branch_name"),
        "commit_sha": arguments.get("commit_sha"),
        "pr_url": arguments.get("pr_url"),
        "workflow_run_id": arguments.get("workflow_run_id"),
        "requirement_id": arguments.get("requirement_id"),
    }
    return _request_api(
        "POST",
        f"/api/bugs/agent-actions/{arguments['bug_id']}/link-fix",
        payload,
        token_required=True,
    )


def _bugs_add_verification(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_fields(arguments, ("bug_id", "agent_id", "status", "summary", "commands"))
    payload = {
        "agent_id": arguments["agent_id"],
        "status": arguments["status"],
        "summary": arguments["summary"],
        "commands": arguments["commands"],
        "screenshots": arguments.get("screenshots") or [],
    }
    return _request_api(
        "POST",
        f"/api/bugs/agent-actions/{arguments['bug_id']}/verification",
        payload,
        token_required=True,
    )


def _bugs_close(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_fields(arguments, ("bug_id", "actor", "resolution"))
    payload = {"actor": arguments["actor"], "resolution": arguments["resolution"]}
    return _request_api(
        "POST",
        f"/api/bugs/agent-actions/{arguments['bug_id']}/close",
        payload,
        token_required=True,
    )


def _bugs_reopen(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_fields(arguments, ("bug_id", "actor", "reason"))
    payload = {"actor": arguments["actor"], "reason": arguments["reason"]}
    return _request_api(
        "POST",
        f"/api/bugs/agent-actions/{arguments['bug_id']}/reopen",
        payload,
        token_required=True,
    )


TOOL_HANDLERS = {
    "bugs_list": _bugs_list,
    "bugs_get": _bugs_get,
    "bugs_agent_queue": _bugs_agent_queue,
    "bugs_intake": _bugs_intake,
    "bugs_claim": _bugs_claim,
    "bugs_materialize_requirement": _bugs_materialize_requirement,
    "bugs_link_fix": _bugs_link_fix,
    "bugs_add_verification": _bugs_add_verification,
    "bugs_close": _bugs_close,
    "bugs_reopen": _bugs_reopen,
}


def _call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    if name not in TOOL_HANDLERS:
        raise McpToolError(
            "validation_required", f"Unknown Bug List MCP tool: {name}", status=400
        )
    args = arguments or {}
    if name in WRITE_TOOLS and not _agent_token():
        raise McpToolError(
            "auth_required",
            "OPS_AGENT_BUG_API_TOKEN is required for Bug List write tools.",
            status=401,
        )
    return TOOL_HANDLERS[name](args)


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return {"structuredContent": payload, "content": [{"type": "text", "text": text}]}


def _json_rpc_result(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _json_rpc_error(
    message_id: Any, code: int, message: str, data: Any = None
) -> dict[str, Any]:
    error_payload = {"code": code, "message": message}
    if data is not None:
        error_payload["data"] = data
    return {"jsonrpc": "2.0", "id": message_id, "error": error_payload}


def _handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return _json_rpc_result(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "synapse-bug-list", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        )
    if method == "tools/list":
        return _json_rpc_result(message_id, {"tools": BUG_LIST_TOOL_DEFINITIONS})
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            result = _call_tool(
                str(params.get("name", "")), params.get("arguments") or {}
            )
            return _json_rpc_result(message_id, _tool_result(result))
        except McpToolError as exc:
            return _json_rpc_error(
                message_id,
                JSON_RPC_TOOL_ERROR,
                exc.code,
                {"status": exc.status, "detail": exc.detail or exc.message},
            )
    if method == "ping":
        return _json_rpc_result(message_id, {})
    return _json_rpc_error(
        message_id, JSON_RPC_METHOD_NOT_FOUND, f"Unsupported method: {method}"
    )


def _serve_stdio() -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            response = _handle_request(message)
        except json.JSONDecodeError as exc:
            response = _json_rpc_error(
                None, JSON_RPC_PARSE_ERROR, "Invalid JSON", str(exc)
            )
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


def main() -> None:
    _serve_stdio()


if __name__ == "__main__":
    main()
