from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionAccountRow,
    SocialDistributionDocumentRow,
    SocialDistributionEventRow,
    SocialDistributionTaskRow,
)
from server.database import SocialTrendItemRow
from server.services.social.agent_content_pack import (
    AgentDistributionDraft,
    CanonicalArticleExpansion,
    CanonicalAssetPack,
)
from server.services.social.distribution_projection import _json_object
from server.services.social.publishing import XPublishResult


def _patch_agent_distribution(monkeypatch):
    def fake_platform_draft(**kwargs):
        platform = kwargs["platform"]
        channel = kwargs["channel_key"]
        canonical = kwargs.get("canonical_url")
        metadata = {
            "generated_by": "agent_content_pack_v1",
            "platform": platform,
            "channel_key": channel,
            "human_gate_required": True,
            "auto_publish": False,
        }
        if platform in {"dev", "devto", "hashnode"} and not canonical:
            metadata["warning"] = "canonical_url_missing"
        checklist = f"Human Gate required for {platform}/{channel}."
        if platform in {"dev", "devto", "hashnode"}:
            checklist += (
                f" Canonical URL 字段填写 {canonical}."
                if canonical
                else " Canonical URL missing."
            )
        return AgentDistributionDraft(
            title=f"{platform} draft: {kwargs['asset_title']}",
            body=f"{platform}/{channel} agent-generated body for {kwargs['asset_title']}",
            checklist=checklist,
            risk_level="normal",
            rationale=f"Adapted for {platform}",
            metadata=metadata,
        )

    def fake_asset_pack(**kwargs):
        asset_type = kwargs["asset_type"]
        signals = kwargs["signals"]
        lead = signals[0]
        return CanonicalAssetPack(
            title=f"Agent asset: {lead.title}",
            summary=f"Agent summary for {lead.summary}",
            body=f"Agent body for {asset_type}: {lead.title}",
            asset_type=asset_type,
            source_type="asset_planner",
            goal_key="synapse_public_preview_traction",
            key_facts=[lead.title],
            recommended_channels=["x", "hacker_news", "devto", "hashnode"],
            source_signal_refs=[signal.source_ref for signal in signals],
            generation_reason="fake agent generation for tests",
            generation_metadata={
                "provider": "test",
                "generated_by": "agent_content_pack_v1",
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
        "server.services.social.distribution_asset_planner.generate_canonical_asset_pack",
        fake_asset_pack,
    )
    monkeypatch.setattr(
        "server.services.social.distribution_documents.generate_canonical_article_expansion",
        fake_canonical_article_expansion,
    )


def _add_approved_canonical_article(db_session, asset_id: int, body: str | None = None):
    doc = SocialDistributionDocumentRow(
        asset_id=asset_id,
        document_kind="canonical_article",
        title="Approved canonical article",
        body_markdown=body
        or "# Approved canonical article\n\nA complete mother draft for platform adaptation.",
        status="approved",
        version=1,
        metadata_json='{"generated_by":"asset_expansion_agent_v1","summary":"Approved canonical summary","key_facts":["fact"]}',
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def test_distribution_accounts_seed_idempotently(synced_client, db_session):
    first = synced_client.get("/api/social/distribution/accounts")
    second = synced_client.get("/api/social/distribution/accounts")

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(first.json()) >= 10
    assert db_session.query(SocialDistributionAccountRow).count() == len(first.json())


def test_create_content_task_creates_source_plan_document(synced_client, db_session):
    response = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={
            "title": "第 1 篇：一人公司最大的问题，不是没人，是没有系统",
            "source_material": "核心问题：上下文切换、流程断裂和质量失控。",
            "target_audience": "solo founders and developers",
            "target_platforms": ["x", "v2ex", "hacker_news", "devto"],
            "source_doc_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing/docs/plans/solo-company-codex-collaboration-content-series-outline.md",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "manual_task"
    assert payload["documents"][0]["document_kind"] == "source_plan"
    assert "Content Implementation Plan" in payload["documents"][0]["body_markdown"]
    doc = db_session.query(SocialDistributionDocumentRow).one()
    metadata = _json_object(doc.metadata_json)
    assert metadata["generated_by"] == "distribution_content_plan_v1"
    assert metadata["structured_plan"]["target_platforms"] == [
        "x",
        "v2ex",
        "hacker_news",
        "devto",
    ]


def test_create_content_task_fails_closed_without_title(synced_client, db_session):
    response = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={"title": "   ", "source_material": "body"},
    )

    assert response.status_code == 400
    assert db_session.query(SocialDistributionDocumentRow).count() == 0


def test_generate_content_plan_and_board_projection(synced_client):
    created = synced_client.post(
        "/api/social/distribution/content-tasks",
        json={"title": "Solo company control plane", "source_material": "Build system before product."},
    ).json()

    generated = synced_client.post(
        f"/api/social/distribution/assets/{created['id']}/generate-content-plan",
        json={"actor": "operator"},
    )
    board = synced_client.get("/api/social/distribution/board")

    assert generated.status_code == 200
    assert len(generated.json()["documents"]) == 1
    assert board.status_code == 200
    columns = {column["key"]: column for column in board.json()["columns"]}
    assert list(columns) == [
        "backlog",
        "needs_review",
        "ready_to_publish",
        "live",
        "blocked",
    ]
    assert columns["needs_review"]["count"] == 1
    card = columns["needs_review"]["cards"][0]
    assert card["document_count"] == 1
    assert card["next_action"].startswith("审核方案")


def test_content_asset_generates_grouped_platform_tasks_serially(
    synced_client, db_session, monkeypatch
):
    _patch_agent_distribution(monkeypatch)
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    selected = [
        row["id"]
        for row in accounts
        if (row["platform"], row["channel_key"])
        in {
            ("devto", "dev.to"),
            ("hashnode", "hashnode.com"),
            ("hacker_news", "news.ycombinator.com"),
        }
    ]
    created = synced_client.post(
        "/api/social/distribution/assets",
        json={
            "asset_type": "article",
            "title": "How AI agents should pay for APIs",
            "summary": "A practical developer guide to agent-native payment rails.",
            "canonical_url": "https://docs.synapse-network.ai/agent-payments",
        },
    )
    assert created.status_code == 200
    asset_id = created.json()["id"]
    _add_approved_canonical_article(db_session, asset_id)

    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset_id}/generate-tasks",
        json={"account_ids": selected, "actor": "operator"},
    )

    assert generated.status_code == 200
    payload = generated.json()
    assert len(payload["generated_task_ids"]) == len(selected)
    assert [result["platform"] for result in payload["results"]] == [
        "hacker_news",
        "devto",
        "hashnode",
    ]
    tasks = (
        db_session.query(SocialDistributionTaskRow)
        .order_by(SocialDistributionTaskRow.id)
        .all()
    )
    assert [task.platform for task in tasks] == ["hacker_news", "devto", "hashnode"]
    assert all(task.status == "draft_ready" for task in tasks)
    assert all("serial_generation" in task.metadata_json for task in tasks)
    assert all("agent_content_pack_v1" in task.metadata_json for task in tasks)
    assert db_session.query(SocialDistributionEventRow).filter(
        SocialDistributionEventRow.event_type == "task_generated"
    ).count() == len(selected)

    grouped = synced_client.get("/api/social/distribution/tasks")
    assert grouped.status_code == 200
    assert grouped.json()["total_assets"] == 1
    assert (
        grouped.json()["groups"][0]["asset"]["title"]
        == "How AI agents should pay for APIs"
    )


