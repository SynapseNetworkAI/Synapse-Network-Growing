"""Copilot OAuth token resolution and device-flow login support."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
from pydantic import BaseModel

from server import config
from server.schemas import CopilotAuthStatus, CopilotDeviceCodeOut, CopilotDeviceCodePollOut

DEFAULT_GITHUB_HOST = "https://github.com"
DEFAULT_COPILOT_CLIENT_ID = "Ov23ctDVkRmgkPke0Mmm"
COPILOT_SCOPES = "read:user,read:org,repo,gist"
JSON_ACCEPT_HEADER = "application/json"


class StoredCopilotAuth(BaseModel):
    host: str = DEFAULT_GITHUB_HOST
    token: str
    login: str | None = None
    source: str
    client_id: str | None = None


class CopilotAuthService:
    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or (Path.home() / ".config" / "github-copilot")

    @property
    def apps_path(self) -> Path:
        return self.config_dir / "apps.json"

    @property
    def oauth_path(self) -> Path:
        return self.config_dir / "oauth.json"

    def resolve_stored_auth(self, host: str = DEFAULT_GITHUB_HOST) -> StoredCopilotAuth | None:
        env_token = self._token_from_env()
        if env_token:
            return StoredCopilotAuth(token=env_token, source="env", host=host)

        apps_auth = self._auth_from_apps_json(host)
        if apps_auth:
            return apps_auth

        oauth_auth = self._auth_from_oauth_json(host)
        if oauth_auth:
            return oauth_auth

        return None

    def get_status(self, host: str = DEFAULT_GITHUB_HOST) -> CopilotAuthStatus:
        auth = self.resolve_stored_auth(host)
        if not auth:
            return CopilotAuthStatus(
                authenticated=False,
                host=host,
                message="Copilot login not found. Run `copilot login` or use /api/copilot-auth/device-code.",
            )

        try:
            login = self.fetch_copilot_login(auth.token, host) or auth.login
            return CopilotAuthStatus(
                authenticated=True,
                host=host,
                login=login,
                source=auth.source,
                message="Copilot OAuth token is available.",
            )
        except RuntimeError as exc:
            return CopilotAuthStatus(
                authenticated=False,
                host=host,
                login=auth.login,
                source=auth.source,
                message=str(exc),
            )

    def request_device_code(self, host: str = DEFAULT_GITHUB_HOST, client_id: str | None = None) -> CopilotDeviceCodeOut:
        resolved_client_id = client_id or self._discover_client_id(host)
        resp = httpx.post(
            f"{host.rstrip('/')}/login/device/code",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": JSON_ACCEPT_HEADER,
            },
            data={
                "client_id": resolved_client_id,
                "scope": COPILOT_SCOPES,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to request device code: {resp.status_code} {resp.text[:300]}")

        body = resp.json()
        return CopilotDeviceCodeOut(
            host=host,
            client_id=resolved_client_id,
            device_code=body["device_code"],
            user_code=body["user_code"],
            verification_uri=body["verification_uri"],
            expires_in=body["expires_in"],
            interval=body["interval"],
        )

    def poll_access_token_once(
        self,
        device_code: str,
        host: str = DEFAULT_GITHUB_HOST,
        client_id: str | None = None,
    ) -> CopilotDeviceCodePollOut:
        resolved_client_id = client_id or self._discover_client_id(host)
        resp = httpx.post(
            f"{host.rstrip('/')}/login/oauth/access_token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": JSON_ACCEPT_HEADER,
            },
            data={
                "client_id": resolved_client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to authorize Copilot login: {resp.status_code} {resp.text[:300]}")

        body = resp.json()
        if isinstance(body.get("access_token"), str):
            token = body["access_token"]
            login = self.fetch_copilot_login(token, host)
            self._store_auth(token=token, login=login, host=host, client_id=resolved_client_id)
            return CopilotDeviceCodePollOut(
                status="complete",
                host=host,
                login=login,
                source="device_flow",
                message="Copilot login completed.",
            )

        if body.get("error") == "authorization_pending":
            return CopilotDeviceCodePollOut(
                status="pending",
                host=host,
                interval=body.get("interval"),
                message="Authorization is still pending.",
            )

        if body.get("error") == "slow_down":
            return CopilotDeviceCodePollOut(
                status="slow_down",
                host=host,
                interval=body.get("interval"),
                message="Polling too frequently. Slow down and try again.",
            )

        return CopilotDeviceCodePollOut(
            status="error",
            host=host,
            message=body.get("error_description") or body.get("error") or "Unknown device-flow error.",
        )

    def fetch_copilot_login(self, token: str, host: str = DEFAULT_GITHUB_HOST) -> str | None:
        resp = httpx.get(
            f"{host.rstrip('/')}/copilot_internal/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": JSON_ACCEPT_HEADER,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Copilot authentication failed: {resp.status_code} {resp.text[:300]}")
        return resp.json().get("login")

    def _token_from_env(self) -> str:
        if config.COPILOT_GITHUB_TOKEN:
            return config.COPILOT_GITHUB_TOKEN
        if config.GH_TOKEN:
            return config.GH_TOKEN
        if config.COPILOT_OAUTH_TOKEN:
            return config.COPILOT_OAUTH_TOKEN
        if config.GITHUB_TOKEN:
            return config.GITHUB_TOKEN
        return ""

    def _discover_client_id(self, host: str) -> str:
        if self.apps_path.exists():
            try:
                payload = json.loads(self.apps_path.read_text(encoding="utf-8"))
                host_key = host.replace("https://", "").rstrip("/") + ":"
                for key, value in payload.items():
                    if key.startswith(host_key):
                        return value.get("githubAppId") or key.split(":", 1)[1]
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                pass
        return DEFAULT_COPILOT_CLIENT_ID

    def _auth_from_apps_json(self, host: str) -> StoredCopilotAuth | None:
        if not self.apps_path.exists():
            return None
        try:
            payload = json.loads(self.apps_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

        host_key = host.replace("https://", "").rstrip("/") + ":"
        for key, value in payload.items():
            if not key.startswith(host_key):
                continue
            token = value.get("oauth_token")
            if token:
                return StoredCopilotAuth(
                    host=host,
                    token=token,
                    login=value.get("user"),
                    source="apps_json",
                    client_id=value.get("githubAppId") or key.split(":", 1)[1],
                )
        return None

    def _auth_from_oauth_json(self, host: str) -> StoredCopilotAuth | None:
        if not self.oauth_path.exists():
            return None
        try:
            payload = json.loads(self.oauth_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

        login_key = f"{host.rstrip('/')}/login/oauth"
        entries = payload.get(login_key, [])
        for entry in entries:
            token = entry.get("accessToken")
            if token:
                account = entry.get("account") or {}
                return StoredCopilotAuth(
                    host=host,
                    token=token,
                    login=account.get("label"),
                    source="oauth_json",
                    client_id=entry.get("id"),
                )
        return None

    def _store_auth(self, token: str, login: str | None, host: str, client_id: str):
        self.config_dir.mkdir(parents=True, exist_ok=True)

        apps_payload = {}
        if self.apps_path.exists():
            try:
                apps_payload = json.loads(self.apps_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                apps_payload = {}

        apps_key = f"{host.replace('https://', '').rstrip('/')}:{client_id}"
        apps_payload[apps_key] = {
            "user": login or "",
            "oauth_token": token,
            "githubAppId": client_id,
            "scopes": COPILOT_SCOPES.split(","),
        }
        self.apps_path.write_text(json.dumps(apps_payload), encoding="utf-8")

        oauth_payload = {}
        if self.oauth_path.exists():
            try:
                oauth_payload = json.loads(self.oauth_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                oauth_payload = {}

        oauth_key = f"{host.rstrip('/')}/login/oauth"
        oauth_payload[oauth_key] = [{
            "id": client_id,
            "accessToken": token,
            "account": {"label": login or "", "id": ""},
            "scopes": COPILOT_SCOPES.split(","),
        }]
        self.oauth_path.write_text(json.dumps(oauth_payload), encoding="utf-8")