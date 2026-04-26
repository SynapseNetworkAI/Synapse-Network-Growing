import io
import urllib.error

import pytest

from server.database import (
    RequirementRow,
    SocialAccountRow,
    SocialPostMetricRow,
    SocialReplyItemRow,
    SocialRepostCandidateRow,
    WorkflowRunRow,
)
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


def _fetch_social_post(client, post_id: int) -> dict:
    rows = client.get("/api/social/posts").json()
    return next(row for row in rows if row["id"] == post_id)


def test_social_draft_create_does_not_call_x_api(monkeypatch, synced_client):
    called = False

    def fail_publish(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("draft creation must not publish to X")

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fail_publish)

    accounts = synced_client.get("/api/social/accounts")
    assert accounts.status_code == 200
    account_id = accounts.json()[0]["id"]

    response = synced_client.post(
        "/api/social/posts",
        json={
            "account_id": account_id,
            "title": "Operator update",
            "body_text": "We are building the Synapse human-agent ops control plane in public.",
            "generated_by": "planner_agent_v1",
            "target_audience": "builders",
            "cta": "Follow for shipping notes",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_review"
    assert payload["source_type"] == "manual_prompt"
    assert payload["policy_check"]["status"] == "passed"
    assert payload["external_post_id"] is None
    assert called is False


def test_social_ops_center_projection_is_human_gated_and_read_only(synced_client, db_session):
    overview = synced_client.get("/api/social/ops/overview")
    assert overview.status_code == 200
    assert overview.json()["human_gate_required"] is True

    goals = synced_client.get("/api/social/campaign-goals")
    assert goals.status_code == 200
    assert goals.json()
    assert "Synapse Network" in goals.json()[0]["title"]

    trends = synced_client.get("/api/social/trends")
    assert trends.status_code == 200
    assert trends.json()[0]["topic"]

    watchlist = synced_client.get("/api/social/watchlist")
    assert watchlist.status_code == 200
    assert any(row["handle"] == "LangChainAI" for row in watchlist.json())

    db_session.add(
        SocialReplyItemRow(
            external_reply_id="reply-1",
            author_handle="builder",
            incoming_text="How do agents pay APIs?",
            intent="technical_question",
            suggested_reply="Synapse gives agents budgeted API access with human-governed official replies.",
        )
    )
    db_session.add(
        SocialRepostCandidateRow(
            author_handle="agent_builder",
            source_text="Agents need safer API budgets.",
            suggested_quote="This is exactly the M2M payment gap Synapse is built for.",
            relevance_score=0.91,
        )
    )
    db_session.add(
        SocialPostMetricRow(
            external_post_id="post-1",
            impressions=1200,
            likes=42,
            replies=5,
            link_clicks=9,
            summary="Good developer engagement.",
        )
    )
    db_session.commit()

    replies = synced_client.get("/api/social/replies")
    reposts = synced_client.get("/api/social/repost-candidates")
    metrics = synced_client.get("/api/social/post-metrics")

    assert replies.status_code == 200
    assert replies.json()[0]["status"] == "needs_review"
    assert reposts.status_code == 200
    assert reposts.json()[0]["suggested_quote"]
    assert metrics.status_code == 200
    assert metrics.json()[0]["impressions"] == 1200


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


def test_agent_prompt_generates_publish_ready_draft_without_publishing(monkeypatch, synced_client):
    called = False

    def fail_publish(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("Agent draft generation must not publish to X")

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fail_publish)
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
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
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Text update","body_text":"Synapse Network now has a cleaner social publishing review loop.","media_decision":"image","image_prompt":"A network visual","image_alt_text":"Network visual"}'
        ),
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"prompt": "Write an update.", "media_mode": "text_only", "actor": "operator"},
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "approved"
    assert payload["media_assets"] == []
    assert image_generator.calls == []
    assert payload["raw_agent_output"]["media_mode"] == "text_only"
    assert payload["raw_agent_output"]["media_decision"] == "text"


def test_auto_media_mode_creates_image_asset_when_agent_decides_image(monkeypatch, synced_client):
    image_generator = FakeImageGenerator()
    monkeypatch.setattr(social_publishing, "image_generator", image_generator)
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Visual launch note","body_text":"Synapse turns agent API usage into settled, budgeted micropayments.","media_decision":"image","image_prompt":"A polished dark SaaS visual of AI agents connected by a payment network","image_alt_text":"AI agents connected through a Synapse settlement layer"}'
        ),
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"prompt": "Write a launch update with a visual if useful.", "media_mode": "auto", "actor": "operator"},
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


