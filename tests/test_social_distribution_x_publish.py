import json

import pytest

from server.database_social_distribution import (
    SocialDistributionDocumentRow,
    SocialDistributionEventRow,
    SocialDistributionTaskRow,
)
from server.services.social.agent_content_pack import generate_platform_task_draft
from server.services.social.publishing import SocialPublishError, XPublishResult
from server.services.social.distribution_tasks import _validate_x_publish_payload
from tests.social_distribution_helpers import patch_agent_distribution


def test_x_dynamic_variant_accepts_minimal_thread_contract(monkeypatch):
    def fake_call(*_args, **_kwargs):
        return (
            '{"x_format":"thread","tweets":["Solo companies need systems, not more tabs.","A control plane turns one source task into reviewed platform docs."],"risk_level":"normal","rationale":"deep content"}',
            {"provider": "test"},
            "test-model",
        )

    monkeypatch.setattr(
        "server.services.social.agent_content_pack._call_content_agent",
        fake_call,
    )

    draft = generate_platform_task_draft(
        asset_title="Solo company operating system",
        asset_summary="Build the system before the product.",
        asset_body="Long canonical article body.",
        asset_metadata={},
        canonical_url=None,
        platform="x",
        channel_key="official",
        display_name="X Official Account",
    )

    assert draft.metadata["x_format"] == "thread"
    assert draft.metadata["format_kind"] == "x_thread"
    assert draft.metadata["weighted_counts"] == [43, 66]
    assert "1/2" in draft.body
    assert "Human Gate required" in draft.checklist


def test_x_dynamic_variant_accepts_long_post_contract(monkeypatch):
    long_post = (
        "Why build a one-person company system before another feature?\n\n"
        "Because the product usually does not break first. The handoffs do."
    )

    def fake_call(*_args, **_kwargs):
        return (
            json.dumps(
                {
                    "platform_title": "Why I am building a one-person company system",
                    "platform_body": None,
                    "x_format": "long_post",
                    "post_text": long_post,
                    "tweets": [],
                    "format_kind": "x_long_post",
                    "target_length": "X Premium long post, density-driven, max 4000 chars",
                    "operator_checklist": "Human Gate required.",
                    "risk_level": "normal",
                    "rationale": "Premium technical long post",
                }
            ),
            {"provider": "test"},
            "test-model",
        )

    monkeypatch.setattr(
        "server.services.social.agent_content_pack._call_content_agent",
        fake_call,
    )

    draft = generate_platform_task_draft(
        asset_title="Why I am building a one-person company system",
        asset_summary="A technical build-in-public founder story.",
        asset_body="Long canonical article body.",
        asset_metadata={},
        canonical_url=None,
        platform="x",
        channel_key="official",
        display_name="X Official Account",
    )

    assert draft.metadata["x_format"] == "long_post"
    assert draft.metadata["format_kind"] == "x_long_post"
    assert draft.metadata["long_post_text"] == long_post
    assert draft.metadata["premium_required"] is True
    assert draft.body == long_post


def test_x_long_post_over_limit_retries_with_agent_repair(monkeypatch):
    repaired = (
        "Why build a one-person company system before another feature?\n\n"
        "Because the hard part is keeping requirements, verification, release, "
        "and distribution in one trustworthy loop."
    )
    calls: list[str] = []

    def fake_call(system_prompt, user_prompt, **_kwargs):
        calls.append(user_prompt)
        if len(calls) == 1:
            return (
                json.dumps(
                    {
                        "platform_title": "Too long",
                        "platform_body": "x" * 4100,
                        "x_format": "long_post",
                        "post_text": "x" * 4100,
                        "tweets": [],
                        "format_kind": "x_long_post",
                        "target_length": "X Premium long post",
                        "operator_checklist": "Human Gate required.",
                        "risk_level": "normal",
                        "rationale": "Needs compression",
                    }
                ),
                {"provider": "test", "attempt": "initial"},
                "test-model",
            )
        return (
            json.dumps(
                {
                    "platform_title": "Repaired",
                    "platform_body": repaired,
                    "x_format": "long_post",
                    "post_text": repaired,
                    "tweets": [],
                    "format_kind": "x_long_post",
                    "target_length": "X Premium long post",
                    "operator_checklist": "Human Gate required.",
                    "risk_level": "normal",
                    "rationale": "Compressed under the limit",
                }
            ),
            {"provider": "test", "attempt": "repair"},
            "test-model",
        )

    monkeypatch.setattr(
        "server.services.social.agent_content_pack._call_content_agent",
        fake_call,
    )

    draft = generate_platform_task_draft(
        asset_title="Why I am building a one-person company system",
        asset_summary="A technical build-in-public founder story.",
        asset_body="Long canonical article body.",
        asset_metadata={},
        canonical_url=None,
        platform="x",
        channel_key="official",
        display_name="X Official Account",
    )

    assert len(calls) == 2
    assert "Required repair" in calls[1]
    assert draft.body == repaired
    assert draft.metadata["x_long_post_repair_attempted"] is True
    assert draft.metadata["x_format"] == "long_post"


