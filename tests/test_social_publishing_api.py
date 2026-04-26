import io
import urllib.error

import pytest

from server.database import RequirementRow, SocialAccountRow, WorkflowRunRow
from server.services.social import publishing as social_publishing
from server.services.workflows import declarative


class FakeSocialCopyProvider:
    def __init__(self, response_text: str):
        self.response_text = response_text

    def call(self, system, user, model, temperature, timeout):
        return self.response_text, 0


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
    assert payload["policy_check"]["status"] == "passed"
    assert payload["external_post_id"] is None
    assert called is False


def test_agent_prompt_generates_publish_ready_draft_without_publishing(monkeypatch, synced_client):
    called = False

    def fail_publish(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("Agent draft generation must not publish to X")

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fail_publish)
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
    assert payload["status"] == "approved"
    assert payload["reviewed_by"] == "operator"
    assert payload["generated_by"] == "social_content_agent_v1"
    assert payload["title"] == "Staging governance update"
    assert payload["body_text"]
    assert payload["body_text"] != prompt
    assert payload["policy_check"]["status"] == "passed"
    assert payload["raw_agent_output"]["media_support"] == "text_only_v1"
    assert payload["external_post_id"] is None
    assert called is False


def test_agent_prompt_uses_dedicated_social_content_provider(monkeypatch, synced_client):
    provider_names: list[str | None] = []
    observed_models: list[str] = []
    observed_prompts: dict[str, str] = {}

    class ObservedProvider:
        def call(self, system, user, model, temperature, timeout):
            observed_prompts["system"] = system
            observed_prompts["user"] = user
            observed_models.append(model)
            return '{"title":"Dedicated provider","body_text":"A concise public X update generated through the social copy provider."}', 0

    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex")
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_MODEL", "gpt-5-codex")
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: provider_names.append(provider_name) or ObservedProvider(),
    )

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"account_id": account_id, "prompt": "Write a concise public update.", "actor": "operator"},
    )

    assert response.status_code == 200
    assert provider_names == ["codex"]
    assert observed_models == ["gpt-5-codex"]
    assert "Product Marketing Context" in observed_prompts["user"]
    assert "Social Content" in observed_prompts["user"]
    assert "Launch Strategy" not in observed_prompts["user"]
    assert "Write a concise public update." in observed_prompts["user"]
    payload = response.json()
    assert payload["raw_agent_output"]["requested_model"] == "gpt-5-codex"
    assert payload["raw_agent_output"]["model"] == "gpt-5-codex"


def test_codex_model_compatibility_falls_back_to_supported_model(monkeypatch, synced_client):
    observed_models: list[str] = []

    class ObservedProvider:
        def call(self, system, user, model, temperature, timeout):
            observed_models.append(model)
            if model == "gpt-5-codex":
                raise RuntimeError("The 'gpt-5-codex' model is not supported when using Codex with a ChatGPT account.")
            return '{"title":"Fallback model","body_text":"Synapse Network now has a concise, human-reviewed X update ready for launch followers."}', 0

    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_PROVIDER", "codex")
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_MODEL", "gpt-5-codex")
    monkeypatch.setattr(social_publishing.config, "SOCIAL_CONTENT_LLM_FALLBACK_MODEL", "gpt-5.4")
    monkeypatch.setattr(social_publishing, "get_provider", lambda provider_name=None: ObservedProvider())

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"account_id": account_id, "prompt": "Write a concise staging launch update.", "actor": "operator"},
    )

    assert response.status_code == 200
    assert observed_models == ["gpt-5-codex", "gpt-5.4"]
    payload = response.json()
    assert payload["raw_agent_output"]["requested_model"] == "gpt-5-codex"
    assert payload["raw_agent_output"]["model"] == "gpt-5.4"


