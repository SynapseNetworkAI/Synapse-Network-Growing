from datetime import datetime, timedelta, timezone

from server.database import (
    SocialPostDraftRow,
    SocialPostMetricRow,
    SocialReplyItemRow,
    SocialRepostCandidateRow,
    SocialTrendItemRow,
    SocialWatchlistAccountRow,
    utcnow,
)
from server.services.social import publishing as social_publishing
from server.services.social import daily_planner as social_daily_planner
from server.services.social import post_metrics as social_post_metrics
from server.services.social.post_metric_features import json_object


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

    def get_posts_by_ids(
        self, tweet_ids: list[str], *, include_owner_metrics: bool = False
    ):
        return [
            social_publishing.XPost(
                id=tweet_ids[0],
                text="Synapse Network launch update.",
                created_at="2026-04-26T12:00:00Z",
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


def test_x_social_daily_content_planner_tops_up_three_human_review_drafts_per_local_day(
    monkeypatch, db_session
):
    calls = []

    def fake_generate(prompt, *, style_type=None, media_mode=None):
        calls.append(
            {"prompt": prompt, "style_type": style_type, "media_mode": media_mode}
        )
        return social_publishing.GeneratedXPost(
            title="Daily Synapse Network update",
            body_text="AI agents need trusted payment rails. Synapse Network helps builders give agents governed API access, budgets, and settlement paths. #AIAgents #AgentEconomy",
            media_decision="text",
            context_sources=("product-marketing-context", "social-content"),
            model="test-model",
        )

    monkeypatch.setattr(social_publishing, "_generate_x_post_copy", fake_generate)
    monkeypatch.setattr(
        social_publishing.x_publisher,
        "publish_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("daily planner must not publish to X")
        ),
    )

    result = social_daily_planner.run_x_social_daily_content_planner(db_session)

    assert result["already_created"] is False
    assert result["already_satisfied"] is True
    assert result["target_count"] == 3
    assert result["active_count"] == 3
    assert len(result["created_post_ids"]) == 3
    assert len(calls) == 3
    assert result["max_created_per_tick"] == 3
    assert calls and calls[0]["media_mode"] == "text_only"

    second = social_daily_planner.run_x_social_daily_content_planner(db_session)

    assert second["already_created"] is True
    assert second["already_satisfied"] is True
    assert second["active_count"] == 3
    assert len(calls) == 3
    rows = (
        db_session.query(SocialPostDraftRow)
        .filter(SocialPostDraftRow.source_type == "daily_planner")
        .order_by(SocialPostDraftRow.id.asc())
        .all()
    )
    assert len(rows) == 3
    for index, row in enumerate(rows, start=1):
        assert row.source_type == "daily_planner"
        assert row.generated_by == "x_social_daily_content_planner"
        assert row.status == "needs_review"
        raw = social_publishing._json_loads(row.raw_agent_output_json, {})
        assert raw["planner_local_date"] == result["planner_local_date"]
        assert raw["planner_run_key"].endswith(f":slot-{index}")
        assert raw["planner_slot"] == index
        assert raw["watchlist_handles"]
    assert (
        db_session.query(SocialPostDraftRow)
        .filter(SocialPostDraftRow.source_type == "daily_planner")
        .count()
        == 3
    )


def test_x_social_daily_content_planner_replenishes_after_publish(
    monkeypatch, db_session
):
    account = social_publishing.ensure_default_social_account(db_session)
    local_date = social_publishing._operator_local_date()
    db_session.add_all(
        [
            SocialPostDraftRow(
                platform="x",
                account_id=account.id,
                source_type="daily_planner",
                title="Published slot",
                body_text="Already shipped.",
                status="published",
                generated_by="x_social_daily_content_planner",
                raw_agent_output_json=social_publishing._json_dumps(
                    {
                        "planner_local_date": local_date,
                        "planner_slot": 1,
                        "planner_run_key": f"x_daily:{account.id}:{local_date}:slot-1",
                    }
                ),
            ),
            SocialPostDraftRow(
                platform="x",
                account_id=account.id,
                source_type="daily_planner",
                title="Active slot 2",
                body_text="Review me.",
                status="needs_review",
                generated_by="x_social_daily_content_planner",
                raw_agent_output_json=social_publishing._json_dumps(
                    {
                        "planner_local_date": local_date,
                        "planner_slot": 2,
                        "planner_run_key": f"x_daily:{account.id}:{local_date}:slot-2",
                    }
                ),
            ),
            SocialPostDraftRow(
                platform="x",
                account_id=account.id,
                source_type="daily_planner",
                title="Active slot 3",
                body_text="Review me too.",
                status="approved",
                generated_by="x_social_daily_content_planner",
                raw_agent_output_json=social_publishing._json_dumps(
                    {
                        "planner_local_date": local_date,
                        "planner_slot": 3,
                        "planner_run_key": f"x_daily:{account.id}:{local_date}:slot-3",
                    }
                ),
            ),
        ]
    )
    db_session.commit()

    monkeypatch.setattr(
        social_publishing,
        "_generate_x_post_copy",
        lambda *args, **kwargs: social_publishing.GeneratedXPost(
            title="Backfill slot",
            body_text="Backfill today's draft inventory after a published post. #AIAgents",
            media_decision="text",
            model="test-model",
        ),
    )

    result = social_daily_planner.run_x_social_daily_content_planner(db_session)

    assert result["target_count"] == 3
    assert result["active_count"] == 3
    assert len(result["created_post_ids"]) == 1
    created = db_session.get(SocialPostDraftRow, result["created_post_ids"][0])
    raw = social_publishing._json_loads(created.raw_agent_output_json, {})
    assert raw["planner_slot"] == 1
    assert created.status == "needs_review"


def test_x_social_trend_and_repost_sweeps_are_filtered_and_human_gated(db_session):
    social_publishing.ensure_default_social_account(db_session)
    db_session.add_all(
        [
            SocialTrendItemRow(
                topic="High quality agent payment discussion",
                summary="Agent builders are discussing budgeted API calls and tool access.",
                relevance_score=0.91,
                status="new",
                source_url="https://x.com/example/status/1",
                author_handle="agent_builder",
            ),
            SocialTrendItemRow(
                topic="Low quality meme",
                summary="Unrelated low-signal meme.",
                relevance_score=0.20,
                status="new",
            ),
        ]
    )
    db_session.commit()

    trend_result = social_publishing.run_x_social_trend_radar_sweep(
        db_session, min_relevance_score=0.70
    )

    assert trend_result["read_only"] is True
    assert trend_result["external_actions"] == []
    assert trend_result["retained_count"] >= 1
    assert trend_result["filtered_count"] >= 1

    repost_result = social_publishing.run_x_social_repost_candidate_sweep(
        db_session, min_relevance_score=0.75
    )

    assert repost_result["human_gate_required"] is True
    assert repost_result["external_actions"] == []
    assert repost_result["created_candidate_ids"]
    candidate = db_session.get(
        SocialRepostCandidateRow, repost_result["created_candidate_ids"][0]
    )
    assert candidate is not None
    assert candidate.status == "candidate"
    assert "Synapse angle" in candidate.suggested_quote


def test_x_social_trend_radar_syncs_due_watchlist_from_x(monkeypatch, db_session):
    social_publishing.ensure_default_social_account(db_session)
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

    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )
    monkeypatch.setattr(social_publishing, "XApiClient", FakeXReadClient)

    result = social_publishing.run_x_social_trend_radar_sweep(
        db_session, min_relevance_score=0.70
    )

    assert result["connector"] == "x_watchlist_timeline"
    assert result["x_read_connector_configured"] is True
    assert result["created_trend_ids"]
    assert result["skipped_short_text_count"] >= 1
    trend = db_session.get(SocialTrendItemRow, result["created_trend_ids"][0])
    assert trend is not None
    assert trend.source_url == "https://x.com/ExampleAI/status/tweet-1"
    assert trend.author_handle == "ExampleAI"
    assert "Public metrics" in trend.summary
    account = (
        db_session.query(SocialWatchlistAccountRow)
        .filter(SocialWatchlistAccountRow.handle == "ExampleAI")
        .one()
    )
    assert account.x_user_id == "user-1"
    assert (
        result["budget_remaining_requests"]
        < social_publishing.config.X_READ_DAILY_REQUEST_BUDGET
    )


