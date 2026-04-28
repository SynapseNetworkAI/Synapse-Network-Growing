import io
import urllib.error
import urllib.parse
from datetime import timedelta

import pytest

from server.database import (
    RequirementRow,
    SocialAccountRow,
    utcnow,
    WorkflowRunRow,
)
from server.routers import social as social_router
from server.services.social import publishing as social_publishing
from server.services.workflows import declarative


class FakeSocialCopyProvider:
    def __init__(self, response_text: str):
        self.response_text = response_text

    def call(self, system, user, model, temperature, timeout):
        return self.response_text, 0


class SequencedSocialCopyProvider:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def call(self, system, user, model, temperature, timeout):
        self.calls.append({"system": system, "user": user, "temperature": temperature})
        if not self.responses:
            raise AssertionError("unexpected provider call")
        return self.responses.pop(0), 0


class FakeImageGenerator:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def generate_image(self, *, prompt: str, asset_id: int):
        self.calls.append({"prompt": prompt, "asset_id": asset_id})
        if self.fail:
            raise ValueError("image provider quota exhausted")
        path = social_publishing._media_runtime_dir() / f"test-media-{asset_id}.png"
        path.write_bytes(b"fake-image")
        return social_publishing.GeneratedImageResult(
            local_path=str(path),
            preview_url=f"/api/social/media/{asset_id}/preview",
        )


class FakeXAccessToken:
    access_token = "test-x-access-token"
    refreshed = True
    refresh_token_rotated = False


class FakeXReadClient:
    def __init__(self, access_token: str):
        self.access_token = access_token

    def get_user_by_username(self, username: str):
        class User:
            pass

        user = User()
        user.id = "user-1"
        user.username = username
        user.name = "Example AI"
        return user

    def get_user_tweets(self, user_id: str, *, max_results: int = 5):
        return [
            social_publishing.XPost(
                id="tweet-1",
                text="AI agents are starting to need reliable API access, budget controls, payment rails, and developer infrastructure for autonomous workflows.",
                author_id=user_id,
                created_at="2026-04-26T12:00:00Z",
                public_metrics={
                    "like_count": 120,
                    "retweet_count": 12,
                    "reply_count": 5,
                    "quote_count": 3,
                },
            ),
            social_publishing.XPost(
                id="tweet-short",
                text="Cool.",
                author_id=user_id,
                created_at="2026-04-26T11:00:00Z",
                public_metrics={"like_count": 500},
            ),
        ]


def _fetch_social_post(client, post_id: int) -> dict:
    rows = client.get("/api/social/posts").json()
    return next(row for row in rows if row["id"] == post_id)


def test_default_social_account_migrates_legacy_token_ref(db_session):
    db_session.add(
        SocialAccountRow(
            platform="x",
            handle=social_publishing.DEFAULT_X_HANDLE,
            display_name="Synapse Network",
            secret_ref="x-official-oauth2-user-token",
            status="active",
        )
    )
    db_session.commit()

    account = social_publishing.ensure_default_social_account(db_session)

    assert account.secret_ref == social_publishing.DEFAULT_X_SECRET_REF


def test_social_campaign_goal_can_be_created(synced_client):
    response = synced_client.post(
        "/api/social/campaign-goals",
        json={
            "title": "Developer education week",
            "objective": "Explain zero-gas micropayments to agent builders.",
            "cadence": "weekly",
            "content_pillars": ["Developer education", "Agent payments"],
            "success_metrics": ["docs clicks"],
            "created_by": "operator",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Developer education week"
    assert payload["content_pillars"] == ["Developer education", "Agent payments"]


def test_social_campaign_goal_requires_title_and_objective(synced_client):
    response = synced_client.post(
        "/api/social/campaign-goals",
        json={"title": "", "objective": ""},
    )

    assert response.status_code == 400
    assert "title and objective" in response.json()["detail"]


def test_agent_prompt_generates_publish_ready_draft_without_publishing(
    monkeypatch, synced_client
):
    called = False

    def fail_publish(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("Agent draft generation must not publish to X")

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fail_publish)
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Staging governance update","body_text":"Staging releases now require clear operator review before public updates ship."}'
        ),
    )
    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    prompt = "Announce that staging release governance now requires explicit operator review before posting."

    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "account_id": account_id,
            "prompt": prompt,
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "generating"
    payload = _fetch_social_post(synced_client, payload["id"])
    assert payload["status"] == "approved"
    assert payload["reviewed_by"] == "operator"
    assert payload["generated_by"] == "social_content_agent_v1"
    assert payload["title"] == "Staging governance update"
    assert payload["body_text"]
    assert payload["body_text"] != prompt
    assert payload["policy_check"]["status"] == "passed"
    assert payload["raw_agent_output"]["media_support"] == "single_image_v1"
    assert payload["external_post_id"] is None
    assert called is False


def test_text_only_media_mode_does_not_create_media_asset(monkeypatch, synced_client):
    image_generator = FakeImageGenerator()
    monkeypatch.setattr(social_publishing, "image_generator", image_generator)
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Text update","body_text":"Synapse Network now has a cleaner social publishing review loop.","media_decision":"image","image_prompt":"A network visual","image_alt_text":"Network visual"}'
        ),
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "prompt": "Write an update.",
            "media_mode": "text_only",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "approved"
    assert payload["media_assets"] == []
    assert image_generator.calls == []
    assert payload["raw_agent_output"]["media_mode"] == "text_only"
    assert payload["raw_agent_output"]["media_decision"] == "text"


def test_auto_media_mode_creates_image_asset_when_agent_decides_image(
    monkeypatch, synced_client
):
    image_generator = FakeImageGenerator()
    monkeypatch.setattr(social_publishing, "image_generator", image_generator)
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Visual launch note","body_text":"Synapse turns agent API usage into settled, budgeted micropayments.","media_decision":"image","image_prompt":"A polished dark SaaS visual of AI agents connected by a payment network","image_alt_text":"AI agents connected through a Synapse settlement layer"}'
        ),
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "prompt": "Write a launch update with a visual if useful.",
            "media_mode": "auto",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "approved"
    assert len(payload["media_assets"]) == 1
    asset = payload["media_assets"][0]
    assert asset["media_type"] == "image"
    assert asset["status"] == "ready"
    assert asset["preview_url"].endswith(f"/api/social/media/{asset['id']}/preview")
    assert asset["alt_text"] == "AI agents connected through a Synapse settlement layer"
    assert image_generator.calls[0]["prompt"].startswith("A polished dark SaaS visual")


def test_image_generation_failure_blocks_publish_until_removed_or_regenerated(
    monkeypatch, synced_client
):
    monkeypatch.setattr(
        social_publishing, "image_generator", FakeImageGenerator(fail=True)
    )
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Visual launch note","body_text":"Synapse turns agent API usage into settled, budgeted micropayments.","media_decision":"image","image_prompt":"A polished launch visual","image_alt_text":"Launch visual"}'
        ),
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "prompt": "Write a launch update with a visual.",
            "media_mode": "image_required",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "approved"
    assert payload["media_assets"][0]["status"] == "failed"
    assert "quota exhausted" in payload["media_assets"][0]["failure_summary"]

    publish = synced_client.post(
        f"/api/social/posts/{payload['id']}/publish-x", json={"actor": "operator"}
    )
    assert publish.status_code == 400
    assert "image media failed" in publish.json()["detail"]


def test_media_preview_regenerate_and_remove_endpoints(monkeypatch, synced_client):
    image_generator = FakeImageGenerator()
    monkeypatch.setattr(social_publishing, "image_generator", image_generator)
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Visual launch note","body_text":"Synapse turns agent API usage into settled, budgeted micropayments.","media_decision":"image","image_prompt":"A polished launch visual","image_alt_text":"Launch visual"}'
        ),
    )

    created = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "prompt": "Write a launch update with a visual.",
            "media_mode": "image_required",
            "actor": "operator",
        },
    ).json()
    payload = _fetch_social_post(synced_client, created["id"])
    asset = payload["media_assets"][0]

    preview = synced_client.get(asset["preview_url"])
    assert preview.status_code == 200
    assert preview.content == b"fake-image"

    regenerated = synced_client.post(
        f"/api/social/posts/{created['id']}/regenerate-image",
        json={"actor": "operator"},
    )
    assert regenerated.status_code == 200
    regenerated_payload = regenerated.json()
    assert (
        len(
            [
                item
                for item in regenerated_payload["media_assets"]
                if item["status"] != "removed"
            ]
        )
        == 1
    )

    active_asset = next(
        item
        for item in regenerated_payload["media_assets"]
        if item["status"] != "removed"
    )
    removed = synced_client.delete(
        f"/api/social/posts/{created['id']}/media/{active_asset['id']}"
    )
    assert removed.status_code == 200
    assert all(item["status"] == "removed" for item in removed.json()["media_assets"])


