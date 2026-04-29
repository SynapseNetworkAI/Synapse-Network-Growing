from server.database import SocialPostDraftRow, utcnow
from server.services.social import daily_planner as social_daily_planner
from server.services.social import post_metrics as social_post_metrics
from server.services.social import publishing as social_publishing
from server.services.social.x_client import (
    XApiAuthError,
    XApiClient,
    XApiRateLimitError,
    XApiTransientError,
)


class FakeXAccessToken:
    access_token = "test-x-access-token"


class FakeXReadClient:
    def __init__(self, access_token: str):
        self.access_token = access_token

    def get_posts_by_ids(
        self, tweet_ids: list[str], *, include_owner_metrics: bool = False
    ):
        return [
            social_publishing.XPost(
                id=tweet_ids[0],
                text="Synapse Network launch update.",
                public_metrics={
                    "like_count": 11,
                    "reply_count": 3,
                    "retweet_count": 2,
                    "impression_count": 1200,
                },
                non_public_metrics={"impression_count": 1400, "url_link_clicks": 9}
                if include_owner_metrics
                else None,
                organic_metrics={"url_link_clicks": 7}
                if include_owner_metrics
                else None,
            )
        ]


def test_x_social_daily_planner_helper_edges(monkeypatch, db_session):
    account = social_publishing.ensure_default_social_account(db_session)
    bad_metadata = SocialPostDraftRow(
        platform="x",
        account_id=account.id,
        title="Bad metadata",
        body_text="metadata",
        raw_agent_output_json='{"planner_slot": "not-int"}',
    )
    assert social_daily_planner._daily_planner_slot(bad_metadata) == 0
    bad_metadata.raw_agent_output_json = (
        '{"planner_run_key": "x_daily:1:2026-04-29:slot-7"}'
    )
    assert social_daily_planner._daily_planner_slot(bad_metadata) == 7
    assert (
        social_daily_planner._campaign_goal_summary(None)[0]
        == "Build trust for Synapse Network official X"
    )
    assert "governed API access" in social_daily_planner._planner_variable_factor(
        "2026-04-29", 1, [], []
    )

    monkeypatch.setattr(
        social_publishing,
        "_finalize_generated_social_post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("agent unavailable")
        ),
    )
    row, _run_key, is_active = social_daily_planner._generate_daily_planner_slot(
        db_session, account_id=account.id, local_date="2026-04-29", daily_rows=[]
    )
    assert row.status == "generating"
    assert is_active is True


def test_x_social_daily_planner_records_failed_slot(monkeypatch, db_session):
    account = social_publishing.ensure_default_social_account(db_session)
    failed = SocialPostDraftRow(
        platform="x",
        account_id=account.id,
        source_type="daily_planner",
        title="Failed slot",
        body_text="",
        status="failed",
    )
    db_session.add(failed)
    db_session.flush()

    monkeypatch.setattr(
        social_daily_planner,
        "_generate_daily_planner_slot",
        lambda *_args, **_kwargs: (
            failed,
            f"x_daily:{account.id}:2026-04-29:slot-1",
            False,
        ),
    )
    created_ids, failed_ids, run_keys = (
        social_daily_planner._top_up_daily_planner_slots(
            db_session,
            account_id=account.id,
            local_date="2026-04-29",
            daily_rows=[],
            active_rows=[],
        )
    )
    assert created_ids == []
    assert failed_ids == [failed.id, failed.id, failed.id]
    assert run_keys == []


def test_x_social_post_metrics_empty_and_missing_branches(monkeypatch, db_session):
    summary = social_post_metrics.social_post_metrics_summary(db_session)
    assert summary.diagnostic
    assert (
        social_post_metrics._metric_value(None, {"value": "bad"}, keys=("value",)) == 0
    )

    empty_result = social_post_metrics.run_x_social_post_observer_sweep(db_session)
    assert empty_result["observed_count"] == 0
    assert "No published X posts" in empty_result["diagnostic"]

    account = social_publishing.ensure_default_social_account(db_session)
    post = SocialPostDraftRow(
        platform="x",
        account_id=account.id,
        source_type="manual_prompt",
        title="Missing metric source",
        body_text="Published post.",
        status="published",
        generated_by="operator",
        external_post_id="missing-x-post",
        published_at=utcnow(),
    )
    db_session.add(post)
    db_session.commit()

    class MissingXReadClient(FakeXReadClient):
        def get_posts_by_ids(
            self, tweet_ids: list[str], *, include_owner_metrics: bool = False
        ):
            return []

    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )
    monkeypatch.setattr(social_post_metrics, "XApiClient", MissingXReadClient)

    missing_result = social_post_metrics.run_x_social_post_observer_sweep(db_session)
    assert missing_result["created_metric_ids"] == []
    assert missing_result["missing_external_ids"] == ["missing-x-post"]


def test_x_social_post_metrics_auth_fallback_and_rate_limit(monkeypatch):
    class OwnerMetricsForbiddenClient(FakeXReadClient):
        def get_posts_by_ids(
            self, tweet_ids: list[str], *, include_owner_metrics: bool = False
        ):
            if include_owner_metrics:
                raise XApiAuthError("owner metrics forbidden")
            return super().get_posts_by_ids(
                tweet_ids, include_owner_metrics=include_owner_metrics
            )

    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )
    monkeypatch.setattr(social_post_metrics, "XApiClient", OwnerMetricsForbiddenClient)
    posts, diagnostic, private_available = social_post_metrics._lookup_x_metric_posts(
        ["tweet-1"]
    )
    assert posts
    assert private_available is False
    assert "Owner metrics unavailable" in diagnostic

    class RateLimitedClient(FakeXReadClient):
        def get_posts_by_ids(
            self, tweet_ids: list[str], *, include_owner_metrics: bool = False
        ):
            raise XApiRateLimitError("rate limited")

    monkeypatch.setattr(social_post_metrics, "XApiClient", RateLimitedClient)
    try:
        social_post_metrics._lookup_x_metric_posts(["tweet-1"])
    except XApiRateLimitError as exc:
        assert "rate limited" in str(exc)
    else:
        raise AssertionError("rate limit should bubble to observer")


def test_x_client_post_lookup_response_shapes(monkeypatch):
    client = XApiClient("token")
    captured: dict[str, object] = {}

    def fake_get_json(path, params):
        captured["path"] = path
        captured["params"] = params
        return {
            "data": [
                {
                    "id": "tweet-1",
                    "text": "Metric lookup post",
                    "public_metrics": {"like_count": 1},
                    "non_public_metrics": {"impression_count": 5},
                    "organic_metrics": {"url_link_clicks": 2},
                }
            ]
        }

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    assert client.get_posts_by_ids([]) == []
    posts = client.get_posts_by_ids(["tweet-1"], include_owner_metrics=True)
    assert posts[0].id == "tweet-1"
    assert posts[0].non_public_metrics["impression_count"] == 5
    assert "non_public_metrics" in captured["params"]["tweet.fields"]

    monkeypatch.setattr(client, "_get_json", lambda *_args, **_kwargs: {})
    assert client.get_posts_by_ids(["tweet-1"]) == []

    monkeypatch.setattr(client, "_get_json", lambda *_args, **_kwargs: {"data": {}})
    try:
        client.get_posts_by_ids(["tweet-1"])
    except XApiTransientError as exc:
        assert "not a list" in str(exc)
    else:
        raise AssertionError("non-list X response should fail closed")
