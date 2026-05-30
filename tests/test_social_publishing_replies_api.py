import io
import json
import urllib.error

import pytest

from server.database import (
    SocialAccountRow,
    SocialReplyItemRow,
    SocialRepostCandidateRow,
)
from server.services.social import publishing as social_publishing
from server.services.social.reply_agent import GeneratedXReply


class FakeXAccessToken:
    access_token = "test-x-access-token"
    refreshed = True
    refresh_token_rotated = False


def _install_fake_reply_agent(monkeypatch, prefix: str = "Agent reply"):
    def fake_generate(candidate):
        return GeneratedXReply(
            suggested_reply=(
                f"{prefix} for @{candidate.author_handle}: "
                f"{candidate.source_text[:60]} Synapse angle: governed access, budgets, and settlement rails."
            ),
            risk_level="normal",
            rationale=f"Specific to @{candidate.author_handle} and the source post.",
            model="test-reply-model",
            generation_metadata={"provider": "test", "model": "test-reply-model"},
        )

    monkeypatch.setattr(social_publishing, "generate_x_reply_for_candidate", fake_generate)


def test_x_social_reply_candidate_sweep_creates_one_human_gated_reply(
    db_session, monkeypatch
):
    _install_fake_reply_agent(monkeypatch)
    db_session.add_all(
        [
            SocialRepostCandidateRow(
                platform="x",
                source_url="https://x.com/NVIDIAAI/status/249",
                author_handle="NVIDIAAI",
                source_text="Agentic tools need reliable infrastructure for coding, APIs, and automation.",
                suggested_quote="Agent-native infrastructure also needs payment and access rails.",
                relevance_score=1.0,
                status="candidate",
            ),
            SocialRepostCandidateRow(
                platform="x",
                source_url="https://x.com/OpenAI/status/250",
                author_handle="OpenAI",
                source_text="AI agents are getting better at reasoning and using tools.",
                suggested_quote="As agents get better at tools, the rails around access, spend, and settlement matter more.",
                relevance_score=0.95,
                status="candidate",
            ),
        ]
    )
    db_session.commit()

    result = social_publishing.run_x_social_reply_candidate_sweep(
        db_session, max_created=1
    )

    assert result["human_gate_required"] is True
    assert result["auto_publish"] is False
    assert result["external_actions"] == []
    assert len(result["created_reply_ids"]) == 1
    reply = db_session.get(SocialReplyItemRow, result["created_reply_ids"][0])
    assert reply is not None
    assert reply.status == "needs_review"
    assert reply.source_candidate_id is not None
    assert reply.source_post_id in {"249", "250"}
    assert reply.suggested_reply
    assert "Great point" not in reply.suggested_reply
    assert "Agent reply for @" in reply.suggested_reply
    metadata = social_publishing._json_loads(reply.metadata_json, {})
    assert metadata["human_gate_required"] is True
    assert metadata["auto_publish"] is False
    assert metadata["generated_by"] == "social_reply_agent_v1"
    assert metadata["provider"] == "test"


def test_x_social_reply_candidate_sweep_skips_local_seed_and_duplicates(
    db_session, monkeypatch
):
    _install_fake_reply_agent(monkeypatch)
    real_candidate = SocialRepostCandidateRow(
        platform="x",
        source_url="https://x.com/AnthropicAI/status/777",
        author_handle="AnthropicAI",
        source_text="Markets of AI agents could provide value, but there are rough edges around access and trust.",
        suggested_quote="Agent markets need trust, budgets, and settlement rails.",
        relevance_score=0.98,
        status="candidate",
    )
    local_candidate = SocialRepostCandidateRow(
        platform="x",
        source_url=None,
        author_handle="unknown",
        source_text="Local seed only.",
        suggested_quote="Local seed should not be replied to.",
        relevance_score=0.99,
        status="candidate",
    )
    db_session.add_all([real_candidate, local_candidate])
    db_session.commit()
    db_session.refresh(real_candidate)
    db_session.add(
        SocialReplyItemRow(
            external_reply_id="target:777",
            source_candidate_id=int(real_candidate.id),
            source_url=real_candidate.source_url,
            source_post_id="777",
            source_author_handle="AnthropicAI",
            source_text=real_candidate.source_text,
            author_handle="AnthropicAI",
            incoming_text=real_candidate.source_text,
            suggested_reply="Already drafted.",
            status="needs_review",
        )
    )
    db_session.commit()

    result = social_publishing.run_x_social_reply_candidate_sweep(
        db_session, max_created=1
    )

    assert result["created_reply_ids"] == []
    assert result["no_candidate"] is True
    assert db_session.query(SocialReplyItemRow).count() == 1