def test_manual_image_upload_replaces_active_media_and_supports_preview(
    monkeypatch, synced_client
):
    image_generator = FakeImageGenerator()
    monkeypatch.setattr(social_publishing, "image_generator", image_generator)
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Visual launch note","body_text":"Synapse turns agent API usage into settled, budgeted micropayments.","media_decision":"image","image_prompt":"A polished launch visual","image_alt_text":"Launch visual"}'
        ),
    )
    created = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "prompt": "Write a launch update with a visual.",
            "media_mode": "image_required",
            "actor": "operator",
        },
    ).json()
    before = _fetch_social_post(synced_client, created["id"])
    assert before["media_assets"][0]["status"] == "ready"

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    upload = synced_client.post(
        f"/api/social/posts/{created['id']}/media/upload",
        data={"actor": "operator", "alt_text": "Operator supplied launch graphic"},
        files={"file": ("launch.png", png, "image/png")},
    )

    assert upload.status_code == 200
    payload = upload.json()
    active_assets = [
        asset for asset in payload["media_assets"] if asset["status"] != "removed"
    ]
    removed_assets = [
        asset for asset in payload["media_assets"] if asset["status"] == "removed"
    ]
    assert len(active_assets) == 1
    assert removed_assets
    assert active_assets[0]["status"] == "ready"
    assert active_assets[0]["alt_text"] == "Operator supplied launch graphic"
    assert synced_client.get(active_assets[0]["preview_url"]).content == png
    assert any(
        event["event_type"] == "image_uploaded_manual" for event in payload["events"]
    )


def test_manual_image_upload_rejects_non_image_and_settled_posts(synced_client):
    created = synced_client.post(
        "/api/social/posts", json={"body_text": "Safe draft."}
    ).json()

    bad_upload = synced_client.post(
        f"/api/social/posts/{created['id']}/media/upload",
        data={"actor": "operator"},
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )
    assert bad_upload.status_code == 400
    assert "image" in bad_upload.json()["detail"]

    synced_client.patch(
        f"/api/social/posts/{created['id']}",
        json={"status": "rejected", "reviewed_by": "operator"},
    )
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    settled_upload = synced_client.post(
        f"/api/social/posts/{created['id']}/media/upload",
        files={"file": ("launch.png", png, "image/png")},
    )
    assert settled_upload.status_code == 400
    assert "settled" in settled_upload.json()["detail"]


def test_manual_image_upload_validation_edge_cases():
    assert social_publishing._image_extension(None, "image/png", b"") == ".png"
    assert social_publishing._image_extension(None, "image/jpeg", b"") == ".jpg"
    assert social_publishing._image_extension(None, "image/webp", b"") == ".webp"
    assert social_publishing._image_extension(None, "image/gif", b"") == ".gif"
    assert social_publishing._image_extension(None, "", b"\xff\xd8\xfffake") == ".jpg"
    assert (
        social_publishing._image_extension(None, "", b"\x89PNG\r\n\x1a\nfake") == ".png"
    )
    assert social_publishing._image_extension(None, "", b"GIF89afake") == ".gif"
    assert social_publishing._image_extension(None, "", b"RIFFxxxxWEBPfake") == ".webp"
    with pytest.raises(ValueError, match="empty"):
        social_publishing._validate_uploaded_image("launch.png", "image/png", b"")
    with pytest.raises(ValueError, match="8MB"):
        social_publishing._validate_uploaded_image(
            "launch.png", "image/png", b"x" * (8 * 1024 * 1024 + 1)
        )
    with pytest.raises(ValueError, match="image"):
        social_publishing._image_extension("notes.txt", "", b"not an image")


def test_media_preview_and_regenerate_validation_errors(monkeypatch, synced_client):
    monkeypatch.setattr(social_publishing, "image_generator", FakeImageGenerator())
    created = synced_client.post(
        "/api/social/posts", json={"body_text": "Safe draft."}
    ).json()
    assert synced_client.get("/api/social/media/999999/preview").status_code == 404
    regenerated = synced_client.post(
        f"/api/social/posts/{created['id']}/regenerate-image",
        json={"actor": "operator"},
    )
    assert regenerated.status_code == 200
    active_asset = next(
        item
        for item in regenerated.json()["media_assets"]
        if item["status"] != "removed"
    )
    assert "Synapse Network official X post" in active_asset["prompt"]
    assert (
        synced_client.delete(
            f"/api/social/posts/{created['id']}/media/999999"
        ).status_code
        == 404
    )
    assert (
        synced_client.delete(
            f"/api/social/posts/{created['id']}/media/{active_asset['id']}"
        ).status_code
        == 200
    )

    synced_client.patch(
        f"/api/social/posts/{created['id']}",
        json={"status": "approved", "reviewed_by": "operator"},
    )
    monkeypatch.setattr(
        social_publishing.x_publisher,
        "publish_text",
        lambda account, body_text: social_publishing.XPublishResult(
            post_id="1804", response_summary={"data": {"id": "1804"}}
        ),
    )
    published = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    ).json()
    assert (
        synced_client.post(
            f"/api/social/posts/{published['id']}/regenerate-image",
            json={"actor": "operator"},
        ).status_code
        == 400
    )
    assert (
        synced_client.delete(
            f"/api/social/posts/{published['id']}/media/999999"
        ).status_code
        == 400
    )


def test_media_preview_rejects_missing_or_outside_files(
    synced_client, db_session, tmp_path
):
    created = synced_client.post(
        "/api/social/posts", json={"body_text": "Safe draft."}
    ).json()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    outside_media = social_publishing.SocialPostMediaAssetRow(
        post_id=int(created["id"]),
        media_type="image",
        status="ready",
        local_path=str(outside),
    )
    db_session.add(outside_media)
    db_session.commit()

    assert (
        synced_client.get(f"/api/social/media/{outside_media.id}/preview").status_code
        == 400
    )

    missing = social_publishing._media_runtime_dir() / "missing-preview.png"
    missing_media = social_publishing.SocialPostMediaAssetRow(
        post_id=int(created["id"]),
        media_type="image",
        status="ready",
        local_path=str(missing),
    )
    db_session.add(missing_media)
    db_session.commit()

    assert (
        synced_client.get(f"/api/social/media/{missing_media.id}/preview").status_code
        == 400
    )


def test_agent_prompt_uses_dedicated_social_content_provider(
    monkeypatch, synced_client
):
    observed: dict[str, object] = {}

    def fake_codex_exec(**kwargs):
        observed.update(kwargs)
        return social_publishing.CodexExecResult(
            text='{"title":"Dedicated provider","body_text":"A concise public X update generated through the social copy provider."}',
            stdout="",
            stderr="",
            exit_code=0,
            execution_time_ms=42,
            command=["codex"],
            output_path=kwargs["output_path"],
            thread_id="thread-social",
            json_event_count=1,
        )

    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex"
    )
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_MODEL", "gpt-5-codex"
    )
    monkeypatch.setattr(social_publishing, "run_codex_exec", fake_codex_exec)

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "account_id": account_id,
            "prompt": "Write a concise public update.",
            "style_type": "technical",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    assert observed["model"] == "gpt-5-codex"
    assert observed["timeout"] >= 180
    assert observed["sandbox_mode"] == "read-only"
    assert observed["output_schema"] == social_publishing.SOCIAL_CODEX_OUTPUT_SCHEMA
    assert "maxLength" not in str(observed["output_schema"])
    assert "Product Marketing Context" in str(observed["prompt"])
    assert "Social Content" in str(observed["prompt"])
    assert "Launch Strategy" not in str(observed["prompt"])
    assert "Write a concise public update." in str(observed["prompt"])
    assert "strong hook" in str(observed["prompt"])
    assert "compelling" in str(observed["prompt"])
    assert "high-trust" in str(observed["prompt"])
    assert "technical:" in str(observed["prompt"])
    assert "X Premium-style post" in str(observed["prompt"])
    assert "Do not optimize for the old 280-character tweet format" in str(
        observed["prompt"]
    )
    assert "2-4 relevant X hashtags" in str(observed["prompt"])
    assert "#AIAgents" in str(observed["prompt"])
    assert "Finish the post with 2-4 natural hashtags" in str(observed["prompt"])
    assert "single X post text under 280 characters" not in str(observed["prompt"])
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["raw_agent_output"]["requested_model"] == "gpt-5-codex"
    assert payload["raw_agent_output"]["model"] == "gpt-5-codex"
    assert payload["raw_agent_output"]["style_type"] == "technical"
    assert payload["raw_agent_output"]["generation_metadata"]["output_artifact"]


