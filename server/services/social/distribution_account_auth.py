"""Computed account readiness for human-gated distribution publishing."""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from server import schemas_social_distribution as dist_schema
from server.database import utcnow
from server.database_social_distribution import SocialDistributionAccountRow
from server.services.social.distribution import ensure_default_distribution_accounts
from server.services.social.publishing import SocialPublishError, x_oauth_token_provider

OFFICIAL_API_PLATFORMS = {"x", "devto", "dev", "reddit", "hashnode"}
BROWSER_ASSISTED_PLATFORMS = {
    "hacker_news",
    "v2ex",
    "hashnode",
    "product_hunt",
    "reddit",
}
MANUAL_ONLY_PLATFORMS = {"hacker_news", "v2ex", "product_hunt"}


def distribution_account_auth_statuses(
    db: Session,
    platform: str | None = None,
    account_id: int | None = None,
) -> dist_schema.SocialDistributionAccountAuthStatusListOut:
    if db.query(SocialDistributionAccountRow).count() == 0:
        ensure_default_distribution_accounts(db)
    query = db.query(SocialDistributionAccountRow)
    if platform:
        query = query.filter(
            SocialDistributionAccountRow.platform == _normalize_platform(platform)
        )
    if account_id is not None:
        query = query.filter(SocialDistributionAccountRow.id == int(account_id))
    rows = query.order_by(
        SocialDistributionAccountRow.priority.asc(),
        SocialDistributionAccountRow.platform.asc(),
        SocialDistributionAccountRow.id.asc(),
    ).all()
    return dist_schema.SocialDistributionAccountAuthStatusListOut(
        items=[_account_auth_status(row) for row in rows],
        generated_at=utcnow(),
    )


def _account_auth_status(
    row: SocialDistributionAccountRow,
) -> dist_schema.SocialDistributionAccountAuthStatusOut:
    platform = _normalize_platform(row.platform)
    capabilities = _capabilities(row.api_capability)
    private_adapter = _private_web_adapter_enabled()
    blockers: list[str] = []
    api_status = _api_status(row, platform, capabilities, blockers)
    oauth_status: str | None = None
    auth_message: str | None = None
    requires_authorization = False
    checked_at = utcnow()
    if platform == "x" and api_status == "task_preflight_required":
        api_status, oauth_status, auth_message, requires_authorization = (
            _x_oauth_live_status(blockers)
        )
    browser_status = _browser_status(row, platform, blockers)
    publish_path = _publish_path(platform, api_status, browser_status)
    return dist_schema.SocialDistributionAccountAuthStatusOut(
        account_id=int(row.id),
        platform=platform,
        channel_key=row.channel_key,
        display_name=row.display_name,
        login_url=row.signup_url,
        publish_path=publish_path,
        api_status=api_status,
        browser_status=browser_status,
        api_supported=_api_supported(platform, capabilities),
        can_publish_via_api=publish_path == "official_api",
        can_use_browser_assist=publish_path == "browser_assisted",
        private_web_adapter_enabled=private_adapter,
        blockers=blockers,
        next_action=_next_action(publish_path, blockers),
        oauth_status=oauth_status,
        requires_authorization=requires_authorization,
        auth_message=auth_message,
        last_checked_at=checked_at,
    )


def _api_status(
    row: SocialDistributionAccountRow,
    platform: str,
    capabilities: set[str],
    blockers: list[str],
) -> str:
    if platform in MANUAL_ONLY_PLATFORMS:
        return "unsupported"
    if platform not in OFFICIAL_API_PLATFORMS:
        return "unsupported"
    if platform == "x" and row.publish_mode == "api_human_gated":
        return _x_api_status(capabilities, blockers)
    if row.publish_mode != "api_human_gated":
        if _api_supported(platform, capabilities):
            blockers.append("api_credential_not_configured")
            return "available_not_configured"
        return "manual_only"
    if not row.credential_ref:
        blockers.append("credential_ref_missing")
        return "missing_secret"
    return _configured_api_status(row, platform, capabilities, blockers)