def test_generate_reply_endpoint_and_publish_reply_uses_x_reply_payload(
    monkeypatch, synced_client, db_session
):
    _install_fake_reply_agent(monkeypatch)
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )

    def fake_publish_reply(account, body_text, *, in_reply_to_tweet_id):
        captured["handle"] = account.handle
        captured["body_text"] = body_text
        captured["in_reply_to_tweet_id"] = in_reply_to_tweet_id
        return social_publishing.XPublishResult(
            post_id="1800000000000000777",
            response_summary={
                "data": {"id": "1800000000000000777"},
                "reply_to": in_reply_to_tweet_id,
            },
        )

    monkeypatch.setattr(
        social_publishing.x_publisher, "publish_reply", fake_publish_reply
    )
    candidate = SocialRepostCandidateRow(
        platform="x",
        source_url="https://x.com/OpenAI/status/777",
        author_handle="OpenAI",
        source_text="AI agents increasingly need reliable tool access and payment primitives.",
        suggested_quote="This is exactly why agent-native payment rails matter.",
        relevance_score=0.91,
        status="candidate",
    )
    published_candidate = SocialRepostCandidateRow(
        platform="x",
        source_url="https://x.com/OpenAI/status/802",
        author_handle="OpenAI",
        source_text="Published source.",
        suggested_quote="Already published.",
        relevance_score=0.8,
        status="candidate",
    )
    db_session.add_all([candidate, published_candidate])
    db_session.commit()
    db_session.refresh(candidate)
    db_session.refresh(published_candidate)

    generated = synced_client.post(
        f"/api/social/repost-candidates/{candidate.id}/generate-reply",
        json={"actor": "operator"},
    )

    assert generated.status_code == 200
    reply = generated.json()
    assert reply["status"] == "needs_review"
    assert reply["source_post_id"] == "777"
    assert reply["source_candidate_id"] == candidate.id
    assert reply["metadata"]["generated_by"] == "social_reply_agent_v1"

    approved = synced_client.patch(
        f"/api/social/replies/{reply['id']}",
        json={
            "suggested_reply": "Agentic products also need governed access, budgets, and settlement rails when tools become paid services.",
            "status": "approved",
            "reviewed_by": "operator",
        },
    )
    assert approved.status_code == 200
    published = synced_client.post(
        f"/api/social/replies/{reply['id']}/publish-x", json={"actor": "operator"}
    )

    assert published.status_code == 200
    payload = published.json()
    assert payload["status"] == "published"
    assert payload["published_external_post_id"] == "1800000000000000777"
    assert captured["handle"] == "SynapseNetworkA"
    assert captured["in_reply_to_tweet_id"] == "777"
    assert "governed access" in captured["body_text"]
    assert "http://" not in captured["body_text"]
    assert "https://" not in captured["body_text"]
    db_session.refresh(candidate)
    assert candidate.status == "replied"


