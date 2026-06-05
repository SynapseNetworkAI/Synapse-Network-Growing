import json

from server import config
from server.database import SocialReplyItemRow, SocialTrendItemRow
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionEventRow,
)
from server.routers import social_distribution as social_distribution_router
from server.services.social import publishing as social_publishing
from server.services.social import distribution_reply_blocks as reply_blocks
from server.services.social import distribution_reply_block_policy as reply_block_policy
from server.services.social.distribution import get_content_asset
from server.services.social.distribution_reply_block_publisher import (
    run_x_social_daily_reply_block_publisher,
)
from server.services.social.reply_agent import GeneratedXReply


def _reply_asset(**metadata):
    payload = {
        "post_intent": "engagement_reply",
        "target_platforms": ["x"],
        "planned_publish_at": "2026-05-01T00:00:00+00:00",
        **metadata,
    }
    return SocialContentAssetRow(
        asset_type="reply",
        source_type="manual_task",
        title="X Week 1 Reply Block Day 5",
        body="Generate value-add reply drafts only.",
        summary="X reply block",
        status="draft",
        created_by="operator",
        agent_metadata_json=json.dumps(payload, sort_keys=True),
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


def test_generate_x_reply_block_creates_agent_reviewed_candidates(
    synced_client, db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={
            "actor": "agent",
            "target_count": 2,
            "agent_review": True,
            "source_posts": [
                {
                    "source_url": "https://x.com/OpenAI/status/101",
                    "author_handle": "OpenAI",
                    "source_text": "Tool-using AI agents need safer paid API access with spend control and receipts.",
                    "rationale": "Agent infrastructure topic.",
                },
                {
                    "source_url": "https://x.com/LangChainAI/status/102",
                    "author_handle": "LangChainAI",
                    "source_text": "Agent workflows increasingly connect to paid tools and need API metering.",
                    "rationale": "Workflow monetization topic.",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply_ids"]
    assert len(payload["reply_ids"]) == 2
    assert payload["failed_reply_ids"] == []
    assert payload["auto_publish"] is False
    assert payload["publish_mode"] == "agent_approved_needs_manual_publish"
    assert len(payload["asset"]["reply_items"]) == 2
    assert payload["asset"]["reply_items"][0]["source_post_id"] == "101"
    assert payload["asset"]["reply_items"][0]["suggested_reply"]
    assert (
        payload["asset"]["reply_items"][0]["metadata"]["agent_quality_review"]["status"]
        == "passed"
    )
    replies = db_session.query(SocialReplyItemRow).order_by(SocialReplyItemRow.id).all()
    assert [reply.status for reply in replies] == [
        "agent_approved_needs_manual_publish",
        "agent_approved_needs_manual_publish",
    ]
    assert replies[0].reviewed_by == "agent"
    assert "Great point" not in replies[0].suggested_reply
    assert "http://" not in replies[0].suggested_reply
    assert "https://" not in replies[0].suggested_reply
    assert replies[0].source_url == "https://x.com/OpenAI/status/101"
    metadata = json.loads(replies[0].metadata_json)
    assert metadata["agent_quality_review"]["status"] == "passed"
    db_session.refresh(asset)
    asset_metadata = json.loads(asset.agent_metadata_json)
    assert asset_metadata["reply_block"]["auto_publish"] is False
    assert (
        asset_metadata["reply_block"]["publish_mode"]
        == "agent_approved_needs_manual_publish"
    )
    assert (
        db_session.query(SocialDistributionEventRow)
        .filter_by(event_type="x_reply_block_candidates_generated")
        .count()
        == 1
    )

    detail_response = synced_client.get(f"/api/social/distribution/assets/{asset.id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert [reply["source_post_id"] for reply in detail["reply_items"]] == [
        "101",
        "102",
    ]


def test_generate_x_reply_block_uses_long_default_runtime_budget(
    synced_client, db_session, monkeypatch
):
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    captured: dict[str, object] = {}

    def fake_generate(db, **kwargs):
        captured.update(kwargs)
        return {
            "asset": get_content_asset(db, int(kwargs["asset_id"])),
            "reply_ids": [],
            "failed_reply_ids": [],
            "source_candidate_ids": [],
            "processed_source_count": 0,
            "auto_publish": False,
            "agent_review": True,
            "timed_out": False,
            "blocked_reason": None,
            "publish_mode": "agent_approved_needs_manual_publish",
            "approval_ref_configured": False,
        }

    monkeypatch.setattr(
        social_distribution_router,
        "generate_x_reply_block_candidates",
        fake_generate,
    )

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={"actor": "agent", "target_count": 5, "agent_review": True},
    )

    assert response.status_code == 200
    assert captured["max_seconds"] == reply_blocks.DEFAULT_REPLY_BLOCK_MAX_SECONDS
    assert (
        captured["per_reply_timeout_seconds"]
        == reply_blocks.DEFAULT_REPLY_BLOCK_PER_REPLY_TIMEOUT_SECONDS
    )


def test_generate_x_reply_block_strips_urls_from_reply_text(
    synced_client, db_session, monkeypatch
):
    def fake_generate(candidate, **_kwargs):
        return GeneratedXReply(
            suggested_reply=(
                "Agent monetization needs spend caps, receipts, and settlement rails. "
                "Implementation notes: https://www.synapse-network.ai/docs"
            ),
            risk_level="normal",
            rationale="URL should be stripped before review.",
            model="test-reply-model",
            generation_metadata={"provider": "test", "model": "test-reply-model"},
        )

    monkeypatch.setattr(
        social_publishing, "generate_x_reply_for_candidate", fake_generate
    )
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={
            "actor": "agent",
            "target_count": 1,
            "agent_review": True,
            "source_posts": [
                {
                    "source_url": "https://x.com/OpenAI/status/555",
                    "author_handle": "OpenAI",
                    "source_text": "How should AI agents handle payments, API pricing, and spend control without giving them unlimited credentials?",
                    "rationale": "Direct agent spend-control pain.",
                }
            ],
        },
    )

    assert response.status_code == 200
    reply = db_session.query(SocialReplyItemRow).one()
    assert reply.source_url == "https://x.com/OpenAI/status/555"
    assert "http://" not in reply.suggested_reply
    assert "https://" not in reply.suggested_reply
    assert "Implementation notes" in reply.suggested_reply


def test_generate_x_reply_block_requires_force_when_candidates_exist(
    synced_client, db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    payload = {
        "actor": "agent",
        "target_count": 1,
        "agent_review": True,
        "source_posts": [
            {
                "source_url": "https://x.com/OpenAI/status/556",
                "author_handle": "OpenAI",
                "source_text": "Agent APIs need budget caps and receipts.",
                "rationale": "Duplicate generation guard.",
            }
        ],
    }

    first = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json=payload,
    )
    assert first.status_code == 200
    duplicate = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json=payload,
    )
    assert duplicate.status_code == 400
    assert "force_regenerate=true" in duplicate.json()["detail"]

    forced = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={**payload, "force_regenerate": True},
    )

    assert forced.status_code == 200
    assert forced.json()["reply_ids"] == first.json()["reply_ids"]
    event_types = [
        row.event_type
        for row in db_session.query(SocialDistributionEventRow)
        .order_by(SocialDistributionEventRow.id)
        .all()
    ]
    assert event_types == [
        "x_reply_block_candidates_generated",
        "x_reply_block_regenerated",
    ]


def test_generate_x_reply_block_fails_closed_without_real_sources(
    synced_client, db_session
):
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={"actor": "agent", "target_count": 5, "source_posts": []},
    )

    assert response.status_code == 400
    assert "Reconnect X before syncing trend/radar sources" in response.json()["detail"]
    assert db_session.query(SocialReplyItemRow).count() == 0
    event = db_session.query(SocialDistributionEventRow).one()
    assert event.event_type == "x_source_sync_blocked"
    payload = json.loads(event.payload_json)
    assert payload["oauth_status"] in {
        "missing_local_secret",
        "invalid_refresh_token",
        "needs_authorization",
        "error",
    }


