from datetime import datetime, timezone

from server.database import SocialPostDraftRow, SocialPostMetricRow
from server.services.social import publishing as social_publishing


def test_social_post_metrics_daily_query_and_detail(synced_client, db_session):
    account = social_publishing.ensure_default_social_account(db_session)
    post = SocialPostDraftRow(
        platform="x",
        account_id=account.id,
        source_type="manual_prompt",
        title="Daily metric post",
        body_text="A public post with measurable engagement.",
        status="published",
        generated_by="operator",
        external_post_id="metric-post-1",
        published_at=datetime(2026, 4, 29, 16, 0, tzinfo=timezone.utc),
    )
    db_session.add(post)
    db_session.flush()
    db_session.add_all(
        [
            SocialPostMetricRow(
                post_id=post.id,
                external_post_id="metric-post-1",
                impressions=100,
                likes=10,
                replies=2,
                reposts=1,
                link_clicks=3,
                summary="Metric row inside Kuala Lumpur local day.",
                observed_at=datetime(2026, 4, 29, 16, 30, tzinfo=timezone.utc),
            ),
            SocialPostMetricRow(
                post_id=post.id,
                external_post_id="metric-post-1",
                impressions=50,
                likes=1,
                observed_at=datetime(2026, 4, 28, 10, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()

    daily = synced_client.get(
        "/api/social/post-metrics/daily?date_from=2026-04-30&date_to=2026-04-30"
    )
    assert daily.status_code == 200
    assert daily.json()["items"][0]["local_date"] == "2026-04-30"
    assert daily.json()["items"][0]["total_impressions"] == 100

    query = synced_client.get("/api/social/post-metrics/query?limit=1&offset=0")
    assert query.status_code == 200
    assert query.json()["total"] == 2
    metric_id = query.json()["items"][0]["id"]

    detail = synced_client.get(f"/api/social/post-metrics/{metric_id}")
    assert detail.status_code == 200
    assert detail.json()["post_title"] == "Daily metric post"
    assert (
        detail.json()["x_url"] == "https://x.com/SynapseNetworkA/status/metric-post-1"
    )