def test_image_generation_failure_blocks_publish_until_removed_or_regenerated(monkeypatch, synced_client):
    monkeypatch.setattr(social_publishing, "image_generator", FakeImageGenerator(fail=True))
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Visual launch note","body_text":"Synapse turns agent API usage into settled, budgeted micropayments.","media_decision":"image","image_prompt":"A polished launch visual","image_alt_text":"Launch visual"}'
        ),
    )

    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"prompt": "Write a launch update with a visual.", "media_mode": "image_required", "actor": "operator"},
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "approved"
    assert payload["media_assets"][0]["status"] == "failed"
    assert "quota exhausted" in payload["media_assets"][0]["failure_summary"]

    publish = synced_client.post(f"/api/social/posts/{payload['id']}/publish-x", json={"actor": "operator"})
    assert publish.status_code == 400
    assert "image media failed" in publish.json()["detail"]


def test_media_preview_regenerate_and_remove_endpoints(monkeypatch, synced_client):
    image_generator = FakeImageGenerator()
    monkeypatch.setattr(social_publishing, "image_generator", image_generator)
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Visual launch note","body_text":"Synapse turns agent API usage into settled, budgeted micropayments.","media_decision":"image","image_prompt":"A polished launch visual","image_alt_text":"Launch visual"}'
        ),
    )

    created = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"prompt": "Write a launch update with a visual.", "media_mode": "image_required", "actor": "operator"},
    ).json()
    payload = _fetch_social_post(synced_client, created["id"])
    asset = payload["media_assets"][0]

    preview = synced_client.get(asset["preview_url"])
    assert preview.status_code == 200
    assert preview.content == b"fake-image"

    regenerated = synced_client.post(f"/api/social/posts/{created['id']}/regenerate-image", json={"actor": "operator"})
    assert regenerated.status_code == 200
    regenerated_payload = regenerated.json()
    assert len([item for item in regenerated_payload["media_assets"] if item["status"] != "removed"]) == 1

    active_asset = next(item for item in regenerated_payload["media_assets"] if item["status"] != "removed")
    removed = synced_client.delete(f"/api/social/posts/{created['id']}/media/{active_asset['id']}")
    assert removed.status_code == 200
    assert all(item["status"] == "removed" for item in removed.json()["media_assets"])


def test_manual_image_upload_replaces_active_media_and_supports_preview(monkeypatch, synced_client):
    image_generator = FakeImageGenerator()
    monkeypatch.setattr(social_publishing, "image_generator", image_generator)
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Visual launch note","body_text":"Synapse turns agent API usage into settled, budgeted micropayments.","media_decision":"image","image_prompt":"A polished launch visual","image_alt_text":"Launch visual"}'
        ),
    )
    created = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"prompt": "Write a launch update with a visual.", "media_mode": "image_required", "actor": "operator"},
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
    active_assets = [asset for asset in payload["media_assets"] if asset["status"] != "removed"]
    removed_assets = [asset for asset in payload["media_assets"] if asset["status"] == "removed"]
    assert len(active_assets) == 1
    assert removed_assets
    assert active_assets[0]["status"] == "ready"
    assert active_assets[0]["alt_text"] == "Operator supplied launch graphic"
    assert synced_client.get(active_assets[0]["preview_url"]).content == png
    assert any(event["event_type"] == "image_uploaded_manual" for event in payload["events"])