def test_agent_prompt_adds_launch_skill_context(monkeypatch, synced_client):
    observed_prompts: dict[str, str] = {}

    class ObservedProvider:
        def call(self, system, user, model, temperature, timeout):
            observed_prompts["system"] = system
            observed_prompts["user"] = user
            return '{"title":"Staging is live","body_text":"Synapse staging is live for operators to review the agent-payment workflow before broader rollout."}', 0

    monkeypatch.setattr(social_publishing, "get_provider", lambda provider_name=None: ObservedProvider())

    account_id = synced_client.get("/api/social/accounts").json()[0]["id"]
    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={"account_id": account_id, "prompt": "Announce the staging launch update.", "actor": "operator"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "launch-strategy" in payload["raw_agent_output"]["context_sources"]
    assert "Launch Strategy" in observed_prompts["user"]
    assert "Announce the staging launch update." in observed_prompts["user"]


def test_agent_prompt_sanitizes_internal_paths_before_provider_call(monkeypatch, synced_client):
    observed_prompts: dict[str, str] = {}

    class ObservedProvider:
        def call(self, system, user, model, temperature, timeout):
            observed_prompts["user"] = user
            return '{"title":"First public update","body_text":"Synapse staging is live, and the team is preparing the first official X update for builders."}', 0

    monkeypatch.setattr(social_publishing, "get_provider", lambda provider_name=None: ObservedProvider())

    response = synced_client.post(
        "/api/social/posts/generate-draft",
        json={
            "prompt": "读取/Users/cliff/workspace/agent/Synapse-Network/docs 给出文档，生成第一篇官方推文。",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    assert "/Users/" not in observed_prompts["user"]
    assert "[internal docs path omitted]" in observed_prompts["user"]


def test_agent_prompt_with_blocked_content_requires_revision_without_publishing(monkeypatch, synced_client):
    called = False

    def fail_publish(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("blocked Agent draft generation must not publish to X")

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fail_publish)
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
    payload = response.json()
    assert payload["status"] == "needs_review"
    assert payload["reviewed_by"] is None
    assert payload["policy_check"]["status"] == "blocked"
    assert payload["external_post_id"] is None
    assert called is False


def test_agent_prompt_copy_is_rejected_without_creating_draft(monkeypatch, synced_client):
    prompt = "Tell people we created an X account and ask them to follow us."
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(f'{{"title":"Copied prompt","body_text":"{prompt}"}}'),
    )

    before = synced_client.get("/api/social/posts").json()
    response = synced_client.post("/api/social/posts/generate-draft", json={"prompt": prompt, "actor": "operator"})
    after = synced_client.get("/api/social/posts").json()

    assert response.status_code == 400
    assert "agent_generation_low_transform" in response.json()["detail"]
    assert len(after) == len(before)


def test_agent_prompt_internal_path_or_workflow_output_is_rejected(monkeypatch, synced_client):
    prompt = "Read /Users/cliff/workspace/agent/Synapse-Network/docs and write the first X post."
    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Internal leak","body_text":"Read /Users/cliff/workspace/agent/Synapse-Network/docs and generate the first post."}'
        ),
    )

    before = synced_client.get("/api/social/posts").json()
    response = synced_client.post("/api/social/posts/generate-draft", json={"prompt": prompt, "actor": "operator"})
    after = synced_client.get("/api/social/posts").json()

    assert response.status_code == 400
    assert response.json()["detail"].startswith("agent_generation_")
    assert len(after) == len(before)

    monkeypatch.setattr(
        social_publishing,
        "get_provider",
        lambda provider_name=None: FakeSocialCopyProvider(
            '{"title":"Workflow JSON","body_text":"acceptance matrix required_commands show the workflow JSON for this launch."}'
        ),
    )
    response = synced_client.post("/api/social/posts/generate-draft", json={"prompt": "Write a launch note.", "actor": "operator"})
    assert response.status_code == 400
    assert response.json()["detail"].startswith("agent_generation_")


def test_agent_generation_invalid_json_fails_without_creating_draft(monkeypatch, synced_client):
    monkeypatch.setattr(social_publishing, "get_provider", lambda provider_name=None: FakeSocialCopyProvider("not json"))

    before = synced_client.get("/api/social/posts").json()
    response = synced_client.post("/api/social/posts/generate-draft", json={"prompt": "Write a launch note.", "actor": "operator"})
    after = synced_client.get("/api/social/posts").json()

    assert response.status_code == 400
    assert "agent_generation_failed" in response.json()["detail"]
    assert len(after) == len(before)


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


def test_policy_check_blocks_empty_long_and_risky_content():
    empty = social_publishing.run_content_policy_check("")
    assert empty["status"] == "blocked"
    assert "body_text_empty" in empty["blocked_reasons"]

    long = social_publishing.run_content_policy_check("x" * 281)
    assert long["status"] == "blocked"
    assert "x_post_exceeds_280_characters" in long["blocked_reasons"]

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