def test_reply_generation_edge_cases_and_api_errors(
    synced_client, db_session, monkeypatch
):
    _install_fake_reply_agent(monkeypatch)
    local_candidate = SocialRepostCandidateRow(
        platform="x",
        source_url=None,
        author_handle="unknown",
        source_text="Local seed only.",
        suggested_quote="Local seed.",
        relevance_score=0.9,
        status="candidate",
    )
    bad_url_candidate = SocialRepostCandidateRow(
        platform="x",
        source_url="https://x.com/OpenAI",
        author_handle="OpenAI",
        source_text="Missing tweet id.",
        suggested_quote="Missing tweet id.",
        relevance_score=0.9,
        status="candidate",
    )
    published_candidate = SocialRepostCandidateRow(
        platform="x",
        source_url="https://x.com/OpenAI/status/999",
        author_handle="OpenAI",
        source_text="Already handled.",
        suggested_quote="Already handled.",
        relevance_score=0.9,
        status="published",
    )
    db_session.add_all([local_candidate, bad_url_candidate, published_candidate])
    db_session.commit()
    db_session.refresh(local_candidate)
    db_session.refresh(bad_url_candidate)
    db_session.refresh(published_candidate)

    assert (
        synced_client.post(
            "/api/social/repost-candidates/999999/generate-reply",
            json={"actor": "operator"},
        ).status_code
        == 404
    )
    assert (
        synced_client.post(
            f"/api/social/repost-candidates/{local_candidate.id}/generate-reply",
            json={"actor": "operator"},
        ).status_code
        == 400
    )
    assert (
        synced_client.post(
            f"/api/social/repost-candidates/{bad_url_candidate.id}/generate-reply",
            json={"actor": "operator"},
        ).status_code
        == 400
    )
    assert (
        synced_client.post(
            f"/api/social/repost-candidates/{published_candidate.id}/generate-reply",
            json={"actor": "operator"},
        ).status_code
        == 400
    )
    assert (
        synced_client.patch(
            "/api/social/replies/999999", json={"status": "approved"}
        ).status_code
        == 404
    )
    assert (
        synced_client.post(
            "/api/social/replies/999999/publish-x", json={"actor": "operator"}
        ).status_code
        == 404
    )

    candidate = SocialRepostCandidateRow(
        platform="x",
        source_url="https://x.com/OpenAI/status/555",
        author_handle="OpenAI",
        source_text="AI agents increasingly need reliable tool access and payment primitives.",
        suggested_quote="Agent-native infrastructure needs payment and access rails.",
        relevance_score=0.91,
        status="candidate",
    )
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)
    first = social_publishing._create_reply_from_repost_candidate(
        db_session, candidate, actor="test"
    )
    second = social_publishing._create_reply_from_repost_candidate(
        db_session, candidate, actor="test"
    )
    assert second.id == first.id

    reply = SocialReplyItemRow(
        external_reply_id="target:556",
        source_url="https://x.com/OpenAI/status/556",
        source_post_id="556",
        incoming_text="Agents need payments.",
        suggested_reply="Safe reply.",
        status="needs_review",
    )
    db_session.add(reply)
    db_session.commit()
    db_session.refresh(reply)
    assert (
        synced_client.patch(
            f"/api/social/replies/{reply.id}", json={"status": "unknown"}
        ).status_code
        == 400
    )
    blocked = synced_client.patch(
        f"/api/social/replies/{reply.id}",
        json={
            "suggested_reply": "Guaranteed risk-free profit if you send funds.",
            "status": "approved",
            "reviewed_by": "operator",
            "review_note": "unsafe",
        },
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "failed"
    assert blocked.json()["metadata"]["review_note"] == "unsafe"
    fixed = synced_client.patch(
        f"/api/social/replies/{reply.id}",
        json={
            "suggested_reply": "Agentic systems need governed payment rails for API access.",
            "status": "failed",
            "reviewed_by": "operator",
        },
    )
    assert fixed.status_code == 200
    assert fixed.json()["status"] == "needs_review"
    assert fixed.json()["failure_summary"] is None
    manually_published = synced_client.patch(
        f"/api/social/replies/{reply.id}",
        json={"status": "published_manual", "reviewed_by": "operator"},
    )
    assert manually_published.status_code == 200
    assert manually_published.json()["published_external_post_id"].startswith("manual:")
    assert (
        synced_client.patch(
            f"/api/social/replies/{reply.id}", json={"status": "published"}
        ).status_code
        == 400
    )

    published_reply = SocialReplyItemRow(
        external_reply_id="1801",
        source_url="https://x.com/OpenAI/status/557",
        source_post_id="557",
        incoming_text="Agents need payments.",
        suggested_reply="Already published.",
        status="published",
    )
    db_session.add(published_reply)
    db_session.commit()
    db_session.refresh(published_reply)
    assert (
        synced_client.patch(
            f"/api/social/replies/{published_reply.id}", json={"status": "approved"}
        ).status_code
        == 400
    )

    def create_raises(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(
        social_publishing, "_create_reply_from_repost_candidate", create_raises
    )
    result = social_publishing.run_x_social_reply_candidate_sweep(
        db_session, max_created=1
    )
    assert result["created_reply_ids"] == []
    assert result["skipped_candidate_ids"]


def test_agent_reply_generation_failure_creates_failed_row(
    db_session, monkeypatch
):
    def fail_generate(_candidate):
        raise ValueError("agent_reply_generation_failed: invalid JSON")

    monkeypatch.setattr(social_publishing, "generate_x_reply_for_candidate", fail_generate)
    candidate = SocialRepostCandidateRow(
        platform="x",
        source_url="https://x.com/OpenAI/status/654",
        author_handle="OpenAI",
        source_text="AI agents need reliable tool access.",
        suggested_quote="Agent-native infrastructure needs payment and access rails.",
        relevance_score=0.91,
        status="candidate",
    )
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)

    reply = social_publishing._create_reply_from_repost_candidate(
        db_session, candidate, actor="test"
    )

    assert reply.status == "failed"
    assert reply.suggested_reply == ""
    assert "invalid JSON" in reply.failure_summary
    metadata = social_publishing._json_loads(reply.metadata_json, {})
    assert metadata["generated_by"] == "social_reply_agent_v1"
    assert metadata["template_fallback"] is False
    assert metadata["generation_failed"] is True


def test_regenerate_unpublished_social_replies_only_updates_unsettled(
    db_session, monkeypatch
):
    _install_fake_reply_agent(monkeypatch, prefix="Regenerated")
    candidate = SocialRepostCandidateRow(
        platform="x",
        source_url="https://x.com/OpenAI/status/801",
        author_handle="OpenAI",
        source_text="AI agents increasingly need reliable tool access.",
        suggested_quote="Payment rails matter for agent tool access.",
        relevance_score=0.91,
        status="candidate",
    )
    published_candidate = SocialRepostCandidateRow(
        platform="x",
        source_url="https://x.com/OpenAI/status/802",
        author_handle="OpenAI",
        source_text="Published source.",
        suggested_quote="Already published.",
        relevance_score=0.8,
        status="candidate",
    )
    db_session.add_all([candidate, published_candidate])
    db_session.commit()
    db_session.refresh(candidate)
    db_session.refresh(published_candidate)
    draft = SocialReplyItemRow(
        external_reply_id="target:801",
        source_candidate_id=int(candidate.id),
        source_url=candidate.source_url,
        source_post_id="801",
        source_author_handle="OpenAI",
        source_text=candidate.source_text,
        incoming_text=candidate.source_text,
        suggested_reply="This is the old deterministic template.",
        status="needs_review",
    )
    published = SocialReplyItemRow(
        external_reply_id="target:802",
        source_candidate_id=int(published_candidate.id),
        source_url=published_candidate.source_url,
        source_post_id="802",
        source_author_handle="OpenAI",
        source_text=published_candidate.source_text,
        incoming_text="Published source.",
        suggested_reply="Published audit text.",
        status="published",
    )
    db_session.add_all([draft, published])
    db_session.commit()

    result = social_publishing.regenerate_unpublished_social_replies_with_agent(
        db_session, actor="operator"
    )

    db_session.refresh(draft)
    db_session.refresh(published)
    assert draft.id in result["regenerated_ids"]
    assert draft.suggested_reply.startswith("Regenerated for @OpenAI")
    assert draft.status == "needs_review"
    assert published.suggested_reply == "Published audit text."


def test_publish_social_reply_validation_edges(monkeypatch, synced_client, db_session):
    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )

    non_x = SocialReplyItemRow(
        platform="linkedin",
        external_reply_id="target:1",
        source_post_id="1",
        incoming_text="External post.",
        suggested_reply="Safe reply.",
        status="approved",
    )
    settled = SocialReplyItemRow(
        external_reply_id="target:2",
        source_post_id="2",
        incoming_text="External post.",
        suggested_reply="Safe reply.",
        status="published",
    )
    empty_text = SocialReplyItemRow(
        external_reply_id="target:3",
        source_post_id="3",
        incoming_text="External post.",
        suggested_reply="",
        status="approved",
    )
    missing_source = SocialReplyItemRow(
        external_reply_id="target:4",
        incoming_text="External post.",
        suggested_reply="Safe reply.",
        status="approved",
    )
    blocked = SocialReplyItemRow(
        external_reply_id="target:5",
        source_post_id="5",
        incoming_text="External post.",
        suggested_reply="Guaranteed risk-free profit if you send funds.",
        status="approved",
    )
    with_url = SocialReplyItemRow(
        external_reply_id="target:6",
        source_post_id="6",
        incoming_text="External post.",
        suggested_reply="Useful implementation notes: https://synapse-network.ai/docs",
        status="approved",
    )
    db_session.add_all([non_x, settled, empty_text, missing_source, blocked, with_url])
    db_session.commit()
    for row in [non_x, settled, empty_text, missing_source, blocked, with_url]:
        db_session.refresh(row)

    assert (
        synced_client.post(
            f"/api/social/replies/{non_x.id}/publish-x", json={"actor": "operator"}
        ).status_code
        == 400
    )
    assert (
        synced_client.post(
            f"/api/social/replies/{settled.id}/publish-x", json={"actor": "operator"}
        ).status_code
        == 400
    )
    assert (
        synced_client.post(
            f"/api/social/replies/{empty_text.id}/publish-x", json={"actor": "operator"}
        ).status_code
        == 400
    )
    assert (
        synced_client.post(
            f"/api/social/replies/{missing_source.id}/publish-x",
            json={"actor": "operator"},
        ).status_code
        == 400
    )
    blocked_response = synced_client.post(
        f"/api/social/replies/{blocked.id}/publish-x", json={"actor": "operator"}
    )
    assert blocked_response.status_code == 200
    assert blocked_response.json()["status"] == "failed"
    assert "Blocked:" in blocked_response.json()["failure_summary"]

    url_response = synced_client.post(
        f"/api/social/replies/{with_url.id}/publish-x", json={"actor": "operator"}
    )
    assert url_response.status_code == 200
    assert url_response.json()["status"] == "failed"
    assert url_response.json()["metadata"]["publish_failure_kind"] == "x_reply_url_blocked"