def test_codex_nonzero_with_valid_json_and_noise_is_accepted(
    monkeypatch, synced_client
):
    def fake_codex_exec(**kwargs):
        return social_publishing.CodexExecResult(
            text='{"title":"Cleanup-noise output","body_text":"Synapse staging is live for builders to review agent payment infrastructure safely."}',
            stdout="",
            stderr="shell_snapshot: failed to delete shell snapshot",
            exit_code=1,
            execution_time_ms=10,
            command=["codex"],
            output_path=kwargs["output_path"],
        )

    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex"
    )
    monkeypatch.setattr(social_publishing, "run_codex_exec", fake_codex_exec)

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "account_id": account_id,
            "prompt": "Write a concise staging launch update.",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["title"] == "Cleanup-noise output"
    assert payload["raw_agent_output"]["generation_metadata"]["exit_code"] == 1
    assert (
        payload["raw_agent_output"]["generation_metadata"][
            "nonzero_exit_with_valid_json"
        ]
        is True
    )


def test_codex_timeout_with_valid_json_artifact_is_accepted(monkeypatch, synced_client):
    def fake_codex_exec(**kwargs):
        return social_publishing.CodexExecResult(
            text='{"title":"Timeout-after-output","body_text":"Synapse Network helps AI agents discover, invoke, and pay for APIs through a settlement layer built for autonomous software.","media_decision":"text","image_prompt":"","image_alt_text":""}',
            stdout="",
            stderr="Codex CLI execution timed out after 180s",
            exit_code=124,
            execution_time_ms=180000,
            command=["codex"],
            output_path=kwargs["output_path"],
        )

    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex"
    )
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_TIMEOUT", 180)
    monkeypatch.setattr(social_publishing, "run_codex_exec", fake_codex_exec)

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "account_id": account_id,
            "prompt": "Write a launch update for Synapse Network.",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "approved"
    assert payload["raw_agent_output"]["generation_metadata"]["exit_code"] == 124
    assert (
        payload["raw_agent_output"]["generation_metadata"]["timeout_after_valid_json"]
        is True
    )


def test_codex_nonzero_without_valid_json_fails_closed(monkeypatch, synced_client):
    def fake_codex_exec(**kwargs):
        return social_publishing.CodexExecResult(
            text="",
            stdout="",
            stderr="permission denied while reading workspace",
            exit_code=1,
            execution_time_ms=10,
            command=["codex"],
            output_path=kwargs["output_path"],
        )

    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex"
    )
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_MODEL", "gpt-5-codex"
    )
    monkeypatch.setattr(social_publishing, "run_codex_exec", fake_codex_exec)

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "account_id": account_id,
            "prompt": "Write a concise staging launch update.",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "failed"
    assert "provider=codex" in payload["failure_summary"]
    assert "exit_code=1" in payload["failure_summary"]
    assert "output_artifact=" in payload["failure_summary"]


def test_codex_model_compatibility_falls_back_to_supported_model(
    monkeypatch, synced_client
):
    observed_models: list[str] = []

    def fake_codex_exec(**kwargs):
        observed_models.append(kwargs["model"])
        if kwargs["model"] in {"gpt-5-codex", "gpt-5.5"}:
            return social_publishing.CodexExecResult(
                text="",
                stdout=f'{{"type":"error","message":"The {kwargs["model"]} model requires a newer version of Codex."}}',
                stderr="",
                exit_code=1,
                execution_time_ms=10,
                command=["codex"],
                output_path=kwargs["output_path"],
            )
        return social_publishing.CodexExecResult(
            text='{"title":"Fallback model","body_text":"Synapse Network now has a concise, human-reviewed X update ready for launch followers."}',
            stdout="",
            stderr="",
            exit_code=0,
            execution_time_ms=12,
            command=["codex"],
            output_path=kwargs["output_path"],
        )

    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex"
    )
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_MODEL", "gpt-5-codex"
    )
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_FALLBACK_MODEL", "gpt-5.5,gpt-5.4"
    )
    monkeypatch.setattr(social_publishing, "run_codex_exec", fake_codex_exec)

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "account_id": account_id,
            "prompt": "Write a concise staging launch update.",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    assert observed_models == ["gpt-5-codex", "gpt-5.5", "gpt-5.4"]
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["raw_agent_output"]["requested_model"] == "gpt-5-codex"
    assert payload["raw_agent_output"]["model"] == "gpt-5.4"
    assert payload["raw_agent_output"]["generation_metadata"]["attempted_models"] == [
        "gpt-5-codex",
        "gpt-5.5",
        "gpt-5.4",
    ]
    assert payload["raw_agent_output"]["generation_metadata"]["fallback_used"] is True


def test_agent_prompt_adds_launch_skill_context(monkeypatch, synced_client):
    observed_prompts: dict[str, str] = {}

    class ObservedProvider:
        def call(self, system, user, model, temperature, timeout):
            observed_prompts["system"] = system
            observed_prompts["user"] = user
            return (
                '{"title":"Staging is live","body_text":"Synapse staging is live for operators to review the agent-payment workflow before broader rollout."}',
                0,
            )

    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing, "get_provider", lambda provider_name=None: ObservedProvider()
    )

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "account_id": account_id,
            "prompt": "Announce the staging launch update.",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert "launch-strategy" in payload["raw_agent_output"]["context_sources"]
    assert "Launch Strategy" in observed_prompts["user"]
    assert "Announce the staging launch update." in observed_prompts["user"]
    assert "strong hook" in observed_prompts["system"]
    assert "clear product value" in observed_prompts["system"]
    assert "hashtags" in observed_prompts["system"]


def test_agent_prompt_sanitizes_internal_paths_before_provider_call(
    monkeypatch, synced_client
):
    observed_prompts: dict[str, str] = {}

    class ObservedProvider:
        def call(self, system, user, model, temperature, timeout):
            observed_prompts["user"] = user
            return (
                '{"title":"First public update","body_text":"Synapse staging is live, and the team is preparing the first official X update for builders."}',
                0,
            )

    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing, "get_provider", lambda provider_name=None: ObservedProvider()
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "prompt": "读取/Users/cliff/workspace/agent/Synapse-Network/docs 给出文档，生成第一篇官方推文。",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "approved"
    assert "/Users/" not in observed_prompts["user"]
    assert "[path]" in observed_prompts["user"]
    assert "读取" in observed_prompts["user"]
    assert "给出文档" in observed_prompts["user"]
    assert "生成第一篇" in observed_prompts["user"]


def test_social_generation_helper_edge_cases(monkeypatch):
    parsed = social_publishing._parse_generated_x_post(
        '{"title":"T","body_text":"B","media_decision":"weird"}'
    )
    assert parsed.media_decision == "text"
    fenced = social_publishing._parse_generated_x_post(
        '```json\n{"title":"Fenced","body_text":"Body"}\n```'
    )
    assert fenced.title == "Fenced"
    extracted = social_publishing._parse_generated_x_post(
        'prefix {"title":"Nested","body_text":"brace in string } ok"} suffix'
    )
    assert extracted.body_text == "brace in string } ok"
    with pytest.raises(ValueError, match="invalid JSON"):
        social_publishing._parse_generated_x_post(
            'prefix {"title": "Broken", "body_text": } suffix'
        )
    assert (
        social_publishing._codex_nonzero_can_use_json(
            social_publishing.CodexExecResult(
                text='{"title":"T","body_text":"B"}',
                stdout="",
                stderr="cleanup error",
                exit_code=1,
                execution_time_ms=1,
                command=["codex"],
                output_path=None,
            )
        )
        is True
    )
    assert (
        social_publishing._codex_nonzero_can_use_json(
            social_publishing.CodexExecResult(
                text="not json",
                stdout="",
                stderr="cleanup error",
                exit_code=1,
                execution_time_ms=1,
                command=["codex"],
                output_path=None,
            )
        )
        is False
    )
    assert "agent economy" in social_publishing._style_guidance("visionary")
    social_publishing._validate_generated_x_post(
        "Write about API access",
        social_publishing.GeneratedXPost(
            title="Reduce API key sprawl",
            body_text="Synapse Network helps AI agents pay for APIs without creating more API key sprawl for developers.",
        ),
    )
    with pytest.raises(ValueError, match="credential-shaped"):
        social_publishing._validate_generated_x_post(
            "Write about a launch",
            social_publishing.GeneratedXPost(
                title="Unsafe", body_text="api_key=sk-test-secret123456"
            ),
        )
    with pytest.raises(ValueError, match="image_prompt_empty"):
        social_publishing._validate_image_prompt("")
    with pytest.raises(ValueError, match="internal_or_secret"):
        social_publishing._validate_image_prompt("workflow JSON with required_commands")
    with pytest.raises(ValueError, match="local_path"):
        social_publishing._validate_image_prompt("/home/cliff/workspace/secret.png")
    with pytest.raises(ValueError, match="high_risk"):
        social_publishing._validate_image_prompt("Guaranteed profit visual")

    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"No prompt","body_text":"Safe public copy.","media_decision":"image"}'
        ),
    )
    with pytest.raises(ValueError, match="image_prompt"):
        social_publishing._generate_x_post_copy(
            "Write with image", media_mode="image_required"
        )


