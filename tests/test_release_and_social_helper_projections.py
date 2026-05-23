from __future__ import annotations

import json

import pytest

from server.database import (
    ReleaseRecordRow,
    RequirementRow,
    SocialAccountRow,
    SocialPostDraftRow,
    SocialPostMetricRow,
)
from server.database_config import (
    is_postgres_url,
    is_sqlite_url,
    resolve_database_url,
)
from server.database_social_distribution import SocialContentAssetRow
from server.services.delivery.deployment_release_evidence import (
    requirement_delivery_payload,
    resolve_commit_sha,
)
from server.services.scheduling.x_social_reply_block_workflow import (
    REPLY_BLOCK_DRY_RUN,
    REPLY_BLOCK_RECURRING_WORKFLOW,
)
from server.services.social.distribution_reply_metadata import reply_ids_from_asset
from server.services.social.post_metric_projection import (
    metric_base_out,
    metric_engagement,
    metric_post_index,
    metric_top_post_out,
)


def test_database_config_resolution_accepts_postgres_and_rejects_prod_sqlite():
    assert is_sqlite_url(" sqlite:///tmp/ops.db ")
    assert is_postgres_url("postgresql+psycopg://user:pass@localhost/db")

    resolved = resolve_database_url(
        env="local",
        explicit_database_url="",
        sqlite_fallback_url="sqlite:///tmp/ops.db",
    )
    assert resolved.is_sqlite
    assert not resolved.is_explicit

    with pytest.raises(RuntimeError, match="explicit PostgreSQL URL"):
        resolve_database_url(
            env="staging",
            explicit_database_url="sqlite:///tmp/ops.db",
            sqlite_fallback_url="sqlite:///fallback.db",
        )


def test_requirement_delivery_payload_and_commit_resolution(db_session):
    requirement = RequirementRow(
        title="Deploy evidence",
        description_markdown="Release evidence smoke.",
        status="done",
        priority="normal",
        source="test",
        target_project_path="/tmp/release-evidence",
        project_key="synapse-network",
        intake_metadata_json="{}",
    )
    db_session.add(requirement)
    db_session.flush()

    assert requirement_delivery_payload(db_session, int(requirement.id)) == {}
    with pytest.raises(ValueError, match="missing a deliverable commit SHA"):
        resolve_commit_sha(db_session, requirement)

    db_session.add(
        ReleaseRecordRow(
            requirement_id=int(requirement.id),
            project_key="synapse-network",
            target_project_path="/tmp/release-evidence",
            status="release_ready",
            delivery_state="merged",
            branch_name="planned",
            actual_branch_name="actual",
            commit_sha="abc123",
            metadata_json=json.dumps({"checks_status": "success"}),
        )
    )
    db_session.commit()

    payload = requirement_delivery_payload(db_session, int(requirement.id))
    assert payload["latest_remote_sha"] == "abc123"
    assert payload["head_branch"] == "actual"
    assert resolve_commit_sha(db_session, requirement) == "abc123"
    assert resolve_commit_sha(db_session, requirement, "override") == "override"


def test_social_metric_projection_helpers(db_session):
    account = SocialAccountRow(platform="x", handle="synapse", secret_ref="secret")
    db_session.add(account)
    db_session.flush()
    post = SocialPostDraftRow(
        platform="x",
        account_id=int(account.id),
        external_post_id="post-1",
        title="Launch thread",
        body_text="body",
        status="published",
    )
    db_session.add(post)
    db_session.flush()
    metric = SocialPostMetricRow(
        post_id=int(post.id),
        external_post_id="post-1",
        impressions=100,
        likes=4,
        replies=3,
        reposts=2,
        follows=1,
        link_clicks=5,
        summary="strong",
    )
    db_session.add(metric)
    db_session.flush()

    assert metric_engagement(metric) == 14
    assert metric_base_out(metric).follows == 1
    assert (
        metric_post_index(db_session, [metric]).posts_by_id[int(post.id)].title
        == "Launch thread"
    )
    top = metric_top_post_out(metric, post)
    assert top.title == "Launch thread"
    assert top.engagement_total == 14
    assert metric_post_index(db_session, []).posts_by_id == {}


def test_reply_metadata_and_workflow_contracts():
    asset = SocialContentAssetRow(
        asset_type="article",
        source_type="manual_task",
        title="Reply block",
        body="",
        agent_metadata_json=json.dumps({"reply_block": {"reply_ids": [1, "2", "x"]}}),
    )
    assert reply_ids_from_asset(asset) == [1, 2]
    asset.agent_metadata_json = "{bad json"
    assert reply_ids_from_asset(asset) == []
    assert (
        REPLY_BLOCK_RECURRING_WORKFLOW["workflow_key"]
        == "x_social_daily_reply_block_publisher"
    )
    assert REPLY_BLOCK_DRY_RUN["auto_reply"] is False
