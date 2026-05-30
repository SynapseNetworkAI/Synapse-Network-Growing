from server.routers import social as social_router
from server.services.social import publishing as social_publishing


def test_x_oauth_start_prefers_env_client_id(monkeypatch, synced_client):
    monkeypatch.setattr(social_publishing.config, "X_OAUTH_CLIENT_ID", "env-client-id")
    monkeypatch.setattr(
        social_publishing.secret_store,
        "read",
        lambda secret_ref: (_ for _ in ()).throw(
            AssertionError(f"secret manager should not be read: {secret_ref}")
        ),
    )

    response = synced_client.get("/api/social/x/oauth/start")

    assert response.status_code == 200
    payload = response.json()
    assert "https://twitter.com/i/oauth2/authorize" in payload["auth_url"]
    assert "client_id=env-client-id" in payload["auth_url"]
    assert "offline.access" in payload["auth_url"]
    assert payload["state"]


def test_x_oauth_start_missing_client_id_fails_without_secret_manager(
    monkeypatch, synced_client
):
    monkeypatch.delenv("X_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.setattr(social_publishing.config, "X_OAUTH_CLIENT_ID", "")
    monkeypatch.setattr(
        social_publishing.secret_store,
        "read",
        lambda secret_ref: (_ for _ in ()).throw(
            AssertionError(f"secret manager should not be read: {secret_ref}")
        ),
    )

    response = synced_client.get("/api/social/x/oauth/start")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "X_OAUTH_CLIENT_ID is required in local environment configuration."
    )


def test_x_oauth_start_social_publish_error_is_bounded(monkeypatch, synced_client):
    monkeypatch.setattr(
        social_router,
        "start_x_oauth_authorization",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            social_publishing.SocialPublishError(
                "gcp_adc_expired",
                "Local Google credentials expired. Run `gcloud auth application-default login`.",
            )
        ),
    )

    response = synced_client.get("/api/social/x/oauth/start")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Local Google credentials expired. Run `gcloud auth application-default login`."
    )


def test_x_oauth_token_provider_prefers_env_client_secret(monkeypatch):
    monkeypatch.setattr(social_publishing.config, "X_OAUTH_CLIENT_ID", "env-client-id")
    monkeypatch.setattr(
        social_publishing.config, "X_OAUTH_CLIENT_SECRET", "env-client-secret"
    )
    monkeypatch.setattr(
        social_publishing.secret_store,
        "read",
        lambda secret_ref: (_ for _ in ()).throw(
            AssertionError(f"secret manager should not be read: {secret_ref}")
        ),
    )

    assert social_publishing.x_oauth_token_provider._client_credentials() == (
        "env-client-id",
        "env-client-secret",
    )
