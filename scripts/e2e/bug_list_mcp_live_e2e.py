#!/usr/bin/env python3
"""Exercise Bug List through the local MCP server against a live Ops API."""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
import time
import uuid
from pathlib import Path
from urllib import error, request

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.mcp.bug_list_env import _read_dotenv_values  # noqa: E402

MCP_SCRIPT = REPO_ROOT / "scripts" / "mcp" / "bug_list_server.py"
DEFAULT_PORT = "19731"


def _merged_env(base_url: str, token: str) -> dict[str, str]:
    dotenv = _read_dotenv_values(REPO_ROOT / ".env")
    env = os.environ.copy()
    for key, value in dotenv.items():
        env.setdefault(key, value)
    env["OPS_BASE_URL"] = base_url
    env["OPS_AGENT_BUG_API_TOKEN"] = token
    return env


def _require_token() -> str:
    token = os.environ.get(
        "OPS_AGENT_BUG_API_TOKEN", ""
    ).strip() or _read_dotenv_values(REPO_ROOT / ".env").get(
        "OPS_AGENT_BUG_API_TOKEN", ""
    )
    if not token:
        raise SystemExit(
            "OPS_AGENT_BUG_API_TOKEN is missing. Run scripts/mcp/register_bug_list_codex.py first."
        )
    return token


def _wait_for_api(base_url: str, timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            with request.urlopen(  # nosec B310
                f"{base_url}/api/bugs?limit=1", timeout=2
            ) as response:
                if response.status == 200:
                    return
        except (OSError, error.URLError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise SystemExit(f"Ops API did not become ready at {base_url}: {last_error}")


def _start_api_if_needed(
    base_url: str, env: dict[str, str]
) -> subprocess.Popen[str] | None:
    if os.environ.get("OPS_BASE_URL"):
        _wait_for_api(base_url)
        return None
    if not env.get("OPS_DATABASE_URL"):
        raise SystemExit("OPS_DATABASE_URL is required to start the temporary Ops API.")
    port = base_url.rsplit(":", 1)[-1]
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "server.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        port,
        "--log-level",
        "warning",
    ]
    api_env = env.copy()
    api_env.update(
        {
            "OPS_ENV": "local",
            "OPS_PORT": port,
            "OPS_E2E_MODE": "1",
            "COPILOT_SDK_MONITOR_ENABLED": "0",
        }
    )
    process = subprocess.Popen(  # noqa: S603 # nosec B603
        command,
        cwd=str(REPO_ROOT),
        env=api_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _wait_for_api(base_url)
    return process


class McpClient:
    def __init__(self, env: dict[str, str]):
        self._next_id = 1
        self._process = subprocess.Popen(  # noqa: S603 # nosec B603
            [sys.executable, str(MCP_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def close(self) -> None:
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()

    def _request(
        self, method: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        message = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        self._next_id += 1
        if params is not None:
            message["params"] = params
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("MCP subprocess pipes are unavailable")
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()
        raw = self._process.stdout.readline()
        if not raw:
            stderr = self._process.stderr.read() if self._process.stderr else ""
            raise RuntimeError(f"MCP server exited unexpectedly: {stderr}")
        payload = json.loads(raw)
        if payload.get("error"):
            raise RuntimeError(json.dumps(payload["error"], ensure_ascii=False))
        return payload["result"]

    def _call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        structured = result.get("structuredContent")
        if not isinstance(structured, dict):
            raise RuntimeError(
                f"MCP tool returned invalid structuredContent for {name}"
            )
        return structured


def _assert_tool_list(client: McpClient) -> None:
    client._request(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "e2e"},
        },
    )
    tools = client._request("tools/list")
    names = {tool["name"] for tool in tools["tools"]}
    required = {
        "bugs_intake",
        "bugs_agent_queue",
        "bugs_claim",
        "bugs_link_fix",
        "bugs_add_verification",
        "bugs_close",
        "bugs_get",
    }
    if not required.issubset(names):
        raise SystemExit(f"MCP tools missing: {sorted(required - names)}")


def main() -> None:
    token = _require_token()
    base_url = os.environ.get(
        "OPS_BASE_URL", f"http://127.0.0.1:{DEFAULT_PORT}"
    ).rstrip("/")
    env = _merged_env(base_url, token)
    api_process = _start_api_if_needed(base_url, env)
    client = McpClient(env)
    fingerprint = f"bug-list-mcp-e2e-{uuid.uuid4().hex}"
    try:
        _assert_tool_list(client)
        intake = client._call_tool(
            "bugs_intake",
            {
                "project_key": "growing",
                "title": "Bug List MCP live E2E",
                "summary": "Validate MCP can drive the Bug List lifecycle.",
                "severity": "normal",
                "fingerprint": fingerprint,
                "metadata": {
                    "acceptance_checks": ["python scripts/e2e/bug_list_mcp_live_e2e.py"]
                },
            },
        )
        bug = intake["bug"]
        bug_id = bug["id"]
        queue = client._call_tool("bugs_agent_queue", {"limit": 100})
        queue_ids = {item["bug"]["id"] for item in queue["items"]}
        if bug_id not in queue_ids:
            raise SystemExit(f"Created bug {bug_id} is missing from agent queue")
        client._call_tool("bugs_claim", {"bug_id": bug_id, "agent_id": "codex-e2e"})
        client._call_tool(
            "bugs_link_fix",
            {
                "bug_id": bug_id,
                "agent_id": "codex-e2e",
                "branch_name": "codex/bug-list-mcp-e2e",
                "commit_sha": "e2e1234567890",
                "pr_url": "https://github.com/SynapseNetworkAI/Synapse-Network-Growing/pull/0",
            },
        )
        client._call_tool(
            "bugs_add_verification",
            {
                "bug_id": bug_id,
                "agent_id": "codex-e2e",
                "status": "verified",
                "summary": "MCP live E2E passed.",
                "commands": [
                    {
                        "command": "python scripts/e2e/bug_list_mcp_live_e2e.py",
                        "status": "passed",
                    }
                ],
                "screenshots": [
                    {
                        "path": "docs/archive/evidence/bugs/mcp-live-e2e.png",
                        "label": "MCP live E2E",
                    }
                ],
            },
        )
        client._call_tool(
            "bugs_close",
            {"bug_id": bug_id, "actor": "codex-e2e", "resolution": "verified"},
        )
        detail = client._call_tool("bugs_get", {"bug_id": bug_id})
        if detail["bug"]["status"] != "closed":
            raise SystemExit(f"Expected closed bug, got {detail['bug']['status']}")
        attempt = detail["latest_fix_attempt"]
        if (
            attempt["commit_sha"] != "e2e1234567890"
            or not attempt["verification_commands"]
        ):
            raise SystemExit("Fix attempt evidence was not persisted")
        if not any(event["event_type"] == "closed" for event in detail["events"]):
            raise SystemExit("Closed event was not recorded")
        print(f"bug_list_mcp_live_e2e: ok bug_id={bug_id}")
    finally:
        client.close()
        if api_process is not None:
            api_process.terminate()
            try:
                api_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                api_process.kill()


if __name__ == "__main__":
    main()
