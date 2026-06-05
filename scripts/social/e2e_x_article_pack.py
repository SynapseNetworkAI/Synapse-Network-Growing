#!/usr/bin/env python3
"""Create and verify a Synapse X Article Pack E2E record.

This script intentionally keeps X Article publishing manual. It can optionally
publish the API teaser post, but only with an explicit confirmation flag.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from server import schemas_social_distribution as dist_schema
from server.config import PROJECT_ROOT
from server.database import SessionLocal, init_db, utcnow
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionDocumentRow,
    SocialDistributionEventRow,
    SocialDistributionTaskRow,
)
from server.services.social.distribution import ensure_default_distribution_accounts
from server.services.social.distribution_article_packs import (
    ARTICLE_TITLE,
    generate_x_article_pack,
)
from server.services.social.distribution_publish_audit import (
    mark_distribution_task_live,
)
from server.services.social.distribution_tasks import publish_distribution_task_to_x


CANONICAL_BODY = """\
Synapse Network is payment infrastructure for AI agents and autonomous services.

It gives an agent a safer operating model than an unlimited API key or a credit
card. The agent can discover a provider service, invoke a metered API with a
capped budget, and produce a receipt that explains what happened.

For users, this means agent actions can be reviewed after the fact instead of
becoming invisible automation. For providers, it means useful APIs can become
discoverable paid services without building custom billing for every agent
integration.
"""


def main() -> int:
    args = _parse_args()
    _validate_args(args)
    init_db()
    result = _run_e2e(args)
    evidence_path = _write_result(_evidence_dir(args.evidence_dir), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"evidence_path={evidence_path}")
    return 0


def _validate_args(args: argparse.Namespace) -> None:
    if args.include_article_url_in_teaser and args.confirm_link_inclusion != "YES":
        raise SystemExit(
            "--include-article-url-in-teaser requires --confirm-link-inclusion YES"
        )
    if args.publish_teaser and args.confirm_real_x_publish != "YES":
        raise SystemExit("--publish-teaser requires --confirm-real-x-publish YES")


def _run_e2e(args: argparse.Namespace) -> dict[str, Any]:
    result = _initial_result(args)
    db = SessionLocal()
    try:
        ensure_default_distribution_accounts(db)
        asset = _create_asset(db)
        canonical = _create_approved_canonical_article(db, asset)
        output = generate_x_article_pack(
            db,
            int(asset.id),
            dist_schema.SocialDistributionGenerateXArticlePackRequest(
                actor="operator",
                article_url=args.article_url,
                teaser_include_article_url=args.include_article_url_in_teaser,
            ),
        )
        article_task, teaser_task, document = _load_generated_rows(db, output)
        article_task = _maybe_mark_article_live(db, article_task, args.article_url)
        teaser_publish, teaser_task = _maybe_publish_teaser(db, teaser_task, args)
        result.update(
            _result_payload(
                asset=asset,
                canonical=canonical,
                article_task=article_task,
                teaser_task=teaser_task,
                document=document,
                cover_image_path=output.cover_image_path,
                teaser_publish=teaser_publish.model_dump(mode="json")
                if teaser_publish
                else None,
                events=_events_for_asset(db, int(asset.id)),
            )
        )
        return result
    finally:
        db.close()


def _initial_result(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "started_at": utcnow().isoformat(),
        "article_url_input": args.article_url or None,
        "publish_teaser_requested": bool(args.publish_teaser),
        "include_article_url_in_teaser": bool(args.include_article_url_in_teaser),
    }


def _load_generated_rows(db, output):
    article_task = db.get(SocialDistributionTaskRow, output.article_task_id)
    teaser_task = db.get(SocialDistributionTaskRow, output.teaser_task_id)
    document = db.get(SocialDistributionDocumentRow, output.article_document_id)
    if article_task is None or teaser_task is None or document is None:
        raise RuntimeError("article_pack_generation_incomplete")
    return article_task, teaser_task, document


def _maybe_mark_article_live(
    db, article_task: SocialDistributionTaskRow, article_url: str
) -> SocialDistributionTaskRow:
    if not article_url:
        return article_task
    mark_distribution_task_live(
        db,
        int(article_task.id),
        dist_schema.SocialDistributionMarkLiveRequest(
            published_url=article_url,
            manual_result_note="X Article manually published in X Web.",
            actor="operator",
        ),
    )
    refreshed = db.get(SocialDistributionTaskRow, int(article_task.id))
    if refreshed is None:
        raise RuntimeError("article_task_missing_after_mark_live")
    return refreshed


def _maybe_publish_teaser(
    db, teaser_task: SocialDistributionTaskRow, args: argparse.Namespace
) -> tuple[Any | None, SocialDistributionTaskRow]:
    if not args.publish_teaser:
        return None, teaser_task
    teaser_publish = publish_distribution_task_to_x(
        db, int(teaser_task.id), actor="operator"
    )
    refreshed = db.get(SocialDistributionTaskRow, int(teaser_task.id))
    if refreshed is None:
        raise RuntimeError("teaser_task_missing_after_publish")
    return teaser_publish, refreshed


def _write_result(evidence_dir: Path, result: dict[str, Any]) -> Path:
    evidence_path = evidence_dir / "e2e-result.json"
    evidence_path.write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    return evidence_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--article-url",
        default="",
        help="Manual X Article URL to backfill after publishing in X Web.",
    )
    parser.add_argument(
        "--include-article-url-in-teaser",
        action="store_true",
        help="Include the manual Article URL in the API teaser post.",
    )
    parser.add_argument(
        "--confirm-link-inclusion",
        default="",
        help="Required as YES when the teaser should include the Article URL.",
    )
    parser.add_argument(
        "--publish-teaser",
        action="store_true",
        help="Perform the real official X API media upload and teaser post.",
    )
    parser.add_argument(
        "--confirm-real-x-publish",
        default="",
        help="Required as YES for --publish-teaser.",
    )
    parser.add_argument(
        "--evidence-dir",
        default=str(
            PROJECT_ROOT
            / "docs"
            / "archive"
            / "evidence"
            / "x-article-pack-e2e-2026-05-24"
        ),
        help="Directory for non-secret E2E evidence.",
    )
    return parser.parse_args()


def _evidence_dir(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _create_asset(db) -> SocialContentAssetRow:
    asset = SocialContentAssetRow(
        asset_type="article",
        source_type="manual",
        title=ARTICLE_TITLE,
        body=CANONICAL_BODY,
        summary=(
            "Introduce Synapse Network as payment rails for AI agents: discovery, "
            "metered API calls, budget control, settlement, and receipts."
        ),
        canonical_url="https://www.synapse-network.ai/",
        goal_key="x_article_pack_platform_intro",
        policy_check_json=json.dumps({"status": "passed", "source": "e2e_script"}),
        agent_metadata_json=json.dumps(
            {
                "source_of_truth": "e2e_x_article_pack",
                "target_url": "https://www.synapse-network.ai/",
            },
            sort_keys=True,
        ),
        status="draft",
        created_by="operator",
    )
    db.add(asset)
    db.flush()
    return asset


def _create_approved_canonical_article(
    db, asset: SocialContentAssetRow
) -> SocialDistributionDocumentRow:
    document = SocialDistributionDocumentRow(
        asset_id=int(asset.id),
        document_kind="canonical_article",
        title=ARTICLE_TITLE,
        body_markdown=CANONICAL_BODY,
        status="approved",
        version=1,
        metadata_json=json.dumps(
            {
                "generated_by": "e2e_x_article_pack",
                "approval_source": "operator_seeded_e2e",
            },
            sort_keys=True,
        ),
    )
    db.add(document)
    db.flush()
    return document


def _result_payload(
    *,
    asset: SocialContentAssetRow,
    canonical: SocialDistributionDocumentRow,
    article_task: SocialDistributionTaskRow | None,
    teaser_task: SocialDistributionTaskRow | None,
    document: SocialDistributionDocumentRow,
    cover_image_path: str | None,
    teaser_publish: dict[str, Any] | None,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    cover_exists = Path(str(cover_image_path or "")).is_file()
    return {
        "asset_id": int(asset.id),
        "canonical_document_id": int(canonical.id),
        "article_document_id": int(document.id),
        "article_task_id": int(article_task.id) if article_task else None,
        "article_task_status": article_task.status if article_task else None,
        "article_task_published_url": article_task.published_url
        if article_task
        else None,
        "teaser_task_id": int(teaser_task.id) if teaser_task else None,
        "teaser_task_status": teaser_task.status if teaser_task else None,
        "teaser_task_external_post_id": teaser_task.external_post_id
        if teaser_task
        else None,
        "teaser_task_published_url": teaser_task.published_url if teaser_task else None,
        "cover_image_path": cover_image_path,
        "cover_image_exists": cover_exists,
        "article_pack_document_status": document.status,
        "teaser_publish_result": teaser_publish,
        "events": events,
    }


def _events_for_asset(db, asset_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(SocialDistributionEventRow)
        .filter(SocialDistributionEventRow.asset_id == asset_id)
        .order_by(SocialDistributionEventRow.id.asc())
        .all()
    )
    return [
        {
            "id": int(row.id),
            "event_type": row.event_type,
            "summary": row.summary,
            "task_id": int(row.task_id) if row.task_id else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


if __name__ == "__main__":
    raise SystemExit(main())
