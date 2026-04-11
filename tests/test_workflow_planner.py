"""Tests for the agent-driven workflow planner: phase detection, dynamic file_scope, target_project_path."""
import json
import pytest
from unittest.mock import MagicMock, patch

from server.database import AgentRow, ArtifactRow, ProjectPolicyRow, RequirementRow, WorkflowStepRow
from server.services.optimization_templates import get_optimization_requirement_template
from server.services.workflow_planner import (
    _DetectedPhases,
    _base_file_scope,
    _build_implementation_steps,
    _detect_phases_fallback,
    _detect_phases_with_agent,
    _project_file_scope,
    _review_file_scope,
    build_planner_output,
)


def _mock_bridge_result(phases: dict) -> MagicMock:
    """Create a mock bridge result returning a JSON phases dict."""
    result = MagicMock()
    result.content = json.dumps(phases)
    return result


# ---------------------------------------------------------------------------
# Keyword fallback detection (still used when agent is unavailable)
# ---------------------------------------------------------------------------

class TestDetectPhasesFallback:
    def test_empty_text(self):
        p = _detect_phases_fallback("")
        assert not p.design and not p.frontend and not p.backend and not p.test_impl
        assert not p.has_sub_steps

    def test_design_only(self):
        p = _detect_phases_fallback("给出方案设计和架构")
        assert p.design
        assert not p.has_sub_steps

    def test_frontend_backend(self):
        p = _detect_phases_fallback("前端 SDK 埋点实现, 后端 API 接受埋点")
        assert p.frontend and p.backend
        assert p.has_sub_steps

    def test_full_requirement_zh(self):
        text = "方案设计，给出前端和后端的代码实现，之后给出自动化测试方案"
        p = _detect_phases_fallback(text)
        assert p.design and p.frontend and p.backend and p.test_impl

    def test_english_keywords(self):
        text = "Design the architecture, implement frontend React UI and backend API with Kafka, then add e2e tests"
        p = _detect_phases_fallback(text)
        assert p.design and p.frontend and p.backend and p.test_impl

    def test_clickhouse_triggers_backend(self):
        p = _detect_phases_fallback("使用 clickhouse 数据库存储")
        assert p.backend

    def test_react_triggers_frontend(self):
        p = _detect_phases_fallback("React component for analytics dashboard")
        assert p.frontend

    def test_pytest_triggers_test_impl(self):
        p = _detect_phases_fallback("Write pytest integration tests")
        assert p.test_impl


# ---------------------------------------------------------------------------
# Agent-based phase detection
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _detect_phases_with_agent is now keyword-only (no agent call)
# ---------------------------------------------------------------------------

class TestDetectPhasesWithAgent:
    def test_all_phases_from_keywords(self):
        p = _detect_phases_with_agent("Build analytics pipeline: schema design, frontend SDK, backend API, pytest tests")
        assert p.design and p.frontend and p.backend and p.test_impl

    def test_no_phases_for_content(self):
        p = _detect_phases_with_agent("Write a blog post about blockchain")
        assert not p.design and not p.frontend and not p.backend and not p.test_impl

    def test_partial_phases(self):
        p = _detect_phases_with_agent("实现前端和后端")
        assert not p.design
        assert p.frontend and p.backend
        assert not p.test_impl
        assert p.has_sub_steps

    def test_fallback_design_frontend_backend(self):
        p = _detect_phases_with_agent("方案设计，给出前端和后端的代码实现")
        assert p.design and p.frontend and p.backend

    def test_fallback_design_backend(self):
        p = _detect_phases_with_agent("方案设计，给出后端实现")
        assert p.design and p.backend


# ---------------------------------------------------------------------------
# File scope generation
# ---------------------------------------------------------------------------

