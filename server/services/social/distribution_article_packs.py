"""X Article publishing packs for human-gated long-form distribution."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server import schemas_social_distribution as dist_schema
from server.database import utcnow
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionAccountRow,
    SocialDistributionDocumentRow,
    SocialDistributionTaskRow,
)
from server.services.social.distribution import get_content_asset
from server.services.social.distribution_article_cover import write_article_cover_png
from server.services.social.distribution_core import _record_event
from server.services.social.distribution_documents import (
    approved_canonical_article_document,
    create_platform_draft_document,
)

ARTICLE_TITLE = "Synapse Network: Payment Rails for AI Agents"
ARTICLE_COVER_ALT = "Synapse Network dashboard concept showing AI agents discovering services, paying for APIs, and receiving receipts."
X_ARTICLES_URL = "https://x.com/compose/articles"


def generate_x_article_pack(
    db: Session,
    asset_id: int,
    body: dist_schema.SocialDistributionGenerateXArticlePackRequest,
) -> dist_schema.SocialDistributionGenerateXArticlePackOut:
    asset = db.get(SocialContentAssetRow, asset_id)
    if asset is None:
        raise ValueError("Content asset not found.")
    canonical = approved_canonical_article_document(db, asset)
    if canonical is None:
        raise ValueError(
            "canonical_article_required: approve the canonical article before generating an X Article pack."
        )
    account = _x_official_account(db)
    article_body = _article_body(asset=asset, canonical=canonical)
    pack = _article_pack_metadata(
        asset=asset,
        article_body=article_body,
        article_url=body.article_url,
    )
    article_task = _upsert_article_task(
        db=db,
        asset=asset,
        account=account,
        article_body=article_body,
        pack=pack,
    )
    teaser_task = _upsert_teaser_task(
        db=db,
        asset=asset,
        account=account,
        pack=pack,
        include_article_url=body.teaser_include_article_url,
    )
    document = _upsert_article_document(
        db, asset=asset, task=article_task, pack=pack, article_body=article_body
    )
    create_platform_draft_document(
        db,
        asset=asset,
        task=article_task,
        metadata={"article_pack_document_id": int(document.id)},
    )
    create_platform_draft_document(
        db,
        asset=asset,
        task=teaser_task,
        metadata={"article_pack_document_id": int(document.id)},
    )
    asset.status = "ready"
    asset.updated_at = utcnow()
    _record_event(
        db,
        asset,
        article_task,
        "x_article_pack_generated",
        body.actor,
        "Generated X Article pack with manual publish checklist and API teaser task.",
        {
            "article_task_id": int(article_task.id),
            "teaser_task_id": int(teaser_task.id),
            "article_document_id": int(document.id),
            "cover_image_path": str(pack["cover_image"]["local_path"]),
            "x_article_api_supported": False,
        },
    )
    db.commit()
    return dist_schema.SocialDistributionGenerateXArticlePackOut(
        asset=get_content_asset(db, int(asset.id)),
        article_task_id=int(article_task.id),
        teaser_task_id=int(teaser_task.id),
        article_document_id=int(document.id),
        cover_image_path=str(pack["cover_image"]["local_path"]),
    )


def _x_official_account(db: Session) -> SocialDistributionAccountRow:
    row = (
        db.query(SocialDistributionAccountRow)
        .filter(
            SocialDistributionAccountRow.platform == "x",
            SocialDistributionAccountRow.channel_key == "official",
        )
        .one_or_none()
    )
    if row is None:
        raise ValueError(
            "x_official_account_missing: configure X Official Account first."
        )
    return row


def _article_body(
    *, asset: SocialContentAssetRow, canonical: SocialDistributionDocumentRow
) -> str:
    body = str(canonical.body_markdown or asset.body or asset.summary or "").strip()
    intro = (
        "Synapse Network is settlement infrastructure for autonomous services: "
        "agents can discover provider APIs, call them with capped budgets, settle "
        "metered usage, and leave receipts a human operator can inspect later."
    )
    sections = [
        f"# {ARTICLE_TITLE}",
        "",
        intro,
        "",
        "## Why agents need payment rails",
        "",
        "Agents are starting to act like economic users. They can search, reason, "
        "call tools, and trigger workflows, but most payment systems still assume a "
        "human is sitting in front of a checkout form.",
        "",
        "Giving an agent an unlimited API key or credit card is the wrong default. "
        "The safer model is a budgeted rail: the agent can spend what it is allowed "
        "to spend, every call is metered, and the operator can inspect the result.",
        "",
        "## What Synapse Network does",
        "",
        "- Agents discover provider services through a registry.",
        "- Developers assign spend limits before the agent starts work.",
        "- Providers meter each paid API call.",
        "- Synapse records receipts so the operator can inspect what happened later.",
        "",
        "## How an agent uses it",
        "",
        "1. Open the Synapse dashboard.",
        "2. Connect a wallet or configure an agent key.",
        "3. Discover a provider service.",
        "4. Invoke the service with a capped budget.",
        "5. Review the receipt and evidence after the call.",
        "",
        "## What the operator sees",
        "",
        "The operator sees the state that matters after the agent acts: which "
        "service was called, how much budget was used, what receipt was produced, "
        "and whether the action should be trusted, retried, or escalated.",
        "",
        "## How providers publish services",
        "",
        "Providers can publish a service, define pricing, expose health/readiness "
        "evidence, and earn when agents call the API.",
        "",
        "## Why receipts matter",
        "",
        body,
        "",
        "Receipts are the difference between an agent doing invisible work and an "
        "agent producing evidence. They give teams something to audit, debug, and "
        "build trust around.",
        "",
        "Synapse keeps high-risk actions human-gated. Agents can execute useful "
        "work, but payments, production changes, and public distribution still need "
        "deterministic evidence and operator approval.",
    ]
    return "\n".join(sections).strip()


def _article_pack_metadata(
    *,
    asset: SocialContentAssetRow,
    article_body: str,
    article_url: str | None,
) -> dict[str, Any]:
    output_dir = (
        config.PROJECT_ROOT
        / "docs"
        / "archive"
        / "evidence"
        / "x-article-packs"
        / f"asset-{int(asset.id)}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    cover_path = output_dir / "synapse-network-x-article-cover.png"
    write_article_cover_png(cover_path)
    cover_image = {
        "kind": "cover_image",
        "local_path": str(cover_path),
        "width": 1200,
        "height": 675,
        "alt_text": ARTICLE_COVER_ALT,
        "prompt": "Black, cyan, and muted gold technical cover for Synapse Network payment rails for AI agents.",
    }
    inline_images = [
        {
            "label": "Dashboard overview",
            "target_url": "https://synapse-network.ai/dashboard/overview",
            "status": "operator_capture_or_playwright_screenshot",
        },
        {
            "label": "Service registry",
            "target_url": "https://synapse-network.ai/marketplace/registry.json",
            "status": "operator_capture_or_playwright_screenshot",
        },
    ]
    inline_gifs = [
        {
            "label": "Agent paid API flow",
            "flow": "dashboard -> discover service -> invoke/pay -> receipt evidence",
            "duration_seconds": "8-12",
            "status": "optional_operator_capture",
        }
    ]
    return {
        "format_kind": "x_article_pack",
        "x_format": "article_pack",
        "article_publish_path": "manual_x_web_articles",
        "x_article_api_supported": False,
        "article_title": ARTICLE_TITLE,
        "article_url": str(article_url or "").strip() or None,
        "article_character_count": len(article_body),
        "cover_image": cover_image,
        "inline_images": inline_images,
        "inline_gifs": inline_gifs,
        "media_manifest": [
            {
                **cover_image,
                "kind": "cover",
                "label": "Article cover",
                "placement_after_heading": "top",
                "dimensions": "1200x675",
                "status": "generated",
            },
            {
                **inline_images[0],
                "kind": "image",
                "placement_after_heading": "What the operator sees",
                "local_path": None,
                "dimensions": None,
            },
            {
                **inline_images[1],
                "kind": "image",
                "placement_after_heading": "How providers publish services",
                "local_path": None,
                "dimensions": None,
            },
            {
                **inline_gifs[0],
                "kind": "gif",
                "placement_after_heading": "How an agent uses it",
                "local_path": None,
                "target_url": "https://synapse-network.ai/dashboard/overview",
                "dimensions": None,
            },
        ],
        "manual_publish_checklist": [
            "Open X Articles from x.com using the Premium official account.",
            "Paste the title and Article body.",
            "Upload the cover image first.",
            "Add inline screenshots/GIFs where they improve comprehension.",
            "Publish manually, then paste the Article URL back into the Article task.",
            "Only publish the API teaser after the Article URL is recorded, or choose a no-link teaser.",
        ],
        "x_articles_url": X_ARTICLES_URL,
    }


def _upsert_article_task(
    *,
    db: Session,
    asset: SocialContentAssetRow,
    account: SocialDistributionAccountRow,
    article_body: str,
    pack: dict[str, Any],
) -> SocialDistributionTaskRow:
    task = _find_or_create_task(db, asset, account, "x_article_manual_publish")
    task.status = "needs_manual_article_publish"
    task.platform_title = str(pack["article_title"])
    task.platform_body = article_body
    task.operator_checklist = "\n".join(
        str(item) for item in pack["manual_publish_checklist"]
    )
    task.submission_url = X_ARTICLES_URL
    task.failure_summary = None
    task.metadata_json = json.dumps(
        {
            "format_kind": "x_article_pack",
            "x_format": "article_pack",
            "article_pack": pack,
            "manual_publish_required": True,
            "api_publish_supported": False,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    task.updated_at = utcnow()
    return task


def _upsert_teaser_task(
    *,
    db: Session,
    asset: SocialContentAssetRow,
    account: SocialDistributionAccountRow,
    pack: dict[str, Any],
    include_article_url: bool,
) -> SocialDistributionTaskRow:
    task = _find_or_create_task(db, asset, account, "x_article_teaser")
    article_url = str(pack.get("article_url") or "").strip()
    teaser = (
        "AI agents do not just need tools. They need payment rails.\n\n"
        "Synapse Network lets agents discover services, pay for metered API calls, and keep receipts a human operator can inspect later."
    )
    if include_article_url and article_url:
        teaser = f"{teaser}\n\nFull Article: {article_url}"
    task.status = "needs_review"
    task.platform_title = "Synapse Network: Payment Rails for AI Agents"
    task.platform_body = teaser
    task.operator_checklist = (
        "Human Gate required. This is an API teaser Post, not the X Article itself. "
        "Upload the cover image through official X media upload, then publish the teaser."
    )
    task.submission_url = "https://x.com/compose/post"
    task.failure_summary = None
    task.metadata_json = json.dumps(
        {
            "format_kind": "x_article_teaser",
            "target_length": "single X post with cover image",
            "character_count": len(teaser),
            "weighted_counts": [len(teaser)],
            "x_format": "single",
            "tweets": [teaser],
            "article_pack": pack,
            "article_task_action": "x_article_manual_publish",
            "x_teaser_media": {
                "local_path": pack["cover_image"]["local_path"],
                "alt_text": pack["cover_image"]["alt_text"],
                "kind": "cover_image",
            },
            "has_media": True,
            "has_url": bool(include_article_url and article_url),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    task.updated_at = utcnow()
    return task


def _upsert_article_document(
    db: Session,
    *,
    asset: SocialContentAssetRow,
    task: SocialDistributionTaskRow,
    pack: dict[str, Any],
    article_body: str,
) -> SocialDistributionDocumentRow:
    existing = (
        db.query(SocialDistributionDocumentRow)
        .filter(
            SocialDistributionDocumentRow.asset_id == int(asset.id),
            SocialDistributionDocumentRow.task_id == int(task.id),
            SocialDistributionDocumentRow.document_kind == "x_article_pack",
            SocialDistributionDocumentRow.platform == "x",
            SocialDistributionDocumentRow.channel_key == "official",
        )
        .one_or_none()
    )
    metadata = {"generated_by": "x_article_pack_v1", **pack}
    if existing:
        existing.version = int(existing.version or 1) + 1
        existing.title = str(pack["article_title"])
        existing.body_markdown = article_body
        existing.status = "generated"
        existing.metadata_json = json.dumps(
            metadata, ensure_ascii=False, sort_keys=True
        )
        existing.updated_at = utcnow()
        return existing
    row = SocialDistributionDocumentRow(
        asset_id=int(asset.id),
        task_id=int(task.id),
        document_kind="x_article_pack",
        platform="x",
        channel_key="official",
        title=str(pack["article_title"]),
        body_markdown=article_body,
        status="generated",
        metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    )
    db.add(row)
    db.flush()
    return row


def _find_or_create_task(
    db: Session,
    asset: SocialContentAssetRow,
    account: SocialDistributionAccountRow,
    action: str,
) -> SocialDistributionTaskRow:
    existing = (
        db.query(SocialDistributionTaskRow)
        .filter(
            SocialDistributionTaskRow.asset_id == int(asset.id),
            SocialDistributionTaskRow.account_id == int(account.id),
            SocialDistributionTaskRow.action == action,
        )
        .one_or_none()
    )
    if existing:
        return existing
    row = SocialDistributionTaskRow(
        asset_id=int(asset.id),
        account_id=int(account.id),
        platform="x",
        channel_key=account.channel_key,
        action=action,
        submission_url=account.signup_url,
    )
    db.add(row)
    db.flush()
    return row