def test_x_dynamic_variant_fails_closed_when_tweet_exceeds_limit(monkeypatch):
    long_tweet = "超" * 141

    def fake_call(*_args, **_kwargs):
        return (
            f'{{"x_format":"single","tweets":["{long_tweet}"],"risk_level":"normal","rationale":"too long"}}',
            {"provider": "test"},
            "test-model",
        )

    monkeypatch.setattr(
        "server.services.social.agent_content_pack._call_content_agent",
        fake_call,
    )

    with pytest.raises(ValueError, match="x_draft_invalid"):
        generate_platform_task_draft(
            asset_title="Too long X post",
            asset_summary=None,
            asset_body="Body",
            asset_metadata={},
            canonical_url=None,
            platform="x",
            channel_key="official",
            display_name="X Official Account",
        )


def test_x_distribution_task_can_publish_after_human_gate(
    synced_client, db_session, monkeypatch
):
    patch_agent_distribution(monkeypatch)

    class FakeXPublisher:
        def __init__(self):
            self.calls = []

        def publish_text(self, account, body_text, media_ids=None):
            self.calls.append(("root", body_text, None))
            assert body_text
            return XPublishResult(
                post_id="1234567890",
                response_summary={"data": {"id": "1234567890"}},
            )

        def publish_reply(self, account, body_text, *, in_reply_to_tweet_id):
            self.calls.append(("reply", body_text, in_reply_to_tweet_id))
            post_id = str(1234567890 + len(self.calls) - 1)
            return XPublishResult(
                post_id=post_id,
                response_summary={"data": {"id": post_id}},
            )

    fake_publisher = FakeXPublisher()
    monkeypatch.setattr(
        "server.services.social.distribution_tasks.x_publisher",
        fake_publisher,
    )
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    x_account = next(row for row in accounts if row["platform"] == "x")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "X publish asset", "summary": "Official X update."},
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])
    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [x_account["id"]]},
    ).json()

    response = synced_client.post(
        f"/api/social/distribution/tasks/{generated['generated_task_ids'][0]}/publish-x",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "live"
    assert payload["external_post_id"] == "1234567890"
    assert [call[0] for call in fake_publisher.calls] == ["root", "reply", "reply"]
    assert payload["metadata"]["published_tweet_ids"] == [
        "1234567890",
        "1234567891",
        "1234567892",
    ]
    assert (
        db_session.query(SocialDistributionEventRow)
        .filter(SocialDistributionEventRow.event_type == "task_published_x_thread")
        .count()
        == 1
    )


def test_x_distribution_auth_status_validates_refresh_before_publish(
    synced_client, db_session, monkeypatch
):
    patch_agent_distribution(monkeypatch)

    class TokenResult:
        access_token = "access-token"
        refresh_token_rotated = True

    monkeypatch.setattr(
        "server.services.social.distribution_tasks.x_oauth_token_provider.get_access_token",
        lambda _secret_ref: TokenResult(),
    )
    task_id = _generated_x_task_id(synced_client, db_session)

    response = synced_client.get(
        f"/api/social/distribution/tasks/{task_id}/x-auth-status"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "authorized"
    assert payload["can_publish"] is True
    assert payload["requires_authorization"] is False
    assert payload["refresh_token_rotated"] is True


def test_x_distribution_auth_status_expired_requests_oauth(
    synced_client, db_session, monkeypatch
):
    patch_agent_distribution(monkeypatch)

    def raise_expired(_secret_ref):
        raise SocialPublishError("x_refresh_failed", "refresh token expired")

    monkeypatch.setattr(
        "server.services.social.distribution_tasks.x_oauth_token_provider.get_access_token",
        raise_expired,
    )
    task_id = _generated_x_task_id(synced_client, db_session)

    response = synced_client.get(
        f"/api/social/distribution/tasks/{task_id}/x-auth-status"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_authorization"
    assert payload["can_publish"] is False
    assert payload["requires_authorization"] is True
    assert payload["auth_message"] == "refresh token expired"


def test_x_distribution_auth_status_gcp_adc_failure_is_diagnostic(
    synced_client, db_session, monkeypatch
):
    patch_agent_distribution(monkeypatch)

    def raise_gcp(_secret_ref):
        raise SocialPublishError("gcp_adc_expired", "Run gcloud auth")

    monkeypatch.setattr(
        "server.services.social.distribution_tasks.x_oauth_token_provider.get_access_token",
        raise_gcp,
    )
    task_id = _generated_x_task_id(synced_client, db_session)

    response = synced_client.get(
        f"/api/social/distribution/tasks/{task_id}/x-auth-status"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "gcp_adc_expired"
    assert payload["can_publish"] is False
    assert payload["requires_authorization"] is False


def test_x_distribution_auth_status_rejects_invalid_task_shapes(
    synced_client, db_session, monkeypatch
):
    patch_agent_distribution(monkeypatch)

    missing = synced_client.get("/api/social/distribution/tasks/999/x-auth-status")
    assert missing.status_code == 404
    assert "not found" in missing.json()["detail"].lower()

    accounts = synced_client.get("/api/social/distribution/accounts").json()
    devto = next(row for row in accounts if row["platform"] == "devto")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "Manual platform", "summary": "DEV is not X."},
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])
    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [devto["id"]]},
    ).json()

    non_x = synced_client.get(
        f"/api/social/distribution/tasks/{generated['generated_task_ids'][0]}/x-auth-status"
    )
    assert non_x.status_code == 400
    assert "only X distribution tasks" in non_x.json()["detail"]

    x_task = db_session.get(
        SocialDistributionTaskRow,
        _generated_x_task_id(synced_client, db_session),
    )
    assert x_task is not None and x_task.account is not None
    x_task.account.publish_mode = "manual_only"
    db_session.commit()

    manual_x = synced_client.get(
        f"/api/social/distribution/tasks/{x_task.id}/x-auth-status"
    )
    assert manual_x.status_code == 400
    assert "not configured for API publishing" in manual_x.json()["detail"]