def test_x_social_trend_radar_records_rate_limit_without_retrying(
    monkeypatch, db_session
):
    social_publishing.ensure_default_social_account(db_session)
    social_publishing.ensure_default_social_ops_seed(db_session)
    db_session.query(SocialWatchlistAccountRow).update(
        {SocialWatchlistAccountRow.last_checked_at: utcnow()}
    )
    db_session.add(
        SocialWatchlistAccountRow(
            platform="x",
            handle="RateLimitedAI",
            category="ai_company",
            status="active",
            last_checked_at=None,
        )
    )
    db_session.commit()

    class RateLimitedClient:
        def __init__(self, access_token: str):
            self.access_token = access_token

        def get_user_by_username(self, username: str):
            raise social_publishing.XApiRateLimitError("too many requests")

    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )
    monkeypatch.setattr(social_publishing, "XApiClient", RateLimitedClient)

    result = social_publishing.run_x_social_trend_radar_sweep(db_session)

    assert result["rate_limited"] is True
    assert "rate limit" in result["diagnostic"].lower()
    account = (
        db_session.query(SocialWatchlistAccountRow)
        .filter(SocialWatchlistAccountRow.handle == "RateLimitedAI")
        .one()
    )
    assert account.last_checked_at is not None


def test_x_social_repost_candidate_sweep_requires_source_url(db_session):
    social_publishing.ensure_default_social_account(db_session)
    db_session.add_all(
        [
            SocialTrendItemRow(
                topic="Local seed should not be reposted",
                summary="Agent builders need payment rails, but this is local seed data without an X source.",
                relevance_score=0.95,
                status="new",
                source_url=None,
            ),
            SocialTrendItemRow(
                topic="Real X source can become repost candidate",
                summary="Agent builders need payment rails and governed API budgets.",
                relevance_score=0.93,
                status="new",
                source_url="https://x.com/example/status/2",
                author_handle="example",
            ),
        ]
    )
    db_session.commit()

    result = social_publishing.run_x_social_repost_candidate_sweep(
        db_session, min_relevance_score=0.75
    )

    assert result["created_candidate_ids"]
    candidates = db_session.query(SocialRepostCandidateRow).all()
    assert all(candidate.source_url for candidate in candidates)
    assert result["skipped_trend_ids"]