def test_distribution_long_form_targets_include_canonical_warning_when_missing(
    synced_client, db_session, monkeypatch
):
    _patch_agent_distribution(monkeypatch)
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    devto = next(row for row in accounts if row["platform"] == "devto")
    created = synced_client.post(
        "/api/social/distribution/assets",
        json={
            "title": "SDK quickstart for agent payments",
            "summary": "A developer tutorial without canonical URL.",
        },
    ).json()
    _add_approved_canonical_article(db_session, created["id"])

    response = synced_client.post(
        f"/api/social/distribution/assets/{created['id']}/generate-tasks",
        json={"account_ids": [devto["id"]]},
    )

    assert response.status_code == 200
    task = response.json()["asset"]["tasks"][0]
    assert task["status"] == "draft_ready"
    assert task["metadata"]["warning"] == "canonical_url_missing"
    assert "Canonical URL missing" in task["operator_checklist"]


def test_distribution_task_manual_live_removed_and_status_validation(
    synced_client, db_session, monkeypatch
):
    _patch_agent_distribution(monkeypatch)
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    devto = next(row for row in accounts if row["platform"] == "devto")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={
            "title": "How AI agents should pay for APIs",
            "summary": "A practical developer guide.",
        },
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])
    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [devto["id"]]},
    ).json()
    task_id = generated["generated_task_ids"][0]

    bad_status = synced_client.patch(
        f"/api/social/distribution/tasks/{task_id}",
        json={"status": "unknown"},
    )
    assert bad_status.status_code == 400

    live = synced_client.post(
        f"/api/social/distribution/tasks/{task_id}/mark-live",
        json={
            "published_url": "https://dev.to/synapsenetwork/agent-payments",
            "manual_result_note": "Published manually by operator.",
        },
    )
    assert live.status_code == 200
    assert live.json()["status"] == "live"
    document = (
        db_session.query(SocialDistributionDocumentRow)
        .filter(SocialDistributionDocumentRow.document_kind == "platform_draft")
        .one()
    )
    assert document.status == "published"

    removed = synced_client.post(
        f"/api/social/distribution/tasks/{task_id}/mark-removed",
        json={"manual_result_note": "Moderator removed duplicate post."},
    )
    assert removed.status_code == 200
    assert removed.json()["status"] == "removed"
    assert removed.json()["manual_result_note"] == "Moderator removed duplicate post."
    db_session.refresh(document)
    assert document.status == "failed"
    board = synced_client.get("/api/social/distribution/board").json()
    columns = {column["key"]: column for column in board["columns"]}
    assert columns["blocked"]["count"] == 1