def test_x_distribution_long_post_publish_uses_single_x_call(
    synced_client, db_session, monkeypatch
):
    monkeypatch.setattr(
        "server.services.social.distribution_tasks.run_content_policy_check",
        lambda _text: {"status": "passed", "blocked_reasons": []},
    )

    class FakeXPublisher:
        def __init__(self):
            self.calls = []

        def publish_text(self, account, body_text, media_ids=None):
            self.calls.append(body_text)
            return XPublishResult(
                post_id="long-123",
                response_summary={"data": {"id": "long-123"}},
            )

        def publish_reply(self, account, body_text, *, in_reply_to_tweet_id):
            raise AssertionError("long post must not publish thread replies")

    fake_publisher = FakeXPublisher()
    monkeypatch.setattr(
        "server.services.social.distribution_tasks.x_publisher",
        fake_publisher,
    )
    task_id = _insert_long_post_task(synced_client, db_session)

    response = synced_client.post(
        f"/api/social/distribution/tasks/{task_id}/publish-x",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "live"
    assert payload["external_post_id"] == "long-123"
    assert payload["metadata"]["x_format"] == "long_post"
    assert fake_publisher.calls == [payload["metadata"]["long_post_text"]]
    assert (
        db_session.query(SocialDistributionEventRow)
        .filter(SocialDistributionEventRow.event_type == "task_published_x_long_post")
        .count()
        == 1
    )
    assert (
        db_session.query(SocialDistributionEventRow)
        .filter(SocialDistributionEventRow.event_type == "task_publish_submitted")
        .count()
        == 1
    )


def test_x_distribution_long_post_api_failure_records_bounded_failure(
    synced_client, db_session, monkeypatch
):
    monkeypatch.setattr(
        "server.services.social.distribution_tasks.run_content_policy_check",
        lambda _text: {"status": "passed", "blocked_reasons": []},
    )

    class FailingLongPostPublisher:
        def publish_text(self, account, body_text, media_ids=None):
            from server.services.social.publishing import SocialPublishError

            raise SocialPublishError(
                "x_long_post_api_rejected",
                "X API rejected long-form text for this account.",
            )

    monkeypatch.setattr(
        "server.services.social.distribution_tasks.x_publisher",
        FailingLongPostPublisher(),
    )
    task_id = _insert_long_post_task(synced_client, db_session)

    response = synced_client.post(
        f"/api/social/distribution/tasks/{task_id}/publish-x",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["failure_summary"] == "X API rejected long-form text for this account."


def test_x_distribution_long_post_publish_payload_validation():
    with pytest.raises(ValueError, match="empty"):
        _validate_x_publish_payload("long_post", [], "")
    with pytest.raises(ValueError, match="exceeds 4000"):
        _validate_x_publish_payload("long_post", [], "x" * 4001)


def test_x_distribution_thread_partial_failure_records_progress(
    synced_client, db_session, monkeypatch
):
    patch_agent_distribution(monkeypatch)
    monkeypatch.setattr(
        "server.services.social.distribution_tasks.run_content_policy_check",
        lambda _text: {"status": "passed", "blocked_reasons": []},
    )

    class PartiallyFailingPublisher:
        def publish_text(self, account, body_text, media_ids=None):
            return XPublishResult(
                post_id="root-1",
                response_summary={"data": {"id": "root-1"}},
            )

        def publish_reply(self, account, body_text, *, in_reply_to_tweet_id):
            from server.services.social.publishing import SocialPublishError

            raise SocialPublishError("x_thread_reply_failed", "reply failed")

    monkeypatch.setattr(
        "server.services.social.distribution_tasks.x_publisher",
        PartiallyFailingPublisher(),
    )
    task_id = _generated_x_task_id(synced_client, db_session)

    response = synced_client.post(
        f"/api/social/distribution/tasks/{task_id}/publish-x",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["failure_summary"] == "reply failed"
    assert payload["metadata"]["published_tweet_ids"] == ["root-1"]
    assert payload["metadata"]["partial_publish_failure_index"] == 2


def test_non_x_distribution_task_cannot_publish_via_api(
    synced_client, db_session, monkeypatch
):
    patch_agent_distribution(monkeypatch)
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    devto = next(row for row in accounts if row["platform"] == "devto")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "Manual-only platform", "summary": "DEV stays manual in v1."},
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])
    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [devto["id"]]},
    ).json()

    response = synced_client.post(
        f"/api/social/distribution/tasks/{generated['generated_task_ids'][0]}/publish-x",
        json={"actor": "operator"},
    )

    assert response.status_code == 400
    assert "only X distribution tasks" in response.json()["detail"]