def test_manual_image_upload_rejects_non_image_and_settled_posts(synced_client):
    created = synced_client.post("/api/social/posts", json={"body_text": "Safe draft."}).json()

    bad_upload = synced_client.post(
        f"/api/social/posts/{created['id']}/media/upload",
        data={"actor": "operator"},
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )
    assert bad_upload.status_code == 400
    assert "image" in bad_upload.json()["detail"]

    synced_client.patch(f"/api/social/posts/{created['id']}", json={"status": "rejected", "reviewed_by": "operator"})
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
    assert social_publishing._image_extension(None, "", b"\x89PNG\r\n\x1a\nfake") == ".png"
    assert social_publishing._image_extension(None, "", b"GIF89afake") == ".gif"
    assert social_publishing._image_extension(None, "", b"RIFFxxxxWEBPfake") == ".webp"
    with pytest.raises(ValueError, match="empty"):
        social_publishing._validate_uploaded_image("launch.png", "image/png", b"")
    with pytest.raises(ValueError, match="8MB"):
        social_publishing._validate_uploaded_image("launch.png", "image/png", b"x" * (8 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="image"):
        social_publishing._image_extension("notes.txt", "", b"not an image")


def test_media_preview_and_regenerate_validation_errors(monkeypatch, synced_client):
    created = synced_client.post("/api/social/posts", json={"body_text": "Safe draft."}).json()
    assert synced_client.get("/api/social/media/999999/preview").status_code == 404
    assert synced_client.post(f"/api/social/posts/{created['id']}/regenerate-image", json={"actor": "operator"}).status_code == 400
    assert synced_client.delete(f"/api/social/posts/{created['id']}/media/999999").status_code == 404

    synced_client.patch(f"/api/social/posts/{created['id']}", json={"status": "approved", "reviewed_by": "operator"})
    monkeypatch.setattr(
        social_publishing.x_publisher,
        "publish_text",
        lambda account, body_text: social_publishing.XPublishResult(post_id="1804", response_summary={"data": {"id": "1804"}}),
    )
    published = synced_client.post(f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}).json()
    assert synced_client.post(f"/api/social/posts/{published['id']}/regenerate-image", json={"actor": "operator"}).status_code == 400
    assert synced_client.delete(f"/api/social/posts/{published['id']}/media/999999").status_code == 400


def test_media_preview_rejects_missing_or_outside_files(synced_client, db_session, tmp_path):
    created = synced_client.post("/api/social/posts", json={"body_text": "Safe draft."}).json()
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

    assert synced_client.get(f"/api/social/media/{outside_media.id}/preview").status_code == 400

    missing = social_publishing._media_runtime_dir() / "missing-preview.png"
    missing_media = social_publishing.SocialPostMediaAssetRow(
        post_id=int(created["id"]),
        media_type="image",
        status="ready",
        local_path=str(missing),
    )
    db_session.add(missing_media)
    db_session.commit()

    assert synced_client.get(f"/api/social/media/{missing_media.id}/preview").status_code == 400


def test_agent_prompt_uses_dedicated_social_content_provider(monkeypatch, synced_client):
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

    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex")
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_MODEL", "gpt-5-codex")
    monkeypatch.setattr(social_publishing, "run_codex_exec", fake_codex_exec)

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"account_id": account_id, "prompt": "Write a concise public update.", "style_type": "technical", "actor": "operator"},
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
    assert "Do not optimize for the old 280-character tweet format" in str(observed["prompt"])
    assert "single X post text under 280 characters" not in str(observed["prompt"])
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["raw_agent_output"]["requested_model"] == "gpt-5-codex"
    assert payload["raw_agent_output"]["model"] == "gpt-5-codex"
    assert payload["raw_agent_output"]["style_type"] == "technical"
    assert payload["raw_agent_output"]["generation_metadata"]["output_artifact"]


def test_codex_nonzero_with_valid_json_and_noise_is_accepted(monkeypatch, synced_client):
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

    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex")
    monkeypatch.setattr(social_publishing, "run_codex_exec", fake_codex_exec)

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"account_id": account_id, "prompt": "Write a concise staging launch update.", "actor": "operator"},
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["title"] == "Cleanup-noise output"
    assert payload["raw_agent_output"]["generation_metadata"]["exit_code"] == 1
    assert payload["raw_agent_output"]["generation_metadata"]["nonzero_exit_with_valid_json"] is True


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

    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex")
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_TIMEOUT", 180)
    monkeypatch.setattr(social_publishing, "run_codex_exec", fake_codex_exec)

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"account_id": account_id, "prompt": "Write a launch update for Synapse Network.", "actor": "operator"},
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "approved"
    assert payload["raw_agent_output"]["generation_metadata"]["exit_code"] == 124
    assert payload["raw_agent_output"]["generation_metadata"]["timeout_after_valid_json"] is True


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

    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex")
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_MODEL", "gpt-5-codex")
    monkeypatch.setattr(social_publishing, "run_codex_exec", fake_codex_exec)

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"account_id": account_id, "prompt": "Write a concise staging launch update.", "actor": "operator"},
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "failed"
    assert "provider=codex" in payload["failure_summary"]
    assert "exit_code=1" in payload["failure_summary"]
    assert "output_artifact=" in payload["failure_summary"]


