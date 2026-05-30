"""Local-first X OAuth client credential helpers."""

from __future__ import annotations

import os
from typing import Callable

from server import config


def read_x_oauth_client_id(read_secret: Callable[[str], str]) -> str:
    value = str(
        config.X_OAUTH_CLIENT_ID or os.environ.get("X_OAUTH_CLIENT_ID", "")
    ).strip()
    return value or read_secret(config.X_OAUTH_CLIENT_ID_SECRET)


def read_x_oauth_client_secret(read_secret: Callable[[str], str]) -> str:
    value = str(
        config.X_OAUTH_CLIENT_SECRET or os.environ.get("X_OAUTH_CLIENT_SECRET", "")
    ).strip()
    return value or read_secret(config.X_OAUTH_CLIENT_SECRET_SECRET)
