"""Typed release task pagination projection."""

from __future__ import annotations

from pydantic import BaseModel

from server.schemas import ReleaseTaskOut


class ReleaseTaskPageOut(BaseModel):
    items: list[ReleaseTaskOut]
    total: int
    limit: int = 10
    offset: int = 0