def test_codex_model_compatibility_falls_back_to_supported_model(monkeypatch, synced_client):
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

    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex")
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_MODEL", "gpt-5-codex")
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_FALLBACK_MODEL", "gpt-5.5,gpt-5.4")
    monkeypatch.setattr(social_publishing, "run_codex_exec", fake_codex_exec)

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"account_id": account_id, "prompt": "Write a concise staging launch update.", "actor": "operator"},
    )

    assert response.status_code == 200
    assert observed_models == ["gpt-5-codex", "gpt-5.5", "gpt-5.4"]
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["raw_agent_output"]["requested_model"] == "gpt-5-codex"
    assert payload["raw_agent_output"]["model"] == "gpt-5.4"
    assert payload["raw_agent_output"]["generation_metadata"]["attempted_models"] == ["gpt-5-codex", "gpt-5.5", "gpt-5.4"]
    assert payload["raw_agent_output"]["generation_metadata"]["fallback_used"] is True


def test_agent_prompt_adds_launch_skill_context(monkeypatch, synced_client):
    observed_prompts: dict[str, str] = {}

    class ObservedProvider:
        def call(self, system, user, model, temperature, timeout):
            observed_prompts["system"] = system
            observed_prompts["user"] = user
            return '{"title":"Staging is live","body_text":"Synapse staging is live for operators to review the agent-payment workflow before broader rollout."}', 0

    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(social_publishing, "get_provider", lambda provider_name=None: ObservedProvider())

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"account_id": account_id, "prompt": "Announce the staging launch update.", "actor": "operator"},
    )

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert "launch-strategy" in payload["raw_agent_output"]["context_sources"]
    assert "Launch Strategy" in observed_prompts["user"]
    assert "Announce the staging launch update." in observed_prompts["user"]
    assert "strong hook" in observed_prompts["system"]
    assert "clear product value" in observed_prompts["system"]


def test_agent_prompt_sanitizes_internal_paths_before_provider_call(monkeypatch, synced_client):
    observed_prompts: dict[str, str] = {}

    class ObservedProvider:
        def call(self, system, user, model, temperature, timeout):
            observed_prompts["user"] = user
            return '{"title":"First public update","body_text":"Synapse staging is live, and the team is preparing the first official X update for builders."}', 0

    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(social_publishing, "get_provider", lambda provider_name=None: ObservedProvider())

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
    parsed = social_publishing._parse_generated_x_post('{"title":"T","body_text":"B","media_decision":"weird"}')
    assert parsed.media_decision == "text"
    fenced = social_publishing._parse_generated_x_post('```json\n{"title":"Fenced","body_text":"Body"}\n```')
    assert fenced.title == "Fenced"
    extracted = social_publishing._parse_generated_x_post('prefix {"title":"Nested","body_text":"brace in string } ok"} suffix')
    assert extracted.body_text == "brace in string } ok"
    with pytest.raises(ValueError, match="invalid JSON"):
        social_publishing._parse_generated_x_post('prefix {"title": "Broken", "body_text": } suffix')
    assert social_publishing._codex_nonzero_can_use_json(
        social_publishing.CodexExecResult(
            text='{"title":"T","body_text":"B"}',
            stdout="",
            stderr="cleanup error",
            exit_code=1,
            execution_time_ms=1,
            command=["codex"],
            output_path=None,
        )
    ) is True
    assert social_publishing._codex_nonzero_can_use_json(
        social_publishing.CodexExecResult(
            text="not json",
            stdout="",
            stderr="cleanup error",
            exit_code=1,
            execution_time_ms=1,
            command=["codex"],
            output_path=None,
        )
    ) is False
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
            social_publishing.GeneratedXPost(title="Unsafe", body_text="api_key=sk-test-secret123456"),
        )
    with pytest.raises(ValueError, match="image_prompt_empty"):
        social_publishing._validate_image_prompt("")
    with pytest.raises(ValueError, match="internal_or_secret"):
        social_publishing._validate_image_prompt("workflow JSON with required_commands")
    with pytest.raises(ValueError, match="local_path"):
        social_publishing._validate_image_prompt("/home/cliff/workspace/secret.png")
    with pytest.raises(ValueError, match="high_risk"):
        social_publishing._validate_image_prompt("Guaranteed profit visual")

    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider('{"title":"No prompt","body_text":"Safe public copy.","media_decision":"image"}'),
    )
    with pytest.raises(ValueError, match="image_prompt"):
        social_publishing._generate_x_post_copy("Write with image", media_mode="image_required")


