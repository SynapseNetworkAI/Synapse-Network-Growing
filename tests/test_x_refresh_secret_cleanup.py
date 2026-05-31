import subprocess

import pytest

from server.services.local_secrets import write_local_secret_version
from server.services.social.publishing import SocialPublishError, XOAuth2AccessToken
from server.services.x_refresh_secret_cleanup import (
    DELETE_CONFIRMATION,
    delete_x_refresh_token_secret_manager,
    dump_delete_result,
    verify_local_x_refresh_token,
)


class VerifiedProvider:
    def get_access_token(self):
        return XOAuth2AccessToken(
            access_token="access-token", refresh_token_rotated=False
        )


class FailingProvider:
    def get_access_token(self):
        raise SocialPublishError("x_refresh_failed", "invalid local refresh token")


class EmptyTokenProvider:
    def get_access_token(self):
        return XOAuth2AccessToken(access_token="", refresh_token_rotated=False)


def _completed(cmd, *, returncode=0, stdout="{}", stderr=""):
    return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)


@pytest.fixture(autouse=True)
def fixed_x_refresh_secret_key(monkeypatch):
    monkeypatch.setattr(
        "server.services.x_refresh_secret_cleanup.config.X_OAUTH_REFRESH_TOKEN_LOCAL_KEY",
        "x-official-oauth2-refresh-token",
    )


def test_delete_x_refresh_secret_refuses_when_local_oauth_unverified(
    monkeypatch, db_session
):
    monkeypatch.setattr(
        "server.services.local_secrets.config.OPS_LOCAL_SECRET_ENCRYPTION_KEY",
        "test-local-secret-key",
    )
    write_local_secret_version(
        db_session, "x-official-oauth2-refresh-token", "refresh-token"
    )
    db_session.commit()

    with pytest.raises(SocialPublishError, match="invalid local refresh token"):
        delete_x_refresh_token_secret_manager(
            projects=["staging-project"],
            confirmation=DELETE_CONFIRMATION,
            dry_run=False,
            runner=lambda cmd: _completed(cmd),
            provider=FailingProvider(),
        )


def test_delete_x_refresh_secret_deletes_staging_and_prod_after_confirmation(
    monkeypatch, db_session
):
    monkeypatch.setattr(
        "server.services.local_secrets.config.OPS_LOCAL_SECRET_ENCRYPTION_KEY",
        "test-local-secret-key",
    )
    write_local_secret_version(
        db_session, "x-official-oauth2-refresh-token", "refresh-token"
    )
    db_session.commit()
    commands: list[list[str]] = []

    def runner(cmd):
        commands.append(cmd)
        return _completed(cmd)

    result = delete_x_refresh_token_secret_manager(
        projects=["fabled-archive-494108-k5", "synapse-network-prod"],
        confirmation=DELETE_CONFIRMATION,
        dry_run=False,
        runner=runner,
        provider=VerifiedProvider(),
    )

    assert result["deleted_count"] == 2
    assert result["error_count"] == 0
    assert result["local_verification"]["verified_refresh"] is True
    delete_commands = [
        cmd for cmd in commands if cmd[:3] == ["gcloud", "secrets", "delete"]
    ]
    assert len(delete_commands) == 2
    assert all("x-official-oauth2-refresh-token" in cmd for cmd in delete_commands)


def test_delete_x_refresh_secret_requires_confirmation_for_apply(
    monkeypatch, db_session
):
    monkeypatch.setattr(
        "server.services.local_secrets.config.OPS_LOCAL_SECRET_ENCRYPTION_KEY",
        "test-local-secret-key",
    )
    write_local_secret_version(
        db_session, "x-official-oauth2-refresh-token", "refresh-token"
    )
    db_session.commit()

    with pytest.raises(ValueError, match="confirmation must be"):
        delete_x_refresh_token_secret_manager(
            projects=["synapse-network-prod"],
            confirmation="YES",
            dry_run=False,
            runner=lambda cmd: _completed(cmd),
            provider=VerifiedProvider(),
        )


def test_local_x_refresh_verification_requires_active_local_version(db_session):
    with pytest.raises(SocialPublishError, match="has no active version"):
        verify_local_x_refresh_token(provider=VerifiedProvider())


def test_local_x_refresh_verification_requires_access_token(monkeypatch, db_session):
    monkeypatch.setattr(
        "server.services.local_secrets.config.OPS_LOCAL_SECRET_ENCRYPTION_KEY",
        "test-local-secret-key",
    )
    write_local_secret_version(
        db_session, "x-official-oauth2-refresh-token", "refresh-token"
    )
    db_session.commit()

    with pytest.raises(SocialPublishError, match="did not return access token"):
        verify_local_x_refresh_token(provider=EmptyTokenProvider())


def test_delete_x_refresh_secret_dry_run_and_not_found_paths(monkeypatch, db_session):
    monkeypatch.setattr(
        "server.services.local_secrets.config.OPS_LOCAL_SECRET_ENCRYPTION_KEY",
        "test-local-secret-key",
    )
    write_local_secret_version(
        db_session, "x-official-oauth2-refresh-token", "refresh-token"
    )
    db_session.commit()

    def runner(cmd):
        if cmd[1:3] == ["secrets", "describe"] and "missing-project" in cmd:
            return _completed(cmd, returncode=1, stderr="Secret not found")
        return _completed(cmd)

    result = delete_x_refresh_token_secret_manager(
        projects=["staging-project", "missing-project"],
        confirmation="",
        dry_run=True,
        runner=runner,
        provider=VerifiedProvider(),
    )

    assert result["projects"][0]["status"] == "would_delete"
    assert result["projects"][1]["status"] == "not_found"
    assert result["not_found_count"] == 1


def test_delete_x_refresh_secret_records_delete_failure(monkeypatch, db_session):
    monkeypatch.setattr(
        "server.services.local_secrets.config.OPS_LOCAL_SECRET_ENCRYPTION_KEY",
        "test-local-secret-key",
    )
    write_local_secret_version(
        db_session, "x-official-oauth2-refresh-token", "refresh-token"
    )
    db_session.commit()

    def runner(cmd):
        if cmd[1:3] == ["secrets", "delete"]:
            return _completed(cmd, returncode=1, stderr="permission denied")
        return _completed(cmd)

    result = delete_x_refresh_token_secret_manager(
        projects=["synapse-network-prod"],
        confirmation=DELETE_CONFIRMATION,
        dry_run=False,
        runner=runner,
        provider=VerifiedProvider(),
    )

    assert result["deleted_count"] == 0
    assert result["error_count"] == 1
    assert result["projects"][0]["status"] == "delete_failed"
    assert "permission denied" in dump_delete_result(result)
