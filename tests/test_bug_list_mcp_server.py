from __future__ import annotations

import json
from io import BytesIO
from urllib import error

import pytest

from scripts.mcp import bug_list_server
from scripts.mcp.bug_list_tool_catalog import READ_TOOLS, WRITE_TOOLS


class _FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


def _http_error(status: int, payload: dict[str, object]) -> error.HTTPError:
    body = BytesIO(json.dumps(payload).encode("utf-8"))
    return error.HTTPError("http://ops.test", status, "boom", hdrs=None, fp=body)


def test_bugs_list_calls_allowlisted_api_path(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["timeout"] = timeout
        return _FakeResponse({"items": [], "total": 0})

    monkeypatch.setenv("OPS_BASE_URL", "http://ops.test")
    monkeypatch.delenv("OPS_AGENT_BUG_API_TOKEN", raising=False)
    monkeypatch.setattr(bug_list_server.request, "urlopen", fake_urlopen)

    result = bug_list_server._call_tool(
        "bugs_list",
        {
            "project_key": "growing",
            "status": "ready_for_agent",
            "limit": 5,
            "offset": 10,
        },
    )

    assert result == {"items": [], "total": 0}
    assert captured["method"] == "GET"
    assert captured["timeout"] == 30
    assert captured["url"] == (
        "http://ops.test/api/bugs?"
        "project_key=growing&status=ready_for_agent&limit=5&offset=10"
    )


def test_write_tool_requires_agent_token(monkeypatch):
    monkeypatch.delenv("OPS_AGENT_BUG_API_TOKEN", raising=False)

    with pytest.raises(bug_list_server.McpToolError) as exc_info:
        bug_list_server._call_tool("bugs_claim", {"bug_id": 7, "agent_id": "codex"})

    assert exc_info.value.code == "auth_required"
    assert exc_info.value.status == 401


def test_write_tool_sends_agent_token(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse({"bug": {"id": 7}, "fix_attempt": {"id": 3}})

    monkeypatch.setenv("OPS_BASE_URL", "http://ops.test")
    monkeypatch.setenv("OPS_AGENT_BUG_API_TOKEN", "local-secret")
    monkeypatch.setattr(bug_list_server.request, "urlopen", fake_urlopen)

    result = bug_list_server._call_tool(
        "bugs_claim", {"bug_id": 7, "agent_id": "codex"}
    )

    assert result["bug"]["id"] == 7
    assert captured["method"] == "POST"
    assert captured["url"] == "http://ops.test/api/bugs/agent-actions/7/claim"
    headers = {key.lower(): value for key, value in captured["headers"].items()}
    assert headers[bug_list_server.AGENT_TOKEN_HEADER.lower()] == "local-secret"
    assert captured["body"] == {"agent_id": "codex", "lease_minutes": 120}


def test_http_errors_are_mapped_to_structured_mcp_errors(monkeypatch):
    def fake_urlopen(req, timeout):
        raise _http_error(409, {"detail": "bug already has an active fix attempt"})

    monkeypatch.setenv("OPS_BASE_URL", "http://ops.test")
    monkeypatch.setenv("OPS_AGENT_BUG_API_TOKEN", "local-secret")
    monkeypatch.setattr(bug_list_server.request, "urlopen", fake_urlopen)

    response = bug_list_server._handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "bugs_claim",
                "arguments": {"bug_id": 7, "agent_id": "codex"},
            },
        }
    )

    assert response is not None
    assert response["error"]["message"] == "already_claimed"
    assert response["error"]["data"]["status"] == 409


def test_missing_verification_evidence_maps_to_missing_evidence(monkeypatch):
    def fake_urlopen(req, timeout):
        raise _http_error(
            400, {"detail": "verification evidence is required before close"}
        )

    monkeypatch.setenv("OPS_BASE_URL", "http://ops.test")
    monkeypatch.setenv("OPS_AGENT_BUG_API_TOKEN", "local-secret")
    monkeypatch.setattr(bug_list_server.request, "urlopen", fake_urlopen)

    response = bug_list_server._handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "bugs_close",
                "arguments": {"bug_id": 7, "actor": "codex", "resolution": "verified"},
            },
        }
    )

    assert response is not None
    assert response["error"]["message"] == "missing_evidence"
    assert response["error"]["data"]["status"] == 400


def test_tools_list_exposes_only_bug_list_allowlist():
    response = bug_list_server._handle_request(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    )

    assert response is not None
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert names == READ_TOOLS | WRITE_TOOLS
    assert all("shell" not in name for name in names)


def test_unknown_tool_is_rejected_without_arbitrary_proxy():
    response = bug_list_server._handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "bugs_proxy", "arguments": {"path": "/api/bugs"}},
        }
    )

    assert response is not None
    assert response["error"]["message"] == "validation_required"