def test_x_distribution_task_can_publish_after_human_gate(
    synced_client, db_session, monkeypatch
):
    _patch_agent_distribution(monkeypatch)

    class FakeXPublisher:
        def publish_text(self, account, body_text, media_ids=None):
            assert body_text
            return XPublishResult(
                post_id="1234567890",
                response_summary={"data": {"id": "1234567890"}},
            )

    monkeypatch.setattr(
        "server.services.social.distribution_tasks.x_publisher",
        FakeXPublisher(),
    )
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    x_account = next(row for row in accounts if row["platform"] == "x")
    assert x_account["publish_mode"] == "api_human_gated"
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "X publish asset", "summary": "Official X update."},
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])
    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [x_account["id"]]},
    ).json()
    task_id = generated["generated_task_ids"][0]

    response = synced_client.post(
        f"/api/social/distribution/tasks/{task_id}/publish-x",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "live"
    assert payload["external_post_id"] == "1234567890"
    assert payload["published_url"].endswith("/1234567890")
    assert (
        db_session.query(SocialDistributionEventRow)
        .filter(SocialDistributionEventRow.event_type == "task_published_x")
        .count()
        == 1
    )


def test_distribution_routes_return_diagnostic_errors_and_update_records(
    synced_client, db_session, monkeypatch
):
    _patch_agent_distribution(monkeypatch)
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    devto = next(row for row in accounts if row["platform"] == "devto")

    missing_account = synced_client.patch(
        "/api/social/distribution/accounts/404",
        json={"status": "active"},
    )
    assert missing_account.status_code == 404
    invalid_account = synced_client.patch(
        f"/api/social/distribution/accounts/{devto['id']}",
        json={"status": "bad"},
    )
    assert invalid_account.status_code == 400
    updated_account = synced_client.patch(
        f"/api/social/distribution/accounts/{devto['id']}",
        json={
            "status": "active",
            "profile_url": " https://dev.to/synapsenetwork ",
            "email_hint": "growth@synapse-network.ai",
            "two_factor_status": "enabled",
            "notes": "Registered by operator.",
        },
    )
    assert updated_account.status_code == 200
    assert updated_account.json()["profile_url"] == "https://dev.to/synapsenetwork"

    empty_title = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "   "},
    )
    assert empty_title.status_code == 400
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "Patchable asset", "summary": "Original."},
    ).json()

    assert synced_client.get("/api/social/distribution/assets").status_code == 200
    assert synced_client.get("/api/social/distribution/assets/404").status_code == 404
    assert (
        synced_client.patch(
            "/api/social/distribution/assets/404", json={"status": "ready"}
        ).status_code
        == 404
    )
    updated_asset = synced_client.patch(
        f"/api/social/distribution/assets/{asset['id']}",
        json={
            "title": "Updated asset",
            "body": "Longer body",
            "summary": "Updated.",
            "canonical_url": "https://docs.synapse-network.ai/updated",
            "goal_key": "growth",
            "status": "ready",
        },
    )
    assert updated_asset.status_code == 200
    assert updated_asset.json()["title"] == "Updated asset"

    no_accounts = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": []},
    )
    assert no_accounts.status_code == 400
    missing_channel = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [devto["id"], 999999]},
    )
    assert missing_channel.status_code == 404

    _add_approved_canonical_article(db_session, asset["id"])
    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [devto["id"]]},
    ).json()
    task_id = generated["generated_task_ids"][0]
    patched = synced_client.patch(
        f"/api/social/distribution/tasks/{task_id}",
        json={
            "status": "submitted",
            "platform_title": "Edited title",
            "platform_body": "Edited body",
            "operator_checklist": "Manual publish only.",
            "submission_url": "https://dev.to/new",
            "published_url": "https://dev.to/synapsenetwork/updated",
            "external_post_id": "devto-1",
            "failure_summary": "",
            "manual_result_note": "submitted",
        },
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "submitted"
    assert (
        synced_client.patch(
            "/api/social/distribution/tasks/404", json={"status": "submitted"}
        ).status_code
        == 404
    )
    assert (
        synced_client.post(
            f"/api/social/distribution/tasks/{task_id}/mark-live",
            json={"published_url": "   "},
        ).status_code
        == 400
    )
    assert (
        synced_client.post(
            f"/api/social/distribution/tasks/{task_id}/mark-removed",
            json={"manual_result_note": "   "},
        ).status_code
        == 400
    )
    assert (
        synced_client.post(
            "/api/social/distribution/tasks/404/mark-live",
            json={"published_url": "https://example.com"},
        ).status_code
        == 404
    )
    assert (
        synced_client.post(
            "/api/social/distribution/tasks/404/mark-removed",
            json={"manual_result_note": "gone"},
        ).status_code
        == 404
    )


def test_distribution_platform_adapters_cover_channel_specific_guidance(
    synced_client, db_session, monkeypatch
):
    _patch_agent_distribution(monkeypatch)
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    wanted = [
        row["id"]
        for row in accounts
        if (row["platform"], row["channel_key"])
        in {
            ("hacker_news", "news.ycombinator.com"),
            ("reddit", "r/LocalLLaMA"),
            ("v2ex", "programmer"),
            ("product_hunt", "producthunt.com"),
            ("hashnode", "hashnode.com"),
        }
    ]
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={
            "title": "Introducing Agent Payment Rails",
            "body": "Body-only summary should be used when summary is missing.",
            "canonical_url": "https://docs.synapse-network.ai/payment-rails",
        },
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])

    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": wanted},
    )

    assert generated.status_code == 200
    tasks = {
        task["platform"] + ":" + task["channel_key"]: task
        for task in generated.json()["asset"]["tasks"]
    }
    assert (
        tasks["hacker_news:news.ycombinator.com"]["metadata"]["generated_by"]
        == "agent_content_pack_v1"
    )
    assert "hacker_news" in tasks["hacker_news:news.ycombinator.com"]["platform_body"]
    assert "reddit" in tasks["reddit:r/LocalLLaMA"]["platform_body"]
    assert "v2ex" in tasks["v2ex:programmer"]["platform_title"]
    assert (
        "Canonical URL 字段填写" in tasks["hashnode:hashnode.com"]["operator_checklist"]
    )
    assert "product_hunt" in tasks["product_hunt:producthunt.com"]["platform_body"]


