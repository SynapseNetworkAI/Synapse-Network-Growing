"""Local environment loading helpers for growth operator scripts."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path, *, override_existing: bool = False) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_env_line(raw)
        if parsed is None:
            continue
        env_key, value = parsed
        if not override_existing and env_key in os.environ:
            continue
        os.environ[env_key] = value


def load_optional_dotenv_path(path_value: str | None) -> bool:
    if not path_value:
        return False
    path = Path(path_value)
    load_dotenv(path, override_existing=False)
    return path.exists()


def parse_env_line(raw: str) -> tuple[str, str] | None:
    line = raw.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line.removeprefix("export ").strip()
    if "=" not in line:
        return None
    key, _, value = line.partition("=")
    return key.strip(), unquote_env_value(value)


def unquote_env_value(value: str) -> str:
    value = value.strip()
    if is_quoted(value):
        return value[1:-1]
    return value


def is_quoted(value: str) -> bool:
    if len(value) < 2:
        return False
    return value[0] == value[-1] and value[0] in {"'", '"'}
