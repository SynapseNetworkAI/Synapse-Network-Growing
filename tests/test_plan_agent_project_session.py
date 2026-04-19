from __future__ import annotations

import json
from pathlib import Path

from server.database import CodexSessionRow, RequirementRow
from server.services.runtime.codex_session_registry import build_planner_project_session_key
from server.services.requirements import service as requirement_service
from server.services.requirements.service import _generate_plan_brief_markdown_with_agent
from server.services.workflows.planner_provider import PlannerResponse


def test_plan_agent_reuses_project_scoped_session_for_same_project(db_session, tmp_path, monkeypatch):
    project_root = (tmp_path / "Synapse-Network").resolve()
    project_root.mkdir()
    calls: list[dict] = []

    def fake_generate_planner_text(request):
        calls.append(request)
        metadata = request.metadata
        metadata.update(
            {
                "planning_session_id": "thread-project-plan",
                "planning_backend": "codex_cli",
                "planning_model": metadata["planning_model"],
                "planning_command": ["codex", "exec"],
            }
        )
        return PlannerResponse(text="Project scoped plan", tokens=0, backend="codex_cli", model=metadata["planning_model"])

    monkeypatch.setattr(requirement_service, "resolve_planner_backend", lambda: "codex_cli")
    monkeypatch.setattr(requirement_service, "resolve_planner_model", lambda backend: "gpt-5.4")
    monkeypatch.setattr(requirement_service, "generate_planner_text", fake_generate_planner_text)

    req1 = RequirementRow(
        title="Requirement one",
        description_markdown="Plan first requirement.",
        target_project_path=str(project_root),
        execution_plan_json=json.dumps({"planning_session_id": "thread-old-requirement"}),
    )
    req2 = RequirementRow(
        title="Requirement two",
        description_markdown="Plan second requirement.",
        target_project_path=str(project_root),
    )
    db_session.add_all([req1, req2])
    db_session.commit()

    plan1, metadata1 = _generate_plan_brief_markdown_with_agent(
        db_session,
        req1,
        acceptance_contract={},
    )
    plan2, metadata2 = _generate_plan_brief_markdown_with_agent(
        db_session,
        req2,
        acceptance_contract={},
    )

    assert plan1 == "Project scoped plan"
    assert plan2 == "Project scoped plan"
    assert calls[0].resume_session_id == "thread-old-requirement"
    assert calls[1].resume_session_id == "thread-project-plan"
    assert metadata1["planning_session_scope"] == "project"
    assert metadata1["planning_resume_source"] == "requirement"
    assert metadata2["planning_resume_source"] == "project"
    assert metadata2["planning_project_root"] == str(project_root)
    assert metadata2["planning_session_key"] == build_planner_project_session_key(project_root=project_root)

    row = db_session.query(CodexSessionRow).filter(CodexSessionRow.role_key == "planner").one()
    assert row.project_root == str(project_root)
    assert row.requirement_id is None
    assert row.current_task_id is None
    assert row.thread_id == "thread-project-plan"
    payload = json.loads(row.metadata_json)
    assert payload["planning_session_scope"] == "project"
    assert payload["planning_requirement_id"] == req2.id
    assert payload["planning_session_key"] == build_planner_project_session_key(project_root=project_root)


def test_plan_agent_keeps_different_projects_isolated(db_session, tmp_path, monkeypatch):
    project_a = (tmp_path / "Project-A").resolve()
    project_b = (tmp_path / "Project-B").resolve()
    project_a.mkdir()
    project_b.mkdir()
    calls: list[dict] = []

    def fake_generate_planner_text(request):
        calls.append(request)
        output_path = Path(request.output_path)
        thread_id = f"thread-{output_path.stem}"
        request.metadata.update({"planning_session_id": thread_id})
        return PlannerResponse(text=f"Plan for {output_path.stem}", tokens=0, backend="codex_cli", model="gpt-5.4")

    monkeypatch.setattr(requirement_service, "resolve_planner_backend", lambda: "codex_cli")
    monkeypatch.setattr(requirement_service, "resolve_planner_model", lambda backend: "gpt-5.4")
    monkeypatch.setattr(requirement_service, "generate_planner_text", fake_generate_planner_text)

    req_a = RequirementRow(
        title="Requirement A",
        description_markdown="Plan project A.",
        target_project_path=str(project_a),
    )
    req_b = RequirementRow(
        title="Requirement B",
        description_markdown="Plan project B.",
        target_project_path=str(project_b),
    )
    db_session.add_all([req_a, req_b])
    db_session.commit()

    _generate_plan_brief_markdown_with_agent(db_session, req_a, acceptance_contract={})
    _generate_plan_brief_markdown_with_agent(db_session, req_b, acceptance_contract={})

    assert calls[0].resume_session_id is None
    assert calls[1].resume_session_id is None
    rows = db_session.query(CodexSessionRow).filter(CodexSessionRow.role_key == "planner").all()
    assert {row.project_root for row in rows} == {str(project_a), str(project_b)}