def test_distribution_reuses_existing_task_and_handles_invalid_metadata(
    synced_client,
    db_session,
    monkeypatch,
):
    _patch_agent_distribution(monkeypatch)
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    devto = next(row for row in accounts if row["platform"] == "devto")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "Reuse task", "summary": "Do not duplicate generated rows."},
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])
    first = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [devto["id"]]},
    ).json()
    second = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [devto["id"]]},
    ).json()

    assert first["generated_task_ids"] == second["generated_task_ids"]
    assert db_session.query(SocialDistributionTaskRow).count() == 1
    task = db_session.query(SocialDistributionTaskRow).one()
    task.metadata_json = "{not-json"
    db_session.commit()

    grouped = synced_client.get("/api/social/distribution/tasks").json()
    assert grouped["groups"][0]["tasks"][0]["metadata"] == {}
    assert _json_object("[]") == {}


def test_distribution_uses_new_asset_task_tables_not_campaign_targets(
    synced_client, db_session
):
    created = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "New source of truth", "summary": "Asset task event model."},
    )
    assert created.status_code == 200
    assert db_session.query(SocialContentAssetRow).count() == 1
    assert db_session.query(SocialDistributionTaskRow).count() == 0


def test_social_asset_planner_samples_one_signal_type_and_creates_one_asset(
    synced_client, db_session, monkeypatch
):
    _patch_agent_distribution(monkeypatch)
    db_session.add(
        SocialTrendItemRow(
            topic="AI agents need payment rails",
            summary="Agent builders increasingly need budgeted API access.",
            relevance_score=0.91,
            status="retained",
        )
    )
    db_session.commit()

    response = synced_client.post("/api/social/distribution/assets/plan-next")

    assert response.status_code == 200
    payload = response.json()
    assert payload["no_asset_created"] is False
    assert payload["selected_asset_type"] == "market_commentary"
    assert payload["selected_signal_count"] == 1
    assert payload["created_asset_id"]
    asset = db_session.get(SocialContentAssetRow, payload["created_asset_id"])
    assert asset is not None
    assert asset.status == "proposed"
    assert asset.source_type == "asset_planner"
    metadata = _json_object(asset.agent_metadata_json)
    assert metadata["generated_by"] == "agent_content_pack_v1"
    assert len(metadata["source_signal_refs"]) == 1


