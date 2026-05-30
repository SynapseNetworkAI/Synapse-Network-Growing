from server.routers import social as social_router
from server.services.social import publishing as social_publishing


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