class TestFileScope:
    def test_base_scope_has_roles_docs(self):
        scope = _base_file_scope()
        assert "roles/**" in scope["allowed_read_globs"]
        assert "roles/**" in scope["allowed_write_globs"]
        assert ".git/**" in scope["blocked_globs"]

    def test_project_scope_without_path(self):
        scope = _project_file_scope(None)
        assert scope == _base_file_scope()

    def test_project_scope_with_path(self):
        path = "/Users/cliff/workspace/agent/Synapse-Network"
        scope = _project_file_scope(path)
        assert f"{path}/**" in scope["allowed_read_globs"]
        assert f"{path}/**" in scope["allowed_write_globs"]

    def test_project_scope_readonly(self):
        path = "/Users/cliff/workspace/agent/Synapse-Network"
        scope = _project_file_scope(path, write=False)
        assert f"{path}/**" in scope["allowed_read_globs"]
        assert f"{path}/**" not in scope["allowed_write_globs"]

    def test_review_scope_is_readonly(self):
        path = "/some/project"
        scope = _review_file_scope(path)
        assert f"{path}/**" in scope["allowed_read_globs"]
        assert f"{path}/**" not in scope["allowed_write_globs"]
        # But can still write to roles/**
        assert "roles/**" in scope["allowed_write_globs"]

    def test_trailing_slash_stripped(self):
        scope = _project_file_scope("/some/path/")
        assert "/some/path/**" in scope["allowed_read_globs"]


# ---------------------------------------------------------------------------
# Implementation step building
# ---------------------------------------------------------------------------

def _mock_requirement(title="Test", description="", target_path=None):
    req = MagicMock(spec=RequirementRow)
    req.title = title
    req.description_markdown = description
    req.target_project_path = target_path
    return req


class TestBuildImplementationSteps:
    def test_single_step_when_no_sub_phases(self):
        req = _mock_requirement(title="Simple task")
        phases = _DetectedPhases()
        steps, keys = _build_implementation_steps(req, phases, None)
        assert len(steps) == 1
        assert keys == ["implementation"]
        assert steps[0]["step_key"] == "implementation"

    def test_multi_phase_creates_sub_steps(self):
        req = _mock_requirement(title="Full stack")
        phases = _DetectedPhases(design=True, frontend=True, backend=True, test_impl=True)
        steps, keys = _build_implementation_steps(req, phases, "/proj")
        assert keys == ["design", "frontend_impl", "backend_impl", "test_impl"]
        assert len(steps) == 4
        # Check dependency chain
        assert steps[0]["depends_on"] == []
        assert steps[1]["depends_on"] == ["design"]
        assert steps[2]["depends_on"] == ["frontend_impl"]
        assert steps[3]["depends_on"] == ["backend_impl"]

    def test_frontend_backend_only(self):
        req = _mock_requirement(title="FB only")
        phases = _DetectedPhases(frontend=True, backend=True)
        steps, keys = _build_implementation_steps(req, phases, "/proj")
        assert keys == ["frontend_impl", "backend_impl"]
        assert steps[0]["depends_on"] == []
        assert steps[1]["depends_on"] == ["frontend_impl"]

    def test_target_path_in_done_when(self):
        req = _mock_requirement(title="Code task")
        phases = _DetectedPhases(frontend=True, backend=True)
        steps, keys = _build_implementation_steps(req, phases, "/my/project")
        for step in steps:
            assert "/my/project" in step["done_when_markdown"]

    def test_file_scope_includes_project_path(self):
        req = _mock_requirement(title="Code task")
        phases = _DetectedPhases(frontend=True, backend=True)
        steps, _ = _build_implementation_steps(req, phases, "/my/project")
        for step in steps:
            assert "/my/project/**" in step["file_scope"]["allowed_write_globs"]


# ---------------------------------------------------------------------------
# Full planner output (integration with DB — mock agent)
# ---------------------------------------------------------------------------

def _patch_agent_phases(phases: dict):
    """Return a context manager that mocks the bridge to return the given phases."""
    mock_bridge_cls = MagicMock()
    mock_bridge_cls.return_value.run_session.return_value = _mock_bridge_result(phases)
    return patch("server.services.copilot_sdk_bridge.CopilotSDKBridge", mock_bridge_cls)


