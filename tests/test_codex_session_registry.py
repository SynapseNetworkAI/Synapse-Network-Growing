from __future__ import annotations

import json

from server.services.runtime.codex_session_registry import (
    build_planner_project_session_key,
    find_reusable_planner_project_session,
    upsert_planner_project_session,
    validate_codex_session_registry,
)


def test_planner_project_session_reuses_canonical_project_scope(db_session, tmp_path):
    project_root = tmp_path / "Synapse-Network"
    project_root.mkdir()
    session_key = build_planner_project_session_key(project_root=project_root)

    row = upsert_planner_project_session(
        db_session,
        project_root=project_root,
        thread_id="thread-planner-project",
        status="completed",
        metadata={
            "planning_requirement_id": 101,
            "planning_backend": "codex_cli",
            "planning_model": "gpt-5.4",
            "planning_usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2},
        },
    )
    db_session.commit()

    assert row.session_key == session_key
    assert row.role_key == "planner"
    assert row.project_root == str(project_root.resolve())
    assert row.requirement_id is None
    assert row.current_task_id is None

    reusable = find_reusable_planner_project_session(db_session, project_root=project_root)
    assert reusable is not None
    assert reusable.thread_id == "thread-planner-project"
    payload = json.loads(reusable.metadata_json)
    assert payload["planning_session_scope"] == "project"
    assert payload["planning_session_key"] == session_key
    assert payload["planning_project_root"] == str(project_root.resolve())
    assert payload["usage"] == {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2}


def test_validate_registry_accepts_planner_session_without_task(db_session, tmp_path):
    project_root = tmp_path / "Synapse-Network"
    project_root.mkdir()
    upsert_planner_project_session(
        db_session,
        project_root=project_root,
        thread_id="thread-planner-diagnostic",
        status="completed",
        metadata={
            "planning_requirement_id": 202,
            "planning_backend": "codex_sdk",
            "planning_model": "gpt-5.4",
        },
    )
    db_session.commit()

    report = validate_codex_session_registry(db_session, project_root=tmp_path)
    assert report["summary"]["total_sessions"] == 1
    assert report["summary"]["sessions_with_issues"] == 0
    session = report["sessions"][0]
    assert session["role_key"] == "planner"
    assert session["requirement_id"] is None
    assert session["current_task_id"] is None
    assert session["issues"] == []
    assert session["metadata_snapshot"]["planning_session_scope"] == "project"
