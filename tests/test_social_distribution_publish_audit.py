from server.database_social_distribution import (
    SocialDistributionDocumentRow,
    SocialDistributionEventRow,
)
from server.services.social.agent_content_pack import AgentDistributionDraft
from server.services.social.distribution_publish_lint import lint_distribution_task
from tests.social_distribution_helpers import patch_agent_distribution


def _add_approved_canonical_article(db_session, asset_id: int):
    doc = SocialDistributionDocumentRow(
        asset_id=asset_id,
        document_kind="canonical_article",
        title="Approved canonical article",
        body_markdown="# Approved canonical article\n\nA complete mother draft for platform adaptation.",
        status="approved",
        version=1,
        metadata_json='{"generated_by":"asset_expansion_agent_v1","summary":"Approved canonical summary","key_facts":["fact"]}',
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def test_distribution_task_published_page_audit_records_visibility_issue(
    synced_client, db_session, monkeypatch
):
    patch_agent_distribution(monkeypatch)
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    reddit = next(row for row in accounts if row["platform"] == "reddit")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={
            "title": "Agent payment discussion",
            "summary": "A practical developer discussion.",
        },
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])
    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [reddit["id"]]},
    ).json()
    task_id = generated["generated_task_ids"][0]
    synced_client.post(
        f"/api/social/distribution/tasks/{task_id}/mark-live",
        json={"published_url": "https://www.reddit.com/r/AI_Agents/comments/1tiav5c/"},
    )

    audited = synced_client.post(
        f"/api/social/distribution/tasks/{task_id}/audit-published-page",
        json={
            "visibility_status": "removed_by_filter",
            "layout_status": "unknown",
            "audit_note": "Reddit page says removed by filters.",
            "actor": "operator",
        },
    )

    assert audited.status_code == 200
    payload = audited.json()
    assert payload["status"] == "live"
    assert payload["metadata"]["visibility_status"] == "removed_by_filter"
    assert payload["metadata"]["layout_status"] == "unknown"
    assert (
        db_session.query(SocialDistributionEventRow)
        .filter(SocialDistributionEventRow.event_type == "task_published_page_audited")
        .count()
        == 1
    )
    board = synced_client.get("/api/social/distribution/board").json()
    columns = {column["key"]: column for column in board["columns"]}
    card = columns["live"]["cards"][0]
    assert card["visibility_issue_count"] == 1


def test_distribution_task_publish_lint_blocks_bad_dev_markdown(
    synced_client, db_session, monkeypatch
):
    def bad_dev_draft(**kwargs):
        return AgentDistributionDraft(
            title="Bad DEV draft",
            body=(
                "AI agents can think, but they still cannot pay. 这不是模型能力问题。 "
                "### 1. Subscriptions are built for human teams\nBody"
            ),
            checklist="Human Gate required.",
            risk_level="normal",
            rationale="bad markdown",
            metadata={
                "generated_by": "agent_content_pack_v1",
                "format_kind": "long_article",
            },
        )

    monkeypatch.setattr(
        "server.services.social.distribution_generation.generate_platform_task_draft",
        bad_dev_draft,
    )
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    devto = next(row for row in accounts if row["platform"] == "devto")
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "Bad DEV article", "summary": "Should require review."},
    ).json()
    _add_approved_canonical_article(db_session, asset["id"])

    generated = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": [devto["id"]]},
    )

    assert generated.status_code == 200
    task = generated.json()["asset"]["tasks"][0]
    lint = task["metadata"]["platform_publish_lint"]
    assert task["status"] == "needs_review"
    assert lint["status"] == "blocked"
    issue_codes = {issue["code"] for issue in lint["issues"]}
    assert "language_mismatch" in issue_codes
    assert "markdown_heading_collapsed" in issue_codes


def test_x_publish_lint_blocks_urls_by_default():
    lint = lint_distribution_task(
        platform="x",
        channel_key="official",
        title="No-link X draft",
        body=(
            "Agent payment rails should start with spend caps and receipts.\n\n"
            "Read more at https://synapse-network.ai/docs"
        ),
    )

    assert lint.status == "blocked"
    assert {issue.code for issue in lint.issues} == {"x_link_not_allowed_by_default"}