class TestBuildPlannerOutput:
    def test_plan_with_target_project_path(self, synced_client, db_session):
        req = RequirementRow(
            title="埋点系统",
            description_markdown="方案设计，给出前端和后端的代码实现，之后给出自动化测试方案",
            target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        )
        db_session.add(req)
        db_session.flush()

        with _patch_agent_phases({"design": True, "frontend": True, "backend": True, "test_impl": True}):
            output, assignments = build_planner_output(db_session, req)

        step_keys = [s["step_key"] for s in output["workflow_steps"]]

        # Should have research, synthesis, implementation sub-steps + review + test + closeout
        assert step_keys[:2] == ["research", "synthesis"]
        assert "design" in step_keys
        assert "frontend_impl" in step_keys
        assert "backend_impl" in step_keys
        assert "test_impl" in step_keys
        assert "review" in step_keys
        assert "test" in step_keys
        assert "closeout" in step_keys

        assert output["target_project_path"] == "/Users/cliff/workspace/agent/Synapse-Network"
        assert output["project_policies"][0]["project_key"] == "synapse-network"
        assert output["schema_version"] == "1.6"
        assert output["detected_phases"]["design"] is True
        assert output["project_intelligence"]["routing_mode"] == "explicit"
        assert output["project_intelligence"]["project_scorecards"][0]["project_key"] == "synapse-network"
        assert output["validation_plan"]["bugfix_owner_role"] == "implementer"
        assert output["validation_plan"]["closeout_owner_role"] == "tester"
        assert output["validation_plan"]["manual_checks"][0]["check_key"] == "review_passed"
        assert output["validation_plan"]["automated_checks"][0]["check_key"] == "validation_passed"
        assert output["delivery_contract"]["branch_strategy"] == "requirement_branch"
        assert output["delivery_contract"]["branch_name"].startswith(f"ops/req-{req.id}-")
        assert output["delivery_contract"]["release_mode"] == "manual"
        assert output["delivery_contract"]["required_checks"]
        assert output["delivery_contract"]["required_capabilities"] == ["git_push", "publish"]
        assert output["delivery_contract"]["auto_publish_allowed"] is False
        assert output["execution_controls"]["capability_matrix"]["shell_access"] is True
        assert output["extensions"]["role_assignments"]["researcher_agent_id"]
        assert output["extensions"]["role_assignments"]["synthesizer_agent_id"]

        # Review should depend on the last impl step (test_impl)
        review_step = next(s for s in output["workflow_steps"] if s["step_key"] == "review")
        assert review_step["depends_on"] == ["test_impl"]
        first_impl = next(s for s in output["workflow_steps"] if s["step_key"] == "design")
        assert first_impl["depends_on"] == ["synthesis"]
        assert first_impl["approval_policy"]["required_capabilities"] == ["shell_access", "git_read", "git_write"]
        assert first_impl["approval_policy"]["deny_execution"] is False

    def test_plan_without_target_project_path(self, synced_client, db_session):
        req = RequirementRow(
            title="Write a blog post",
            description_markdown="Write a marketing blog post about Synapse",
        )
        db_session.add(req)
        db_session.flush()

        with _patch_agent_phases({"design": False, "frontend": False, "backend": False, "test_impl": False}):
            output, _ = build_planner_output(db_session, req)

        step_keys = [s["step_key"] for s in output["workflow_steps"]]

        # Should fall back to research + synthesis + single implementation step
        assert step_keys[:3] == ["research", "synthesis", "implementation"]
        assert "implementation" in step_keys
        assert "design" not in step_keys
        assert output["target_project_path"] is None
        assert output["project_intelligence"]["routing_mode"] == "unrouted"

    def test_plan_simple_backend_frontend(self, synced_client, db_session):
        req = RequirementRow(
            title="Feature X",
            description_markdown="实现前端 UI 和后端 API",
            target_project_path="/proj",
        )
        db_session.add(req)
        db_session.flush()

        with _patch_agent_phases({"design": False, "frontend": True, "backend": True, "test_impl": False}):
            output, _ = build_planner_output(db_session, req)

        step_keys = [s["step_key"] for s in output["workflow_steps"]]
        assert step_keys == ["research", "synthesis", "frontend_impl", "backend_impl", "review", "test", "closeout"]

    def test_policy_augments_file_scope(self, synced_client, db_session):
        db_session.add(
            ProjectPolicyRow(
                project_key="proj-policy",
                display_name="Proj Policy",
                root_path="/proj",
                status="active",
                allowed_write_globs_json='["src/**"]',
                forbidden_globs_json='["secrets/**"]',
                required_checks_json='["pytest -q"]',
                release_mode="manual",
                requires_manual_approval=True,
            )
        )
        db_session.commit()

        req = RequirementRow(
            title="Scoped feature",
            description_markdown="实现前端 UI 和后端 API",
            target_project_path="/proj",
        )
        db_session.add(req)
        db_session.flush()

        with _patch_agent_phases({"design": False, "frontend": True, "backend": True, "test_impl": False}):
            output, _ = build_planner_output(db_session, req)

        frontend_step = next(s for s in output["workflow_steps"] if s["step_key"] == "frontend_impl")
        assert "/proj/src/**" in frontend_step["file_scope"]["allowed_write_globs"]
        assert "/proj/secrets/**" in frontend_step["file_scope"]["blocked_globs"]

    def test_capability_matrix_marks_step_as_denied_when_shell_is_disabled(self, synced_client, db_session):
        db_session.add(
            ProjectPolicyRow(
                project_key="restricted-proj",
                display_name="Restricted Proj",
                root_path="/restricted",
                status="active",
                allowed_write_globs_json='["src/**"]',
                forbidden_globs_json='["secrets/**"]',
                required_checks_json='[]',
                release_mode="manual",
                requires_manual_approval=True,
                capability_matrix_json=json.dumps({
                    "shell_access": False,
                    "git_read": True,
                    "git_write": True,
                    "git_push": False,
                    "network_access": False,
                    "publish": False,
                }),
                interrupt_policy_json=json.dumps({
                    "operator_confirmation_actions": ["publish"],
                    "auto_pause_on_events": ["capability_denied"],
                    "auto_abort_on_events": ["forbidden_write"],
                }),
            )
        )
        db_session.commit()

        req = RequirementRow(
            title="Restricted feature",
            description_markdown="实现后端 API",
            target_project_path="/restricted",
        )
        db_session.add(req)
        db_session.flush()

        with _patch_agent_phases({"design": False, "frontend": False, "backend": True, "test_impl": False}):
            output, _ = build_planner_output(db_session, req)

        research_step = next(s for s in output["workflow_steps"] if s["step_key"] == "research")
        implementation_step = next(s for s in output["workflow_steps"] if s["step_key"] == "implementation")
        assert research_step["approval_policy"]["deny_execution"] is True
        assert "shell_access disabled by project capability matrix" in research_step["approval_policy"]["deny_reasons"]
        assert implementation_step["approval_policy"]["required_capabilities"] == ["shell_access", "git_read", "git_write"]

    def test_auto_routing_metadata_for_sdk_requirement(self, synced_client, db_session):
        req = RequirementRow(
            title="Improve SDK integration",
            description_markdown="Update the Python SDK MCP integration flow for developers.",
        )
        db_session.add(req)
        db_session.flush()

        with _patch_agent_phases({"design": False, "frontend": False, "backend": False, "test_impl": False}):
            output, _ = build_planner_output(db_session, req)

        assert output["project_intelligence"]["routing_mode"] == "auto"
        assert output["project_intelligence"]["routed_project_keys"] == ["synapse-network-sdk"]

    def test_template_acceptance_checks_are_merged_into_planner_output(self, synced_client, db_session):
        req = RequirementRow(
            title="Template-backed release work",
            description_markdown="Remove recurring release blockers.",
            target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        )
        db_session.add(req)
        db_session.flush()
        template = get_optimization_requirement_template("release_bottleneck")
        db_session.add(
            ArtifactRow(
                requirement_id=req.id,
                artifact_type="requirement_template",
                content_summary="Template context",
                machine_readable_payload=json.dumps({
                    "template_key": template["template_key"],
                    "acceptance_checks": template["acceptance_checks"],
                }),
            )
        )
        db_session.commit()

        with _patch_agent_phases({"design": False, "frontend": False, "backend": True, "test_impl": True}):
            output, _ = build_planner_output(db_session, req)

        acceptance_keys = [item["check_key"] for item in output["acceptance_checks"]]
        assert "review_passed" in acceptance_keys
        assert "validation_passed" in acceptance_keys
        assert "release_blocker_removed" in acceptance_keys
        assert "rollback_path_documented" in acceptance_keys
        assert output["requirement_template"]["template_key"] == "release_bottleneck"

        review_step = next(step for step in output["workflow_steps"] if step["step_key"] == "review")
        test_step = next(step for step in output["workflow_steps"] if step["step_key"] == "test")
        assert any(target["check_key"] == "rollback_path_documented" for target in review_step["validation_targets"])
        assert any(target["check_key"] == "release_blocker_removed" for target in test_step["validation_targets"])


