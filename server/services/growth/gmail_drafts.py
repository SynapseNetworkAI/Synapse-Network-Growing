from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy.orm import Session

from server import config
from server.database_growth import (
    GrowthLeadRow,
    GrowthOutreachEventRow,
    GrowthOutreachMessageRow,
)
from server.schemas_growth import GrowthOutreachMessageOut
from server.services.growth.serializer import json_dumps, json_loads, message_out
from server.services.local_secrets import (
    LocalSecretStoreError,
    read_latest_local_secret,
)


class GmailDraftError(RuntimeError):
    """Raised when Gmail draft creation cannot safely proceed."""


def create_gmail_draft(
    db: Session,
    message_id: int,
    *,
    actor: str,
    metadata: dict[str, object] | None = None,
) -> GrowthOutreachMessageOut:
    message = _message_or_404(db, message_id)
    if message.status != "approved":
        raise GmailDraftError("gmail_draft_requires_approved_message")
    lead = _lead_or_404(db, message.lead_id)
    message_metadata = json_loads(message.metadata_json, {})
    if message_metadata.get("gmail_draft_id"):
        return message_out(message)
    contact_email = _contact_email(lead, message_metadata)
    if not contact_email:
        raise GmailDraftError("gmail_draft_requires_trusted_contact_email")

    access_token = _gmail_access_token(db)
    gmail_payload = _post_gmail_draft(
        access_token=access_token,
        sender=str(config.GMAIL_SENDER_EMAIL or "me").strip() or "me",
        to_email=contact_email,
        subject=message.subject,
        body=message.body,
    )
    draft_id = str(gmail_payload.get("id") or "").strip()
    gmail_message = (
        gmail_payload.get("message")
        if isinstance(gmail_payload.get("message"), dict)
        else {}
    )
    if not draft_id:
        raise GmailDraftError("gmail_draft_create_failed_missing_id")

    created_at = datetime.now(timezone.utc).isoformat()
    message_metadata.update(
        {
            "gmail_status": "draft_created",
            "gmail_draft_id": draft_id,
            "gmail_message_id": str(gmail_message.get("id") or ""),
            "gmail_thread_id": str(gmail_message.get("threadId") or ""),
            "draft_url": f"https://mail.google.com/mail/u/0/#drafts?compose={draft_id}",
            "contact_email": contact_email,
            "gmail_created_at": created_at,
        }
    )
    if metadata:
        message_metadata["gmail_operator_metadata"] = dict(metadata)
    message.metadata_json = json_dumps(message_metadata)
    message.status = "queued"
    lead.status = "queued"
    db.add(
        GrowthOutreachEventRow(
            lead_id=lead.id,
            message_id=message.id,
            event_type="gmail_draft_created",
            actor=actor or "operator",
            from_status="approved",
            to_status="queued",
            summary="Gmail draft created; no email was sent automatically.",
            metadata_json=json_dumps(
                {
                    "gmail_draft_id": draft_id,
                    "contact_email": contact_email,
                    "auto_send": False,
                }
            ),
        )
    )
    db.commit()
    return message_out(message)


def _gmail_access_token(db: Session) -> str:
    client_id = str(config.GMAIL_OAUTH_CLIENT_ID or "").strip()
    client_secret = str(config.GMAIL_OAUTH_CLIENT_SECRET or "").strip()
    if not client_id or not client_secret:
        raise GmailDraftError(
            "gmail_auth_required: configure GMAIL_OAUTH_CLIENT_ID and GMAIL_OAUTH_CLIENT_SECRET"
        )
    try:
        refresh_token = read_latest_local_secret(
            db, config.GMAIL_OAUTH_REFRESH_TOKEN_LOCAL_KEY
        )
    except LocalSecretStoreError as exc:
        raise GmailDraftError(f"gmail_auth_required: {exc}") from exc
    response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if response.status_code >= 400:
        raise GmailDraftError(
            f"gmail_auth_required: token refresh failed ({response.status_code})"
        )
    token = str(response.json().get("access_token") or "").strip()
    if not token:
        raise GmailDraftError(
            "gmail_auth_required: token refresh did not return access_token"
        )
    return token


def _post_gmail_draft(
    *,
    access_token: str,
    sender: str,
    to_email: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    message = EmailMessage()
    message["To"] = to_email
    if sender and sender != "me":
        message["From"] = sender
    message["Subject"] = subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
    response = httpx.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"message": {"raw": raw}},
        timeout=30,
    )
    if response.status_code >= 400:
        raise GmailDraftError(
            f"gmail_draft_create_failed: Gmail API returned {response.status_code}"
        )
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _contact_email(lead: GrowthLeadRow, message_metadata: dict[str, Any]) -> str:
    candidate = str(message_metadata.get("contact_email") or "").strip()
    if candidate and "noreply.github.com" not in candidate.lower():
        return candidate
    try:
        parsed = json.loads(lead.contact_channels_json or "[]")
    except Exception:
        parsed = []
    for channel in parsed if isinstance(parsed, list) else []:
        if not isinstance(channel, dict):
            continue
        value = str(channel.get("value") or "").strip()
        if value and "@" in value and "noreply.github.com" not in value.lower():
            return value
    return ""


def _lead_or_404(db: Session, lead_id: int) -> GrowthLeadRow:
    row = db.query(GrowthLeadRow).filter(GrowthLeadRow.id == int(lead_id)).first()
    if row is None:
        raise GmailDraftError("growth lead not found")
    return row


def _message_or_404(db: Session, message_id: int) -> GrowthOutreachMessageRow:
    row = (
        db.query(GrowthOutreachMessageRow)
        .filter(GrowthOutreachMessageRow.id == int(message_id))
        .first()
    )
    if row is None:
        raise GmailDraftError("outreach message not found")
    return row
