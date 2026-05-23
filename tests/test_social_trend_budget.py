from server.database import SocialTrendItemRow, SocialWatchlistAccountRow, utcnow
from server.database_social_budget import social_x_read_budget_events
from server.services.social import publishing as social_publishing


class FakeXAccessToken:
    access_token = "test-x-access-token"


class FakeXReadClient:
    def __init__(self, access_token: str):
        self.access_token = access_token

    def get_user_tweets(self, user_id: str, *, max_results: int = 5):
        return [
            social_publishing.XPost(
                id="tweet-1",
                text="AI agents are starting to need reliable API access, budget controls, payment rails, and developer infrastructure for autonomous workflows.",
                author_id=user_id,
                created_at="2026-04-26T12:00:00Z",
                public_metrics={"like_count": 120, "retweet_count": 12},
            )
        ]


def test_social_x_read_budget_table_uses_sqlalchemy_autoincrement_schema():
    id_column = social_x_read_budget_events.c.id

    assert id_column.primary_key is True
    assert id_column.autoincrement is True


def test_x_social_trend_radar_stops_when_daily_read_budget_is_exhausted(
    monkeypatch, db_session
):
    social_publishing.ensure_default_social_ops_seed(db_session)
    db_session.query(SocialWatchlistAccountRow).update(
        {SocialWatchlistAccountRow.last_checked_at: utcnow()}
    )
    db_session.add(
        SocialWatchlistAccountRow(
            platform="x",
            handle="BudgetAI",
            category="ai_company",
            status="active",
            last_checked_at=None,
        )
    )
    db_session.commit()

    monkeypatch.setattr(social_publishing.config, "X_READ_DAILY_REQUEST_BUDGET", 0)
    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("token refresh must not happen after budget exhaustion")
        ),
    )

    result = social_publishing.run_x_social_trend_radar_sweep(db_session)

    assert result["budget_exhausted"] is True
    assert result["created_trend_ids"] == []
    assert "budget exhausted" in result["diagnostic"].lower()


def test_x_social_trend_radar_reuses_cached_x_user_id(monkeypatch, db_session):
    social_publishing.ensure_default_social_ops_seed(db_session)
    db_session.query(SocialWatchlistAccountRow).update(
        {SocialWatchlistAccountRow.last_checked_at: utcnow()}
    )
    db_session.add(
        SocialWatchlistAccountRow(
            platform="x",
            handle="CachedAI",
            display_name="Cached AI",
            category="agent_framework",
            rationale="Cached X user id should avoid user lookup reads.",
            status="active",
            x_user_id="cached-user-1",
            last_checked_at=None,
        )
    )
    db_session.commit()

    class CachedUserClient(FakeXReadClient):
        def get_user_by_username(self, username: str):
            raise AssertionError("cached x_user_id should skip user lookup")

    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )
    monkeypatch.setattr(social_publishing, "XApiClient", CachedUserClient)

    result = social_publishing.run_x_social_trend_radar_sweep(
        db_session, min_relevance_score=0.70
    )

    assert result["created_trend_ids"]
    trend = db_session.get(SocialTrendItemRow, result["created_trend_ids"][0])
    assert trend.author_handle == "CachedAI"
