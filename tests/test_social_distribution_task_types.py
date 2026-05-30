import json

from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionDocumentRow,
)
from server.services.social.agent_content_pack import CanonicalArticleExpansion
from server.services.social.distribution_projection import _json_object
from tests.social_distribution_helpers import patch_agent_distribution


def _patch_agent_distribution(monkeypatch):
    patch_agent_distribution(monkeypatch)

    def fake_canonical_article_expansion(**kwargs):
        return CanonicalArticleExpansion(
            title=f"Canonical article: {kwargs['asset_title']}",
            summary=f"Expanded summary for {kwargs['asset_title']}",
            body_markdown=f"# {kwargs['asset_title']}\n\nConcrete details.",
            key_facts=["density-driven canonical article"],
            generation_reason="fake expansion for tests",
            metadata={"provider": "test"},
        )

    monkeypatch.setattr(
        "server.services.social.distribution_documents.generate_canonical_article_expansion",
        fake_canonical_article_expansion,
    )


def _add_approved_canonical_article(db_session, asset_id: int):
    doc = SocialDistributionDocumentRow(
        asset_id=asset_id,
        document_kind="canonical_article",
        title="Approved canonical article",
        body_markdown="# Approved canonical article\n\nA complete mother draft.",
        status="approved",
        version=1,
        metadata_json='{"generated_by":"asset_expansion_agent_v1"}',
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def test_create_x_article_pack_task_locks_channel_to_x(synced_client):
    response = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={
            "title": "Synapse Network: Payment Rails for AI Agents",
            "task_type": "x_article_pack",
            "source_material": "Explain Synapse as payment rails for AI agents.",
            "target_platforms": ["x"],
        },
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["agent_metadata"]["task_type"] == "x_article_pack"
    assert payload["agent_metadata"]["channel_selection_mode"] == "locked_x"
    assert payload["agent_metadata"]["target_platforms"] == ["x"]


def test_create_content_task_reuses_existing_non_terminal_asset(synced_client):
    request = {
        "title": "Synapse Network: Payment Rails for AI Agents",
        "task_type": "x_article_pack",
        "source_material": "Explain Synapse as payment rails for AI agents.",
        "target_platforms": ["x"],
    }
    first = synced_client.post("/api/social/distribution/content-tasks", json=request)
    second = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={**request, "title": "  synapse   network: payment rails for ai agents  "},
    )

    assert first.status_code == 200, first.json()
    assert second.status_code == 200, second.json()
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["agent_metadata"]["reused_existing"] is True


def test_create_content_task_allows_same_title_for_different_task_type(synced_client):
    title = "Synapse Network: Payment Rails for AI Agents"
    article = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={"title": title, "task_type": "x_article_pack", "target_platforms": ["x"]},
    )
    media = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={"title": title, "task_type": "x_media_post", "target_platforms": ["x"]},
    )

    assert article.status_code == 200, article.json()
    assert media.status_code == 200, media.json()
    assert article.json()["id"] != media.json()["id"]


def test_create_content_task_allows_same_title_for_different_campaign(synced_client):
    title = "Campaign-scoped Synapse article"
    first = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={
            "title": title,
            "task_type": "x_article_pack",
            "campaign_key": "week_1",
            "target_platforms": ["x"],
        },
    )
    second = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={
            "title": title,
            "task_type": "x_article_pack",
            "campaign_key": "week_2",
            "target_platforms": ["x"],
        },
    )

    assert first.status_code == 200, first.json()
    assert second.status_code == 200, second.json()
    assert first.json()["id"] != second.json()["id"]


def test_archived_duplicate_does_not_block_new_content_task(synced_client, db_session):
    request = {
        "title": "Archive duplicate then recreate",
        "task_type": "x_article_pack",
        "target_platforms": ["x"],
    }
    first = synced_client.post("/api/social/distribution/content-tasks", json=request)
    row = db_session.get(SocialContentAssetRow, first.json()["id"])
    row.status = "archived"
    metadata = _json_object(row.agent_metadata_json)
    metadata["archive_reason"] = "archived_duplicate"
    row.agent_metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    db_session.commit()

    second = synced_client.post("/api/social/distribution/content-tasks", json=request)

    assert second.status_code == 200, second.json()
    assert second.json()["id"] != first.json()["id"]
    assert second.json()["agent_metadata"]["reused_existing"] is False


def test_x_only_content_task_rejects_non_x_channels(synced_client):
    response = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={
            "title": "X-only content should not fan out",
            "task_type": "x_media_post",
            "source_material": "Short X media post.",
            "target_platforms": ["x", "devto"],
        },
    )

    assert response.status_code == 400
    assert "X-only" in response.json()["detail"]


def test_x_media_post_approve_generates_only_x_task(
    synced_client, db_session, monkeypatch
):
    _patch_agent_distribution(monkeypatch)
    created = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={
            "title": "X media post about agent receipts",
            "task_type": "x_media_post",
            "source_material": "Agents need receipts after paid API calls.",
            "target_platforms": ["x"],
        },
    ).json()
    _add_approved_canonical_article(db_session, created["id"])
    synced_client.get("/api/social/distribution/accounts")

    response = synced_client.post(
        f"/api/social/distribution/assets/{created['id']}/approve-and-generate-tasks",
        json={"account_ids": [], "actor": "operator"},
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert [result["platform"] for result in payload["results"]] == ["x"]
    assert payload["asset"]["agent_metadata"]["task_type"] == "x_media_post"