def test_openai_image_generator_success_and_failure_paths(monkeypatch):
    generator = social_publishing.SocialImageGenerator()
    monkeypatch.setattr(social_publishing.config, "SOCIAL_IMAGE_PROVIDER", "disabled")
    with pytest.raises(ValueError, match="unsupported provider"):
        generator.generate_image(prompt="A safe image", asset_id=501)

    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_IMAGE_PROVIDER", "openai_images"
    )
    monkeypatch.setattr(social_publishing.config, "OPENAI_API_KEY", "")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        generator.generate_image(prompt="A safe image", asset_id=502)

    class FakeImageResponse:
        def __init__(self, raw: bytes):
            self.raw = raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return self.raw

    monkeypatch.setattr(social_publishing.config, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: FakeImageResponse(
            b'{"data":[{"b64_json":"ZmFrZS1pbWFnZQ=="}]}'
        ),
    )
    result = generator.generate_image(prompt="A safe image", asset_id=503)
    assert result.preview_url.endswith("/api/social/media/503/preview")
    assert "social-post-media-503.png" in result.local_path

    def raise_openai_http(request, timeout):
        raise urllib.error.HTTPError(
            "https://api.openai.com/v1/images/generations",
            400,
            "bad",
            {},
            io.BytesIO(b"bad request"),
        )

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", raise_openai_http)
    with pytest.raises(ValueError, match="HTTP 400"):
        generator.generate_image(prompt="A safe image", asset_id=504)

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: FakeImageResponse(b'{"data":[{}]}'),
    )
    with pytest.raises(ValueError, match="did not return image data"):
        generator.generate_image(prompt="A safe image", asset_id=505)


def test_agent_prompt_with_blocked_content_requires_revision_without_publishing(
    monkeypatch, synced_client
):
    called = False

    def fail_publish(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("blocked Agent draft generation must not publish to X")

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fail_publish)
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Unsafe launch claim","body_text":"Guaranteed risk-free returns. Send funds now."}'
        ),
    )
    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]

    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "account_id": account_id,
            "prompt": "Guaranteed risk-free returns. Send funds now to capture the launch opportunity.",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "needs_review"
    assert payload["reviewed_by"] is None
    assert payload["policy_check"]["status"] == "blocked"
    assert payload["external_post_id"] is None
    assert called is False


def test_agent_prompt_copy_retries_once_before_creating_draft(
    monkeypatch, synced_client
):
    prompt = "Tell people we created an X account and ask them to follow us."
    provider = SequencedSocialCopyProvider(
        [
            f'{{"title":"Copied prompt","body_text":"{prompt}"}}',
            '{"title":"Synapse Network is live on X","body_text":"AI agents need a way to pay for APIs safely. Synapse Network gives them zero-gas micropayments, budget isolation, and an MCP-native path to discover and use services."}',
        ]
    )
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing, "get_provider", lambda provider_name=None: provider
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft", json={"prompt": prompt, "actor": "operator"}
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "approved"
    assert payload["body_text"] != prompt
    assert (
        payload["raw_agent_output"]["generation_metadata"]["rewrite_attempted"] is True
    )
    assert len(provider.calls) == 2
    assert provider.calls[0]["temperature"] == 0.7
    assert provider.calls[1]["temperature"] == 0.3


def test_agent_invalid_json_retries_once_before_creating_draft(
    monkeypatch, synced_client
):
    prompt = "Introduce Synapse Network to AI agent builders."
    provider = SequencedSocialCopyProvider(
        [
            "Title: Synapse Network\nBody: AI agents need safe payment rails.",
            '{"title":"Synapse Network for AI agents","body_text":"AI agents can reason and use tools, but they still need safe payment rails. Synapse Network gives builders zero-gas micropayments, budget isolation, and a settlement layer for API access."}',
        ]
    )
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing, "get_provider", lambda provider_name=None: provider
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft", json={"prompt": prompt, "actor": "operator"}
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "approved"
    assert payload["title"] == "Synapse Network for AI agents"
    assert (
        payload["raw_agent_output"]["generation_metadata"]["rewrite_attempted"] is True
    )
    assert "not valid JSON" in provider.calls[1]["user"]


def test_social_codex_output_schema_requires_all_declared_properties():
    properties = set(social_publishing.SOCIAL_CODEX_OUTPUT_SCHEMA["properties"].keys())
    required = set(social_publishing.SOCIAL_CODEX_OUTPUT_SCHEMA["required"])

    assert required == properties


def test_agent_prompt_copy_still_fails_after_rewrite_budget(monkeypatch, synced_client):
    prompt = "Tell people we created an X account and ask them to follow us."
    provider = SequencedSocialCopyProvider(
        [
            f'{{"title":"Copied prompt","body_text":"{prompt}"}}',
            f'{{"title":"Still copied prompt","body_text":"{prompt}"}}',
        ]
    )
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing, "get_provider", lambda provider_name=None: provider
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft", json={"prompt": prompt, "actor": "operator"}
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "failed"
    assert "agent_generation_low_transform" in payload["failure_summary"]


def test_agent_prompt_internal_path_or_workflow_output_is_rejected(
    monkeypatch, synced_client
):
    prompt = "Read /Users/cliff/workspace/agent/Synapse-Network/docs and write the first X post."
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Internal leak","body_text":"Read /Users/cliff/workspace/agent/Synapse-Network/docs and generate the first post."}'
        ),
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft", json={"prompt": prompt, "actor": "operator"}
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "failed"
    assert payload["failure_summary"].startswith("agent_generation_")

    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Workflow JSON","body_text":"acceptance matrix required_commands show the workflow JSON for this launch."}'
        ),
    )
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"prompt": "Write a launch note.", "actor": "operator"},
    )
    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "failed"
    assert payload["failure_summary"].startswith("agent_generation_")


def test_agent_generation_invalid_json_fails_without_creating_draft(
    monkeypatch, synced_client
):
    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider("not json"),
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"prompt": "Write a launch note.", "actor": "operator"},
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "failed"
    assert "agent_generation_failed" in payload["failure_summary"]


def test_agent_generation_provider_failure_fails_without_creating_draft(
    monkeypatch, synced_client
):
    class FailingProvider:
        def call(self, system, user, model, temperature, timeout):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider"
    )
    monkeypatch.setattr(
        social_publishing, "get_provider", lambda provider_name=None: FailingProvider()
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"prompt": "Write a launch note.", "actor": "operator"},
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "failed"
    assert "provider unavailable" in payload["failure_summary"]


def test_unapproved_draft_cannot_publish(synced_client):
    created = synced_client.post(
        "/api/social/posts",
        json={"body_text": "A safe draft that still needs human review."},
    ).json()

    response = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    )

    assert response.status_code == 400
    assert "only approved" in response.json()["detail"]


def test_approved_draft_publishes_to_x_with_mocked_publisher(
    monkeypatch, synced_client
):
    captured: dict[str, str] = {}

    def fake_publish(account, body_text):
        captured["handle"] = account.handle
        captured["body_text"] = body_text
        return social_publishing.XPublishResult(
            post_id="1800000000000000001",
            response_summary={"data": {"id": "1800000000000000001"}},
        )

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fake_publish)
    created = synced_client.post(
        "/api/social/posts",
        json={
            "body_text": "Synapse Agent Ops now has a human-gated X publishing surface."
        },
    ).json()
    approved = synced_client.patch(
        f"/api/social/posts/{created['id']}",
        json={"status": "approved", "reviewed_by": "operator"},
    )
    assert approved.status_code == 200

    response = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "published"
    assert payload["external_post_id"] == "1800000000000000001"
    assert payload["external_url"].endswith("/status/1800000000000000001")
    assert captured == {
        "handle": "SynapseNetworkA",
        "body_text": "Synapse Agent Ops now has a human-gated X publishing surface.",
    }


