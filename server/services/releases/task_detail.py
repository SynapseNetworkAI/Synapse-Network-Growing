"""Read-only ReleaseTask detail projection."""

from __future__ import annotations

from sqlalchemy.orm import Session

from server.database import ReleaseTaskRow
from server.schemas import ReleaseTaskOut
from server.services.releases.tasks import _release_task_to_out


def get_release_task(db: Session, task_id: int) -> ReleaseTaskOut:
    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Release task not found.")
    return _release_task_to_out(row)
