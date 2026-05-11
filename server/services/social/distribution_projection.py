"""Projection helpers for social distribution rows."""

from __future__ import annotations

import json

from server import schemas_social_distribution as dist_schema
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionAccountRow,
    SocialDistributionDocumentRow,
    SocialDistributionEventRow,
    SocialDistributionTaskRow,
)


def _asset_out(row: SocialContentAssetRow) -> dist_schema.SocialContentAssetOut:
    tasks = list(row.tasks or [])
    return dist_schema.SocialContentAssetOut(
        id=int(row.id),
        asset_type=row.asset_type,
        source_type=row.source_type,
        title=row.title,
        body=row.body,
        summary=row.summary,
        canonical_url=row.canonical_url,
        source_signal_id=row.source_signal_id,
        goal_key=row.goal_key,
        policy_check=_json_object(row.policy_check_json),
        agent_metadata=_json_object(row.agent_metadata_json),
        status=row.status,
        created_by=row.created_by,
        task_count=len(tasks),
        status_counts=_status_counts(tasks),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _asset_detail_out(
    row: SocialContentAssetRow,
) -> dist_schema.SocialContentAssetDetailOut:
    base = _asset_out(row)
    return dist_schema.SocialContentAssetDetailOut(
        **base.model_dump(),
        tasks=[_task_out(task) for task in row.tasks],
        events=[_event_out(event) for event in row.events],
        documents=[_document_out(document) for document in row.documents],
    )


def _task_out(row: SocialDistributionTaskRow) -> dist_schema.SocialDistributionTaskOut:
    account = row.account
    return dist_schema.SocialDistributionTaskOut(
        id=int(row.id),
        asset_id=int(row.asset_id),
        account_id=int(row.account_id),
        platform=row.platform,
        channel_key=row.channel_key,
        action=row.action,
        account_display_name=account.display_name if account else None,
        signup_url=account.signup_url if account else None,
        publish_mode=account.publish_mode if account else "manual_only",
        api_capability=account.api_capability if account else "none",
        credential_ref_configured=bool(account and account.credential_ref),
        status=row.status,
        platform_title=row.platform_title,
        platform_body=row.platform_body,
        operator_checklist=row.operator_checklist,
        submission_url=row.submission_url,
        published_url=row.published_url,
        external_post_id=row.external_post_id,
        failure_summary=row.failure_summary,
        manual_result_note=row.manual_result_note,
        metadata=_json_object(row.metadata_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def account_out(
    row: SocialDistributionAccountRow,
) -> dist_schema.SocialDistributionAccountOut:
    return dist_schema.SocialDistributionAccountOut(
        id=int(row.id),
        platform=row.platform,
        channel_key=row.channel_key,
        display_name=row.display_name,
        signup_url=row.signup_url,
        profile_url=row.profile_url,
        account_type=row.account_type,
        priority=row.priority,
        status=row.status,
        email_hint=row.email_hint,
        two_factor_status=row.two_factor_status,
        read_automation_mode=row.read_automation_mode,
        human_publish_required=bool(row.human_publish_required),
        publish_mode=row.publish_mode,
        credential_ref_configured=bool(row.credential_ref),
        api_capability=row.api_capability,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _event_out(
    row: SocialDistributionEventRow,
) -> dist_schema.SocialDistributionEventOut:
    return dist_schema.SocialDistributionEventOut(
        id=int(row.id),
        asset_id=int(row.asset_id),
        task_id=int(row.task_id) if row.task_id is not None else None,
        event_type=row.event_type,
        actor=row.actor,
        summary=row.summary,
        payload=_json_object(row.payload_json),
        created_at=row.created_at,
    )


def _document_out(
    row: SocialDistributionDocumentRow,
) -> dist_schema.SocialDistributionDocumentOut:
    return dist_schema.SocialDistributionDocumentOut(
        id=int(row.id),
        asset_id=int(row.asset_id),
        task_id=int(row.task_id) if row.task_id is not None else None,
        document_kind=row.document_kind,
        platform=row.platform,
        channel_key=row.channel_key,
        title=row.title,
        body_markdown=row.body_markdown,
        status=row.status,
        version=int(row.version or 1),
        metadata=_json_object(row.metadata_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _status_counts(rows: list[SocialDistributionTaskRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts


def _json_object(value: str | None) -> dict[str, object]:
    try:
        payload = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