def test_approved_draft_with_image_uploads_media_before_x_publish(
    monkeypatch, synced_client, db_session
):
    captured: dict[str, object] = {}

    def fake_upload(account, image_path):
        captured["upload_handle"] = account.handle
        captured["image_path"] = image_path
        return "media-123"

    def fake_publish(account, body_text, media_ids=None):
        captured["publish_handle"] = account.handle
        captured["body_text"] = body_text
        captured["media_ids"] = media_ids
        return social_publishing.XPublishResult(
            post_id="1800000000000000042",
            response_summary={"data": {"id": "1800000000000000042"}},
        )

    monkeypatch.setattr(social_publishing.x_publisher, "upload_image", fake_upload)
    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fake_publish)
    created = synced_client.post(
        "/api/social/posts",
        json={
            "body_text": "Synapse Network now ships reviewable X posts with generated images."
        },
    ).json()
    synced_client.patch(
        f"/api/social/posts/{created['id']}",
        json={"status": "approved", "reviewed_by": "operator"},
    )
    image_path = social_publishing._media_runtime_dir() / "publish-test-image.png"
    image_path.write_bytes(b"fake-image")
    media = social_publishing.SocialPostMediaAssetRow(
        post_id=int(created["id"]),
        media_type="image",
        status="ready",
        prompt="A Synapse Network visual",
        alt_text="Synapse Network visual",
        local_path=str(image_path),
        preview_url="/api/social/media/999/preview",
    )
    db_session.add(media)
    db_session.commit()

    response = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "published"
    assert captured["media_ids"] == ["media-123"]
    assert (
        captured["body_text"]
        == "Synapse Network now ships reviewable X posts with generated images."
    )
    assert payload["media_assets"][0]["x_media_id"] == "media-123"
    assert payload["media_assets"][0]["status"] == "uploaded"


def test_publish_rejects_pending_image_and_reuses_uploaded_media_id(
    monkeypatch, synced_client, db_session
):
    created = synced_client.post(
        "/api/social/posts",
        json={
            "body_text": "Synapse Network now supports human-reviewed X image posts."
        },
    ).json()
    synced_client.patch(
        f"/api/social/posts/{created['id']}",
        json={"status": "approved", "reviewed_by": "operator"},
    )
    pending_media = social_publishing.SocialPostMediaAssetRow(
        post_id=int(created["id"]),
        media_type="image",
        status="generating",
        prompt="A pending image",
    )
    db_session.add(pending_media)
    db_session.commit()

    pending = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    )
    assert pending.status_code == 400
    assert "not ready" in pending.json()["detail"]

    pending_media.status = "removed"
    ready_media = social_publishing.SocialPostMediaAssetRow(
        post_id=int(created["id"]),
        media_type="image",
        status="uploaded",
        prompt="Already uploaded image",
        x_media_id="media-existing",
    )
    db_session.add(ready_media)
    db_session.commit()

    def fail_upload(account, image_path):
        raise AssertionError("existing X media id should be reused")

    captured: dict[str, object] = {}

    def fake_publish(account, body_text, media_ids=None):
        captured["media_ids"] = media_ids
        return social_publishing.XPublishResult(
            post_id="1800000000000000099",
            response_summary={"data": {"id": "1800000000000000099"}},
        )

    monkeypatch.setattr(social_publishing.x_publisher, "upload_image", fail_upload)
    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fake_publish)

    published = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    )
    assert published.status_code == 200
    assert captured["media_ids"] == ["media-existing"]


def test_x_media_upload_failure_does_not_fallback_to_text_only(
    monkeypatch, synced_client, db_session
):
    def fail_upload(account, image_path):
        raise social_publishing.SocialPublishError(
            "x_media_upload_failed", "X media upload failed."
        )

    def fail_if_text_publish(*args, **kwargs):
        raise AssertionError("must not publish text-only when image upload fails")

    monkeypatch.setattr(social_publishing.x_publisher, "upload_image", fail_upload)
    monkeypatch.setattr(
        social_publishing.x_publisher, "publish_text", fail_if_text_publish
    )
    created = synced_client.post(
        "/api/social/posts", json={"body_text": "Safe image-backed post."}
    ).json()
    synced_client.patch(
        f"/api/social/posts/{created['id']}",
        json={"status": "approved", "reviewed_by": "operator"},
    )
    image_path = social_publishing._media_runtime_dir() / "publish-fail-image.png"
    image_path.write_bytes(b"fake-image")
    db_session.add(
        social_publishing.SocialPostMediaAssetRow(
            post_id=int(created["id"]),
            media_type="image",
            status="ready",
            prompt="A Synapse Network visual",
            alt_text="Synapse Network visual",
            local_path=str(image_path),
            preview_url="/api/social/media/1000/preview",
        )
    )
    db_session.commit()

    response = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["failure_summary"] == "X media upload failed."


def test_x_auth_failure_is_bounded_and_does_not_leak_secret(monkeypatch, synced_client):
    def fake_publish(account, body_text):
        raise social_publishing.SocialPublishError(
            "x_auth_failed",
            "X API authentication failed. Update the OAuth user token secret.",
        )

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fake_publish)
    created = synced_client.post(
        "/api/social/posts", json={"body_text": "Safe post."}
    ).json()
    synced_client.patch(
        f"/api/social/posts/{created['id']}",
        json={"status": "approved", "reviewed_by": "operator"},
    )

    response = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert (
        payload["failure_summary"]
        == "X API authentication failed. Update the OAuth user token secret."
    )
    assert "token-value" not in str(payload).lower()
    assert "authorization" not in str(payload).lower()


def test_x_oauth_start_returns_pkce_authorization_url(monkeypatch, synced_client):
    social_publishing.x_oauth_token_provider._cache.clear()

    def fake_read(secret_ref):
        if secret_ref == social_publishing.config.X_OAUTH_CLIENT_ID_SECRET:
            return "client-id-123"
        raise AssertionError(f"unexpected secret read: {secret_ref}")

    monkeypatch.setattr(social_publishing.secret_store, "read", fake_read)

    response = synced_client.get("/api/social/x/oauth/start")

    assert response.status_code == 200
    payload = response.json()
    assert "https://twitter.com/i/oauth2/authorize" in payload["auth_url"]
    assert "tweet.write" in payload["auth_url"]
    assert "media.write" in payload["auth_url"]
    assert "offline.access" in payload["auth_url"]
    assert "code_challenge_method=S256" in payload["auth_url"]
    query = urllib.parse.parse_qs(urllib.parse.urlparse(payload["auth_url"]).query)
    assert query["redirect_uri"] == [
        "http://127.0.0.1:9600/api/social/x/oauth/callback"
    ]
    assert payload["state"]


def test_social_oauth_router_errors_are_bounded(monkeypatch, synced_client):
    monkeypatch.setattr(
        social_router,
        "start_x_oauth_authorization",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("oauth start failed")),
    )
    start = synced_client.get("/api/social/x/oauth/start")
    assert start.status_code == 400
    assert start.json()["detail"] == "oauth start failed"

    monkeypatch.setattr(
        social_router,
        "complete_x_oauth_authorization",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("oauth callback failed")
        ),
    )
    callback = synced_client.get("/api/social/x/oauth/callback?state=s&code=c")
    assert callback.status_code == 400
    assert callback.json()["detail"] == "oauth callback failed"


def test_x_oauth_callback_stores_refresh_token_without_returning_access_token(
    monkeypatch, synced_client
):
    social_publishing.x_oauth_token_provider._cache.clear()
    stored_versions: list[tuple[str, str]] = []

    def fake_read(secret_ref):
        if secret_ref == social_publishing.config.X_OAUTH_CLIENT_ID_SECRET:
            return "client-id-123"
        if secret_ref == social_publishing.config.X_OAUTH_CLIENT_SECRET_SECRET:
            return "client-secret-456"
        raise AssertionError(f"unexpected secret read: {secret_ref}")

    class FakeTokenResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return b'{"access_token":"access-token-secret","refresh_token":"refresh-token-secret","expires_in":7200}'

    monkeypatch.setattr(social_publishing.secret_store, "read", fake_read)
    monkeypatch.setattr(
        social_publishing.secret_store,
        "add_version",
        lambda secret_ref, value: stored_versions.append((secret_ref, value)),
    )
    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: FakeTokenResponse(),
    )

    start = synced_client.get("/api/social/x/oauth/start").json()
    callback = synced_client.get(
        f"/api/social/x/oauth/callback?state={start['state']}&code=oauth-code"
    )

    assert callback.status_code == 200
    payload = callback.json()
    assert payload["status"] == "authorized"
    assert "access-token-secret" not in str(payload)
    assert stored_versions == [
        (social_publishing.config.X_OAUTH_REFRESH_TOKEN_SECRET, "refresh-token-secret")
    ]


