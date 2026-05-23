"""Platform-specific publish lint for social distribution tasks."""

from __future__ import annotations

import re

from pydantic import BaseModel


BLOCKED = "blocked"
PASSED = "passed"
WARNING = "warning"

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_URL_RE = re.compile(r"https?://\S+")
_INLINE_HEADING_RE = re.compile(r"[^\n]\s+#{1,6}\s+\S")
_HEADING_RE = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
_MARKETING_PHRASES = (
    "stripe for ai agents",
    "game-changer",
    "revolutionary",
    "disruptive",
    "ultimate platform",
)


class PublishLintIssue(BaseModel):
    code: str
    message: str


class PublishLintResult(BaseModel):
    status: str
    issues: list[PublishLintIssue]
    warnings: list[PublishLintIssue]
    platform: str
    channel_key: str


def lint_distribution_task(
    *,
    platform: str,
    channel_key: str,
    title: str | None,
    body: str | None,
    metadata: dict[str, object] | None = None,
) -> PublishLintResult:
    """Return a deterministic pre-publish lint result.

    The result is intentionally metadata-shaped so it can be persisted without a
    schema migration and displayed by the operator UI.
    """

    metadata = metadata or {}
    normalized = "devto" if platform == "dev" else platform
    title_text = str(title or "").strip()
    body_text = str(body or "").strip()
    issues: list[PublishLintIssue] = []
    warnings: list[PublishLintIssue] = []
    platform_issues, platform_warnings = _platform_lint(
        normalized, title_text, body_text
    )

    issues.extend(_language_issues(normalized, title_text, body_text, metadata))
    issues.extend(platform_issues)
    warnings.extend(platform_warnings)

    status = BLOCKED if issues else WARNING if warnings else PASSED
    return PublishLintResult(
        status=status,
        issues=issues,
        warnings=warnings,
        platform=normalized,
        channel_key=channel_key,
    )


def lint_summary(result: PublishLintResult) -> str:
    if result.issues:
        first = result.issues[0]
        return first.message or first.code or "publish lint blocked"
    if result.warnings:
        first = result.warnings[0]
        return first.message or first.code or "publish lint warning"
    return "Publish lint passed."


def _platform_lint(
    platform: str,
    title: str,
    body: str,
) -> tuple[list[PublishLintIssue], list[PublishLintIssue]]:
    issue_checks = {
        "devto": _markdown_article_issues,
        "hashnode": _markdown_article_issues,
        "reddit": _reddit_issues,
        "hacker_news": lambda value: _hn_issues(title, value),
    }
    warning_checks = {
        "x": _x_warnings,
        "reddit": _reddit_warnings,
        "hacker_news": _hn_warnings,
    }
    issue_check = issue_checks.get(platform, _no_issues)
    warning_check = warning_checks.get(platform, _no_issues)
    return issue_check(body), warning_check(body)


def _no_issues(_body: str) -> list[PublishLintIssue]:
    return []


def _language_issues(
    platform: str,
    title: str,
    body: str,
    metadata: dict[str, object],
) -> list[PublishLintIssue]:
    if platform not in {"x", "devto", "hashnode", "hacker_news", "reddit"}:
        return []
    if not _CJK_RE.search(f"{title}\n{body}") or metadata.get("allow_bilingual"):
        return []
    return [
        _issue(
            "language_mismatch",
            "English platform draft contains CJK characters; set allow_bilingual=true only when intentional.",
        )
    ]


def _markdown_article_issues(body: str) -> list[PublishLintIssue]:
    issues: list[PublishLintIssue] = []
    if _INLINE_HEADING_RE.search(body):
        issues.append(
            _issue(
                "markdown_heading_collapsed",
                "Markdown heading appears inline with paragraph text; add blank lines before headings.",
            )
        )
    for match in _HEADING_RE.finditer(body):
        start, end = match.span()
        before = body[max(0, start - 2) : start]
        after = body[end : min(len(body), end + 2)]
        if start > 0 and before != "\n\n":
            issues.append(
                _issue(
                    "markdown_heading_missing_blank_before",
                    "Markdown headings need a blank line before them for DEV/Hashnode rendering.",
                )
            )
            break
        if end < len(body) and after != "\n\n":
            issues.append(
                _issue(
                    "markdown_heading_missing_blank_after",
                    "Markdown headings need a blank line after them for DEV/Hashnode rendering.",
                )
            )
            break
    return issues


def _x_warnings(body: str) -> list[PublishLintIssue]:
    warnings: list[PublishLintIssue] = []
    first_fold = body[:280]
    if "\n\n" not in first_fold:
        warnings.append(
            _issue(
                "x_first_fold_dense",
                "X first fold has no paragraph break; add whitespace before publishing.",
            )
        )
    if len(_URL_RE.findall(body)) > 1:
        warnings.append(
            _issue(
                "x_too_many_links",
                "X draft has more than one link; keep the long post focused.",
            )
        )
    if body.count("#") > 1:
        warnings.append(
            _issue(
                "x_hashtag_heavy",
                "X draft uses multiple hashtags; avoid marketing-style hashtag stuffing.",
            )
        )
    return warnings


def _reddit_issues(body: str) -> list[PublishLintIssue]:
    if not _URL_RE.search(body):
        return []
    return [
        _issue(
            "reddit_link_in_body",
            "Reddit discussion drafts should not put product links in the post body; move links to a comment when subreddit rules allow it.",
        )
    ]


def _reddit_warnings(body: str) -> list[PublishLintIssue]:
    if len(body) <= 3200:
        return []
    return [
        _issue(
            "reddit_body_long",
            "Reddit draft is long for a discussion post; consider narrowing it to one technical question.",
        )
    ]


def _hn_issues(title: str, body: str) -> list[PublishLintIssue]:
    combined = f"{title}\n{body}".lower()
    if not any(phrase in combined for phrase in _MARKETING_PHRASES):
        return []
    return [
        _issue(
            "hn_marketing_framing",
            "Hacker News drafts should be neutral engineering submissions, not product positioning.",
        )
    ]


def _hn_warnings(body: str) -> list[PublishLintIssue]:
    if len(body) <= 1200:
        return []
    return [
        _issue(
            "hn_comment_long",
            "HN first comment is long; keep it terse and evidence-led.",
        )
    ]


def _issue(code: str, message: str) -> PublishLintIssue:
    return PublishLintIssue(code=code, message=message)