def test_x_api_publisher_reply_payload_and_http_errors(monkeypatch):
    account = SocialAccountRow(
        platform="x", handle="SynapseNetworkA", secret_ref="x-official", status="active"
    )
    requests: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload: str):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit=None):
            return self.payload.encode("utf-8")

    monkeypatch.setattr(
        social_publishing, "_read_secret_token", lambda _secret_ref: "short-lived-token"
    )

    def ok_urlopen(request, timeout):
        requests.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse('{"data":{"id":"reply-123"}}')

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", ok_urlopen)
    result = social_publishing.XApiPublisher().publish_reply(
        account, "Helpful reply", in_reply_to_tweet_id="123"
    )
    assert result.post_id == "reply-123"
    assert requests[0]["text"] == "Helpful reply"
    assert requests[0]["reply"] == {"in_reply_to_tweet_id": "123"}

    with pytest.raises(social_publishing.SocialPublishError) as url_blocked:
        social_publishing.XApiPublisher().publish_reply(
            account,
            "Helpful reply with https://synapse-network.ai/docs",
            in_reply_to_tweet_id="123",
        )
    assert url_blocked.value.kind == "x_reply_url_blocked"
    assert len(requests) == 1

    with pytest.raises(social_publishing.SocialPublishError, match="target tweet id"):
        social_publishing.XApiPublisher().publish_reply(
            account, "Helpful reply", in_reply_to_tweet_id=""
        )

    def missing_id_urlopen(_request, timeout):
        return FakeResponse('{"data":{}}')

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", missing_id_urlopen)
    with pytest.raises(social_publishing.SocialPublishError, match="did not include"):
        social_publishing.XApiPublisher().publish_reply(
            account, "Helpful reply", in_reply_to_tweet_id="123"
        )

    def http_error(code: int):
        def _raise(_request, timeout):
            raise urllib.error.HTTPError(
                "https://api.x.com/2/tweets", code, "error", {}, io.BytesIO(b"x error")
            )

        return _raise

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", http_error(403))
    with pytest.raises(
        social_publishing.SocialPublishError, match="authentication failed"
    ) as auth_error:
        social_publishing.XApiPublisher().publish_reply(
            account, "Helpful reply", in_reply_to_tweet_id="123"
        )
    assert auth_error.value.kind == "x_reply_auth_failed"
    assert (
        "tweet.write" in auth_error.value.summary
        and "x error" in auth_error.value.summary
    )

    def forbidden_reply(_request, timeout):
        raw = b'{"detail":"Reply to this conversation is not allowed because you have not been mentioned"}'
        raise urllib.error.HTTPError(
            "https://api.x.com/2/tweets", 403, "error", {}, io.BytesIO(raw)
        )

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", forbidden_reply)
    with pytest.raises(
        social_publishing.SocialPublishError, match="Reply manually"
    ) as forbidden_error:
        social_publishing.XApiPublisher().publish_reply(
            account, "Helpful reply", in_reply_to_tweet_id="123"
        )
    assert forbidden_error.value.kind == "x_reply_conversation_forbidden"

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", http_error(429))
    with pytest.raises(social_publishing.SocialPublishError, match="rate limit"):
        social_publishing.XApiPublisher().publish_reply(
            account, "Helpful reply", in_reply_to_tweet_id="123"
        )
    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", http_error(500))
    with pytest.raises(social_publishing.SocialPublishError, match="HTTP 500"):
        social_publishing.XApiPublisher().publish_reply(
            account, "Helpful reply", in_reply_to_tweet_id="123"
        )

    def generic_error(_request, timeout):
        raise RuntimeError("network down")

    monkeypatch.setattr(social_publishing.urllib.request, "urlopen", generic_error)
    with pytest.raises(social_publishing.SocialPublishError, match="network down"):
        social_publishing.XApiPublisher().publish_reply(
            account, "Helpful reply", in_reply_to_tweet_id="123"
        )


def test_publish_social_reply_auth_failure_is_diagnostic(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )

    def fail_publish_reply(*_args, **_kwargs):
        raise social_publishing.SocialPublishError(
            "x_reply_auth_failed",
            "X reply authentication failed. Reconnect the X official account.",
        )

    monkeypatch.setattr(
        social_publishing.x_publisher, "publish_reply", fail_publish_reply
    )
    reply = SocialReplyItemRow(
        external_reply_id="target:888",
        source_url="https://x.com/OpenAI/status/888",
        source_post_id="888",
        source_author_handle="OpenAI",
        source_text="Agents need reliable tool access.",
        author_handle="OpenAI",
        incoming_text="Agents need reliable tool access.",
        suggested_reply="Agentic systems need governed access and settlement rails as tool usage becomes paid.",
        status="approved",
    )
    db_session.add(reply)
    db_session.commit()
    db_session.refresh(reply)

    response = synced_client.post(
        f"/api/social/replies/{reply.id}/publish-x", json={"actor": "operator"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert (
        "authentication failed" in payload["failure_summary"]
        and "Reconnect" in payload["failure_summary"]
    )
    assert payload["metadata"]["publish_failure_kind"] == "x_reply_auth_failed"
