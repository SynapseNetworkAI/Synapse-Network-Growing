"""Tests for Copilot login state resolution and device-flow endpoints."""
import json
from unittest.mock import MagicMock, patch

from server.schemas import CopilotAuthStatus
from server.services.copilot_auth import CopilotAuthService


def test_copilot_auth_service_resolves_apps_json(tmp_path):
    config_dir = tmp_path / "github-copilot"
    config_dir.mkdir()
    (config_dir / "apps.json").write_text(json.dumps({
        "github.com:cli-client": {
            "user": "octocat",
            "oauth_token": "gho_test",
            "githubAppId": "cli-client",
            "scopes": ["repo"],
        }
    }), encoding="utf-8")

    with patch("server.services.copilot_auth.config.COPILOT_OAUTH_TOKEN", ""), patch("server.services.copilot_auth.config.GITHUB_TOKEN", ""):
        auth = CopilotAuthService(config_dir=config_dir).resolve_stored_auth()

    assert auth is not None
    assert auth.token == "gho_test"
    assert auth.login == "octocat"
    assert auth.source == "apps_json"


def test_copilot_auth_service_falls_back_to_oauth_json(tmp_path):
    config_dir = tmp_path / "github-copilot"
    config_dir.mkdir()
    (config_dir / "oauth.json").write_text(json.dumps({
        "https://github.com/login/oauth": [
            {
                "id": "cli-client",
                "accessToken": "gho_oauth",
                "account": {"label": "octocat", "id": "1"},
                "scopes": ["repo"],
            }
        ]
    }), encoding="utf-8")

    with patch("server.services.copilot_auth.config.COPILOT_OAUTH_TOKEN", ""), patch("server.services.copilot_auth.config.GITHUB_TOKEN", ""):
        auth = CopilotAuthService(config_dir=config_dir).resolve_stored_auth()

    assert auth is not None
    assert auth.token == "gho_oauth"
    assert auth.login == "octocat"
    assert auth.source == "oauth_json"


def test_request_copilot_device_code_endpoint(client):
    with patch("server.routers.copilot_auth.auth_service.request_device_code") as mock_request:
        mock_request.return_value = {
            "host": "https://github.com",
            "client_id": "cli-client",
            "device_code": "device-code",
            "user_code": "123-456",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }

        resp = client.post("/api/copilot-auth/device-code", json={})

    assert resp.status_code == 200
    assert resp.json()["device_code"] == "device-code"


def test_poll_copilot_device_code_complete_persists_login(tmp_path):
    config_dir = tmp_path / "github-copilot"
    service = CopilotAuthService(config_dir=config_dir)

    token_response = MagicMock()
    token_response.status_code = 200
    token_response.json.return_value = {"access_token": "gho_new"}

    user_response = MagicMock()
    user_response.status_code = 200
    user_response.json.return_value = {"login": "octocat"}

    with patch("httpx.post", return_value=token_response), patch("httpx.get", return_value=user_response):
        result = service.poll_access_token_once(device_code="device-code", client_id="cli-client")

    assert result.status == "complete"
    assert result.login == "octocat"
    stored = json.loads((config_dir / "apps.json").read_text(encoding="utf-8"))
    assert stored["github.com:cli-client"]["oauth_token"] == "gho_new"


def test_copilot_auth_status_endpoint_returns_resolved_status(client):
    with patch("server.routers.copilot_auth.auth_service.get_status") as mock_status:
        mock_status.return_value = CopilotAuthStatus(
            authenticated=True,
            host="https://github.com",
            login="octocat",
            source="apps_json",
            message="Copilot OAuth token is available.",
        )

        resp = client.get("/api/copilot-auth/status")

    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True
    assert resp.json()["login"] == "octocat"