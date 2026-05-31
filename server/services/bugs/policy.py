"""Bug workbench policy helpers for evidence and next actions."""

from __future__ import annotations

import json

from server.database import BugFixAttemptRow, BugRecordRow
from server.services.bugs.serializer import json_loads


def requires_screenshot(row: BugRecordRow) -> bool:
    metadata = json_loads(row.metadata_json, {})
    if bool(metadata.get("requires_screenshot_verification")):
        return True
    text = " ".join(
        [
            str(row.title or ""),
            str(row.summary or ""),
            json.dumps(metadata, ensure_ascii=False),
        ]
    ).lower()
    return any(
        token in text for token in ("frontend", "ui", "page", "screenshot", "browser")
    )


def verification_status(payload: dict[str, object]) -> str:
    status = str(payload.get("status") or "fixed_pending_verification").strip()
    if status in {"fixed_pending_verification", "verified", "failed"}:
        return status
    raise ValueError(
        "verification status must be fixed_pending_verification|verified|failed"
    )


def _has_verification_attempt(attempt: BugFixAttemptRow | None) -> bool:
    return attempt is not None and str(attempt.status or "") == "verified"


def _has_verification_commands(attempt: BugFixAttemptRow) -> bool:
    return bool(json_loads(attempt.verification_commands_json, []))


def _has_commit_or_pr(attempt: BugFixAttemptRow) -> bool:
    return bool(
        str(attempt.commit_sha or "").strip() or str(attempt.pr_url or "").strip()
    )


def _has_required_screenshots(row: BugRecordRow, attempt: BugFixAttemptRow) -> bool:
    if not requires_screenshot(row):
        return True
    return bool(json_loads(attempt.verification_screenshots_json, []))


def close_missing_requirements(
    row: BugRecordRow, attempt: BugFixAttemptRow | None
) -> list[str]:
    if not _has_verification_attempt(attempt):
        return ["verified_fix_attempt"]
    if attempt is None:
        return ["verified_fix_attempt"]
    checks = [
        ("verification_commands", _has_verification_commands(attempt)),
        ("commit_or_pr", _has_commit_or_pr(attempt)),
        ("screenshot", _has_required_screenshots(row, attempt)),
    ]
    return [name for name, ok in checks if not ok]


def ensure_close_evidence(row: BugRecordRow, attempt: BugFixAttemptRow | None) -> None:
    missing = close_missing_requirements(row, attempt)
    if not missing:
        return
    if "verified_fix_attempt" in missing:
        raise ValueError("bug requires a verified fix attempt before close")
    if "verification_commands" in missing:
        raise ValueError("bug requires verification command evidence before close")
    if "commit_or_pr" in missing:
        raise ValueError("bug requires a commit or PR before close")
    if "screenshot" in missing:
        raise ValueError("bug requires screenshot verification before close")


def allowed_next_actions(
    row: BugRecordRow, attempt: BugFixAttemptRow | None
) -> list[str]:
    status = str(row.status or "").strip()
    if attempt is None and status in {"open", "triaged", "ready_for_agent", "reopened"}:
        return ["claim", "materialize_requirement"]
    actions: list[str] = []
    if status not in {"closed", "duplicate", "wontfix"}:
        actions.extend(["link_fix", "verify", "reopen"])
    if not close_missing_requirements(row, attempt):
        actions.append("close")
    return actions
