"""Tests for Copilot login state resolution and device-flow endpoints."""
import json
from unittest.mock import MagicMock, patch

from server.schemas import CopilotAuthStatus
from server.services.runtime.copilot_auth import CopilotAuthService


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

    with patch("server.services.runtime.copilot_auth.config.COPILOT_GITHUB_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.GH_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.COPILOT_OAUTH_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.GITHUB_TOKEN", ""):
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

    with patch("server.services.runtime.copilot_auth.config.COPILOT_GITHUB_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.GH_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.COPILOT_OAUTH_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.GITHUB_TOKEN", ""):
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


def test_copilot_auth_status_reports_missing_login(tmp_path):
    service = CopilotAuthService(config_dir=tmp_path / "github-copilot")

    with patch("server.services.runtime.copilot_auth.config.COPILOT_GITHUB_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.GH_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.COPILOT_OAUTH_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.GITHUB_TOKEN", ""):
        status = service.get_status()

    assert status.authenticated is False
    assert "Copilot login not found" in status.message


def test_copilot_auth_status_reports_invalid_stored_token(tmp_path):
    service = CopilotAuthService(config_dir=tmp_path / "github-copilot")

    with patch("server.services.runtime.copilot_auth.config.COPILOT_GITHUB_TOKEN", "gho_bad"), patch.object(service, "fetch_copilot_login", side_effect=RuntimeError("token expired")):
        status = service.get_status()

    assert status.authenticated is False
    assert status.source == "env"
    assert status.message == "token expired"


def test_request_device_code_service_success(tmp_path):
    service = CopilotAuthService(config_dir=tmp_path / "github-copilot")
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "device_code": "device-code",
        "user_code": "123-456",
        "verification_uri": "https://github.com/login/device",
        "expires_in": 900,
        "interval": 5,
    }

    with patch("httpx.post", return_value=response):
        result = service.request_device_code(client_id="client-id")

    assert result.client_id == "client-id"
    assert result.device_code == "device-code"


def test_request_device_code_service_failure(tmp_path):
    service = CopilotAuthService(config_dir=tmp_path / "github-copilot")
    response = MagicMock()
    response.status_code = 500
    response.text = "boom"

    with patch("httpx.post", return_value=response):
        try:
            service.request_device_code(client_id="client-id")
        except RuntimeError as exc:
            assert "Failed to request device code" in str(exc)
        else:
            raise AssertionError("device code failure was not raised")


def test_copilot_auth_service_prefers_copilot_github_token_from_env(tmp_path):
    config_dir = tmp_path / "github-copilot"
    config_dir.mkdir()

    with patch("server.services.runtime.copilot_auth.config.COPILOT_GITHUB_TOKEN", "github_pat_models"), patch("server.services.runtime.copilot_auth.config.GH_TOKEN", "gho_from_gh_token"), patch("server.services.runtime.copilot_auth.config.COPILOT_OAUTH_TOKEN", "gho_from_copilot_oauth"), patch("server.services.runtime.copilot_auth.config.GITHUB_TOKEN", "gho_from_github_token"):
        auth = CopilotAuthService(config_dir=config_dir).resolve_stored_auth()

    assert auth is not None
    assert auth.token == "github_pat_models"
    assert auth.source == "env"


def test_copilot_auth_service_falls_back_to_gh_token_when_copilot_github_token_missing(tmp_path):
    config_dir = tmp_path / "github-copilot"
    config_dir.mkdir()

    with patch("server.services.runtime.copilot_auth.config.COPILOT_GITHUB_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.GH_TOKEN", "gho_from_gh_token"), patch("server.services.runtime.copilot_auth.config.COPILOT_OAUTH_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.GITHUB_TOKEN", ""):
        auth = CopilotAuthService(config_dir=config_dir).resolve_stored_auth()

    assert auth is not None
    assert auth.token == "gho_from_gh_token"
    assert auth.source == "env"


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


def test_poll_copilot_device_code_pending_slow_down_and_error(tmp_path):
    service = CopilotAuthService(config_dir=tmp_path / "github-copilot")
    response = MagicMock()
    response.status_code = 200

    response.json.return_value = {"error": "authorization_pending", "interval": 7}
    with patch("httpx.post", return_value=response):
        pending = service.poll_access_token_once(device_code="device-code", client_id="client-id")
    assert pending.status == "pending"
    assert pending.interval == 7

    response.json.return_value = {"error": "slow_down", "interval": 10}
    with patch("httpx.post", return_value=response):
        slow_down = service.poll_access_token_once(device_code="device-code", client_id="client-id")
    assert slow_down.status == "slow_down"
    assert slow_down.interval == 10

    response.json.return_value = {"error": "bad_verification_code", "error_description": "wrong code"}
    with patch("httpx.post", return_value=response):
        error = service.poll_access_token_once(device_code="device-code", client_id="client-id")
    assert error.status == "error"
    assert error.message == "wrong code"


def test_poll_copilot_device_code_http_failure(tmp_path):
    service = CopilotAuthService(config_dir=tmp_path / "github-copilot")
    response = MagicMock()
    response.status_code = 503
    response.text = "unavailable"

    with patch("httpx.post", return_value=response):
        try:
            service.poll_access_token_once(device_code="device-code", client_id="client-id")
        except RuntimeError as exc:
            assert "Failed to authorize Copilot login" in str(exc)
        else:
            raise AssertionError("poll failure was not raised")


def test_fetch_copilot_login_success_and_failure(tmp_path):
    service = CopilotAuthService(config_dir=tmp_path / "github-copilot")
    success = MagicMock()
    success.status_code = 200
    success.json.return_value = {"login": "octocat"}
    with patch("httpx.get", return_value=success):
        assert service.fetch_copilot_login("gho_test") == "octocat"

    failure = MagicMock()
    failure.status_code = 401
    failure.text = "bad token"
    with patch("httpx.get", return_value=failure):
        try:
            service.fetch_copilot_login("gho_bad")
        except RuntimeError as exc:
            assert "Copilot authentication failed" in str(exc)
        else:
            raise AssertionError("fetch failure was not raised")


def test_copilot_auth_ignores_malformed_config_files(tmp_path):
    config_dir = tmp_path / "github-copilot"
    config_dir.mkdir()
    (config_dir / "apps.json").write_text("{bad json", encoding="utf-8")
    (config_dir / "oauth.json").write_text("{bad json", encoding="utf-8")

    with patch("server.services.runtime.copilot_auth.config.COPILOT_GITHUB_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.GH_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.COPILOT_OAUTH_TOKEN", ""), patch("server.services.runtime.copilot_auth.config.GITHUB_TOKEN", ""):
        auth = CopilotAuthService(config_dir=config_dir).resolve_stored_auth()

    assert auth is None


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