def test_x_oauth_callback_rejects_invalid_and_expired_state(
    monkeypatch, synced_client, db_session
):
    with pytest.raises(ValueError, match="requires state and code"):
        social_publishing.complete_x_oauth_authorization(db_session, state="", code="")
    with pytest.raises(ValueError, match="not recognized"):
        social_publishing.complete_x_oauth_authorization(
            db_session, state="missing", code="code"
        )

    account = social_publishing.ensure_default_social_account(db_session)
    used = social_publishing.SocialOAuthSessionRow(
        platform="x",
        account_id=int(account.id),
        state="used-state",
        code_verifier="verifier",
        redirect_uri="http://127.0.0.1/callback",
        scope=social_publishing.X_OAUTH_SCOPE,
        status="completed",
        expires_at=utcnow() + timedelta(minutes=5),
    )
    expired = social_publishing.SocialOAuthSessionRow(
        platform="x",
        account_id=int(account.id),
        state="expired-state",
        code_verifier="verifier",
        redirect_uri="http://127.0.0.1/callback",
        scope=social_publishing.X_OAUTH_SCOPE,
        status="pending",
        expires_at=utcnow() - timedelta(minutes=1),
    )
    db_session.add_all([used, expired])
    db_session.commit()

    with pytest.raises(ValueError, match="already used"):
        social_publishing.complete_x_oauth_authorization(
            db_session, state="used-state", code="code"
        )
    with pytest.raises(ValueError, match="expired"):
        social_publishing.complete_x_oauth_authorization(
            db_session, state="expired-state", code="code"
        )


def test_x_oauth_callback_marks_session_failed_on_exchange_error(
    monkeypatch, db_session
):
    account = social_publishing.ensure_default_social_account(db_session)
    session = social_publishing.SocialOAuthSessionRow(
        platform="x",
        account_id=int(account.id),
        state="exchange-fails",
        code_verifier="verifier",
        redirect_uri="http://127.0.0.1/callback",
        scope=social_publishing.X_OAUTH_SCOPE,
        status="pending",
        expires_at=utcnow() + timedelta(minutes=5),
    )
    db_session.add(session)
    db_session.commit()

    def fail_exchange(**kwargs):
        raise social_publishing.SocialPublishError(
            "x_refresh_failed", "token exchange failed"
        )

    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "exchange_authorization_code",
        fail_exchange,
    )
    with pytest.raises(ValueError, match="token exchange failed"):
        social_publishing.complete_x_oauth_authorization(
            db_session, state="exchange-fails", code="code"
        )
    db_session.refresh(session)
    assert session.status == "failed"


def test_publish_refreshes_oauth_access_token_and_records_refresh_event(
    monkeypatch, synced_client
):
    social_publishing.x_oauth_token_provider._cache.clear()
    stored_versions: list[tuple[str, str]] = []
    seen_authorizations: list[str] = []

    def fake_read(secret_ref):
        values = {
            social_publishing.config.X_OAUTH_CLIENT_ID_SECRET: "client-id-123",
            social_publishing.config.X_OAUTH_CLIENT_SECRET_SECRET: "client-secret-456",
            social_publishing.config.X_OAUTH_REFRESH_TOKEN_SECRET: "refresh-old",
        }
        if secret_ref in values:
            return values[secret_ref]
        raise AssertionError(f"unexpected secret read: {secret_ref}")

    class FakeResponse:
        def __init__(self, raw: bytes):
            self.raw = raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return self.raw

    def fake_urlopen(request, timeout):
        if request.full_url == social_publishing.X_OAUTH_TOKEN_URL:
            return FakeResponse(
                b'{"access_token":"access-fresh","refresh_token":"refresh-new","expires_in":7200}'
            )
        if request.full_url == social_publishing.X_POST_URL:
            seen_authorizations.append(
                dict(request.header_items()).get("Authorization", "")
            )
            return FakeResponse(b'{"data":{"id":"1800000000000000999"}}')
        raise AssertionError(f"unexpected url: {request.full_url}")

    monkeypatch.setattr(social_publishing.secret_store, "read", fake_read)
    monkeypatch.setattr(
        social_publishing.secret_store,
        "add_version",
        lambda secret_ref, value: stored_versions.append((secret_ref, value)),
    )
    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", fake_urlopen)

    created = synced_client.post(
        "/api/social/posts", json={"body_text": "Safe post after OAuth refresh."}
    ).json()
    synced_client.patch(
        f"/api/social/posts/{created['id']}",
        json={"status": "approved", "reviewed_by": "operator"},
    )
    published = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    ).json()

    assert published["status"] == "published"
    assert published["external_post_id"] == "1800000000000000999"
    assert seen_authorizations == ["Bearer access-fresh"]
    assert stored_versions == [
        (social_publishing.config.X_OAUTH_REFRESH_TOKEN_SECRET, "refresh-new")
    ]
    events = [
        event
        for event in published["events"]
        if event["event_type"] == "x_token_refreshed"
    ]
    assert events
    assert "access-fresh" not in str(published)


def test_failed_publish_can_be_retried_after_secret_or_rate_limit_fix(
    monkeypatch, synced_client
):
    attempts = {"count": 0}

    def flaky_publish(account, body_text):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise social_publishing.SocialPublishError(
                "x_auth_failed",
                "X API authentication failed. Update the OAuth user token secret.",
            )
        return social_publishing.XPublishResult(
            post_id="1800000000000000044",
            response_summary={"data": {"id": "1800000000000000044"}},
        )

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", flaky_publish)
    created = synced_client.post(
        "/api/social/posts", json={"body_text": "Safe post after credential recovery."}
    ).json()
    synced_client.patch(
        f"/api/social/posts/{created['id']}",
        json={"status": "approved", "reviewed_by": "operator"},
    )

    failed = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    ).json()
    assert failed["status"] == "failed"
    assert "authentication failed" in failed["failure_summary"]

    retried = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    )
    assert retried.status_code == 200
    payload = retried.json()
    assert payload["status"] == "published"
    assert payload["external_post_id"] == "1800000000000000044"
    assert attempts["count"] == 2


def test_x_rate_limit_failure_records_failed_status(monkeypatch, synced_client):
    def fake_publish(account, body_text):
        raise social_publishing.SocialPublishError(
            "x_rate_limited",
            "X API rate limit reached. Try again after the rate-limit window.",
        )

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fake_publish)
    created = synced_client.post(
        "/api/social/posts", json={"body_text": "Safe post for rate limit test."}
    ).json()
    synced_client.patch(
        f"/api/social/posts/{created['id']}",
        json={"status": "approved", "reviewed_by": "operator"},
    )

    response = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert "rate limit" in payload["failure_summary"].lower()


def test_blocked_content_cannot_be_approved(synced_client):
    created = synced_client.post(
        "/api/social/posts",
        json={"body_text": "Guaranteed risk-free return. Send funds now."},
    ).json()

    response = synced_client.patch(
        f"/api/social/posts/{created['id']}",
        json={"status": "approved", "reviewed_by": "operator"},
    )

    assert response.status_code == 400
    assert "blocked social content" in response.json()["detail"]


def test_policy_check_blocks_empty_and_risky_content_but_not_long_text():
    empty = social_publishing.run_content_policy_check("")
    assert empty["status"] == "blocked"
    assert "body_text_empty" in empty["blocked_reasons"]

    long = social_publishing.run_content_policy_check("x" * 600)
    assert long["status"] == "passed"
    assert long["character_count"] == 600
    assert "x_post_exceeds_280_characters" not in long["blocked_reasons"]

    risky = social_publishing.run_content_policy_check(
        "Launching soon with guaranteed risk-free return."
    )
    assert risky["status"] == "blocked"
    assert "guaranteed_return" in risky["blocked_reasons"]
    assert "time_sensitive_claim_review" in risky["warnings"]


