from datetime import timedelta

from server.database import SocialReplyItemRow, utcnow
from server.database_social_analytics import (
    SocialAccountSnapshotRow,
    SocialWeeklyReviewRow,
)
from server.services.social.post_metric_observer_targets import (
    metric_row_from_x_post,
    published_targets_for_metrics,
)


def test_manual_metric_records_feedback_conversions_and_weekly_review(
    synced_client, db_session
):
    response = synced_client.post(
        "/api/social/post-metrics/manual",
        json={
            "external_post_id": "manual-feedback-1",
            "impressions": 100,
            "bookmarks": 8,
            "replies": 2,
            "profile_visits": 5,
            "negative_feedback_count": 1,
            "subscription_conversions": 1,
            "post_intent": "technical_explainer",
            "topic_tags": ["agent_payments", "budget_caps"],
            "hook_text": "Give an AI agent a budget, not your card.",
            "has_url": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["negative_feedback_count"] == 1
    assert payload["subscription_conversions"] == 1
    assert payload["topic_tags"] == ["agent_payments", "budget_caps"]
    assert payload["has_url"] is False

    review_response = synced_client.post(
        "/api/social/analytics/weekly-reviews/run",
        json={"days": 7, "dry_run": False},
    )

    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert review_payload["review_id"]
    assert review_payload["content_generation_guidance"]["best_topics"]
    assert db_session.query(SocialWeeklyReviewRow).count() == 1


def test_x_account_snapshot_api_lists_followers_delta(db_session, synced_client):
    db_session.add_all(
        [
            SocialAccountSnapshotRow(
                platform="x",
                account_handle="SynapseNetworkA",
                followers=10,
                following=21,
                profile_url="https://x.com/SynapseNetworkA",
                observed_at=utcnow() - timedelta(days=1),
            ),
            SocialAccountSnapshotRow(
                platform="x",
                account_handle="SynapseNetworkA",
                followers=13,
                following=21,
                profile_url="https://x.com/SynapseNetworkA",
                observed_at=utcnow(),
            ),
        ]
    )
    db_session.commit()

    response = synced_client.get("/api/social/account-snapshots")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["followers"] == 13
    assert payload["items"][0]["followers_delta"] == 3


def test_x_social_weekly_review_recurring_workflow_is_dry_runnable(synced_client):
    workflows = synced_client.get("/api/recurring-workflows")
    assert workflows.status_code == 200
    assert "x_social_weekly_analytics_review" in {
        row["workflow_key"] for row in workflows.json()
    }

    weekly = synced_client.post(
        "/api/recurring-workflows/x_social_weekly_analytics_review/run",
        json={"dry_run": True},
    )

    assert weekly.status_code == 200
    assert weekly.json()["result"]["generates"] == "content_generation_guidance"


def test_published_reply_items_are_metric_observer_targets(db_session):
    manual_reply = SocialReplyItemRow(
        platform="x",
        external_reply_id="source-reply-manual",
        source_post_id="source-post-manual",
        source_author_handle="agentbuilder",
        incoming_text="Manual reply was posted outside API.",
        suggested_reply="Manual reply evidence should not be observed as a real post.",
        status="live",
        source_url="https://x.com/agentbuilder/status/source-post-manual",
        published_external_post_id="manual:2057791192738283000",
    )
    reply = SocialReplyItemRow(
        platform="x",
        external_reply_id="source-reply-1",
        source_post_id="source-post-1",
        source_author_handle="agentbuilder",
        incoming_text="How should agents control API spend?",
        suggested_reply="Give agents a capped budget and an auditable receipt.",
        status="live",
        source_url="https://x.com/agentbuilder/status/source-post-1",
        published_external_post_id="https://x.com/SynapseNetworkA/status/2057791192738283669",
        metadata_json='{"x_reply_source_strategy":"agent_economy_monetization"}',
    )
    db_session.add_all([manual_reply, reply])
    db_session.commit()

    targets = published_targets_for_metrics(db_session, max_records=10)

    reply_targets = [
        target for target in targets if target.external_post_id == "2057791192738283669"
    ]
    assert len(reply_targets) == 1
    assert reply_targets[0].source_kind == "reply"
    assert reply_targets[0].metadata["reply_item_id"] == reply.id
    assert all(target.external_post_id != "2057791192738283000" for target in targets)


def test_metric_row_records_link_clicks_only_when_post_has_url():
    class FakeXPost:
        public_metrics = {"like_count": 1, "reply_count": 2}
        non_public_metrics = {"url_link_clicks": 7, "impression_count": 20}
        organic_metrics = {}

    target = type(
        "Target",
        (),
        {
            "post_id": None,
            "external_post_id": "2057791192738283669",
            "published_at": utcnow(),
            "source_kind": "distribution_task",
            "body_text": "Implementation notes: https://docs.synapse-network.ai",
            "metadata": {},
            "title": "Post with link",
            "status": "live",
            "task_id": 1,
        },
    )()

    metric = metric_row_from_x_post(
        target,
        FakeXPost(),
        observed_at=utcnow(),
        private_metrics_available=True,
    )

    assert metric.link_clicks == 7
