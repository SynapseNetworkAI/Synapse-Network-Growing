from __future__ import annotations

import pytest

from server.database_config import resolve_database_url


def test_local_database_url_falls_back_to_sqlite():
    resolved = resolve_database_url(
        env="local",
        explicit_database_url=None,
        sqlite_fallback_url="sqlite:///server/ops.db",
    )

    assert resolved.url == "sqlite:///server/ops.db"
    assert resolved.is_sqlite is True
    assert resolved.is_explicit is False


@pytest.mark.parametrize("env", ["staging", "prod", "production"])
def test_production_like_env_requires_explicit_postgres_url(env):
    with pytest.raises(RuntimeError, match="OPS_DATABASE_URL"):
        resolve_database_url(
            env=env,
            explicit_database_url=None,
            sqlite_fallback_url="sqlite:///server/ops.db",
        )
    with pytest.raises(RuntimeError, match="SQLite"):
        resolve_database_url(
            env=env,
            explicit_database_url="sqlite:///server/ops.db",
            sqlite_fallback_url="sqlite:///server/ops.db",
        )


def test_production_like_env_accepts_postgres_url():
    resolved = resolve_database_url(
        env="prod",
        explicit_database_url="postgresql+psycopg://user:pass@localhost:5432/ops",
        sqlite_fallback_url="sqlite:///server/ops.db",
    )

    assert resolved.is_postgres is True
    assert resolved.is_sqlite is False
    assert resolved.is_explicit is True
