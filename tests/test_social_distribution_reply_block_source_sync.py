import json

from server.database import (
    SocialReplyItemRow,
    SocialWatchlistAccountRow,
    utcnow,
)
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionEventRow,
)
from server.services.social import distribution_reply_blocks as reply_blocks
from server.services.social import distribution_reply_block_policy as reply_block_policy
from server.services.social import publishing as social_publishing
from server.services.social.distribution_reply_block_publisher import (
    run_x_social_daily_reply_block_publisher,
)
from tests.test_social_distribution_reply_blocks import (
    _reply_asset,
    _install_reply_agent,
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
                id=str(6100 + index),
                text=(
                    "AI agents need reliable paid API access with budget controls, "
                    "metering, receipts, settlement evidence, and safe developer "
                    f"infrastructure before autonomous workflows can scale. Example {index}."
                ),
                author_id=user_id,
                created_at=f"2026-04-26T12:0{index}:00Z",
                public_metrics={
                    "like_count": 120 + index,
                    "retweet_count": 12,
                    "reply_count": 5,
                    "quote_count": 3,
                },
            )
            for index in range(1, max(5, int(max_results)) + 1)
        ]


def _prepare_due_x_watchlist(db_session):
    social_publishing.ensure_default_social_ops_seed(db_session)
    db_session.query(SocialWatchlistAccountRow).update(
        {SocialWatchlistAccountRow.last_checked_at: utcnow()}
    )
    db_session.add(
        SocialWatchlistAccountRow(
            platform="x",
            handle="ExampleAI",
            display_name="Example AI",
            category="agent_framework",
            rationale="Relevant agent infrastructure account.",
            status="active",
            last_checked_at=None,
        )
    )
    db_session.commit()


def _install_x_read_budget(monkeypatch):
    monkeypatch.setattr(social_publishing.config, "X_READ_DAILY_REQUEST_BUDGET", 1000)
    monkeypatch.setattr(
        social_publishing.config, "X_TREND_DAILY_SOURCE_POST_BUDGET", 1000
    )


def test_generate_x_reply_block_reports_empty_trend_inventory_after_sync_attempt(
    synced_client, db_session, monkeypatch
):
    monkeypatch.setattr(
        reply_block_policy.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: social_publishing.XOAuth2AccessToken(
            "access-token", refreshed=False
        ),
    )
    monkeypatch.setattr(
        reply_blocks,
        "sync_reply_sources_from_watchlist",
        lambda *_args, **_kwargs: {
            "read_only": True,
            "external_actions": [],
            "connector": "x_watchlist_timeline",
            "x_read_connector_configured": True,
            "created_trend_ids": [],
            "retained_trend_ids": [],
            "retained_count": 0,
            "filtered_count": 0,
            "watchlist_active_count": 0,
            "due_watchlist_count": 0,
            "synced_handles": [],
            "diagnostic": "No watchlist accounts are due for X timeline sync.",
        },
    )
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={"actor": "agent", "target_count": 5},
    )

    assert response.status_code == 400
    assert "no usable X source posts were found" in response.json()["detail"]
    assert db_session.query(SocialReplyItemRow).count() == 0


def test_generate_x_reply_block_syncs_watchlist_when_inventory_empty(
    synced_client, db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    _install_x_read_budget(monkeypatch)
    _prepare_due_x_watchlist(db_session)
    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )
    monkeypatch.setattr(social_publishing, "XApiClient", FakeXReadClient)
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={"actor": "agent", "target_count": 5, "agent_review": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["reply_ids"]) == 5
    assert payload["auto_publish"] is False
    assert payload["source_sync"]["connector"] == "x_watchlist_timeline"
    assert payload["source_sync"]["created_trend_ids"]
    replies = db_session.query(SocialReplyItemRow).order_by(SocialReplyItemRow.id).all()
    assert len(replies) == 5
    assert {reply.status for reply in replies} == {
        "agent_approved_needs_manual_publish"
    }
    assert all(reply.published_external_post_id is None for reply in replies)
    assert all(
        reply.source_url.startswith("https://x.com/ExampleAI/status/")
        for reply in replies
    )
    event_types = [
        row.event_type
        for row in db_session.query(SocialDistributionEventRow)
        .order_by(SocialDistributionEventRow.id)
        .all()
    ]
    assert event_types == [
        "x_reply_block_source_sync_attempted",
        "x_reply_block_candidates_generated",
    ]
    db_session.refresh(asset)
    asset_metadata = json.loads(asset.agent_metadata_json)
    assert asset_metadata["reply_block"]["source_sync"]["created_trend_ids"]


def test_daily_reply_block_workflow_syncs_watchlist_then_queues_candidates(
    db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    _install_x_read_budget(monkeypatch)
    _prepare_due_x_watchlist(db_session)
    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )
    monkeypatch.setattr(social_publishing, "XApiClient", FakeXReadClient)
    db_session.query(SocialContentAssetRow).delete()
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()

    result = run_x_social_daily_reply_block_publisher(db_session)

    assert result["processed"] is True
    assert result["asset_id"] == asset.id
    assert result["auto_publish"] is False
    assert result["result"]["source_sync"]["created_trend_ids"]
    replies = db_session.query(SocialReplyItemRow).order_by(SocialReplyItemRow.id).all()
    assert len(replies) == 5
    assert {reply.status for reply in replies} == {
        "agent_approved_needs_manual_publish"
    }
    assert all(reply.published_external_post_id is None for reply in replies)