# ---------------------------------------------------------------------------
# API integration: create requirement with target_project_path
# ---------------------------------------------------------------------------

class TestRequirementApiWithProjectPath:
    def test_create_requirement_with_target_project_path(self, synced_client):
        resp = synced_client.post(
            "/api/requirements",
            json={
                "title": "Analytics pipeline",
                "description_markdown": "Build 前端 SDK and 后端 API",
                "target_project_path": "/Users/cliff/workspace/Synapse-Network",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["requirement"]["target_project_path"] == "/Users/cliff/workspace/Synapse-Network"

    def test_create_requirement_without_target_project_path(self, synced_client):
        resp = synced_client.post(
            "/api/requirements",
            json={
                "title": "Simple task",
                "description_markdown": "Write a blog post",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["requirement"]["target_project_path"] is None

    def test_plan_with_target_path_creates_multi_steps(self, synced_client, db_session):
        create_resp = synced_client.post(
            "/api/requirements",
            json={
                "title": "Full stack feature",
                "description_markdown": "方案设计，给出前端和后端的代码实现，之后给出自动化测试方案",
                "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network",
            },
        )
        requirement_id = create_resp.json()["requirement"]["id"]

        with _patch_agent_phases({"design": True, "frontend": True, "backend": True, "test_impl": True}):
            plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")

        assert plan_resp.status_code == 200
        steps = plan_resp.json()["workflow_run"]["steps"]
        step_keys = [s["step_key"] for s in steps]

        # All context + implementation sub-steps + review + test + closeout
        assert step_keys[:2] == ["research", "synthesis"]
        assert "design" in step_keys
        assert "frontend_impl" in step_keys
        assert "backend_impl" in step_keys
        assert "test_impl" in step_keys
        assert "review" in step_keys
        assert "test" in step_keys
        assert "closeout" in step_keys

        # Verify file_scope from DB directly
        impl_step = db_session.query(WorkflowStepRow).filter(
            WorkflowStepRow.step_key == "frontend_impl",
            WorkflowStepRow.requirement_id == requirement_id,
        ).first()
        scope = json.loads(impl_step.file_scope_json)
        assert "/Users/cliff/workspace/agent/Synapse-Network/**" in scope["allowed_write_globs"]

    def test_plan_without_target_path_creates_single_impl_step(self, synced_client):
        create_resp = synced_client.post(
            "/api/requirements",
            json={
                "title": "Blog post",
                "description_markdown": "Write a marketing blog post",
            },
        )
        requirement_id = create_resp.json()["requirement"]["id"]

        with _patch_agent_phases({"design": False, "frontend": False, "backend": False, "test_impl": False}):
            plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")

        assert plan_resp.status_code == 200
        steps = plan_resp.json()["workflow_run"]["steps"]
        impl_steps = [s for s in steps if s["step_type"] == "implementation"]
        assert len(impl_steps) == 1
        assert impl_steps[0]["step_key"] == "implementation"
        all_step_keys = [s["step_key"] for s in steps]
        assert all_step_keys[:3] == ["research", "synthesis", "implementation"]
