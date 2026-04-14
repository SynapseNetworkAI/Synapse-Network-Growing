from __future__ import annotations

"""Shared structured logging helpers for ops-dashboard."""

import json
import logging
import time
from contextlib import contextmanager
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Iterator

import structlog

_SERVICE_NAME = "ops-dashboard"
_ENV_NAME = "local"
_SENSITIVE_KEYS = {
    "authorization",
    "authorization_header",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "webhook_url",
}


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if isinstance(value, BaseException):
        return str(value)
    return str(value)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): ("[REDACTED]" if str(key).lower() in _SENSITIVE_KEYS else _sanitize_value(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseException):
        return str(value)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


def _add_service_and_env(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict.setdefault("service", _SERVICE_NAME)
    event_dict.setdefault("env", _ENV_NAME)
    return event_dict


def _normalize_error_fields(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    if "error" in event_dict and "error_message" not in event_dict:
        event_dict["error_message"] = event_dict.pop("error")
    return event_dict


def _sanitize_event_dict(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _sanitize_value(value) for key, value in event_dict.items()}


def _ensure_message(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    message = event_dict.get("message")
    event = event_dict.get("event")
    if not message:
        event_dict["message"] = str(event or "")
    return event_dict


def _serializer(payload: Any, **kwargs: Any) -> str:
    kwargs.setdefault("ensure_ascii", False)
    kwargs.setdefault("default", _json_default)
    return json.dumps(payload, **kwargs)


def _coerce_logger(logger: Any) -> structlog.stdlib.BoundLogger:
    if hasattr(logger, "bind") and hasattr(logger, "info"):
        return logger
    if isinstance(logger, logging.Logger):
        return structlog.stdlib.get_logger(logger.name)
    return structlog.stdlib.get_logger(str(logger))


def _level_method(level: int) -> str:
    if level >= logging.CRITICAL:
        return "critical"
    if level >= logging.ERROR:
        return "error"
    if level >= logging.WARNING:
        return "warning"
    if level >= logging.INFO:
        return "info"
    return "debug"


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)


def bind_context(**fields: Any) -> None:
    if not fields:
        return
    structlog.contextvars.bind_contextvars(**_sanitize_value(fields))


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()


def format_log_fields(**fields: Any) -> str:
    """Backward-compatible helper for older call sites/tests."""
    cleaned = _sanitize_value(fields)
    return _serializer(cleaned, sort_keys=True)


def log_event(
    logger: Any,
    event: str,
    *,
    level: int = logging.INFO,
    exc_info: BaseException | bool | tuple[Any, Any, Any] | None = None,
    **fields: Any,
) -> None:
    target = _coerce_logger(logger)
    method = getattr(target, _level_method(level))
    method(event, exc_info=exc_info, **fields)


@contextmanager
def timed_operation(
    logger: Any,
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
        extra.setdefault("error_message", str(exc))
        log_event(logger, event, level=logging.ERROR, exc_info=exc, **fields, **extra)
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        merged = {**fields, **extra, "duration_ms": duration_ms, "outcome": outcome}
        effective_level = slow_level if duration_ms >= slow_ms else level
        log_event(logger, event, level=effective_level, **merged)


def setup_ops_logging(
    *,
    log_level: str,
    log_dir: str,
    log_file: str,
    backup_days: int,
    service_name: str = "ops-dashboard",
    env: str = "local",
) -> None:
    global _SERVICE_NAME, _ENV_NAME

    root = logging.getLogger()
    if getattr(root, "_ops_dashboard_configured", False):
        return

    _SERVICE_NAME = str(service_name or "ops-dashboard")
    _ENV_NAME = str(env or "local")

    level = getattr(logging, str(log_level).upper(), logging.INFO)
    root.setLevel(level)
    root.handlers.clear()

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts")
    pre_chain = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        _add_service_and_env,
        _normalize_error_fields,
        _sanitize_event_dict,
        _ensure_message,
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *pre_chain,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=pre_chain,
        processor=structlog.processors.JSONRenderer(serializer=_serializer, sort_keys=True),
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        log_path / log_file,
        when="midnight",
        interval=1,
        backupCount=max(1, int(backup_days)),
        encoding="utf-8",
        utc=True,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    setattr(root, "_ops_dashboard_configured", True)


def _reset_logging_for_tests() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        handler.close()
        root.removeHandler(handler)
    setattr(root, "_ops_dashboard_configured", False)
    clear_context()