def test_social_asset_planner_fail_closed_when_agent_generation_fails(
    synced_client, db_session, monkeypatch
):
    def raise_generation_failure(**_kwargs):
        raise RuntimeError("LLM API error 429: insufficient_quota")

    monkeypatch.setattr(
        "server.services.social.distribution_asset_planner.generate_canonical_asset_pack",
        raise_generation_failure,
    )
    db_session.add(
        SocialTrendItemRow(
            topic="AI agents need payment rails",
            summary="Agent builders increasingly need budgeted API access.",
            relevance_score=0.91,
            status="retained",
        )
    )
    db_session.commit()

    response = synced_client.post("/api/social/distribution/assets/plan-next")

    assert response.status_code == 200
    payload = response.json()
    assert payload["no_asset_created"] is True
    assert payload["created_asset_id"] is None
    assert "asset_generation_failed" in payload["reason"]
    assert db_session.query(SocialContentAssetRow).count() == 0


def test_social_asset_planner_stops_when_daily_inventory_is_satisfied(
    synced_client, db_session
):
    for index in range(3):
        db_session.add(
            SocialContentAssetRow(
                asset_type=(
                    "shipping_proof",
                    "developer_education",
                    "market_commentary",
                )[index],
                source_type="asset_planner",
                title=f"Existing asset {index}",
                status="proposed",
                created_by="test",
            )
        )
    db_session.add(
        SocialTrendItemRow(
            topic="Unused signal",
            summary="Should not create a fourth asset.",
            relevance_score=0.95,
            status="retained",
        )
    )
    db_session.commit()

    response = synced_client.post("/api/social/distribution/assets/plan-next")

    assert response.status_code == 200
    assert response.json()["already_satisfied"] is True
    assert db_session.query(SocialContentAssetRow).count() == 3


