#!/usr/bin/env python3
"""Scan Gmail inbox for provider replies and draft human-reviewed responses."""

from __future__ import annotations

import argparse
import email
import imaplib
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from email.message import Message
from email.policy import default
from email.utils import parsedate_to_datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.database import SessionLocal, engine
from server.database_growth import GrowthProviderReplyRow
from server.services.growth.provider_reply_monitor import (
    InboxEmail,
    scan_provider_replies,
)
from scripts.growth.local_env import load_dotenv

DEFAULT_IMAP_HOST = "imap.gmail.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_RUN_HISTORY = (
    PROJECT_ROOT / "server" / "logs" / "growth-provider-reply-monitor.jsonl"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true", help="Persist matched replies and drafts."
    )
    parser.add_argument(
        "--days", type=int, default=14, help="How far back to scan Gmail INBOX."
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="Maximum inbox messages to fetch."
    )
    parser.add_argument(
        "--fixture-json",
        default="",
        help="Read inbox messages from fixture JSON instead of Gmail.",
    )
    parser.add_argument(
        "--watch", action="store_true", help="Keep scanning Gmail on a fixed interval."
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=900,
        help="Watch mode interval between scans.",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Stop watch mode after N runs. 0 means no limit.",
    )
    parser.add_argument(
        "--run-history-jsonl",
        default=str(DEFAULT_RUN_HISTORY),
        help="Append structured run history JSONL. Set to empty string to disable.",
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    GrowthProviderReplyRow.__table__.create(bind=engine, checkfirst=True)
    runs = 0
    last_code = 0
    while True:
        runs += 1
        last_code = run_once(args)
        if not args.watch:
            return last_code
        if args.max_runs and runs >= args.max_runs:
            return last_code
        time.sleep(max(args.interval_seconds, 60))


def run_once(args: argparse.Namespace) -> int:
    started_at = datetime.now(UTC)
    record: dict[str, object] = {
        "event": "growth_provider_reply_monitor_run",
        "mode": "apply" if args.apply else "dry_run",
        "source": "fixture" if args.fixture_json else "gmail_imap",
        "dry_run": not args.apply,
        "days": int(args.days),
        "limit": int(args.limit),
        "started_at": started_at.isoformat(),
    }
    try:
        emails = (
            load_fixture(Path(args.fixture_json))
            if args.fixture_json
            else fetch_gmail_inbox(days=args.days, limit=args.limit)
        )
        with SessionLocal() as db:
            result = scan_provider_replies(db, emails, dry_run=not args.apply)
        record.update(
            {
                "status": "succeeded",
                "scanned": result.scanned,
                "matched": result.matched,
                "created": result.created,
                "skipped_existing": result.skipped_existing,
                "skipped_unmatched": result.skipped_unmatched,
                "reply_ids": result.reply_ids,
            }
        )
        emit(record)
        return 0
    except SystemExit as exc:
        message = str(exc)
        record.update(
            {"status": "failed", "error_type": "SystemExit", "error_message": message}
        )
        emit(record, stderr=True)
        return int(exc.code) if isinstance(exc.code, int) and exc.code else 1
    except Exception as exc:
        record.update(
            {
                "status": "failed",
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            }
        )
        emit(record, stderr=True)
        return 1
    finally:
        completed_at = datetime.now(UTC)
        record["completed_at"] = completed_at.isoformat()
        record["duration_ms"] = round(
            (completed_at - started_at).total_seconds() * 1000, 2
        )
        append_run_history(args.run_history_jsonl, record)


def emit(record: dict[str, object], *, stderr: bool = False) -> None:
    safe = {
        key: value
        for key, value in record.items()
        if key not in {"started_at", "completed_at", "duration_ms", "event"}
    }
    print(
        json.dumps(safe, ensure_ascii=False, sort_keys=True),
        file=sys.stderr if stderr else sys.stdout,
    )


def append_run_history(path_value: str, record: dict[str, object]) -> None:
    if not path_value.strip():
        return
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def fetch_gmail_inbox(*, days: int, limit: int) -> list[InboxEmail]:
    username, password = gmail_imap_credentials()
    host = os.environ.get("GMAIL_IMAP_HOST", DEFAULT_IMAP_HOST).strip()
    port = int(os.environ.get("GMAIL_IMAP_PORT", str(DEFAULT_IMAP_PORT)).strip())
    since = (datetime.now(UTC) - timedelta(days=max(days, 1))).strftime("%d-%b-%Y")
    try:
        with imaplib.IMAP4_SSL(host, port, timeout=30) as mailbox:
            mailbox.login(username, password)
            mailbox.select("INBOX", readonly=True)
            return fetch_inbox_messages(mailbox, since=since, limit=limit)
    except OSError as exc:
        raise SystemExit(
            f"Gmail IMAP connection failed for {host}:{port}: {exc}"
        ) from exc
    except imaplib.IMAP4.error as exc:
        raise SystemExit(f"Gmail IMAP operation failed: {exc}") from exc


def gmail_imap_credentials() -> tuple[str, str]:
    username = first_env("GMAIL_IMAP_USERNAME", "GMAIL_SMTP_USERNAME")
    password = first_env("GMAIL_IMAP_APP_PASSWORD", "GMAIL_SMTP_APP_PASSWORD")
    if username and password:
        return username, password
    raise SystemExit(
        "Missing Gmail IMAP credentials. Set GMAIL_IMAP_USERNAME and "
        "GMAIL_IMAP_APP_PASSWORD, or reuse GMAIL_SMTP_USERNAME and "
        "GMAIL_SMTP_APP_PASSWORD from the ignored .env."
    )


def fetch_inbox_messages(
    mailbox: imaplib.IMAP4_SSL, *, since: str, limit: int
) -> list[InboxEmail]:
    status, data = mailbox.search(None, "SINCE", since)
    if status != "OK":
        raise SystemExit(f"Gmail search failed: {status}")
    emails: list[InboxEmail] = []
    for message_id in reversed(data[0].split()[-max(limit, 1) :]):
        raw = fetch_message_bytes(mailbox, message_id)
        if raw:
            emails.append(
                inbox_email_from_message(raw, fallback_id=message_id.decode())
            )
    return emails


def fetch_message_bytes(mailbox: imaplib.IMAP4_SSL, message_id: bytes) -> bytes | None:
    status, payload = mailbox.fetch(message_id, "(RFC822)")
    if status != "OK":
        return None
    return next(
        (item[1] for item in payload if isinstance(item, tuple) and len(item) == 2),
        None,
    )


def inbox_email_from_message(raw: bytes, *, fallback_id: str) -> InboxEmail:
    message = email.message_from_bytes(raw, policy=default)
    body = extract_text(message)
    mailbox_message_id = (message.get("Message-ID") or fallback_id).strip()
    received_at = parse_message_datetime(message)
    return InboxEmail(
        mailbox_message_id=mailbox_message_id,
        thread_id=message.get("Thread-ID", "") or message.get("References", "") or "",
        from_header=message.get("From", ""),
        subject=message.get("Subject", ""),
        snippet=body[:240],
        body_text=body,
        received_at=received_at,
    )


def extract_text(message: Message) -> str:
    if message.is_multipart():
        return extract_multipart_text(message)
    return extract_leaf_text(message)


def extract_multipart_text(message: Message) -> str:
    parts: list[str] = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_content_type() != "text/plain":
            continue
        text = extract_leaf_text(part)
        if text:
            parts.append(text)
    return "\n".join(part.strip() for part in parts if part.strip())


def extract_leaf_text(message: Message) -> str:
    payload = message.get_payload(decode=True)
    if payload:
        return payload.decode(
            message.get_content_charset() or "utf-8", errors="replace"
        ).strip()
    return str(message.get_payload() or "").strip()


def parse_message_datetime(message: Message) -> datetime | None:
    raw = message.get("Date", "")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_fixture(path: Path) -> list[InboxEmail]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload if isinstance(payload, list) else payload.get("items", [])
    return [fixture_email(item, index) for index, item in enumerate(items)]


def fixture_email(item: dict[str, object], index: int) -> InboxEmail:
    return InboxEmail(
        mailbox_message_id=str(item.get("mailbox_message_id") or f"fixture-{index}"),
        thread_id=str(item.get("thread_id") or ""),
        from_header=str(item.get("from_header") or item.get("from") or ""),
        subject=str(item.get("subject") or ""),
        snippet=str(item.get("snippet") or ""),
        body_text=fixture_body_text(item),
        received_at=fixture_received_at(item),
    )


def fixture_body_text(item: dict[str, object]) -> str:
    for key in ("body_text", "body", "snippet"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def fixture_received_at(item: dict[str, object]) -> datetime | None:
    value = item.get("received_at")
    return datetime.fromisoformat(str(value)) if value else None


def first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
