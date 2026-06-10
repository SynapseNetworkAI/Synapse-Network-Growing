"""Shared source-host audit event ordering helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.services.growth.ai_visibility_source_host_surfaces import (
    source_host_surface,
)

SurfaceEvent = tuple[datetime, str, str]


def record_surface_event(
    surface_events: dict[str, SurfaceEvent],
    surface_or_host: str,
    status: str,
    event_time: datetime,
    tie_breaker: str,
) -> None:
    surface = source_host_surface(surface_or_host)
    candidate = (event_time, tie_breaker, status)
    current = surface_events.get(surface)
    if current is None or candidate[:2] >= current[:2]:
        surface_events[surface] = candidate


def record_payload_surface_event(
    surface_events: dict[str, SurfaceEvent],
    surface_or_host: str,
    status: str,
    payload: dict[str, Any],
    path: Path,
) -> None:
    record_surface_event(
        surface_events,
        surface_or_host,
        status,
        evidence_event_time(payload, path),
        path.name,
    )


def append_surface_status_event(
    surfaces: list[str],
    surface_events: dict[str, SurfaceEvent],
    surface_or_host: str,
    status: str,
    payload: dict[str, Any],
    path: Path,
) -> None:
    surfaces.append(surface_or_host)
    record_payload_surface_event(
        surface_events,
        surface_or_host,
        status,
        payload,
        path,
    )


def append_live_surface_event(
    surfaces: list[str],
    surface_events: dict[str, SurfaceEvent],
    surface_or_host: str,
    payload: dict[str, Any],
    path: Path,
) -> None:
    append_surface_status_event(
        surfaces,
        surface_events,
        surface_or_host,
        "already_live",
        payload,
        path,
    )


def append_review_pending_surface_event(
    surfaces: list[str],
    surface_events: dict[str, SurfaceEvent],
    surface_or_host: str,
    payload: dict[str, Any],
    path: Path,
) -> None:
    append_surface_status_event(
        surfaces,
        surface_events,
        surface_or_host,
        "review_pending_live_recheck",
        payload,
        path,
    )


def _surface_statuses(surface_events: dict[str, SurfaceEvent]) -> dict[str, str]:
    return {surface: item[2] for surface, item in sorted(surface_events.items())}


def evidence_event_time(payload: dict[str, Any], path: Path) -> datetime:
    for key in ("checked_at", "generated_at", "recorded_at", "created_at"):
        value = str(payload.get(key) or "").strip()
        if not value:
            continue
        try:
            return normalized_datetime(
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            )
        except ValueError:
            continue
    return date_from_filename(path)


def date_from_filename(path: Path) -> datetime:
    try:
        return datetime.fromisoformat(path.name[:10]).replace(tzinfo=UTC)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


def normalized_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