def test_social_asset_planner_returns_no_signal_when_inputs_are_empty(synced_client):
    response = synced_client.post("/api/social/distribution/assets/plan-next")

    assert response.status_code == 200
    payload = response.json()
    assert payload["no_asset_created"] is True
    assert payload["reason"] == "no_qualified_signal"
    assert payload["signals"] == []


def test_social_asset_planner_sanitizes_local_paths_before_asset_creation(
    synced_client, db_session, monkeypatch
):
    _patch_agent_distribution(monkeypatch)
    db_session.add(
        SocialTrendItemRow(
            topic="SDK docs update /Users/cliff/workspace/private",
            summary="Traceback and token=secret should not enter public assets.",
            relevance_score=0.92,
            status="retained",
        )
    )
    db_session.commit()

    response = synced_client.post("/api/social/distribution/assets/plan-next")

    assert response.status_code == 200
    asset = db_session.get(SocialContentAssetRow, response.json()["created_asset_id"])
    assert asset is not None
    combined = f"{asset.title}\n{asset.summary}\n{asset.body}"
    assert "/Users/" not in combined
    assert "token=secret" not in combined


def test_distribution_task_generation_missing_asset_returns_404(synced_client):
    response = synced_client.post(
        "/api/social/distribution/assets/404/generate-tasks",
        json={"account_ids": [1]},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Content asset not found."


def test_non_x_distribution_task_cannot_publish_via_api(
    synced_client, db_session, monkeypatch
):
    _patch_agent_distribution(monkeypatch)
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    devto = next(row for row in accounts if row["platform"] == "devto")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "Manual-only platform", "summary": "DEV stays manual in v1."},
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])
    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [devto["id"]]},
    ).json()

    response = synced_client.post(
        f"/api/social/distribution/tasks/{generated['generated_task_ids'][0]}/publish-x",
        json={"actor": "operator"},
    )

    assert response.status_code == 400
    assert "only X distribution tasks" in response.json()["detail"]


def test_x_distribution_publish_policy_blocked_records_failure(
    synced_client, db_session, monkeypatch
):
    _patch_agent_distribution(monkeypatch)
    monkeypatch.setattr(
        "server.services.social.distribution_tasks.run_content_policy_check",
        lambda _text: {"status": "blocked", "blocked_reasons": ["test_policy"]},
    )
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    x_account = next(row for row in accounts if row["platform"] == "x")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "Blocked X task", "summary": "Should fail policy."},
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])
    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [x_account["id"]]},
    ).json()
    task_id = generated["generated_task_ids"][0]
    task = db_session.get(SocialDistributionTaskRow, task_id)
    assert task is not None
    task.platform_body = "Internal workflow JSON: required_commands"
    db_session.commit()

    response = synced_client.post(
        f"/api/social/distribution/tasks/{task_id}/publish-x",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert "policy_blocked" in payload["failure_summary"]
    assert (
        db_session.query(SocialDistributionEventRow)
        .filter(SocialDistributionEventRow.event_type == "task_publish_blocked")
        .count()
        == 1
    )


def test_x_distribution_publish_error_records_bounded_failure(
    synced_client, db_session, monkeypatch
):
    _patch_agent_distribution(monkeypatch)
    monkeypatch.setattr(
        "server.services.social.distribution_tasks.run_content_policy_check",
        lambda _text: {"status": "passed", "blocked_reasons": []},
    )

    class FailingXPublisher:
        def publish_text(self, account, body_text, media_ids=None):
            raise Exception("unexpected")

    def raise_social_publish_error(account, body_text, media_ids=None):
        from server.services.social.publishing import SocialPublishError

        raise SocialPublishError("x_publish_auth_failed", "auth failed")

    failing = FailingXPublisher()
    failing.publish_text = raise_social_publish_error
    monkeypatch.setattr(
        "server.services.social.distribution_tasks.x_publisher", failing
    )
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    x_account = next(row for row in accounts if row["platform"] == "x")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "X auth failure", "summary": "Publish should fail clearly."},
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])
    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [x_account["id"]]},
    ).json()

    response = synced_client.post(
        f"/api/social/distribution/tasks/{generated['generated_task_ids'][0]}/publish-x",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["failure_summary"] == "auth failed"
