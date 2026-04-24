"""Bridge to the Node-based Copilot SDK runner."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from server import config
from server.services.runtime.copilot_auth import CopilotAuthService


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
        self._ensure_runner_exists()
        env = self._runner_env()

        completed = subprocess.run(
            [self.node_bin, str(self.runner_path)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=str(self.runner_path.parent),
            env=env,
            timeout=self._subprocess_timeout(timeout),
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
            message = self._normalize_error_message(message, payload)
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

    def start_session(self, payload: dict) -> int:
        launch_payload = dict(payload)
        launch_payload.setdefault("action", "start")
        return self._spawn_worker(launch_payload)

    def resume_session(self, payload: dict) -> int:
        launch_payload = dict(payload)
        launch_payload.setdefault("action", "resume")
        return self._spawn_worker(launch_payload)

    def _normalize_error_message(self, message: str, payload: dict) -> str:
        model = payload.get("model")
        if not isinstance(model, str):
            return message
        if 'is not available' not in message:
            return message
        candidate = model.strip().lower()
        if candidate and candidate != model:
            return (
                f'{message} Copilot SDK model ids are case-sensitive. '
                f'Try "{candidate}" if it appears in models.list for the current auth context.'
            )
        return (
            f"{message} Copilot SDK model ids must match models.list exactly for the current auth context."
        )

    def _subprocess_timeout(self, timeout: int | None) -> int | None:
        if timeout is None:
            timeout = config.COPILOT_SDK_TIMEOUT
        if timeout <= 0:
            return None
        return timeout

    def _ensure_runner_exists(self) -> None:
        if self.runner_path.exists():
            return
        raise RuntimeError(
            f"Copilot SDK runner not found at {self.runner_path}. "
            "Install the runner dependencies and keep ORCHESTRATION_BACKEND=legacy until ready."
        )

    def _runner_env(self) -> dict[str, str]:
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
        return env

    def _spawn_worker(self, payload: dict) -> int:
        self._ensure_runner_exists()
        env = self._runner_env()

        stdout_path = payload.get("stdoutPath")
        stderr_path = payload.get("stderrPath")

        stdout_handle = None
        stderr_handle = None
        try:
            if isinstance(stdout_path, str) and stdout_path:
                stdout_file = Path(stdout_path)
                stdout_file.parent.mkdir(parents=True, exist_ok=True)
                stdout_handle = open(stdout_file, "a", encoding="utf-8")
            if isinstance(stderr_path, str) and stderr_path:
                stderr_file = Path(stderr_path)
                stderr_file.parent.mkdir(parents=True, exist_ok=True)
                stderr_handle = open(stderr_file, "a", encoding="utf-8")

            process = subprocess.Popen(
                [self.node_bin, str(self.runner_path)],
                stdin=subprocess.PIPE,
                stdout=stdout_handle or subprocess.DEVNULL,
                stderr=stderr_handle or subprocess.DEVNULL,
                text=True,
                cwd=str(self.runner_path.parent),
                env=env,
                start_new_session=True,
            )
            if process.stdin is None:
                raise RuntimeError("Copilot SDK worker failed to acquire stdin")
            process.stdin.write(json.dumps(payload))
            process.stdin.flush()
            process.stdin.close()
            self._write_worker_pid(payload, int(process.pid or 0))
            return int(process.pid or 0)
        finally:
            if stdout_handle is not None:
                stdout_handle.close()
            if stderr_handle is not None:
                stderr_handle.close()

    def _write_worker_pid(self, payload: dict, pid: int) -> None:
        state_path = payload.get("statePath")
        if not isinstance(state_path, str) or not state_path:
            return

        state_file = Path(state_path)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if state_file.exists():
            try:
                existing = json.loads(state_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
        existing["workerPid"] = pid
        existing.setdefault("status", "starting")
        if payload.get("sessionId") is not None:
            existing.setdefault("sessionId", payload.get("sessionId"))
        state_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")