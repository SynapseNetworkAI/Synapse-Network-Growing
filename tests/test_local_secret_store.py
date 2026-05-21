import pytest

from server.database_local_secrets import LocalSecretVersionRow
from server.services import local_secrets


def test_local_secret_store_requires_encryption_key(monkeypatch, db_session):
    monkeypatch.setattr(local_secrets.config, "OPS_LOCAL_SECRET_ENCRYPTION_KEY", "")

    with pytest.raises(
        local_secrets.LocalSecretStoreError, match="OPS_LOCAL_SECRET_ENCRYPTION_KEY"
    ):
        local_secrets.write_local_secret_version(db_session, "x-refresh", "secret")


def test_local_secret_store_encrypts_and_keeps_latest_three(monkeypatch, db_session):
    monkeypatch.setattr(
        local_secrets.config, "OPS_LOCAL_SECRET_ENCRYPTION_KEY", "test-local-secret-key"
    )

    for index in range(5):
        local_secrets.write_local_secret_version(
            db_session,
            "x-official-oauth2-refresh-token",
            f"refresh-{index}",
            metadata={"index": index},
            keep_active=3,
        )
    db_session.commit()

    rows = (
        db_session.query(LocalSecretVersionRow)
        .filter(LocalSecretVersionRow.secret_key == "x-official-oauth2-refresh-token")
        .order_by(LocalSecretVersionRow.version.asc())
        .all()
    )
    assert [row.version for row in rows] == [1, 2, 3, 4, 5]
    assert [row.status for row in rows] == [
        "retired",
        "retired",
        "active",
        "active",
        "active",
    ]
    assert all("refresh-" not in row.ciphertext for row in rows)
    assert (
        local_secrets.read_latest_local_secret(
            db_session, "x-official-oauth2-refresh-token"
        )
        == "refresh-4"
    )


def test_local_secret_store_dedupes_latest_value(monkeypatch, db_session):
    monkeypatch.setattr(
        local_secrets.config, "OPS_LOCAL_SECRET_ENCRYPTION_KEY", "test-local-secret-key"
    )

    first = local_secrets.write_local_secret_version(db_session, "x-refresh", "same")
    second = local_secrets.write_local_secret_version(db_session, "x-refresh", "same")
    db_session.commit()

    assert first.id == second.id
    assert (
        db_session.query(LocalSecretVersionRow)
        .filter(LocalSecretVersionRow.secret_key == "x-refresh")
        .count()
        == 1
    )


def test_local_secret_store_fail_closed_edges(monkeypatch, db_session):
    monkeypatch.setattr(
        local_secrets.config, "OPS_LOCAL_SECRET_ENCRYPTION_KEY", "test-local-secret-key"
    )

    with pytest.raises(local_secrets.LocalSecretStoreError, match="empty"):
        local_secrets.encrypt_local_secret("")
    with pytest.raises(local_secrets.LocalSecretStoreError, match="ciphertext"):
        local_secrets.decrypt_local_secret("")
    with pytest.raises(local_secrets.LocalSecretStoreError, match="key"):
        local_secrets.latest_local_secret_version(db_session, "")
    with pytest.raises(local_secrets.LocalSecretStoreError, match="no active version"):
        local_secrets.read_latest_local_secret(db_session, "missing-secret")
    with pytest.raises(local_secrets.LocalSecretStoreError, match="cannot decrypt"):
        local_secrets.decrypt_local_secret("not-a-fernet-token")


def test_local_secret_store_retire_policy_preserves_invalid_metadata(
    monkeypatch, db_session
):
    monkeypatch.setattr(
        local_secrets.config, "OPS_LOCAL_SECRET_ENCRYPTION_KEY", "test-local-secret-key"
    )
    old = local_secrets.write_local_secret_version(
        db_session, "x-refresh-invalid-json", "first", keep_active=2
    )
    old.metadata_json = "{not-json"
    local_secrets.write_local_secret_version(
        db_session, "x-refresh-invalid-json", "second", keep_active=2
    )
    local_secrets.write_local_secret_version(
        db_session, "x-refresh-invalid-json", "third", keep_active=2
    )
    db_session.commit()

    db_session.refresh(old)
    assert old.status == "retired"
    assert "local_secret_keep_latest_policy" in old.metadata_json