def test_x_social_helper_branches_are_deterministic(monkeypatch, db_session):
    assert social_publishing._ensure_aware_utc(datetime(2026, 1, 1)).tzinfo is not None
    monkeypatch.setattr(social_publishing.config, "OPERATOR_TIMEZONE", "Invalid/Zone")
    assert social_publishing._operator_timezone().key == "UTC"

    post = SocialPostDraftRow(
        platform="x",
        account_id=1,
        title="Bad metadata",
        body_text="metadata",
        raw_agent_output_json="[]",
    )
    assert social_daily_planner._daily_planner_raw_metadata(post) == {}
    assert social_publishing._parse_x_datetime(None).tzinfo is not None
    assert social_publishing._parse_x_datetime("not-a-date").tzinfo is not None
    assert social_publishing._parse_x_datetime("2026-04-27T00:00:00").tzinfo is None
    assert social_publishing._x_engagement_score({}) == 0.0
    assert social_publishing._gcp_adc_reauth_summary().startswith(
        "Local Google credentials expired"
    )
    assert social_publishing._extract_x_post_id(None) == ""
    assert (
        social_publishing._extract_x_post_id("https://x.com/OpenAI/status/12345")
        == "12345"
    )
    assert (
        social_publishing._extract_x_post_id("https://x.com/i/web/statuses/23456")
        == "23456"
    )
    assert (
        social_publishing._extract_x_post_id("https://example.com/share?tweet_id=34567")
        == "34567"
    )
    assert social_publishing._extract_x_post_id("https://example.com/no-id") == ""
    assert not hasattr(social_publishing, "_reply_generation_for_candidate")

    watch = SocialWatchlistAccountRow(
        handle="TimezoneAI", last_checked_at=datetime.now(timezone.utc)
    )
    assert (
        social_publishing._is_due_for_x_watchlist_sync(
            watch, datetime.now(timezone.utc)
        )
        is False
    )
    short_post = social_publishing.XPost(id="short", text="Tiny")
    assert (
        social_publishing._should_keep_x_post(short_post, 1.0, min_relevance_score=0.1)
        is False
    )
    assert (
        social_publishing._is_value_add_quote("Great point!", "AI agents need payments")
        is False
    )
    assert (
        social_publishing._is_value_add_quote(
            "AI agents need payment rails. Synapse adds budgets and governed API access for builders.",
            "AI agents need payment rails.",
        )
        is False
    )

    social_publishing.ensure_default_social_ops_seed(db_session)
    db_session.query(SocialWatchlistAccountRow).update(
        {SocialWatchlistAccountRow.last_checked_at: utcnow()}
    )
    db_session.commit()
    result = social_publishing._sync_x_watchlist_timeline_posts(
        db_session, min_relevance_score=0.70
    )
    assert result["due_watchlist_count"] == 0


