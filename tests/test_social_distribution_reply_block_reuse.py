import json

from server.database import SocialReplyItemRow, SocialTrendItemRow
from server.database_social_distribution import SocialContentAssetRow
from server.services.social import publishing as social_publishing
from server.services.social import distribution_reply_block_policy as reply_block_policy
from server.services.social.reply_agent import GeneratedXReply


def _reply_asset():
    return SocialContentAssetRow(
        asset_type="reply",
        source_type="manual_task",
        title="X Week 1 Reply Block Day 5",
        body="Generate value-add reply drafts only.",
        summary="X reply block",
        status="draft",
        created_by="operator",
        agent_metadata_json=json.dumps(
            {
                "post_intent": "engagement_reply",
                "target_platforms": ["x"],
                "planned_publish_at": "2026-05-01T00:00:00+00:00",
            },
            sort_keys=True,
        ),
    )


def _install_reply_agent(monkeypatch):
    def fake_generate(candidate, **_kwargs):
        return GeneratedXReply(
            suggested_reply=(
                f"Useful angle from @{candidate.author_handle}: agent tools need governed access, "
                "budget controls, and receipts when APIs become paid actions."
            ),
            risk_level="normal",
            rationale="Specific, constructive, and avoids engagement bait.",
            model="test-reply-model",
            generation_metadata={"provider": "test", "model": "test-reply-model"},
        )

    monkeypatch.setattr(
        social_publishing, "generate_x_reply_for_candidate", fake_generate
    )


def test_generate_x_reply_block_reuses_other_assets_sources_when_inventory_exhausted(
    synced_client, db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    monkeypatch.setattr(
        reply_block_policy.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: social_publishing.XOAuth2AccessToken(
            "access-token", refreshed=False
        ),
    )
    asset = _reply_asset()
    db_session.add(asset)
    db_session.flush()
    for index in range(1, 6):
        post_id = f"{asset.id}730{index}"
        db_session.add(
            SocialTrendItemRow(
                source_platform="x",
                source_url=f"https://x.com/x402/status/{post_id}",
                author_handle="x402",
                topic=f"Used elsewhere agent payment source {index}",
                summary=(
                    "Agent payments, x402, API metering, and settlement rails "
                    "for autonomous workflows."
                ),
                relevance_score=1.0 - (index * 0.01),
                status="new",
            )
        )
        db_session.add(
            SocialReplyItemRow(
                external_reply_id=f"other-asset:{asset.id}:{post_id}",
                source_post_id=post_id,
                source_url=f"https://x.com/x402/status/{post_id}",
                source_author_handle="x402",
                source_text="Already drafted by another reply block.",
                author_handle="x402",
                incoming_text="Already drafted by another reply block.",
                suggested_reply="Existing draft from another asset.",
                status="published_manual",
            )
        )
    db_session.commit()
    db_session.refresh(asset)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={"actor": "agent", "target_count": 5, "agent_review": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["reply_ids"]) == 5
    generated = (
        db_session.query(SocialReplyItemRow)
        .filter(SocialReplyItemRow.id.in_(payload["reply_ids"]))
        .order_by(SocialReplyItemRow.id)
        .all()
    )
    assert len(generated) == 5
    assert {reply.status for reply in generated} == {
        "agent_approved_needs_manual_publish"
    }
    assert {reply.source_author_handle for reply in generated} == {"x402"}