def _browser_status(
    row: SocialDistributionAccountRow,
    platform: str,
    blockers: list[str],
) -> str:
    if row.status in {"paused", "retired"}:
        blockers.append(f"account_{row.status}")
        return "blocked"
    if _v2ex_balance_blocked(row, platform):
        blockers.append("v2ex_insufficient_balance")
        return "blocked"
    if platform == "product_hunt":
        blockers.append("product_hunt_launch_requires_manual_operator_flow")
        return "manual_required"
    if _hashnode_browser_setup_missing(row, platform):
        blockers.append("hashnode_blog_or_publication_not_configured")
        return "manual_setup_required"
    return _generic_browser_status(row, platform, blockers)


def _x_api_status(capabilities: set[str], blockers: list[str]) -> str:
    if "post" not in capabilities:
        blockers.append("x_api_capability_missing_post")
        return "missing_capability"
    return "task_preflight_required"


def _x_oauth_live_status(blockers: list[str]) -> tuple[str, str, str, bool]:
    try:
        token = x_oauth_token_provider.get_access_token()
    except SocialPublishError as exc:
        oauth_status = _x_oauth_status_from_error(exc)
        blockers.append(oauth_status)
        return "blocked", oauth_status, exc.summary, True
    message = "X OAuth refresh token is valid."
    if token.refresh_token_rotated:
        message = "X OAuth refresh token is valid and was rotated locally."
    return "ready", "authorized", message, False


def _x_oauth_status_from_error(exc: SocialPublishError) -> str:
    summary = str(exc.summary or "").lower()
    if exc.kind == "x_refresh_failed":
        return "invalid_refresh_token"
    if "local secret" in summary or "not found" in summary or "missing" in summary:
        return "missing_local_secret"
    if exc.kind == "x_auth_failed":
        return "needs_authorization"
    return "error"


def _configured_api_status(
    row: SocialDistributionAccountRow,
    platform: str,
    capabilities: set[str],
    blockers: list[str],
) -> str:
    if platform == "hashnode" and "article" in capabilities and not row.profile_url:
        blockers.append("hashnode_publication_or_blog_missing")
        return "manual_setup_required"
    if platform == "reddit" and "post" in capabilities:
        return "ready"
    if capabilities & {"post", "article"}:
        return "ready"
    blockers.append("api_capability_missing")
    return "missing_capability"


def _v2ex_balance_blocked(row: SocialDistributionAccountRow, platform: str) -> bool:
    notes = str(row.notes or "").lower()
    return platform == "v2ex" and (
        "0 coin" in notes or "0.0" in notes or "余额不足" in notes
    )


def _hashnode_browser_setup_missing(
    row: SocialDistributionAccountRow, platform: str
) -> bool:
    return platform == "hashnode" and not row.profile_url


def _generic_browser_status(
    row: SocialDistributionAccountRow,
    platform: str,
    blockers: list[str],
) -> str:
    if (
        row.status in {"active", "registered"}
        and platform in BROWSER_ASSISTED_PLATFORMS
    ):
        return "browser_session_ready"
    if platform in BROWSER_ASSISTED_PLATFORMS:
        blockers.append("browser_login_not_verified")
        return "need_login"
    return "manual_only"


def _publish_path(platform: str, api_status: str, browser_status: str) -> str:
    if api_status in {"ready", "task_preflight_required"}:
        return "official_api"
    if browser_status == "browser_session_ready":
        return "browser_assisted"
    if browser_status in {"blocked", "manual_setup_required"}:
        return "blocked"
    if platform in MANUAL_ONLY_PLATFORMS or browser_status in {
        "manual_required",
        "need_login",
    }:
        return "manual_only"
    return "blocked" if api_status.startswith("missing") else "manual_only"


def _next_action(publish_path: str, blockers: list[str]) -> str:
    if publish_path == "official_api":
        return "API publish can proceed after task-level Human Gate."
    if publish_path == "browser_assisted":
        return "Use browser-assisted publishing; operator must confirm final submit."
    if blockers:
        return "Resolve blocker: " + ", ".join(blockers)
    return "Manual publish required; copy content and mark live after posting."


def _capabilities(value: str | None) -> set[str]:
    return {item.strip() for item in str(value or "").split(",") if item.strip()}


def _api_supported(platform: str, capabilities: set[str]) -> bool:
    return platform in OFFICIAL_API_PLATFORMS and bool(
        capabilities & {"post", "article", "long_post"}
    )


def _private_web_adapter_enabled() -> bool:
    return os.environ.get("SOCIAL_PRIVATE_WEB_ADAPTER", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _normalize_platform(platform: str) -> str:
    return "devto" if platform.strip() == "dev" else platform.strip()
