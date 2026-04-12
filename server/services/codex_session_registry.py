from __future__ import annotations

"""Scoped session registry for Codex CLI thread reuse and validation."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server.database import CodexSessionRow, TaskRow, utcnow


def build_session_key(*, role_key: str, project_root: str, requirement_id: int | None) -> str:
    raw = f"{role_key.strip().lower()}|{project_root.strip()}|{int(requirement_id or 0)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def find_reusable_session(
    db: Session,
    *,
    role_key: str,
    project_root: str,
    requirement_id: int | None,
) -> CodexSessionRow | None:
    session_key = build_session_key(role_key=role_key, project_root=project_root, requirement_id=requirement_id)
    row = (
        db.query(CodexSessionRow)
        .filter(CodexSessionRow.session_key == session_key)
        .order_by(CodexSessionRow.updated_at.desc(), CodexSessionRow.id.desc())
        .first()
    )
    if row is None or not str(row.thread_id or "").strip():
        return None
    if str(row.status or "") not in {"completed", "resumable"}:
        return None
    ttl = max(60, int(config.CODEX_CLI_SESSION_REUSE_TTL_SECONDS))
    last_used = row.last_used_at or row.updated_at or row.created_at
    if last_used is None:
        return None
    last_used = _as_aware(last_used)
    now = _as_aware(utcnow())
    if last_used is None or now is None:
        return None
    if now > last_used + timedelta(seconds=ttl):
        row.status = "expired"
        db.commit()
        return None
    metadata = _load_metadata(row.metadata_json)
    usage_totals = metadata.get("usage_totals") if isinstance(metadata.get("usage_totals"), dict) else {}
    latest_usage = metadata.get("usage") if isinstance(metadata.get("usage"), dict) else {}
    usage = usage_totals or latest_usage
    turn_count = int(metadata.get("cumulative_turn_count") or metadata.get("turn_count") or 0)
    cached_input_tokens = int(usage.get("cached_input_tokens") or 0) if isinstance(usage, dict) else 0
    input_tokens = int(usage.get("input_tokens") or 0) if isinstance(usage, dict) else 0
    if config.CODEX_CLI_SESSION_MAX_TURNS > 0 and turn_count >= config.CODEX_CLI_SESSION_MAX_TURNS:
        row.status = "rotated"
        row.metadata_json = json.dumps(
            _merge_metadata(
                _load_metadata(row.metadata_json),
                {"rotated_reason": f"turn_count>={config.CODEX_CLI_SESSION_MAX_TURNS}"},
            ),
            default=str,
        )
        db.commit()
        return None
    if (
        config.CODEX_CLI_SESSION_MAX_CACHED_INPUT_TOKENS > 0
        and cached_input_tokens >= config.CODEX_CLI_SESSION_MAX_CACHED_INPUT_TOKENS
    ):
        row.status = "rotated"
        row.metadata_json = json.dumps(
            _merge_metadata(
                _load_metadata(row.metadata_json),
                {
                    "rotated_reason": (
                        f"cached_input_tokens>={config.CODEX_CLI_SESSION_MAX_CACHED_INPUT_TOKENS}"
                    )
                },
            ),
            default=str,
        )
        db.commit()
        return None
    if config.CODEX_CLI_SESSION_MAX_INPUT_TOKENS > 0 and input_tokens >= config.CODEX_CLI_SESSION_MAX_INPUT_TOKENS:
        row.status = "rotated"
        row.metadata_json = json.dumps(
            _merge_metadata(
                _load_metadata(row.metadata_json),
                {"rotated_reason": f"input_tokens>={config.CODEX_CLI_SESSION_MAX_INPUT_TOKENS}"},
            ),
            default=str,
        )
        db.commit()
        return None
    return row


def upsert_session_launch(
    db: Session,
    *,
    role_key: str,
    project_root: str,
    requirement_id: int | None,
    workflow_run_id: int | None,
    task_id: int,
    thread_id: str | None,
    status: str,
    resume_count: int = 0,
    metadata: dict[str, Any] | None = None,
) -> CodexSessionRow:
    session_key = build_session_key(role_key=role_key, project_root=project_root, requirement_id=requirement_id)
    row = db.query(CodexSessionRow).filter(CodexSessionRow.session_key == session_key).first()
    if row is None:
        row = CodexSessionRow(
            session_key=session_key,
            role_key=role_key,
            project_root=project_root,
            requirement_id=requirement_id,
            workflow_run_id=workflow_run_id,
        )
        db.add(row)
    existing_metadata = _load_metadata(row.metadata_json)
    merged_metadata = _merge_metadata(existing_metadata, metadata or {})
    row.current_task_id = task_id
    row.thread_id = thread_id or row.thread_id
    row.status = status
    row.last_used_at = utcnow()
    row.last_heartbeat_at = row.last_heartbeat_at or utcnow()
    row.resume_count = int(resume_count)
    row.metadata_json = json.dumps(merged_metadata, default=str)
    db.flush()
    return row


def update_session_state(
    db: Session,
    *,
    role_key: str,
    project_root: str,
    requirement_id: int | None,
    thread_id: str | None = None,
    status: str | None = None,
    heartbeat: bool = False,
    current_task_id: int | None = None,
    resume_count: int | None = None,
    metadata_patch: dict[str, Any] | None = None,
) -> CodexSessionRow | None:
    session_key = build_session_key(role_key=role_key, project_root=project_root, requirement_id=requirement_id)
    row = db.query(CodexSessionRow).filter(CodexSessionRow.session_key == session_key).first()
    if row is None:
        return None
    if thread_id:
        row.thread_id = thread_id
    if status:
        row.status = status
    if heartbeat:
        row.last_heartbeat_at = utcnow()
    row.last_used_at = utcnow()
    if current_task_id is not None:
        row.current_task_id = current_task_id
    if resume_count is not None:
        row.resume_count = int(resume_count)
    if metadata_patch:
        payload = _merge_metadata(_load_metadata(row.metadata_json), metadata_patch, current_task_id=current_task_id, status=status)
        row.metadata_json = json.dumps(payload, default=str)
    db.flush()
    return row


def _load_metadata(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        data = json.loads(payload)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _usage_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        "input_tokens": int(value.get("input_tokens") or 0),
        "cached_input_tokens": int(value.get("cached_input_tokens") or 0),
        "output_tokens": int(value.get("output_tokens") or 0),
    }


def _merge_metadata(
    existing: dict[str, Any],
    patch: dict[str, Any],
    *,
    current_task_id: int | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    payload = dict(existing or {})
    payload.update(patch or {})
    usage_patch = _usage_dict(patch.get("usage"))
    if usage_patch:
        payload["usage"] = usage_patch
    existing_totals = _usage_dict(payload.get("usage_totals"))
    if usage_patch:
        effective_task_id = current_task_id if current_task_id is not None else _safe_int(payload.get("last_task_id"))
        last_usage_task_id = _safe_int(payload.get("last_usage_task_id"))
        terminal = str(status or payload.get("status") or "").strip().lower() in {"completed", "failed", "resumable"}
        if terminal and effective_task_id is not None and effective_task_id != last_usage_task_id:
            payload["usage_totals"] = {
                "input_tokens": int(existing_totals.get("input_tokens") or 0) + int(usage_patch.get("input_tokens") or 0),
                "cached_input_tokens": int(existing_totals.get("cached_input_tokens") or 0)
                + int(usage_patch.get("cached_input_tokens") or 0),
                "output_tokens": int(existing_totals.get("output_tokens") or 0) + int(usage_patch.get("output_tokens") or 0),
            }
            payload["last_usage_task_id"] = effective_task_id
        elif existing_totals:
            payload["usage_totals"] = existing_totals
    turn_count_patch = _safe_int(patch.get("turn_count"))
    if turn_count_patch is not None:
        payload["turn_count"] = turn_count_patch
        effective_task_id = current_task_id if current_task_id is not None else _safe_int(payload.get("last_task_id"))
        last_turn_task_id = _safe_int(payload.get("last_turn_task_id"))
        terminal = str(status or payload.get("status") or "").strip().lower() in {"completed", "failed", "resumable"}
        if terminal and effective_task_id is not None and effective_task_id != last_turn_task_id:
            payload["cumulative_turn_count"] = int(payload.get("cumulative_turn_count") or 0) + turn_count_patch
            payload["last_turn_task_id"] = effective_task_id
    return payload


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _maybe_path(value: Any) -> Path | None:
    path_str = str(value or "").strip()
    if not path_str:
        return None
    return Path(path_str)


def _trim_state_snapshot(state_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state_payload, dict):
        return {}
    keys = [
        "status",
        "pid",
        "thread_id",
        "exit_code",
        "resume_count",
        "started_at",
        "resumed_at",
        "completed_at",
    ]
    return {key: state_payload.get(key) for key in keys if key in state_payload}


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def validate_codex_session_registry(
    db: Session,
    *,
    project_root: Path | None = None,
    stale_threshold_seconds: float | None = None,
) -> dict[str, Any]:
    """Return diagnostics for Codex CLI session registry integrity.

    The report is structured for downstream tooling:

    {
        "summary": {"total_sessions": N, "sessions_with_issues": M, "total_issues": K},
        "sessions": [
            {
                "session_key": str,
                "status": str,
                "thread_id": str | None,
                "current_task_id": int | None,
                "task_status": str | None,
                "issues": [{"code": str, "detail": str}, ...],
                "metadata_snapshot": {...},
                "state_snapshot": {...},
                "file_probes": [{"key": str, "path": str | None, "status": str}],
            }
        ]
    }
    """

    rows = (
        db.query(CodexSessionRow)
        .order_by(CodexSessionRow.updated_at.desc(), CodexSessionRow.id.desc())
        .all()
    )
    if not rows:
        return {"summary": {"total_sessions": 0, "sessions_with_issues": 0, "total_issues": 0}, "sessions": []}

    valid_project_root = (project_root or config.PROJECT_ROOT).resolve()
    threshold_seconds = stale_threshold_seconds
    if threshold_seconds is None:
        threshold_seconds = max(config.CODEX_CLI_STALE_AFTER_SEC * 2, 1)
    now = utcnow()

    task_ids = [int(row.current_task_id) for row in rows if row.current_task_id]
    task_map: dict[int, TaskRow] = {}
    if task_ids:
        task_rows = db.query(TaskRow).filter(TaskRow.id.in_(task_ids)).all()
        task_map = {int(task.id): task for task in task_rows}

    sessions: list[dict[str, Any]] = []
    total_issues = 0

    for row in rows:
        metadata = _load_metadata(row.metadata_json)
        issues: list[dict[str, str]] = []
        metadata_snapshot = {
            key: metadata.get(key)
            for key in (
                "cwd",
                "model",
                "pid",
                "session_key",
                "thread_id",
                "resume_thread_id",
                "resume_count",
                "last_task_id",
                "json_event_count",
            )
            if key in metadata
        }
        file_probes: list[dict[str, Any]] = []
        state_snapshot: dict[str, Any] | None = None

        # Validate registry invariants
        expected_key = build_session_key(
            role_key=row.role_key,
            project_root=row.project_root,
            requirement_id=row.requirement_id,
        )
        if expected_key != row.session_key:
            issues.append(
                {
                    "code": "session_key_mismatch",
                    "detail": f"expected {expected_key} got {row.session_key}",
                }
            )

        if not metadata:
            issues.append({"code": "metadata_missing", "detail": "metadata_json empty or invalid"})

        metadata_session_key = str(metadata.get("session_key") or "").strip()
        if metadata_session_key and metadata_session_key != row.session_key:
            issues.append(
                {
                    "code": "metadata_session_key_mismatch",
                    "detail": f"registry={row.session_key} metadata={metadata_session_key}",
                }
            )

        metadata_last_task = _safe_int(metadata.get("last_task_id") or metadata.get("current_task_id"))
        if metadata_last_task and row.current_task_id and metadata_last_task != int(row.current_task_id):
            issues.append(
                {
                    "code": "metadata_last_task_mismatch",
                    "detail": f"registry_task={row.current_task_id} metadata_last_task={metadata_last_task}",
                }
            )

        metadata_thread = str(metadata.get("thread_id") or metadata.get("resume_thread_id") or "").strip()
        if metadata_thread and row.thread_id and metadata_thread != row.thread_id:
            issues.append(
                {
                    "code": "metadata_thread_mismatch",
                    "detail": f"registry={row.thread_id} metadata={metadata_thread}",
                }
            )

        if str(row.status or "") in {"active", "resumable", "completed"} and not str(row.thread_id or "").strip():
            issues.append(
                {
                    "code": "thread_missing",
                    "detail": f"session status={row.status} lacks thread_id",
                }
            )

        task = task_map.get(int(row.current_task_id or 0)) if row.current_task_id else None
        if row.current_task_id and task is None:
            issues.append(
                {
                    "code": "task_not_found",
                    "detail": f"current_task_id={row.current_task_id}",
                }
            )

        row_status = str(row.status or "").lower()
        if task is not None:
            task_status = str(task.status or "")
            if row_status == "active" and task_status != "running":
                issues.append(
                    {
                        "code": "task_status_mismatch",
                        "detail": f"registry active but task status={task_status}",
                    }
                )
            if row_status == "completed" and task_status not in {"completed", "pending_approval"}:
                issues.append(
                    {
                        "code": "task_status_mismatch",
                        "detail": f"registry completed but task status={task_status}",
                    }
                )

        last_heartbeat = _as_aware(row.last_heartbeat_at)
        if row_status in {"active", "resumable"}:
            if last_heartbeat is None:
                issues.append(
                    {
                        "code": "heartbeat_missing",
                        "detail": "active session missing last heartbeat timestamp",
                    }
                )
            else:
                heartbeat_age = (now - last_heartbeat).total_seconds()
                if heartbeat_age > threshold_seconds:
                    issues.append(
                        {
                            "code": "heartbeat_stale",
                            "detail": f"age={int(heartbeat_age)}s threshold={int(threshold_seconds)}s",
                        }
                    )

        # Monitor metadata file probes (state/stdout/stderr/prompt)
        for key in ("state_path", "stdout_path", "stderr_path", "prompt_path"):
            path_obj = _maybe_path(metadata.get(key))
            probe: dict[str, Any] = {"key": key, "path": None, "status": "untracked"}
            if path_obj is not None:
                probe["path"] = _relative_path(path_obj, valid_project_root)
                probe["status"] = "exists" if path_obj.exists() else "missing"
            file_probes.append(probe)

            if key == "state_path" and row_status in {"active", "resumable"}:
                if path_obj is None:
                    issues.append(
                        {
                            "code": "state_path_untracked",
                            "detail": "active session missing state_path in metadata",
                        }
                    )
                elif not path_obj.exists():
                    issues.append(
                        {
                            "code": "state_path_missing",
                            "detail": str(path_obj),
                        }
                    )
                else:
                    try:
                        payload = json.loads(path_obj.read_text(encoding="utf-8"))
                        state_snapshot = _trim_state_snapshot(payload)
                        state_thread = str(state_snapshot.get("thread_id") or "").strip()
                        if state_thread and row.thread_id and state_thread != row.thread_id:
                            issues.append(
                                {
                                    "code": "state_thread_mismatch",
                                    "detail": f"state={state_thread} registry={row.thread_id}",
                                }
                            )
                    except Exception as exc:
                        issues.append(
                            {
                                "code": "state_path_parse_error",
                                "detail": f"{path_obj}: {exc}",
                            }
                        )

        last_used = _as_aware(row.last_used_at)
        entry = {
            "session_key": row.session_key,
            "role_key": row.role_key,
            "project_root": row.project_root,
            "requirement_id": row.requirement_id,
            "workflow_run_id": row.workflow_run_id,
            "current_task_id": row.current_task_id,
            "thread_id": row.thread_id,
            "status": row.status,
            "resume_count": row.resume_count,
            "last_used_at": last_used.isoformat() if last_used else None,
            "last_heartbeat_at": last_heartbeat.isoformat() if last_heartbeat else None,
            "task_status": str(task.status or "") if task else None,
            "task_runtime_session_id": str(task.runtime_session_id or "") if task else None,
            "issues": issues,
            "metadata_snapshot": metadata_snapshot,
            "state_snapshot": state_snapshot,
            "file_probes": file_probes,
        }
        sessions.append(entry)
        total_issues += len(issues)

    summary = {
        "total_sessions": len(sessions),
        "sessions_with_issues": sum(1 for entry in sessions if entry["issues"]),
        "total_issues": total_issues,
        "stale_threshold_seconds": int(threshold_seconds),
    }
    return {"summary": summary, "sessions": sessions}