def test_social_post_update_reject_rewrite_and_filter(synced_client):
    first = synced_client.post(
        "/api/social/posts", json={"body_text": "First safe draft."}
    ).json()
    second = synced_client.post(
        "/api/social/posts", json={"body_text": "Second safe draft."}
    ).json()

    edit_response = synced_client.patch(
        f"/api/social/posts/{first['id']}",
        json={
            "title": "Edited title",
            "body_text": "Edited safe draft.",
            "status": "draft",
            "reviewed_by": "operator",
            "review_note": "tightened copy",
            "target_audience": "operators",
            "cta": "Follow the build",
            "agent_rationale": "Make the update concise.",
        },
    )
    assert edit_response.status_code == 200
    edited = edit_response.json()
    assert edited["status"] == "draft"
    assert edited["title"] == "Edited title"
    assert edited["policy_check"]["status"] == "passed"

    rewrite = synced_client.post(
        f"/api/social/posts/{first['id']}/request-rewrite",
        json={"actor": "operator", "feedback": "Make it calmer."},
    )
    assert rewrite.status_code == 200
    assert rewrite.json()["review_note"] == "Make it calmer."

    rejected = synced_client.patch(
        f"/api/social/posts/{second['id']}",
        json={"status": "rejected", "reviewed_by": "operator"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    filtered = synced_client.get("/api/social/posts?status=rejected")
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [second["id"]]

    rewrite_settled = synced_client.post(
        f"/api/social/posts/{second['id']}/request-rewrite", json={"actor": "operator"}
    )
    assert rewrite_settled.status_code == 400


def test_social_api_rejects_invalid_inputs(synced_client, db_session):
    invalid_platform = synced_client.post(
        "/api/social/posts", json={"platform": "linkedin", "body_text": "Safe draft."}
    )
    assert invalid_platform.status_code == 400

    invalid_status = synced_client.post(
        "/api/social/posts", json={"body_text": "Safe draft.", "status": "published"}
    )
    assert invalid_status.status_code == 400

    blocked_approved = synced_client.post(
        "/api/social/posts",
        json={"body_text": "Send funds for guaranteed profit.", "status": "approved"},
    )
    assert blocked_approved.status_code == 400

    account = SocialAccountRow(
        platform="mastodon",
        handle="synapse",
        display_name="Synapse",
        secret_ref="env:TOKEN",
        status="active",
    )
    db_session.add(account)
    db_session.commit()
    inactive = SocialAccountRow(
        platform="x",
        handle="Inactive",
        display_name="Inactive",
        secret_ref="env:TOKEN",
        status="disabled",
    )
    db_session.add(inactive)
    db_session.commit()

    wrong_platform = synced_client.post(
        "/api/social/posts",
        json={"account_id": int(account.id), "body_text": "Safe draft."},
    )
    assert wrong_platform.status_code == 400
    inactive_response = synced_client.post(
        "/api/social/posts",
        json={"account_id": int(inactive.id), "body_text": "Safe draft."},
    )
    assert inactive_response.status_code == 400
    missing_post = synced_client.patch(
        "/api/social/posts/9999", json={"status": "approved"}
    )
    assert missing_post.status_code == 404

    created = synced_client.post(
        "/api/social/posts", json={"body_text": "Safe draft."}
    ).json()
    invalid_patch = synced_client.patch(
        f"/api/social/posts/{created['id']}", json={"status": "publishing"}
    )
    assert invalid_patch.status_code == 400


def test_published_social_post_cannot_be_edited(monkeypatch, synced_client):
    monkeypatch.setattr(
        social_publishing.x_publisher,
        "publish_text",
        lambda account, body_text: social_publishing.XPublishResult(
            post_id="1802", response_summary={"data": {"id": "1802"}}
        ),
    )
    created = synced_client.post(
        "/api/social/posts", json={"body_text": "Safe draft."}
    ).json()
    synced_client.patch(
        f"/api/social/posts/{created['id']}", json={"status": "approved"}
    )
    published = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    ).json()

    response = synced_client.patch(
        f"/api/social/posts/{published['id']}",
        json={"body_text": "Edit after publish."},
    )

    assert response.status_code == 400
    assert "cannot be edited" in response.json()["detail"]


def test_secret_token_env_and_publisher_http_error_paths(monkeypatch):
    with pytest.raises(
        social_publishing.SocialPublishError, match="secret reference is empty"
    ):
        social_publishing._read_secret_token("")
    with pytest.raises(
        social_publishing.SocialPublishError, match="environment variable is missing"
    ):
        social_publishing._read_secret_token("env:MISSING_X_TOKEN")
    monkeypatch.setenv("X_TEST_TOKEN", "token-value")
    assert social_publishing._read_secret_token("env:X_TEST_TOKEN") == "token-value"

    account = SocialAccountRow(
        platform="x", handle="SynapseNetworkA", secret_ref="env:X_TEST_TOKEN"
    )
    publisher = social_publishing.XApiPublisher()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return b'{"data":{"id":"1803"}}'

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(),
    )
    result = publisher.publish_text(account, "Safe text.")
    assert result.post_id == "1803"

    def raise_http(status):
        raise urllib.error.HTTPError(
            "https://api.x.com/2/tweets",
            status,
            "error",
            {},
            io.BytesIO(b"failure body"),
        )

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: raise_http(401),
    )
    with pytest.raises(social_publishing.SocialPublishError) as auth_error:
        publisher.publish_text(account, "Safe text.")
    assert auth_error.value.kind == "x_publish_auth_failed"

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: raise_http(429),
    )
    with pytest.raises(social_publishing.SocialPublishError) as rate_error:
        publisher.publish_text(account, "Safe text.")
    assert rate_error.value.kind == "x_rate_limited"

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: raise_http(500),
    )
    with pytest.raises(social_publishing.SocialPublishError) as api_error:
        publisher.publish_text(account, "Safe text.")
    assert api_error.value.kind == "x_api_failed"

    class MissingIdResponse(FakeResponse):
        def read(self, _limit):
            return b'{"data":{}}'

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: MissingIdResponse(),
    )
    with pytest.raises(
        social_publishing.SocialPublishError, match="did not include a post id"
    ):
        publisher.publish_text(account, "Safe text.")


def test_secret_store_gcp_paths_and_version_rotation(monkeypatch):
    store = social_publishing.SecretValueStore()
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("STAGING_GCP_PROJECT_ID", raising=False)

    with pytest.raises(
        social_publishing.SocialPublishError, match="secret reference is empty"
    ):
        store._secret_name("")
    assert (
        store._secret_name("projects/demo/secrets/x/versions/latest")
        == "projects/demo/secrets/x/versions/latest"
    )
    with pytest.raises(
        social_publishing.SocialPublishError, match="project id is required"
    ):
        store._secret_name("x-secret")

    with pytest.raises(
        social_publishing.SocialPublishError, match="secret reference is empty"
    ):
        store._secret_parent("")
    assert (
        store._secret_parent("projects/demo/secrets/x/versions/latest")
        == "projects/demo/secrets/x"
    )
    with pytest.raises(
        social_publishing.SocialPublishError, match="project id is required"
    ):
        store._secret_parent("x-secret")

    monkeypatch.setenv("GCP_PROJECT_ID", "demo-project")
    assert (
        store._secret_name("x-secret")
        == "projects/demo-project/secrets/x-secret/versions/latest"
    )
    assert store._secret_parent("x-secret") == "projects/demo-project/secrets/x-secret"
    with pytest.raises(
        social_publishing.SocialPublishError, match="environment variable is missing"
    ):
        store.read("env:MISSING")
    with pytest.raises(
        social_publishing.SocialPublishError, match="environment variable"
    ):
        store.add_version("env:X_REFRESH", "new-refresh")

    class FakePayload:
        data = b"secret-value"

    class FakeAccessResponse:
        payload = FakePayload()

    calls: list[dict] = []

    class FakeSecretManagerClient:
        def access_secret_version(self, request):
            calls.append({"access": request})
            return FakeAccessResponse()

        def add_secret_version(self, request):
            calls.append({"add": request})

    from google.cloud import secretmanager

    monkeypatch.setattr(
        secretmanager, "SecretManagerServiceClient", lambda: FakeSecretManagerClient()
    )
    assert store.read("x-secret") == "secret-value"
    store.add_version("x-refresh", "new-refresh")
    assert (
        calls[0]["access"]["name"]
        == "projects/demo-project/secrets/x-secret/versions/latest"
    )
    assert calls[1]["add"]["parent"] == "projects/demo-project/secrets/x-refresh"
    assert calls[1]["add"]["payload"]["data"] == b"new-refresh"

    class EmptySecretManagerClient(FakeSecretManagerClient):
        def access_secret_version(self, request):
            return type(
                "Response", (), {"payload": type("Payload", (), {"data": b""})()}
            )()

    monkeypatch.setattr(
        secretmanager, "SecretManagerServiceClient", lambda: EmptySecretManagerClient()
    )
    with pytest.raises(social_publishing.SocialPublishError, match="secret is empty"):
        store.read("x-secret")