def test_generate_x_reply_block_missing_client_config_has_bounded_error(
    synced_client, db_session, monkeypatch
):
    monkeypatch.setattr(
        reply_block_policy.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError(
                "X_OAUTH_CLIENT_ID is required in local environment configuration."
            )
        ),
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
    assert "X OAuth client configuration missing" in response.json()["detail"]
    event = db_session.query(SocialDistributionEventRow).one()
    assert event.event_type == "x_source_sync_blocked"
    payload = json.loads(event.payload_json)
    assert payload["oauth_status"] == "missing_client_config"


def test_generate_x_reply_block_selects_agent_economy_sources_from_trends(
    synced_client, db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    monkeypatch.setattr(
        reply_block_policy.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: social_publishing.XOAuth2AccessToken(
            "access-token", refreshed=True
        ),
    )
    asset = _reply_asset()
    db_session.add(asset)
    for index in range(1, 11):
        if index <= 5:
            topic = f"Agent payment pain {index}"
            summary = (
                "How should an AI agent pay for paid APIs without handing it an unlimited "
                "credit card? We need API pricing, spend control, receipts, and provider "
                "metering before this is safe for builders."
            )
            score = 0.95 - (index * 0.01)
        else:
            topic = f"Generic AI launch {index}"
            summary = "Launching today with a giveaway and broad AI news, but no technical payment or spend-control context."
            score = 0.94 - (index * 0.01)
        db_session.add(
            SocialTrendItemRow(
                source_platform="x",
                source_url=f"https://x.com/builder{index}/status/{800 + index}",
                author_handle=f"builder{index}",
                topic=topic,
                summary=summary,
                relevance_score=score,
                status="new",
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
    replies = db_session.query(SocialReplyItemRow).order_by(SocialReplyItemRow.id).all()
    assert len(replies) == 5
    for reply in replies:
        metadata = json.loads(reply.metadata_json)
        strategy = metadata["x_reply_source_strategy"]
        assert strategy["strategy"] == "agent_economy_monetization"
        assert strategy["source_bucket"] == "direct_pain"
        assert strategy["reply_angle"] in {
            "budget_cap",
            "per_call_settlement",
            "receipt_evidence",
            "api_metering",
        }
        assert strategy["selected"] is True
        assert not strategy["do_not_reply_reason"]
    rejected = (
        db_session.query(SocialTrendItemRow)
        .filter(SocialTrendItemRow.topic.like("Generic AI launch%"))
        .all()
    )
    assert rejected
    assert any(
        json.loads(row.metadata_json)["reply_source_strategy"]["do_not_reply_reason"]
        for row in rejected
    )


def test_generate_x_reply_block_selects_agentic_economy_payment_rail_posts(
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
    for index, text in enumerate(
        [
            "The agentic economy needs programmable, real-time rails for dynamic endpoints, microtransactions, and activity at machine scale.",
            "Financial rails built with agents as economic actors can let software pay for services without unlimited API keys.",
            "Developers building secure autonomous workflows need embedded wallets and stablecoin payments that stay scoped to the task.",
        ],
        start=1,
    ):
        db_session.add(
            SocialTrendItemRow(
                source_platform="x",
                source_url=f"https://x.com/circle/status/{910 + index}",
                author_handle="circle",
                topic=text,
                summary=f"{text} Source: X watchlist @circle.",
                relevance_score=0.95,
                status="new",
            )
        )
    db_session.commit()
    db_session.refresh(asset)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={"actor": "agent", "target_count": 3, "agent_review": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["reply_ids"]) == 3
    replies = db_session.query(SocialReplyItemRow).order_by(SocialReplyItemRow.id).all()
    assert len(replies) == 3
    for reply in replies:
        strategy = json.loads(reply.metadata_json)["x_reply_source_strategy"]
        assert strategy["source_bucket"] == "ecosystem_discussion"
        assert strategy["reply_angle"] in {
            "agent_economy_context",
            "api_metering",
            "governed_access",
        }
        assert strategy["selected"] is True
        assert strategy["do_not_reply_reason"] is None


def test_generate_x_reply_block_skips_existing_sources_and_selects_agent_infra_posts(
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
    for index in range(1, 6):
        post_id = f"710{index}"
        db_session.add(
            SocialTrendItemRow(
                source_platform="x",
                source_url=f"https://x.com/x402/status/{post_id}",
                author_handle="x402",
                topic=f"Existing agent payment source {index}",
                summary="Agent payments, x402, API metering, and settlement rails for autonomous workflows.",
                relevance_score=1.0 - (index * 0.01),
                status="new",
            )
        )
        db_session.add(
            SocialReplyItemRow(
                external_reply_id=f"target:{post_id}",
                source_post_id=post_id,
                source_url=f"https://x.com/x402/status/{post_id}",
                source_author_handle="x402",
                source_text="Already drafted source.",
                author_handle="x402",
                incoming_text="Already drafted source.",
                suggested_reply="Existing draft.",
                status="agent_approved_needs_manual_publish",
            )
        )
    for index, text in enumerate(
        [
            "Getting an agent running now means choosing a runtime, inference backend, and tool-use stack.",
            "Agent skills and modular architecture make video search workflows easier to operate.",
            "OpenRouter, Vercel AI Gateway, Cursor, and Kilo Code are becoming a practical agent toolchain.",
            "The access and permissions granted to agents should evolve with external API workflows.",
            "Computer use for coding agents makes governed tool access more important.",
        ],
        start=1,
    ):
        db_session.add(
            SocialTrendItemRow(
                source_platform="x",
                source_url=f"https://x.com/agentinfra/status/720{index}",
                author_handle="agentinfra",
                topic=f"Agent infrastructure source {index}",
                summary=f"{text} Source: X watchlist @agentinfra.",
                relevance_score=0.9 - (index * 0.01),
                status="new",
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
    replies = db_session.query(SocialReplyItemRow).order_by(SocialReplyItemRow.id).all()
    generated = [
        reply for reply in replies if reply.source_author_handle == "agentinfra"
    ]
    assert len(generated) == 5
    for reply in generated:
        strategy = json.loads(reply.metadata_json)["x_reply_source_strategy"]
        assert strategy["source_bucket"] == "agent_infrastructure_signal"
        assert strategy["selected"] is True
        assert strategy["do_not_reply_reason"] is None


def test_generate_x_reply_block_rejects_generic_or_unsafe_sources(
    synced_client, db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={
            "actor": "agent",
            "target_count": 2,
            "source_posts": [
                {
                    "source_url": "https://x.com/hype/status/901",
                    "author_handle": "hype",
                    "source_text": "Launching today. Sign up now for a giveaway.",
                    "rationale": "Generic promotion.",
                },
                {
                    "source_url": "https://x.com/coin/status/902",
                    "author_handle": "coin",
                    "source_text": "Token price pump incoming. Trading signal for AI coin.",
                    "rationale": "Unsafe crypto promo.",
                },
            ],
        },
    )

    assert response.status_code == 400
    assert "requires real X source posts" in response.json()["detail"]
    assert db_session.query(SocialReplyItemRow).count() == 0


def test_generate_x_reply_block_timeout_fails_closed(
    synced_client, db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    ticks = iter([0.0, 2.0])
    monkeypatch.setattr(reply_blocks, "_monotonic_seconds", lambda: next(ticks, 2.0))
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={
            "actor": "agent",
            "target_count": 1,
            "max_seconds": 1,
            "source_posts": [
                {
                    "source_url": "https://x.com/OpenAI/status/103",
                    "author_handle": "OpenAI",
                    "source_text": "Agent workflows should stay bounded with budget caps for paid API calls.",
                    "rationale": "Timeout coverage.",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["timed_out"] is True
    assert payload["reply_ids"] == []
    assert "x_reply_block_generation_timeout" in payload["blocked_reason"]
    db_session.refresh(asset)
    assert asset.status == "failed"
    assert db_session.query(SocialReplyItemRow).count() == 0
    assert (
        db_session.query(SocialDistributionEventRow)
        .filter_by(event_type="x_reply_block_generation_timeout")
        .count()
        == 1
    )


def test_generate_x_reply_block_rejects_article_assets(synced_client, db_session):
    asset = SocialContentAssetRow(
        asset_type="article",
        source_type="manual_task",
        title="Long-form article",
        status="draft",
        created_by="operator",
        agent_metadata_json='{"target_platforms":["x","devto"]}',
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={"actor": "agent"},
    )

    assert response.status_code == 400
    assert "not an X engagement reply task" in response.json()["detail"]


def test_reply_block_board_uses_x_reply_task_kind(synced_client, db_session):
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()

    response = synced_client.get("/api/social/distribution/board")

    assert response.status_code == 200
    columns = {column["key"]: column for column in response.json()["columns"]}
    card = columns["needs_review"]["cards"][0]
    assert card["task_kind_code"] == "x_reply_block"
    assert card["task_kind_action"] == "generate_x_reply_candidates"
    assert "X 回复候选" in card["next_action"]


def test_reply_block_board_moves_generated_candidates_to_ready_to_publish(
    synced_client, db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={
            "actor": "agent",
            "target_count": 1,
            "agent_review": True,
            "source_posts": [
                {
                    "source_url": "https://x.com/OpenAI/status/501",
                    "author_handle": "OpenAI",
                    "source_text": "Agents need high-signal operating loops and spend control before calling paid tools.",
                    "rationale": "Reply board projection coverage.",
                },
            ],
        },
    )
    assert response.status_code == 200

    board = synced_client.get("/api/social/distribution/board").json()
    ready_column = {column["key"]: column for column in board["columns"]}[
        "ready_to_publish"
    ]
    card = ready_column["cards"][0]
    assert card["asset"]["id"] == asset.id
    assert card["task_kind_code"] == "x_reply_block"
    assert card["ready_to_publish_count"] == 1
    assert card["status_counts"]["agent_approved_needs_manual_publish"] == 1


def test_reply_block_board_moves_published_manual_reply_to_live(
    synced_client, db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={
            "actor": "agent",
            "target_count": 1,
            "agent_review": True,
            "source_posts": [
                {
                    "source_url": "https://x.com/OpenAI/status/502",
                    "author_handle": "OpenAI",
                    "source_text": "Agent workflows need receipts.",
                    "rationale": "Live board projection coverage.",
                },
            ],
        },
    ).json()
    reply_id = generated["reply_ids"][0]

    update = synced_client.patch(
        f"/api/social/replies/{reply_id}",
        json={"status": "published_manual", "reviewed_by": "operator"},
    )
    assert update.status_code == 200

    board = synced_client.get("/api/social/distribution/board").json()
    live_column = {column["key"]: column for column in board["columns"]}["live"]
    card = live_column["cards"][0]
    assert card["asset"]["id"] == asset.id
    assert card["live_count"] == 1
    assert card["status_counts"]["published_manual"] == 1


def test_daily_reply_block_workflow_queues_candidates_without_auto_publish(
    db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    asset = _reply_asset()
    asset.body = (
        "https://x.com/OpenAI/status/201 Tool calls need governed external API access."
    )
    db_session.add(asset)
    db_session.commit()

    result = run_x_social_daily_reply_block_publisher(db_session)

    assert result["processed"] is True
    assert result["asset_id"] == asset.id
    assert result["auto_publish"] is False
    reply = db_session.query(SocialReplyItemRow).one()
    assert reply.status == "agent_approved_needs_manual_publish"
    assert reply.published_external_post_id is None


def test_x_reply_block_auto_publish_requires_opt_in_evidence(
    synced_client, db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    monkeypatch.setattr(config, "X_AI_REPLY_APPROVAL_REF", "x-approval-2026-05")
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={
            "actor": "agent",
            "target_count": 1,
            "auto_publish": True,
            "source_posts": [
                {
                    "source_url": "https://x.com/OpenAI/status/301",
                    "author_handle": "OpenAI",
                    "source_text": "Agent workflows need policy gates, budget caps, and receipts for paid API calls.",
                    "rationale": "Compliance coverage.",
                }
            ],
        },
    )

    assert response.status_code == 400
    assert "opt_in_evidence" in response.json()["detail"]
    assert db_session.query(SocialReplyItemRow).count() == 0


def test_x_reply_block_auto_publish_uses_api_when_approval_and_opt_in_exist(
    synced_client, db_session, monkeypatch
):
    _install_reply_agent(monkeypatch)
    monkeypatch.setattr(config, "X_AI_REPLY_APPROVAL_REF", "x-approval-2026-05")
    asset = _reply_asset()
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    def fake_publish(db, reply_id, body):
        row = db.get(SocialReplyItemRow, reply_id)
        row.status = "published"
        row.published_external_post_id = f"x-reply-{reply_id}"
        row.external_reply_id = f"x-reply-{reply_id}"
        db.commit()
        db.refresh(row)
        return social_publishing._social_reply_out(row)

    monkeypatch.setattr(reply_blocks, "publish_social_reply_to_x", fake_publish)

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset.id}/generate-x-reply-block",
        json={
            "actor": "agent",
            "target_count": 1,
            "auto_publish": True,
            "source_posts": [
                {
                    "source_url": "https://x.com/OpenAI/status/302",
                    "author_handle": "OpenAI",
                    "source_text": "Agent workflows need policy gates, budget caps, and receipts for paid API calls.",
                    "rationale": "Compliance coverage.",
                    "opt_in_evidence": "Campaign partner opted in to AI-assisted replies.",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["auto_publish"] is True
    assert payload["publish_mode"] == "approved"
    reply = db_session.query(SocialReplyItemRow).one()
    assert reply.status == "published"
    assert reply.published_external_post_id == f"x-reply-{reply.id}"
