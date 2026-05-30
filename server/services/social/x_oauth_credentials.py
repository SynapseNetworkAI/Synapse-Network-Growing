"""Local-only X OAuth client credential helpers."""

from __future__ import annotations

import os
from collections.abc import Callable

from server import config


def _required_env_value(name: str, configured: str) -> str:
    value = str(configured or os.environ.get(name, "")).strip()
    if not value:
        raise ValueError(f"{name} is required in local environment configuration.")
    return value


def read_x_oauth_client_id(read_secret: Callable[[str], str] | None = None) -> str:
    value = str(
        config.X_OAUTH_CLIENT_ID or os.environ.get("X_OAUTH_CLIENT_ID", "")
    ).strip()
    return _required_env_value("X_OAUTH_CLIENT_ID", value)


def read_x_oauth_client_secret(read_secret: Callable[[str], str] | None = None) -> str:
    value = str(
        config.X_OAUTH_CLIENT_SECRET or os.environ.get("X_OAUTH_CLIENT_SECRET", "")
    ).strip()
    return _required_env_value("X_OAUTH_CLIENT_SECRET", value)