def test_openai_image_generator_success_and_failure_paths(monkeypatch):
    generator = social_publishing.SocialImageGenerator()
    monkeypatch.setattr(social_publishing.config, "SOCIAL_IMAGE_PROVIDER", "disabled")
    with pytest.raises(ValueError, match="unsupported provider"):
        generator.generate_image(prompt="A safe image", asset_id=501)

    monkeypatch.setattr(social_publishing.config, "SOCIAL_IMAGE_PROVIDER", "openai_images")
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
        lambda request, timeout: FakeImageResponse(b'{"data":[{"b64_json":"ZmFrZS1pbWFnZQ=="}]}'),
    )
    result = generator.generate_image(prompt="A safe image", asset_id=503)
    assert result.preview_url.endswith("/api/social/media/503/preview")
    assert "social-post-media-503.png" in result.local_path

    def raise_openai_http(request, timeout):
        raise urllib.error.HTTPError("https://api.openai.com/v1/images/generations", 400, "bad", {}, io.BytesIO(b"bad request"))

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


def test_agent_prompt_with_blocked_content_requires_revision_without_publishing(monkeypatch, synced_client):
    called = False

    def fail_publish(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("blocked Agent draft generation must not publish to X")

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fail_publish)
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider('{"title":"Unsafe launch claim","body_text":"Guaranteed risk-free returns. Send funds now."}'),
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


def test_agent_prompt_copy_retries_once_before_creating_draft(monkeypatch, synced_client):
    prompt = "Tell people we created an X account and ask them to follow us."
    provider = SequencedSocialCopyProvider(
        [
            f'{{"title":"Copied prompt","body_text":"{prompt}"}}',
            '{"title":"Synapse Network is live on X","body_text":"AI agents need a way to pay for APIs safely. Synapse Network gives them zero-gas micropayments, budget isolation, and an MCP-native path to discover and use services."}',
        ]
    )
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(social_publishing, "get_provider", lambda provider_name=None: provider)

    response = synced_client.post("/api/social/posts/generate-draft", json={"prompt": prompt, "actor": "operator"})

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "approved"
    assert payload["body_text"] != prompt
    assert payload["raw_agent_output"]["generation_metadata"]["rewrite_attempted"] is True
    assert len(provider.calls) == 2
    assert provider.calls[0]["temperature"] == 0.7
    assert provider.calls[1]["temperature"] == 0.3


def test_agent_invalid_json_retries_once_before_creating_draft(monkeypatch, synced_client):
    prompt = "Introduce Synapse Network to AI agent builders."
    provider = SequencedSocialCopyProvider(
        [
            "Title: Synapse Network\nBody: AI agents need safe payment rails.",
            '{"title":"Synapse Network for AI agents","body_text":"AI agents can reason and use tools, but they still need safe payment rails. Synapse Network gives builders zero-gas micropayments, budget isolation, and a settlement layer for API access."}',
        ]
    )
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(social_publishing, "get_provider", lambda provider_name=None: provider)

    response = synced_client.post("/api/social/posts/generate-draft", json={"prompt": prompt, "actor": "operator"})

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "approved"
    assert payload["title"] == "Synapse Network for AI agents"
    assert payload["raw_agent_output"]["generation_metadata"]["rewrite_attempted"] is True
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
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(social_publishing, "get_provider", lambda provider_name=None: provider)

    response = synced_client.post("/api/social/posts/generate-draft", json={"prompt": prompt, "actor": "operator"})

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "failed"
    assert "agent_generation_low_transform" in payload["failure_summary"]


def test_agent_prompt_internal_path_or_workflow_output_is_rejected(monkeypatch, synced_client):
    prompt = "Read /Users/cliff/workspace/agent/Synapse-Network/docs and write the first X post."
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Internal leak","body_text":"Read /Users/cliff/workspace/agent/Synapse-Network/docs and generate the first post."}'
        ),
    )

    response = synced_client.post("/api/social/posts/generate-draft", json={"prompt": prompt, "actor": "operator"})

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
    response = synced_client.post("/api/social/posts/generate-draft", json={"prompt": "Write a launch note.", "actor": "operator"})
    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "failed"
    assert payload["failure_summary"].startswith("agent_generation_")


def test_agent_generation_invalid_json_fails_without_creating_draft(monkeypatch, synced_client):
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(social_publishing, "get_provider", lambda provider_name=None: FakeSocialCopyProvider("not json"))

    response = synced_client.post("/api/social/posts/generate-draft", json={"prompt": "Write a launch note.", "actor": "operator"})

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "failed"
    assert "agent_generation_failed" in payload["failure_summary"]


