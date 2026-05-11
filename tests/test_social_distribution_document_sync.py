from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionAccountRow,
    SocialDistributionDocumentRow,
    SocialDistributionTaskRow,
)


def _legacy_task(db_session, status="draft_ready"):
    asset = SocialContentAssetRow(
        asset_type="article",
        source_type="asset_planner",
        title="Legacy generated asset",
        summary="Legacy asset generated before platform documents existed.",
        status="ready",
        created_by="test",
    )
    account = SocialDistributionAccountRow(
        platform="devto",
        channel_key="dev.to",
        display_name="DEV Community",
        signup_url="https://dev.to/enter",
        status="active",
    )
    db_session.add_all([asset, account])
    db_session.flush()
    task = SocialDistributionTaskRow(
        asset_id=asset.id,
        account_id=account.id,
        platform="devto",
        channel_key="dev.to",
        status=status,
        platform_title="Legacy DEV title",
        platform_body="Legacy DEV body",
    )
    db_session.add(task)
    db_session.commit()
    return asset, task


def test_board_backfills_platform_documents_for_legacy_tasks(synced_client, db_session):
    asset, _task = _legacy_task(db_session)

    board = synced_client.get("/api/social/distribution/board")
    detail = synced_client.get(f"/api/social/distribution/assets/{asset.id}")

    assert board.status_code == 200
    assert detail.status_code == 200
    assert db_session.query(SocialDistributionDocumentRow).count() == 1
    document = detail.json()["documents"][0]
    assert document["document_kind"] == "platform_draft"
    assert document["status"] == "generated"
    columns = {column["key"]: column for column in board.json()["columns"]}
    assert columns["ready_to_publish"]["count"] == 1


def test_distribution_task_patch_maps_document_status(synced_client, db_session):
    _asset, task = _legacy_task(db_session)

    approved = synced_client.patch(
        f"/api/social/distribution/tasks/{task.id}",
        json={"status": "approved"},
    )
    assert approved.status_code == 200
    document = db_session.query(SocialDistributionDocumentRow).one()
    assert document.status == "approved"

    skipped = synced_client.patch(
        f"/api/social/distribution/tasks/{task.id}",
        json={"status": "skipped"},
    )
    assert skipped.status_code == 200
    db_session.refresh(document)
    assert document.status == "failed"
