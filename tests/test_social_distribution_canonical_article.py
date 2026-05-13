from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionDocumentRow,
    SocialDistributionEventRow,
)
from server.services.social.agent_content_pack import (
    AgentDistributionDraft,
    CanonicalArticleExpansion,
)


def _patch_canonical_article_generation(monkeypatch):
    def fake_platform_draft(**kwargs):
        platform = kwargs["platform"]
        channel = kwargs["channel_key"]
        return AgentDistributionDraft(
            title=f"{platform} draft: {kwargs['asset_title']}",
            body=f"{platform}/{channel} agent-generated body for {kwargs['asset_title']}",
            checklist=f"Human Gate required for {platform}/{channel}.",
            risk_level="normal",
            rationale=f"Adapted for {platform}",
            metadata={
                "generated_by": "agent_content_pack_v1",
                "platform": platform,
                "channel_key": channel,
                "human_gate_required": True,
                "auto_publish": False,
            },
        )

    def fake_canonical_article_expansion(**kwargs):
        return CanonicalArticleExpansion(
            title=f"Canonical article: {kwargs['asset_title']}",
            summary=f"Expanded summary for {kwargs['asset_title']}",
            body_markdown=(
                f"# {kwargs['asset_title']}\n\n"
                "This is a density-driven canonical article with concrete details."
            ),
            key_facts=["density-driven canonical article"],
            generation_reason="fake expansion for tests",
            metadata={
                "provider": "test",
                "generated_by": "asset_expansion_agent_v1",
            },
        )

    monkeypatch.setattr(
        "server.services.social.distribution_generation.generate_platform_task_draft",
        fake_platform_draft,
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
        metadata_json='{"generated_by":"asset_expansion_agent_v1","summary":"Approved canonical summary","key_facts":["fact"]}',
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def test_short_asset_requires_approved_canonical_article_before_platform_tasks(
    synced_client, monkeypatch
):
    _patch_canonical_article_generation(monkeypatch)
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    x_account = next(row for row in accounts if row["platform"] == "x")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={
            "title": "Short outline only",
            "body": "Three bullets. Not a full article yet.",
        },
    ).json()

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [x_account["id"]], "actor": "operator"},
    )

    assert response.status_code == 400
    assert "canonical_article_required" in response.json()["detail"]


def test_expand_and_approve_canonical_article_gate(
    synced_client, db_session, monkeypatch
):
    _patch_canonical_article_generation(monkeypatch)
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={
            "title": "One-person company system outline",
            "body": "Why I build a system before only building a product.",
        },
    ).json()

    expanded = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/expand-canonical-article",
        json={"actor": "operator"},
    )
    assert expanded.status_code == 200
    canonical = next(
        doc
        for doc in expanded.json()["documents"]
        if doc["document_kind"] == "canonical_article"
    )
    assert canonical["status"] == "needs_review"
    assert canonical["metadata"]["generated_by"] == "asset_expansion_agent_v1"

    approved = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/approve-canonical-article",
        json={"actor": "operator", "document_id": canonical["id"]},
    )

    assert approved.status_code == 200
    doc = db_session.get(SocialDistributionDocumentRow, canonical["id"])
    assert doc is not None
    assert doc.status == "approved"
    assert (
        db_session.query(SocialDistributionEventRow)
        .filter(SocialDistributionEventRow.event_type == "canonical_article_approved")
        .count()
        == 1
    )


def test_approve_and_generate_marks_asset_approved_before_serial_tasks(
    synced_client, db_session, monkeypatch
):
    _patch_canonical_article_generation(monkeypatch)
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    devto = next(row for row in accounts if row["platform"] == "devto")
    created = synced_client.post(
        "/api/social/distribution/assets",
        json={
            "title": "Approve and generate",
            "summary": "One click should approve asset and generate tasks.",
            "status": "proposed",
        },
    ).json()
    _add_approved_canonical_article(db_session, created["id"])

    response = synced_client.post(
        f"/api/social/distribution/assets/{created['id']}/approve-and-generate-tasks",
        json={"account_ids": [devto["id"]], "actor": "operator"},
    )

    assert response.status_code == 200
    asset = db_session.get(SocialContentAssetRow, created["id"])
    assert asset is not None
    assert asset.status == "ready"
    event_types = [
        row.event_type
        for row in db_session.query(SocialDistributionEventRow)
        .order_by(SocialDistributionEventRow.id)
        .all()
    ]
    assert "asset_approved" in event_types
    assert "task_generated" in event_types
    docs = db_session.query(SocialDistributionDocumentRow).all()
    assert {doc.document_kind for doc in docs} == {
        "canonical_article",
        "platform_draft",
    }
    platform_doc = next(doc for doc in docs if doc.document_kind == "platform_draft")
    assert platform_doc.task_id == response.json()["generated_task_ids"][0]
    assert '"source_document_id"' in platform_doc.metadata_json
    assert "devto/dev.to agent-generated body" in platform_doc.body_markdown
