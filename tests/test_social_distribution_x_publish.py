import pytest

from server.database_social_distribution import (
    SocialDistributionDocumentRow,
    SocialDistributionEventRow,
    SocialDistributionTaskRow,
)
from server.services.social.agent_content_pack import generate_platform_task_draft
from server.services.social.publishing import XPublishResult
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
