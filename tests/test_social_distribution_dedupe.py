import json

from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionAccountRow,
    SocialDistributionDocumentRow,
    SocialDistributionEventRow,
    SocialDistributionTaskRow,
)
from server.services.social.distribution_dedupe import (
    DuplicateArchiveOptions,
    archive_duplicate_content_tasks,
)
from server.services.social.distribution_projection import _json_object


CONTENT_TASK_KEY = "x_article_pack|synapse network: payment rails for ai agents||"


def test_archive_duplicate_content_tasks_dry_run_does_not_mutate(db_session):
    keeper, duplicate = _seed_duplicate_pair(db_session)

    result = archive_duplicate_content_tasks(
        db_session,
        DuplicateArchiveOptions(
            dry_run=True,
            title="Synapse Network: Payment Rails for AI Agents",
            task_type="x_article_pack",
        ),
    )

    db_session.refresh(keeper)
    db_session.refresh(duplicate)
    assert result.dry_run is True
    assert result.archived_count == 1
    assert result.groups[0].keeper_id == keeper.id
    assert result.groups[0].duplicate_ids == [duplicate.id]
    assert duplicate.status == "ready"
    assert db_session.query(SocialDistributionEventRow).count() == 0


def test_archive_duplicate_content_tasks_apply_writes_metadata_and_event(db_session):
    keeper, duplicate = _seed_duplicate_pair(db_session)

    result = archive_duplicate_content_tasks(
        db_session,
        DuplicateArchiveOptions(
            dry_run=False,
            title="Synapse Network: Payment Rails for AI Agents",
            task_type="x_article_pack",
            actor="operator",
        ),
    )

    db_session.refresh(duplicate)
    metadata = _json_object(duplicate.agent_metadata_json)
    event = db_session.query(SocialDistributionEventRow).one()
    assert result.archived_count == 1
    assert duplicate.status == "archived"
    assert metadata["archive_reason"] == "archived_duplicate"
    assert metadata["duplicate_of_asset_id"] == keeper.id
    assert metadata["archived_by"] == "operator"
    assert metadata["archived_at"]
    assert event.asset_id == duplicate.id
    assert event.event_type == "content_task_archived_duplicate"


def test_archive_duplicate_content_tasks_skips_published_duplicate(db_session):
    keeper, duplicate = _seed_duplicate_pair(db_session)
    keeper.tasks[1].status = "live"
    keeper.tasks[1].published_url = "https://x.com/SynapseNetworkA/status/keeper"
    duplicate.tasks.append(
        SocialDistributionTaskRow(
            account_id=_account(db_session).id,
            platform="x",
            channel_key="official",
            action="x_article_teaser",
            status="live",
            published_url="https://x.com/SynapseNetworkA/status/1",
        )
    )
    db_session.commit()

    result = archive_duplicate_content_tasks(
        db_session,
        DuplicateArchiveOptions(
            dry_run=False,
            title="Synapse Network: Payment Rails for AI Agents",
            task_type="x_article_pack",
        ),
    )

    db_session.refresh(duplicate)
    assert result.archived_count == 0
    assert result.groups[0].skipped[0].asset_id == duplicate.id
    assert result.groups[0].skipped[0].reason == "has_publish_evidence"
    assert duplicate.status == "ready"


def test_archived_content_assets_are_hidden_from_list_but_detail_remains(
    synced_client,
):
    created = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={
            "title": "Hidden archived content task",
            "task_type": "x_article_pack",
            "target_platforms": ["x"],
        },
    ).json()

    patch = synced_client.patch(
        f"/api/social/distribution/assets/{created['id']}",
        json={"status": "archived"},
    )
    listed = synced_client.get("/api/social/distribution/assets")
    detail = synced_client.get(f"/api/social/distribution/assets/{created['id']}")

    assert patch.status_code == 200
    assert listed.status_code == 200
    assert created["id"] not in [row["id"] for row in listed.json()]
    assert detail.status_code == 200
    assert detail.json()["status"] == "archived"


def test_content_task_create_reuses_legacy_x_article_pack_asset(
    synced_client,
    db_session,
):
    legacy, _ = _seed_duplicate_pair(db_session)
    legacy.source_type = "manual"
    legacy.goal_key = "x_article_pack_platform_intro"
    legacy.agent_metadata_json = json.dumps(
        {
            "source_of_truth": "e2e_x_article_pack",
            "target_url": "https://www.synapse-network.ai/",
        },
        sort_keys=True,
    )
    db_session.commit()

    response = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={
            "title": "Synapse Network: Payment Rails for AI Agents",
            "task_type": "x_article_pack",
            "goal_key": "x_article_pack_platform_intro",
            "target_platforms": ["x"],
        },
    )

    assert response.status_code == 200, response.json()
    assert response.json()["id"] == legacy.id
    assert response.json()["agent_metadata"]["reused_existing"] is True


def _seed_duplicate_pair(db_session):
    account = _account(db_session)
    keeper = SocialContentAssetRow(
        asset_type="article",
        source_type="manual_task",
        title="Synapse Network: Payment Rails for AI Agents",
        summary="Keep this asset.",
        status="ready",
        created_by="operator",
        agent_metadata_json=_metadata(CONTENT_TASK_KEY),
    )
    duplicate = SocialContentAssetRow(
        asset_type="article",
        source_type="manual_task",
        title="Synapse Network: Payment Rails for AI Agents",
        summary="Archive this duplicate.",
        status="ready",
        created_by="operator",
        agent_metadata_json=_metadata(CONTENT_TASK_KEY),
    )
    db_session.add_all([keeper, duplicate])
    db_session.flush()
    keeper.documents.append(
        SocialDistributionDocumentRow(
            document_kind="x_article_pack",
            title="Article Pack",
            body_markdown="# Article",
            status="generated",
        )
    )
    keeper.tasks.extend(
        [
            SocialDistributionTaskRow(
                account_id=account.id,
                platform="x",
                channel_key="official",
                action="x_article_manual_publish",
                status="needs_manual_article_publish",
            ),
            SocialDistributionTaskRow(
                account_id=account.id,
                platform="x",
                channel_key="official",
                action="x_article_teaser",
                status="needs_review",
            ),
        ]
    )
    db_session.commit()
    return keeper, duplicate


def _account(db_session):
    account = (
        db_session.query(SocialDistributionAccountRow)
        .filter_by(platform="x", channel_key="official")
        .one_or_none()
    )
    if account:
        return account
    account = SocialDistributionAccountRow(
        platform="x",
        channel_key="official",
        display_name="X Official Account",
        account_type="official",
        priority="P0",
        status="active",
        publish_mode="api_human_gated",
        api_capability="post,long_post",
    )
    db_session.add(account)
    db_session.flush()
    return account


def _metadata(content_task_key: str) -> str:
    return json.dumps(
        {
            "content_task_key": content_task_key,
            "task_type": "x_article_pack",
            "campaign_key": "",
            "target_platforms": ["x"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
