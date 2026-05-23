import json

from server import config
from server.database import SocialReplyItemRow
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionEventRow,
)
from server.services.social import publishing as social_publishing
from server.services.social import distribution_reply_blocks as reply_blocks
from server.services.social.distribution_reply_blocks import (
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
                    "source_text": "Tool-using agents need safer ways to call external APIs.",
                    "rationale": "Agent infrastructure topic.",
                },
                {
                    "source_url": "https://x.com/LangChainAI/status/102",
                    "author_handle": "LangChainAI",
                    "source_text": "Agent workflows increasingly connect to paid tools and services.",
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
                    "source_text": "Agent workflows should stay bounded.",
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
                    "source_text": "Agents need high-signal operating loops.",
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
                    "source_text": "Agent workflows need policy gates.",
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
                    "source_text": "Agent workflows need policy gates.",
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
