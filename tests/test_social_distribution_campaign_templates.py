from server.database_social_distribution import SocialContentAssetRow
from server.services.social.distribution_projection import _json_object


def test_create_x_brand_week_campaign_template_is_idempotent(synced_client, db_session):
    first = synced_client.post(
        "/api/social/distribution/campaign-templates/x-brand-week-technical-builders"
    )
    second = synced_client.post(
        "/api/social/distribution/campaign-templates/x-brand-week-technical-builders"
    )

    assert first.status_code == 200
    assert first.json()["campaign_key"] == "x_brand_awareness_week_1"
    assert first.json()["created_count"] == 12
    assert first.json()["existing_count"] == 0
    assert second.status_code == 200
    assert second.json()["created_count"] == 0
    assert second.json()["existing_count"] == 12
    assets = (
        db_session.query(SocialContentAssetRow)
        .filter(SocialContentAssetRow.goal_key == "x_brand_awareness_week_1")
        .order_by(SocialContentAssetRow.title)
        .all()
    )
    assert len(assets) == 12
    metadata = [_json_object(asset.agent_metadata_json) for asset in assets]
    assert all(row["target_platforms"] == ["x"] for row in metadata)
    assert {row["campaign_key"] for row in metadata} == {"x_brand_awareness_week_1"}
    assert {row["post_intent"] for row in metadata} >= {
        "brand_positioning",
        "technical_explainer",
        "build_in_public",
        "weekly_log",
        "engagement_reply",
    }
    assert all("planned_publish_at" in row for row in metadata)
