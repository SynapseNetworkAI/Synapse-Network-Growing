"""Encrypted local secret version store for operator-owned OAuth material."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func
from sqlalchemy.orm import Session

from server import config
from server.database_local_secrets import LocalSecretVersionRow


class LocalSecretStoreError(RuntimeError):
    """Raised for fail-closed local secret storage errors."""


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, default=str)


def _json_loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _fernet_from_config() -> Fernet:
    raw = str(config.OPS_LOCAL_SECRET_ENCRYPTION_KEY or "").strip()
    if not raw:
        raise LocalSecretStoreError(
            "OPS_LOCAL_SECRET_ENCRYPTION_KEY is required for local encrypted secret storage."
        )
    candidate = raw.removeprefix("fernet:").encode("utf-8")
    try:
        return Fernet(candidate)
    except Exception:
        derived = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
        return Fernet(derived)


def encrypt_local_secret(plaintext: str) -> str:
    value = str(plaintext or "")
    if not value:
        raise LocalSecretStoreError("Cannot store an empty local secret value.")
    return _fernet_from_config().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_local_secret(ciphertext: str) -> str:
    token = str(ciphertext or "").strip()
    if not token:
        raise LocalSecretStoreError("Local secret ciphertext is empty.")
    try:
        return _fernet_from_config().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise LocalSecretStoreError(
            "Local secret encryption key cannot decrypt the stored secret."
        ) from exc


def latest_local_secret_version(
    db: Session, secret_key: str
) -> LocalSecretVersionRow | None:
    key = str(secret_key or "").strip()
    if not key:
        raise LocalSecretStoreError("Local secret key is required.")
    return (
        db.query(LocalSecretVersionRow)
        .filter(
            LocalSecretVersionRow.secret_key == key,
            LocalSecretVersionRow.status == "active",
        )
        .order_by(LocalSecretVersionRow.version.desc(), LocalSecretVersionRow.id.desc())
        .first()
    )


def read_latest_local_secret(db: Session, secret_key: str) -> str:
    row = latest_local_secret_version(db, secret_key)
    if row is None:
        raise LocalSecretStoreError(
            f"Local secret {secret_key!r} has no active version."
        )
    return decrypt_local_secret(str(row.ciphertext))


def write_local_secret_version(
    db: Session,
    secret_key: str,
    plaintext: str,
    *,
    metadata: dict[str, Any] | None = None,
    keep_active: int = 3,
    dedupe_latest: bool = True,
) -> LocalSecretVersionRow:
    key = str(secret_key or "").strip()
    if not key:
        raise LocalSecretStoreError("Local secret key is required.")
    latest = latest_local_secret_version(db, key)
    if latest is not None and dedupe_latest:
        try:
            if decrypt_local_secret(str(latest.ciphertext)) == str(plaintext or ""):
                return latest
        except LocalSecretStoreError:
            raise
    max_version = (
        db.query(func.max(LocalSecretVersionRow.version))
        .filter(LocalSecretVersionRow.secret_key == key)
        .scalar()
    )
    row = LocalSecretVersionRow(
        secret_key=key,
        version=int(max_version or 0) + 1,
        ciphertext=encrypt_local_secret(plaintext),
        status="active",
        metadata_json=_json_dumps(metadata or {}),
    )
    db.add(row)
    db.flush()
    retire_old_local_secret_versions(db, key, keep_active=keep_active)
    return row


def retire_old_local_secret_versions(
    db: Session, secret_key: str, *, keep_active: int = 3
) -> int:
    key = str(secret_key or "").strip()
    keep = max(1, int(keep_active or 3))
    rows = (
        db.query(LocalSecretVersionRow)
        .filter(
            LocalSecretVersionRow.secret_key == key,
            LocalSecretVersionRow.status == "active",
        )
        .order_by(LocalSecretVersionRow.version.desc(), LocalSecretVersionRow.id.desc())
        .all()
    )
    retired = 0
    for row in rows[keep:]:
        row.status = "retired"
        metadata = _json_loads(row.metadata_json)
        metadata["retired_reason"] = "local_secret_keep_latest_policy"
        row.metadata_json = _json_dumps(metadata)
        retired += 1
    return retired