def test_x_distribution_publish_policy_blocked_records_failure(
    synced_client, db_session, monkeypatch
):
    patch_agent_distribution(monkeypatch)
    monkeypatch.setattr(
        "server.services.social.distribution_tasks.run_content_policy_check",
        lambda _text: {"status": "blocked", "blocked_reasons": ["test_policy"]},
    )
    task_id = _generated_x_task_id(synced_client, db_session)
    task = db_session.get(SocialDistributionTaskRow, task_id)
    assert task is not None
    task.platform_body = "Internal workflow JSON: required_commands"
    db_session.commit()

    response = synced_client.post(
        f"/api/social/distribution/tasks/{task_id}/publish-x",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert "policy_blocked" in payload["failure_summary"]
    assert (
        db_session.query(SocialDistributionEventRow)
        .filter(SocialDistributionEventRow.event_type == "task_publish_blocked")
        .count()
        == 1
    )


def test_x_distribution_publish_error_records_bounded_failure(
    synced_client, db_session, monkeypatch
):
    patch_agent_distribution(monkeypatch)
    monkeypatch.setattr(
        "server.services.social.distribution_tasks.run_content_policy_check",
        lambda _text: {"status": "passed", "blocked_reasons": []},
    )

    class FailingXPublisher:
        def publish_text(self, account, body_text, media_ids=None):
            from server.services.social.publishing import SocialPublishError

            raise SocialPublishError("x_publish_auth_failed", "auth failed")

    monkeypatch.setattr(
        "server.services.social.distribution_tasks.x_publisher", FailingXPublisher()
    )

    response = synced_client.post(
        f"/api/social/distribution/tasks/{_generated_x_task_id(synced_client, db_session)}/publish-x",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["failure_summary"] == "auth failed"


def test_x_distribution_refresh_failure_marks_account_needs_authorization(
    synced_client, db_session, monkeypatch
):
    patch_agent_distribution(monkeypatch)
    monkeypatch.setattr(
        "server.services.social.distribution_tasks.run_content_policy_check",
        lambda _text: {"status": "passed", "blocked_reasons": []},
    )

    class RefreshFailingXPublisher:
        def publish_text(self, account, body_text, media_ids=None):
            from server.services.social.publishing import SocialPublishError

            raise SocialPublishError(
                "x_refresh_failed",
                'X OAuth token exchange failed with HTTP 400: {"error":"invalid_request"}',
            )

    monkeypatch.setattr(
        "server.services.social.distribution_tasks.x_publisher",
        RefreshFailingXPublisher(),
    )

    response = synced_client.post(
        f"/api/social/distribution/tasks/{_generated_x_task_id(synced_client, db_session)}/publish-x",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"

    account = synced_client.get("/api/social/accounts").json()[0]
    assert account["status"] == "needs_authorization"
    assert account["auth_status"] == "needs_authorization"
    assert "Start OAuth authorization again" in account["auth_message"]


def _generated_x_task_id(synced_client, db_session) -> int:
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    x_account = next(row for row in accounts if row["platform"] == "x")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "X task", "summary": "Publish should be human gated."},
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])
    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [x_account["id"]]},
    ).json()
    return int(generated["generated_task_ids"][0])