def test_agent_generation_provider_failure_fails_without_creating_draft(monkeypatch, synced_client):
    class FailingProvider:
        def call(self, system, user, model, temperature, timeout):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "test-provider")
    monkeypatch.setattr(social_publishing, "get_provider", lambda provider_name=None: FailingProvider())

    response = synced_client.post("/api/social/posts/generate-draft", json={"prompt": "Write a launch note.", "actor": "operator"})

    assert response.status_code == 200
    payload = _fetch_social_post(synced_client, response.json()["id"])
    assert payload["status"] == "failed"
    assert "provider unavailable" in payload["failure_summary"]


def test_unapproved_draft_cannot_publish(synced_client):
    created = synced_client.post(
        "/api/social/posts",
        json={"body_text": "A safe draft that still needs human review."},
    ).json()

    response = synced_client.post(f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"})

    assert response.status_code == 400
    assert "only approved" in response.json()["detail"]


def test_approved_draft_publishes_to_x_with_mocked_publisher(monkeypatch, synced_client):
    captured: dict[str, str] = {}

    def fake_publish(account, body_text):
        captured["handle"] = account.handle
        captured["body_text"] = body_text
        return social_publishing.XPublishResult(post_id="1800000000000000001", response_summary={"data": {"id": "1800000000000000001"}})

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fake_publish)
    created = synced_client.post(
        "/api/social/posts",
        json={"body_text": "Synapse Agent Ops now has a human-gated X publishing surface."},
    ).json()
    approved = synced_client.patch(
        f"/api/social/posts/{created['id']}",
        json={"status": "approved", "reviewed_by": "operator"},
    )
    assert approved.status_code == 200

    response = synced_client.post(f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "published"
    assert payload["external_post_id"] == "1800000000000000001"
    assert payload["external_url"].endswith("/status/1800000000000000001")
    assert captured == {
        "handle": "SynapseNetworkA",
        "body_text": "Synapse Agent Ops now has a human-gated X publishing surface.",
    }


def test_approved_draft_with_image_uploads_media_before_x_publish(monkeypatch, synced_client, db_session):
    captured: dict[str, object] = {}

    def fake_upload(account, image_path):
        captured["upload_handle"] = account.handle
        captured["image_path"] = image_path
        return "media-123"

    def fake_publish(account, body_text, media_ids=None):
        captured["publish_handle"] = account.handle
        captured["body_text"] = body_text
        captured["media_ids"] = media_ids
        return social_publishing.XPublishResult(post_id="1800000000000000042", response_summary={"data": {"id": "1800000000000000042"}})

    monkeypatch.setattr(social_publishing.x_publisher, "upload_image", fake_upload)
    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fake_publish)
    created = synced_client.post(
        "/api/social/posts",
        json={"body_text": "Synapse Network now ships reviewable X posts with generated images."},
    ).json()
    synced_client.patch(f"/api/social/posts/{created['id']}", json={"status": "approved", "reviewed_by": "operator"})
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

    response = synced_client.post(f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "published"
    assert captured["media_ids"] == ["media-123"]
    assert captured["body_text"] == "Synapse Network now ships reviewable X posts with generated images."
    assert payload["media_assets"][0]["x_media_id"] == "media-123"
    assert payload["media_assets"][0]["status"] == "uploaded"


def test_publish_rejects_pending_image_and_reuses_uploaded_media_id(monkeypatch, synced_client, db_session):
    created = synced_client.post(
        "/api/social/posts",
        json={"body_text": "Synapse Network now supports human-reviewed X image posts."},
    ).json()
    synced_client.patch(f"/api/social/posts/{created['id']}", json={"status": "approved", "reviewed_by": "operator"})
    pending_media = social_publishing.SocialPostMediaAssetRow(
        post_id=int(created["id"]),
        media_type="image",
        status="generating",
        prompt="A pending image",
    )
    db_session.add(pending_media)
    db_session.commit()

    pending = synced_client.post(f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"})
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
        return social_publishing.XPublishResult(post_id="1800000000000000099", response_summary={"data": {"id": "1800000000000000099"}})

    monkeypatch.setattr(social_publishing.x_publisher, "upload_image", fail_upload)
    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fake_publish)

    published = synced_client.post(f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"})
    assert published.status_code == 200
    assert captured["media_ids"] == ["media-existing"]


def test_x_media_upload_failure_does_not_fallback_to_text_only(monkeypatch, synced_client, db_session):
    def fail_upload(account, image_path):
        raise social_publishing.SocialPublishError("x_media_upload_failed", "X media upload failed.")

    def fail_if_text_publish(*args, **kwargs):
        raise AssertionError("must not publish text-only when image upload fails")

    monkeypatch.setattr(social_publishing.x_publisher, "upload_image", fail_upload)
    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fail_if_text_publish)
    created = synced_client.post("/api/social/posts", json={"body_text": "Safe image-backed post."}).json()
    synced_client.patch(f"/api/social/posts/{created['id']}", json={"status": "approved", "reviewed_by": "operator"})
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

    response = synced_client.post(f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["failure_summary"] == "X media upload failed."


def test_x_auth_failure_is_bounded_and_does_not_leak_secret(monkeypatch, synced_client):
    def fake_publish(account, body_text):
        raise social_publishing.SocialPublishError("x_auth_failed", "X API authentication failed. Update the OAuth user token secret.")

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fake_publish)
    created = synced_client.post("/api/social/posts", json={"body_text": "Safe post."}).json()
    synced_client.patch(f"/api/social/posts/{created['id']}", json={"status": "approved", "reviewed_by": "operator"})

    response = synced_client.post(f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["failure_summary"] == "X API authentication failed. Update the OAuth user token secret."
    assert "token-value" not in str(payload).lower()
    assert "authorization" not in str(payload).lower()


def test_x_rate_limit_failure_records_failed_status(monkeypatch, synced_client):
    def fake_publish(account, body_text):
        raise social_publishing.SocialPublishError("x_rate_limited", "X API rate limit reached. Try again after the rate-limit window.")

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fake_publish)
    created = synced_client.post("/api/social/posts", json={"body_text": "Safe post for rate limit test."}).json()
    synced_client.patch(f"/api/social/posts/{created['id']}", json={"status": "approved", "reviewed_by": "operator"})

    response = synced_client.post(f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"})

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

    risky = social_publishing.run_content_policy_check("Launching soon with guaranteed risk-free return.")
    assert risky["status"] == "blocked"
    assert "guaranteed_return" in risky["blocked_reasons"]
    assert "time_sensitive_claim_review" in risky["warnings"]


def test_social_post_update_reject_rewrite_and_filter(synced_client):
    first = synced_client.post("/api/social/posts", json={"body_text": "First safe draft."}).json()
    second = synced_client.post("/api/social/posts", json={"body_text": "Second safe draft."}).json()

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

    rejected = synced_client.patch(f"/api/social/posts/{second['id']}", json={"status": "rejected", "reviewed_by": "operator"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    filtered = synced_client.get("/api/social/posts?status=rejected")
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [second["id"]]

    rewrite_settled = synced_client.post(f"/api/social/posts/{second['id']}/request-rewrite", json={"actor": "operator"})
    assert rewrite_settled.status_code == 400


def test_social_api_rejects_invalid_inputs(synced_client, db_session):
    invalid_platform = synced_client.post("/api/social/posts", json={"platform": "linkedin", "body_text": "Safe draft."})
    assert invalid_platform.status_code == 400

    invalid_status = synced_client.post("/api/social/posts", json={"body_text": "Safe draft.", "status": "published"})
    assert invalid_status.status_code == 400

    blocked_approved = synced_client.post(
        "/api/social/posts",
        json={"body_text": "Send funds for guaranteed profit.", "status": "approved"},
    )
    assert blocked_approved.status_code == 400

    account = SocialAccountRow(platform="mastodon", handle="synapse", display_name="Synapse", secret_ref="env:TOKEN", status="active")
    db_session.add(account)
    db_session.commit()
    inactive = SocialAccountRow(platform="x", handle="Inactive", display_name="Inactive", secret_ref="env:TOKEN", status="disabled")
    db_session.add(inactive)
    db_session.commit()

    wrong_platform = synced_client.post("/api/social/posts", json={"account_id": int(account.id), "body_text": "Safe draft."})
    assert wrong_platform.status_code == 400
    inactive_response = synced_client.post("/api/social/posts", json={"account_id": int(inactive.id), "body_text": "Safe draft."})
    assert inactive_response.status_code == 400
    missing_post = synced_client.patch("/api/social/posts/9999", json={"status": "approved"})
    assert missing_post.status_code == 404

    created = synced_client.post("/api/social/posts", json={"body_text": "Safe draft."}).json()
    invalid_patch = synced_client.patch(f"/api/social/posts/{created['id']}", json={"status": "publishing"})
    assert invalid_patch.status_code == 400


def test_published_social_post_cannot_be_edited(monkeypatch, synced_client):
    monkeypatch.setattr(
        social_publishing.x_publisher,
        "publish_text",
        lambda account, body_text: social_publishing.XPublishResult(post_id="1802", response_summary={"data": {"id": "1802"}}),
    )
    created = synced_client.post("/api/social/posts", json={"body_text": "Safe draft."}).json()
    synced_client.patch(f"/api/social/posts/{created['id']}", json={"status": "approved"})
    published = synced_client.post(f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}).json()

    response = synced_client.patch(f"/api/social/posts/{published['id']}", json={"body_text": "Edit after publish."})

    assert response.status_code == 400
    assert "cannot be edited" in response.json()["detail"]


def test_secret_token_env_and_publisher_http_error_paths(monkeypatch):
    with pytest.raises(social_publishing.SocialPublishError, match="secret reference is empty"):
        social_publishing._read_secret_token("")
    with pytest.raises(social_publishing.SocialPublishError, match="environment variable is missing"):
        social_publishing._read_secret_token("env:MISSING_X_TOKEN")
    monkeypatch.setenv("X_TEST_TOKEN", "token-value")
    assert social_publishing._read_secret_token("env:X_TEST_TOKEN") == "token-value"

    account = SocialAccountRow(platform="x", handle="SynapseNetworkA", secret_ref="env:X_TEST_TOKEN")
    publisher = social_publishing.XApiPublisher()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return b'{"data":{"id":"1803"}}'

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", lambda request, timeout: FakeResponse())
    result = publisher.publish_text(account, "Safe text.")
    assert result.post_id == "1803"

    def raise_http(status):
        raise urllib.error.HTTPError("https://api.x.com/2/tweets", status, "error", {}, io.BytesIO(b"failure body"))

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", lambda request, timeout: raise_http(401))
    with pytest.raises(social_publishing.SocialPublishError) as auth_error:
        publisher.publish_text(account, "Safe text.")
    assert auth_error.value.kind == "x_auth_failed"

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", lambda request, timeout: raise_http(429))
    with pytest.raises(social_publishing.SocialPublishError) as rate_error:
        publisher.publish_text(account, "Safe text.")
    assert rate_error.value.kind == "x_rate_limited"

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", lambda request, timeout: raise_http(500))
    with pytest.raises(social_publishing.SocialPublishError) as api_error:
        publisher.publish_text(account, "Safe text.")
    assert api_error.value.kind == "x_api_failed"

    class MissingIdResponse(FakeResponse):
        def read(self, _limit):
            return b'{"data":{}}'

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", lambda request, timeout: MissingIdResponse())
    with pytest.raises(social_publishing.SocialPublishError, match="did not include a post id"):
        publisher.publish_text(account, "Safe text.")


def test_x_media_upload_http_error_paths(monkeypatch):
    monkeypatch.setenv("X_TEST_TOKEN", "token-value")
    account = SocialAccountRow(platform="x", handle="SynapseNetworkA", secret_ref="env:X_TEST_TOKEN")
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

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", lambda request, timeout: FakeUploadResponse(b'{"media_id_string":"m-1"}'))
    assert publisher.upload_image(account, str(image_path)) == "m-1"

    with pytest.raises(social_publishing.SocialPublishError, match="file is missing"):
        publisher.upload_image(account, str(image_path.with_name("missing.png")))

    def raise_media_http(status):
        raise urllib.error.HTTPError("https://upload.twitter.com/1.1/media/upload.json", status, "error", {}, io.BytesIO(b"media failure"))

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", lambda request, timeout: raise_media_http(403))
    with pytest.raises(social_publishing.SocialPublishError) as auth_error:
        publisher.upload_image(account, str(image_path))
    assert auth_error.value.kind == "x_auth_failed"

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", lambda request, timeout: raise_media_http(429))
    with pytest.raises(social_publishing.SocialPublishError) as rate_error:
        publisher.upload_image(account, str(image_path))
    assert rate_error.value.kind == "x_rate_limited"

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", lambda request, timeout: raise_media_http(500))
    with pytest.raises(social_publishing.SocialPublishError) as media_error:
        publisher.upload_image(account, str(image_path))
    assert media_error.value.kind == "x_media_upload_failed"

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", lambda request, timeout: FakeUploadResponse(b'{}'))
    with pytest.raises(social_publishing.SocialPublishError, match="media_id"):
        publisher.upload_image(account, str(image_path))

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", lambda request, timeout: FakeUploadResponse(b'{"data":{"id":"1805"}}'))
    result = publisher.publish_text(account, "Safe text.", media_ids=["m-1"])
    assert result.response_summary["media_ids"] == ["m-1"]


def test_x_content_workflow_atoms_create_draft_without_external_publish(monkeypatch, db_session):
    monkeypatch.setattr(
        social_publishing.x_publisher,
        "publish_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("workflow draft atom must not publish")),
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