def test_secret_store_creates_missing_refresh_secret_before_adding_version(monkeypatch):
    store = social_publishing.SecretValueStore()
    monkeypatch.setenv("GCP_PROJECT_ID", "demo-project")

    from google.api_core import exceptions as google_exceptions
    from google.cloud import secretmanager

    calls: list[dict] = []

    class FakeSecretManagerClient:
        def __init__(self):
            self.created = False

        def add_secret_version(self, request):
            calls.append({"add": request})
            if not self.created:
                raise google_exceptions.NotFound("secret missing")

        def create_secret(self, request):
            calls.append({"create": request})
            self.created = True

    client = FakeSecretManagerClient()
    monkeypatch.setattr(secretmanager, "SecretManagerServiceClient", lambda: client)

    store.add_version("x-refresh", "new-refresh")

    assert calls[0]["add"]["parent"] == "projects/demo-project/secrets/x-refresh"
    assert calls[1]["create"]["parent"] == "projects/demo-project"
    assert calls[1]["create"]["secret_id"] == "x-refresh"
    assert calls[1]["create"]["secret"]["replication"] == {"automatic": {}}
    assert calls[2]["add"]["payload"]["data"] == b"new-refresh"


def test_secret_store_create_request_rejects_invalid_secret_refs(monkeypatch):
    store = social_publishing.SecretValueStore()
    monkeypatch.setattr(store, "_secret_parent", lambda _ref: "projects/demo")

    with pytest.raises(
        social_publishing.SocialPublishError, match="reference is invalid"
    ):
        store._secret_create_request("x-refresh")

    monkeypatch.setattr(store, "_secret_parent", lambda _ref: "projects/demo/secrets/")
    with pytest.raises(
        social_publishing.SocialPublishError, match="reference is invalid"
    ):
        store._secret_create_request("x-refresh")

    assert store._is_secret_not_found(RuntimeError("404 secret not found"))


def test_oauth_token_provider_status_and_error_paths(monkeypatch):
    class FakeStore:
        def __init__(self):
            self.values = {
                social_publishing.config.X_OAUTH_CLIENT_ID_SECRET: "client-id",
                social_publishing.config.X_OAUTH_CLIENT_SECRET_SECRET: "client-secret",
                social_publishing.config.X_OAUTH_REFRESH_TOKEN_SECRET: "refresh-token",
            }
            self.rotations: list[tuple[str, str]] = []

        def read(self, key):
            value = self.values.get(key)
            if value is None:
                raise social_publishing.SocialPublishError("x_auth_failed", "missing")
            return value

        def add_version(self, key, value):
            self.rotations.append((key, value))

    provider = social_publishing.XOAuth2TokenProvider(FakeStore())
    assert provider.auth_status()[0] == "authorized"

    provider_missing = social_publishing.XOAuth2TokenProvider(
        type(
            "MissingStore",
            (),
            {
                "read": lambda self, key: (_ for _ in ()).throw(
                    social_publishing.SocialPublishError(
                        "x_auth_failed", "missing refresh"
                    )
                ),
            },
        )()
    )
    assert provider_missing.auth_status() == ("needs_authorization", "missing refresh")

    provider_expired = social_publishing.XOAuth2TokenProvider(
        type(
            "ExpiredStore",
            (),
            {
                "read": lambda self, key: (_ for _ in ()).throw(
                    social_publishing.SocialPublishError(
                        "gcp_adc_expired", "Run `gcloud auth application-default login`"
                    )
                ),
            },
        )()
    )
    assert provider_expired.auth_status() == (
        "gcp_adc_expired",
        "Run `gcloud auth application-default login`",
    )

    class FakeResponse:
        def __init__(self, raw: bytes):
            self.raw = raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return self.raw

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(b'{"expires_in":7200}'),
    )
    with pytest.raises(
        social_publishing.SocialPublishError, match="did not include access_token"
    ):
        provider.get_access_token()
    with pytest.raises(
        social_publishing.SocialPublishError,
        match="callback response did not include access_token",
    ):
        provider.exchange_authorization_code(
            code="code",
            code_verifier="verifier",
            redirect_uri="http://127.0.0.1/callback",
        )

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(
            b'{"access_token":"access-only","expires_in":7200}'
        ),
    )
    with pytest.raises(
        social_publishing.SocialPublishError, match="did not include refresh_token"
    ):
        provider.exchange_authorization_code(
            code="code",
            code_verifier="verifier",
            redirect_uri="http://127.0.0.1/callback",
        )

    def raise_http(status):
        raise urllib.error.HTTPError(
            "https://api.x.com/2/oauth2/token",
            status,
            "error",
            {},
            io.BytesIO(b"oauth failure"),
        )

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: raise_http(400),
    )
    with pytest.raises(
        social_publishing.SocialPublishError, match="token exchange failed"
    ):
        provider.get_access_token()

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: raise_http(500),
    )
    with pytest.raises(
        social_publishing.SocialPublishError, match="token endpoint returned"
    ):
        provider.get_access_token()


def test_x_media_upload_http_error_paths(monkeypatch):
    monkeypatch.setenv("X_TEST_TOKEN", "token-value")
    account = SocialAccountRow(
        platform="x", handle="SynapseNetworkA", secret_ref="env:X_TEST_TOKEN"
    )
    publisher = social_publishing.XApiPublisher()
    image_path = social_publishing._media_runtime_dir() / "x-upload-test.png"
    image_path.write_bytes(b"fake-image")

    class FakeUploadResponse:
        def __init__(self, raw: bytes):
            self.raw = raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return self.raw

    captured_upload: dict[str, object] = {}

    def fake_media_upload(request, timeout):
        captured_upload["url"] = request.full_url
        captured_upload["headers"] = dict(request.header_items())
        captured_upload["payload"] = social_publishing._json_loads(
            request.data.decode("utf-8"), {}
        )
        return FakeUploadResponse(b'{"data":{"id":"m-1"}}')

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", fake_media_upload)
    assert publisher.upload_image(account, str(image_path)) == "m-1"
    assert captured_upload["url"] == "https://api.x.com/2/media/upload"
    assert captured_upload["payload"]["media_category"] == "tweet_image"
    assert captured_upload["payload"]["media_type"] == "image/png"
    assert captured_upload["payload"]["media"]

    with pytest.raises(social_publishing.SocialPublishError, match="file is missing"):
        publisher.upload_image(account, str(image_path.with_name("missing.png")))

    def raise_media_http(status):
        raise urllib.error.HTTPError(
            "https://api.x.com/2/media/upload",
            status,
            "error",
            {},
            io.BytesIO(b"media failure"),
        )

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: raise_media_http(403),
    )
    with pytest.raises(social_publishing.SocialPublishError) as auth_error:
        publisher.upload_image(account, str(image_path))
    assert auth_error.value.kind == "x_media_upload_auth_failed"
    assert "media.write" in auth_error.value.summary

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: raise_media_http(429),
    )
    with pytest.raises(social_publishing.SocialPublishError) as rate_error:
        publisher.upload_image(account, str(image_path))
    assert rate_error.value.kind == "x_rate_limited"

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: raise_media_http(500),
    )
    with pytest.raises(social_publishing.SocialPublishError) as media_error:
        publisher.upload_image(account, str(image_path))
    assert media_error.value.kind == "x_media_upload_failed"

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: FakeUploadResponse(b"{}"),
    )
    with pytest.raises(social_publishing.SocialPublishError, match="media_id"):
        publisher.upload_image(account, str(image_path))

    monkeypatch.setattr(
        social_publishing.urllib.request,
        "urlopen",
        lambda request, timeout: FakeUploadResponse(b'{"data":{"id":"1805"}}'),
    )
    result = publisher.publish_text(account, "Safe text.", media_ids=["m-1"])
    assert result.response_summary["media_ids"] == ["m-1"]


def test_x_content_workflow_atoms_create_draft_without_external_publish(
    monkeypatch, db_session
):
    monkeypatch.setattr(
        social_publishing.x_publisher,
        "publish_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("workflow draft atom must not publish")
        ),
    )
    requirement = RequirementRow(
        title="Draft X launch update",
        description_markdown="Synapse is validating human-gated social publishing.",
        status="ready",
        project_key="synapse-network-growing",
    )
    db_session.add(requirement)
    db_session.flush()
    run = WorkflowRunRow(
        requirement_id=int(requirement.id),
        workflow_key="x_official_account_content_ops",
        current_state="generate_draft",
        status="running",
    )
    db_session.add(run)
    db_session.commit()
    ctx = declarative.WorkflowContext(
        db=db_session,
        workflow_run=run,
        requirement=requirement,
        spec=declarative.build_x_official_account_content_ops_workflow_spec(),
        state_key="generate_draft",
        state_spec={},
        blackboard={},
    )

    draft_result = declarative._x_generate_content_draft(ctx)
    policy_result = declarative._x_content_policy_check(ctx)

    assert draft_result.writes["social_post"]["status"] == "needs_review"
    assert policy_result.writes["content_policy_check"]["status"] == "passed"