def test_x_social_trend_radar_handles_auth_failure_as_diagnostic(
    monkeypatch, db_session
):
    social_publishing.ensure_default_social_account(db_session)
    social_publishing.ensure_default_social_ops_seed(db_session)
    db_session.query(SocialWatchlistAccountRow).update(
        {SocialWatchlistAccountRow.last_checked_at: utcnow()}
    )
    db_session.add(
        SocialWatchlistAccountRow(
            platform="x",
            handle="AuthFailAI",
            category="ai_company",
            status="active",
            last_checked_at=None,
        )
    )
    db_session.commit()

    class AuthFailClient:
        def __init__(self, access_token: str):
            self.access_token = access_token

        def get_user_by_username(self, username: str):
            raise social_publishing.XApiAuthError("auth failed")

    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )
    monkeypatch.setattr(social_publishing, "XApiClient", AuthFailClient)

    result = social_publishing.run_x_social_trend_radar_sweep(db_session)

    assert result["x_read_connector_configured"] is True
    assert "auth failed" in result["diagnostic"]


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


def test_social_post_detail_returns_events_and_publish_result(
    monkeypatch, synced_client
):
    monkeypatch.setattr(
        social_publishing.x_publisher,
        "publish_text",
        lambda account, body_text, media_ids=None: social_publishing.XPublishResult(
            post_id="1801",
            response_summary={"data": {"id": "1801"}},
        ),
    )
    created = synced_client.post(
        "/api/social/posts",
        json={
            "title": "Operator update",
            "body_text": "Synapse Network now has a human-reviewed X publishing workflow.",
            "status": "approved",
        },
    ).json()

    published = synced_client.post(
        f"/api/social/posts/{created['id']}/publish-x", json={"actor": "operator"}
    )
    assert published.status_code == 200

    detail = synced_client.get(f"/api/social/posts/{created['id']}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["id"] == created["id"]
    assert payload["external_post_id"] == "1801"
    assert payload["external_url"].endswith("/status/1801")
    event_types = [event["event_type"] for event in payload["events"]]
    assert "draft_created" in event_types
    assert "publish_requested" in event_types
    assert "published" in event_types
    assert payload["events"][-1]["payload"]["external_post_id"] == "1801"


def test_social_post_detail_missing_returns_404(synced_client):
    response = synced_client.get("/api/social/posts/999999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_social_ops_center_projection_is_human_gated_and_read_only(
    synced_client, db_session
):
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
    summary = synced_client.get("/api/social/post-metrics/summary")
    assert summary.status_code == 200
    assert summary.json()["total_likes"] == 42
    assert summary.json()["top_posts"]


def test_manual_social_post_metrics_capture_x_brand_signal_fields(synced_client):
    response = synced_client.post(
        "/api/social/post-metrics/manual",
        json={
            "external_post_id": "manual-x-week-1-day-1",
            "impressions": 300,
            "profile_visits": 12,
            "replies": 2,
            "bookmarks": 4,
            "follows": 1,
            "format_kind": "x_long_post",
            "summary": "Manual Week 1 X metric entry.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["external_post_id"] == "manual-x-week-1-day-1"
    assert payload["profile_visits"] == 12
    assert payload["bookmarks"] == 4
    assert payload["format_kind"] == "x_long_post"
    summary = synced_client.get("/api/social/post-metrics/summary")
    assert summary.status_code == 200
    assert summary.json()["total_profile_visits"] == 12
    assert summary.json()["total_bookmarks"] == 4
    assert summary.json()["top_posts"][0]["bookmarks"] == 4


def test_x_social_post_observer_sweep_writes_metrics(monkeypatch, db_session):
    account = social_publishing.ensure_default_social_account(db_session)
    post = SocialPostDraftRow(
        platform="x",
        account_id=account.id,
        source_type="manual_prompt",
        title="Published metrics target",
        body_text="Published post for metrics.",
        status="published",
        generated_by="operator",
        external_post_id="tweet-metrics-1",
        published_at=utcnow(),
    )
    db_session.add(post)
    db_session.commit()

    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )
    monkeypatch.setattr(social_post_metrics, "XApiClient", FakeXReadClient)

    result = social_post_metrics.run_x_social_post_observer_sweep(db_session)

    assert result["read_only"] is True
    assert result["observed_count"] == 1
    metric = db_session.get(SocialPostMetricRow, result["created_metric_ids"][0])
    assert metric.post_id == post.id
    assert metric.external_post_id == "tweet-metrics-1"
    assert metric.impressions == 1400
    assert metric.likes == 11
    metadata = json_object(metric.metadata_json)
    assert metadata["content_type"] == "original"
    assert metadata["has_url"] is False
    assert metric.link_clicks == 0

    summary = social_post_metrics.social_post_metrics_summary(db_session)
    assert summary.total_impressions == 1400
    assert summary.top_posts[0].external_post_id == "tweet-metrics-1"


def test_social_trend_query_filters_and_detail_endpoint(synced_client, db_session):
    now = utcnow()
    old = now - timedelta(days=10)
    db_session.add_all(
        [
            SocialTrendItemRow(
                source_platform="x",
                source_url="https://x.com/OpenAI/status/4242",
                author_handle="OpenAI",
                topic="synapse-query-marker AI agents need payment rails",
                summary="A high-signal X post about agent payment infrastructure.",
                relevance_score=0.93,
                status="new",
                collected_at=now,
            ),
            SocialTrendItemRow(
                source_platform="x",
                source_url=None,
                author_handle=None,
                topic="synapse-query-marker local seed",
                summary="Local inspiration without a source URL.",
                relevance_score=0.70,
                status="saved",
                collected_at=now,
            ),
            SocialTrendItemRow(
                source_platform="rss",
                source_url="https://example.com/agent-payments",
                author_handle="ExampleSource",
                topic="synapse-query-marker external article",
                summary="Non-X source retained for future platform expansion.",
                relevance_score=0.80,
                status="new",
                collected_at=old,
            ),
        ]
    )
    db_session.commit()

    local_day = social_publishing._operator_local_date(now)
    response = synced_client.get(
        "/api/social/trends/query",
        params={
            "q": "synapse-query-marker",
            "source_kind": "x_post",
            "author_handle": "@OpenAI",
            "date_from": local_day,
            "date_to": local_day,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["author_handle"] == "OpenAI"
    assert payload["items"][0]["source_kind"] == "x_post"

    local_seed = synced_client.get(
        "/api/social/trends/query",
        params={
            "q": "synapse-query-marker",
            "source_kind": "local_seed",
            "date_from": local_day,
            "date_to": local_day,
        },
    )

    assert local_seed.status_code == 200
    assert local_seed.json()["total"] == 1
    assert local_seed.json()["items"][0]["source_kind"] == "local_seed"

    all_sources = synced_client.get(
        "/api/social/trends/query",
        params={
            "q": "synapse-query-marker",
            "source_kind": "all",
            "limit": 10,
            "offset": 0,
        },
    )
    assert all_sources.status_code == 200
    assert all_sources.json()["total"] == 3

    other_source = synced_client.get(
        "/api/social/trends/query",
        params={"q": "synapse-query-marker", "source_kind": "other"},
    )
    assert other_source.status_code == 200
    assert other_source.json()["total"] == 1
    assert other_source.json()["items"][0]["source_kind"] == "other"

    invalid_date = synced_client.get(
        "/api/social/trends/query", params={"date_from": "not-a-date"}
    )
    assert invalid_date.status_code == 400
    assert "invalid date filter" in invalid_date.json()["detail"]

    invalid_source = synced_client.get(
        "/api/social/trends/query", params={"source_kind": "bluesky"}
    )
    assert invalid_source.status_code == 400
    assert "unsupported source_kind" in invalid_source.json()["detail"]

    detail_id = payload["items"][0]["id"]
    detail = synced_client.get(f"/api/social/trends/{detail_id}")
    assert detail.status_code == 200
    assert detail.json()["source_url"] == "https://x.com/OpenAI/status/4242"
    assert (
        detail.json()["summary"]
        == "A high-signal X post about agent payment infrastructure."
    )

    missing = synced_client.get("/api/social/trends/999999")
    assert missing.status_code == 404


def test_repost_candidate_quote_publish_creates_human_gated_x_post(
    monkeypatch, synced_client, db_session
):
    captured: dict[str, str] = {}

    def fake_publish(account, body_text, media_ids=None):
        captured["handle"] = account.handle
        captured["body_text"] = body_text
        return social_publishing.XPublishResult(
            post_id="1800000000000000031",
            response_summary={"data": {"id": "1800000000000000031"}},
        )

    monkeypatch.setattr(social_publishing.x_publisher, "publish_text", fake_publish)
    candidate = SocialRepostCandidateRow(
        platform="x",
        source_url="https://x.com/OpenAI/status/100",
        author_handle="OpenAI",
        source_text="AI agents increasingly need reliable tool access and payment primitives.",
        suggested_quote="This is exactly why agent-native payment rails matter: builders need budgeted API access without manual billing glue.",
        relevance_score=0.91,
        status="candidate",
    )
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)

    response = synced_client.post(
        f"/api/social/repost-candidates/{candidate.id}/publish-x",
        json={"actor": "operator", "action": "quote"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert captured["handle"] == "SynapseNetworkA"
    assert "agent-native payment rails matter" in captured["body_text"]
    assert "https://x.com/OpenAI/status/100" in captured["body_text"]
    post = (
        db_session.query(SocialPostDraftRow)
        .filter(SocialPostDraftRow.source_type == "repost_candidate")
        .one()
    )
    assert post.status == "published"
    assert post.reviewed_by == "operator"
    raw = social_publishing._json_loads(post.raw_agent_output_json, {})
    assert raw["repost_candidate_id"] == candidate.id
    assert raw["repost_action"] == "quote"