def _insert_long_post_task(synced_client, db_session) -> int:
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    x_account = next(row for row in accounts if row["platform"] == "x")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "X long post asset", "summary": "Premium long-form post."},
    ).json()
    body = (
        "Why I am building a one-person company system, not just a product.\n\n"
        "A one-person company usually breaks before the code does: context "
        "switching, release drift, and distribution gaps pile up faster than "
        "features ship. The system is the product surface that keeps those "
        "handoffs visible."
    )
    task = SocialDistributionTaskRow(
        asset_id=asset["id"],
        account_id=x_account["id"],
        platform="x",
        channel_key="official",
        action="post",
        status="needs_review",
        platform_title="Why I am building a one-person company system",
        platform_body=body,
        operator_checklist="Human Gate required. X Premium long post.",
        metadata_json=json.dumps(
            {
                "format_kind": "x_long_post",
                "target_length": "X Premium long post, density-driven, max 4000 chars",
                "character_count": len(body),
                "soft_max_chars": 4000,
                "x_format": "long_post",
                "long_post_text": body,
                "premium_required": True,
                "counting_mode": "plain_character_count",
            }
        ),
    )
    db_session.add(task)
    db_session.commit()
    return int(task.id)


def _add_approved_canonical_article(db_session, asset_id: int):
    db_session.add(
        SocialDistributionDocumentRow(
            asset_id=asset_id,
            document_kind="canonical_article",
            title="Approved canonical article",
            body_markdown="# Approved canonical article\n\nA complete mother draft.",
            status="approved",
            version=1,
            metadata_json='{"generated_by":"asset_expansion_agent_v1","summary":"Approved canonical summary","key_facts":["fact"]}',
        )
    )
    db_session.commit()
