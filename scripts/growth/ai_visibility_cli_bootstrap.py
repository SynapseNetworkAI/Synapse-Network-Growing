"""Import-path bootstrap for directly executed growth scripts."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_project_root(script_file: str) -> None:
    project_root = Path(script_file).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
