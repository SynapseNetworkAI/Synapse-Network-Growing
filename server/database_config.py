from __future__ import annotations

"""Database URL resolution and environment safety policy."""

from dataclasses import dataclass


SQLITE_PREFIXES = ("sqlite://", "sqlite+pysqlite://")
POSTGRES_PREFIXES = ("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")
PRODUCTION_LIKE_ENVS = {"prod", "production", "staging"}


@dataclass(frozen=True)
class DatabaseConfigResolution:
    url: str
    is_explicit: bool
    is_sqlite: bool
    is_postgres: bool


def is_sqlite_url(url: str) -> bool:
    return url.strip().lower().startswith(SQLITE_PREFIXES)


def is_postgres_url(url: str) -> bool:
    return url.strip().lower().startswith(POSTGRES_PREFIXES)


def resolve_database_url(
    *,
    env: str,
    explicit_database_url: str | None,
    sqlite_fallback_url: str,
) -> DatabaseConfigResolution:
    normalized_env = (env or "local").strip().lower()
    explicit = (explicit_database_url or "").strip()
    url = explicit or sqlite_fallback_url
    is_sqlite = is_sqlite_url(url)
    is_postgres = is_postgres_url(url)
    if normalized_env in PRODUCTION_LIKE_ENVS and (not explicit or is_sqlite):
        raise RuntimeError(
            "OPS_DATABASE_URL must be an explicit PostgreSQL URL when OPS_ENV "
            f"is {normalized_env!r}; SQLite is local/test fallback only."
        )
    return DatabaseConfigResolution(
        url=url,
        is_explicit=bool(explicit),
        is_sqlite=is_sqlite,
        is_postgres=is_postgres,
    )
