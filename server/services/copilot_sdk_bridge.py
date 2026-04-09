"""Bridge to the Node-based Copilot SDK runner."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from server import config
from server.services.copilot_auth import CopilotAuthService


@dataclass
class CopilotSDKBridgeEvent:
    type: str
    detail: str = ""


@dataclass
class CopilotSDKBridgeResult:
    content: str = ""
    session_id: str | None = None
    selected_agent: str | None = None
    tokens_used: int = 0
    events: list[CopilotSDKBridgeEvent] = field(default_factory=list)


class CopilotSDKBridge:
    def __init__(
        self,
        node_bin: str | None = None,
        runner_path: str | Path | None = None,
        cwd: str | Path | None = None,
    ):
        self.node_bin = node_bin or config.COPILOT_SDK_NODE_BIN
        self.runner_path = Path(runner_path or config.COPILOT_SDK_RUNNER_PATH).resolve()
        self.cwd = Path(cwd or config.PROJECT_ROOT).resolve()
        self.auth_service = CopilotAuthService()

    def run_session(self, payload: dict, timeout: int | None = None) -> CopilotSDKBridgeResult:
        if not self.runner_path.exists():
            raise RuntimeError(
                f"Copilot SDK runner not found at {self.runner_path}. "
                "Install the runner dependencies and keep ORCHESTRATION_BACKEND=legacy until ready."
            )

        env = os.environ.copy()
        github_token = config.COPILOT_GITHUB_TOKEN or config.GH_TOKEN or config.COPILOT_OAUTH_TOKEN or config.GITHUB_TOKEN
        if not github_token:
            auth = self.auth_service.resolve_stored_auth()
            github_token = auth.token if auth else ""
        if github_token:
            env.setdefault("COPILOT_GITHUB_TOKEN", github_token)
            env.setdefault("GH_TOKEN", github_token)
            env.setdefault("GITHUB_TOKEN", github_token)
            env.setdefault("COPILOT_OAUTH_TOKEN", github_token)

        completed = subprocess.run(
            [self.node_bin, str(self.runner_path)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=str(self.runner_path.parent),
            env=env,
            timeout=timeout or config.COPILOT_SDK_TIMEOUT,
            check=False,
        )

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        if not stdout:
            raise RuntimeError(stderr or "Copilot SDK runner returned no output")

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Copilot SDK runner returned invalid JSON: {stdout[:500]}") from exc

        if not data.get("success"):
            message = data.get("error") or stderr or "Copilot SDK runner failed"
            raise RuntimeError(message)

        return CopilotSDKBridgeResult(
            content=data.get("content", ""),
            session_id=data.get("sessionId"),
            selected_agent=data.get("selectedAgent"),
            tokens_used=int(data.get("tokensUsed", 0) or 0),
            events=[
                CopilotSDKBridgeEvent(type=item.get("type", "runtime_event"), detail=item.get("detail", ""))
                for item in data.get("events", [])
                if isinstance(item, dict)
            ],
        )