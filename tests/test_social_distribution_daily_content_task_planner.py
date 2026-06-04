from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionDocumentRow,
    SocialDistributionTaskRow,
)
from server.services.result_objects import ServiceObjectResult
from server.services.social.agent_content_pack import CanonicalArticleExpansion
from server.services.social.daily_content_task_planner import (
    run_x_social_daily_content_task_planner,
)
from server.services.social.distribution_board import social_distribution_board
from server.services.social.distribution_projection import _json_object
from tests.social_distribution_helpers import patch_agent_distribution


def _patch_daily_task_agents(monkeypatch, tmp_path):
    patch_agent_distribution(monkeypatch)

    def fake_canonical_article_expansion(**kwargs):
        return CanonicalArticleExpansion(
            title=f"Canonical article: {kwargs['asset_title']}",
            summary="Synapse lets agents pay for APIs, data, and model calls with receipts.",
            body_markdown=(
                "# Synapse Network daily plan\n\n"
                "Synapse Network helps AI agents discover services, pay for API data "
                "and large-model calls with capped budgets, and gives providers a way "
                "to earn from metered agent usage."
            ),
            key_facts=[
                "agents can pay for API/data/model calls",
                "providers can earn from metered usage",
            ],
            generation_reason="fake expansion for daily content task tests",
            metadata={"provider": "test"},
        )

    monkeypatch.setattr(
        "server.services.social.distribution_documents.generate_canonical_article_expansion",
        fake_canonical_article_expansion,
    )
    monkeypatch.setattr(
        "server.services.social.distribution_article_packs.config.PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        "server.services.social.daily_content_task_planner.run_content_policy_check",
        lambda _text: ServiceObjectResult(
            {"status": "passed", "blocked_reasons": [], "warnings": []}
        ),
    )


def test_daily_x_content_task_planner_creates_article_and_media_to_ready_to_publish(
    synced_client, db_session, monkeypatch, tmp_path
):
    _patch_daily_task_agents(monkeypatch, tmp_path)

    response = synced_client.post(
        "/api/social/distribution/assets/plan-daily-x-content",
        json={
            "local_date": "2026-06-04",
            "strategy_key": "synapse-awareness",
            "strategy_summary": "Explain what Synapse does, how agents pay for APIs/data/models, and how providers earn.",
        },
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["workflow_key"] == "x_social_daily_content_task_planner"
    assert payload["target_task_types"] == ["x_article_pack", "x_media_post"]
    assert payload["created_asset_ids"]
    assert payload["auto_publish"] is False
    assert payload["human_gate_required"] is True
    assert {task["task_type"] for task in payload["tasks"]} == {
        "x_article_pack",
        "x_media_post",
    }
    assert {task["column_key"] for task in payload["tasks"]} == {"ready_to_publish"}
    assert all(task["ready_to_publish_count"] > 0 for task in payload["tasks"])

    db_session.expire_all()
    assets = (
        db_session.query(SocialContentAssetRow)
        .order_by(SocialContentAssetRow.id.asc())
        .all()
    )
    assert len(assets) == 2
    for asset in assets:
        metadata = _json_object(asset.agent_metadata_json)
        assert metadata["daily_content_task_planner"] is True
        assert metadata["daily_strategy_key"] == "synapse-awareness"
        assert metadata["daily_local_date"] == "2026-06-04"
        assert metadata["auto_publish"] is False
        assert metadata["human_gate_required"] is True
        assert asset.status == "ready"
        assert {
            document.document_kind
            for document in db_session.query(SocialDistributionDocumentRow)
            .filter_by(asset_id=asset.id)
            .all()
        } >= {"source_plan", "canonical_article", "platform_draft"}

    article = next(
        row
        for row in assets
        if _json_object(row.agent_metadata_json)["task_type"] == "x_article_pack"
    )
    article_tasks = (
        db_session.query(SocialDistributionTaskRow)
        .filter_by(asset_id=article.id)
        .order_by(SocialDistributionTaskRow.action.asc())
        .all()
    )
    assert {task.action for task in article_tasks} == {
        "x_article_manual_publish",
        "x_article_teaser",
    }
    assert any(task.status == "needs_manual_article_publish" for task in article_tasks)
    assert any(task.status == "approved" for task in article_tasks)

    media = next(
        row
        for row in assets
        if _json_object(row.agent_metadata_json)["task_type"] == "x_media_post"
    )
    media_tasks = (
        db_session.query(SocialDistributionTaskRow).filter_by(asset_id=media.id).all()
    )
    assert len(media_tasks) == 1
    assert media_tasks[0].platform == "x"
    assert media_tasks[0].status == "approved"
    assert "agent_review" in _json_object(media_tasks[0].metadata_json)

    board = social_distribution_board(db_session)
    ready_cards = board.columns[2].cards
    assert {card.task_kind_code for card in ready_cards} >= {
        "x_article_pack",
        "x_media_post",
    }


def test_daily_x_content_task_planner_is_idempotent_for_same_strategy_day(
    db_session, monkeypatch, tmp_path
):
    _patch_daily_task_agents(monkeypatch, tmp_path)

    first = run_x_social_daily_content_task_planner(
        db_session,
        strategy_key="synapse-awareness",
        local_date="2026-06-04",
    )
    article_doc_versions = {
        int(row.id): int(row.version or 1)
        for row in db_session.query(SocialDistributionDocumentRow)
        .filter(SocialDistributionDocumentRow.document_kind == "x_article_pack")
        .all()
    }
    second = run_x_social_daily_content_task_planner(
        db_session,
        strategy_key="synapse-awareness",
        local_date="2026-06-04",
    )

    assert first.created_asset_ids
    assert second.created_asset_ids == []
    assert set(second.existing_asset_ids) == set(first.created_asset_ids)
    assert all(task.reused_existing for task in second.tasks)
    assert db_session.query(SocialContentAssetRow).count() == 2
    assert db_session.query(SocialDistributionTaskRow).count() == 3
    assert article_doc_versions == {
        int(row.id): int(row.version or 1)
        for row in db_session.query(SocialDistributionDocumentRow)
        .filter(SocialDistributionDocumentRow.document_kind == "x_article_pack")
        .all()
    }


def test_daily_x_content_task_agent_review_blocks_to_human_review(
    db_session, monkeypatch, tmp_path
):
    _patch_daily_task_agents(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "server.services.social.daily_content_task_planner.run_content_policy_check",
        lambda _text: ServiceObjectResult(
            {
                "status": "blocked",
                "blocked_reasons": ["unsafe_financial_claim"],
                "warnings": [],
            }
        ),
    )

    result = run_x_social_daily_content_task_planner(
        db_session,
        strategy_key="synapse-awareness",
        local_date="2026-06-04",
    )

    assert {task.stage for task in result.tasks} == {"needs_human_review"}
    assert all(task.blocker == "agent_review_policy_blocked" for task in result.tasks)
    assert db_session.query(SocialDistributionTaskRow).count() == 0
    docs = db_session.query(SocialDistributionDocumentRow).all()
    canonical_docs = [doc for doc in docs if doc.document_kind == "canonical_article"]
    assert canonical_docs
    assert {doc.status for doc in canonical_docs} == {"needs_review"}
