from __future__ import annotations

"""Shared logging helpers for ops-dashboard."""

import logging
import time
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value).replace("\n", "\\n")


def format_log_fields(**fields: Any) -> str:
    pairs: list[str] = []
    for key, value in fields.items():
        if value is None or value == "":
            continue
        pairs.append(f"{key}={_stringify(value)}")
    return " ".join(pairs)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    exc_info: BaseException | bool | tuple[Any, Any, Any] | None = None,
    **fields: Any,
) -> None:
    payload = format_log_fields(event=event, **fields)
    logger.log(level, payload or event, exc_info=exc_info)


@contextmanager
def timed_operation(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    slow_level: int = logging.WARNING,
    slow_ms: float = 2000.0,
    **fields: Any,
) -> Iterator[dict[str, Any]]:
    started = time.perf_counter()
    extra: dict[str, Any] = {}
    outcome = "ok"
    try:
        yield extra
    except Exception as exc:
        outcome = "error"
        extra.setdefault("error_type", exc.__class__.__name__)
        extra.setdefault("error", str(exc))
        log_event(logger, event, level=logging.ERROR, exc_info=exc, **fields, **extra)
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        merged = {**fields, **extra, "duration_ms": duration_ms, "outcome": outcome}
        effective_level = slow_level if duration_ms >= slow_ms else level
        log_event(logger, event, level=effective_level, **merged)


def setup_ops_logging(*, log_level: str, log_dir: str, log_file: str, max_bytes: int, backup_count: int) -> None:
    root = logging.getLogger()
    if getattr(root, "_ops_dashboard_configured", False):
        return

    level = getattr(logging, str(log_level).upper(), logging.INFO)
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path / log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    setattr(root, "_ops_dashboard_configured", True)
