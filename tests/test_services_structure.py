from __future__ import annotations

import importlib
import inspect
from pathlib import Path


REPO_ROOT = Path("/Users/cliff/workspace/agent/Synapse-Network-Growing")
SERVICES_ROOT = REPO_ROOT / "server" / "services"

PACKAGE_DIRS = [
    "agents",
    "runtime",
    "projects",
    "requirements",
    "bugs",
    "signals",
    "reviews",
    "scheduling",
    "delivery",
    "workflows",
    "workflows/orchestrator",
]

REMOVED_FLAT_MODULES = [
    "acceptance.py",
    "agent_loader.py",
    "agent_matcher.py",
    "alerting.py",
    "bug_intake.py",
    "bug_log_scheduler.py",
    "bug_log_sweep.py",
    "bug_sources.py",
    "codex_cli.py",
    "codex_cli_monitor.py",
    "codex_session_registry.py",
    "company_review.py",
    "context_loader.py",
    "copilot_auth.py",
    "copilot_sdk_bridge.py",
    "copilot_sdk_monitor.py",
    "copilot_sdk_state.py",
    "crew_engine.py",
    "delivery_pr.py",
    "delivery_vcs.py",
    "deployment_governance.py",
    "execution_resolver.py",
    "external_bug_adapter.py",
    "incidents.py",
    "llm_adapter.py",
    "openai_responses_monitor.py",
    "optimization_signals.py",
    "optimization_templates.py",
    "portfolio_scheduler.py",
    "project_intelligence.py",
    "project_onboarding.py",
    "project_policy.py",
    "recurring_workflows.py",
    "requirement_approval.py",
    "requirement_attachments.py",
    "requirement_family.py",
    "requirement_sources.py",
    "role_kpis.py",
    "runtime_guards.py",
    "skill_loader.py",
    "task_metadata.py",
    "task_runner.py",
    "task_runtime.py",
    "workflow_orchestrator.py",
    "workflow_planner.py",
]


def test_service_packages_include_readme_and_init() -> None:
    for relative in PACKAGE_DIRS:
        package_dir = SERVICES_ROOT / relative
        assert package_dir.is_dir(), relative
        assert (package_dir / "__init__.py").exists(), relative
        assert (package_dir / "README.md").exists(), relative


def test_service_package_readmes_include_boundary_sections() -> None:
    for relative in PACKAGE_DIRS[:-1]:
        readme = (SERVICES_ROOT / relative / "README.md").read_text(encoding="utf-8")
        assert "迁移映射" in readme, relative
        if relative != "workflows":
            assert "依赖边界" in readme, relative


def test_removed_flat_service_modules_stay_deleted() -> None:
    for filename in REMOVED_FLAT_MODULES:
        assert not (SERVICES_ROOT / filename).exists(), filename


def test_package_import_paths_resolve_public_callables() -> None:
    alerting = importlib.import_module("server.services.runtime.alerting")
    runtime_guards = importlib.import_module("server.services.runtime.runtime_guards")
    attachments = importlib.import_module("server.services.requirements.attachments")
    bug_sources = importlib.import_module("server.services.bugs.sources")

    assert callable(alerting.send_lark_text_alert)
    assert callable(runtime_guards.is_openai_runtime_guard_error)
    assert callable(attachments.persist_requirement_attachments)
    assert callable(bug_sources.list_bug_source_registry)


def test_selected_public_functions_have_docstrings() -> None:
    modules = [
        importlib.import_module("server.services.runtime.alerting"),
        importlib.import_module("server.services.runtime.runtime_guards"),
        importlib.import_module("server.services.requirements.attachments"),
        importlib.import_module("server.services.bugs.sources"),
        importlib.import_module("server.services.reviews.role_kpis"),
    ]
    for module in modules:
        for name, value in inspect.getmembers(module):
            if name.startswith("_") or not inspect.isfunction(value):
                continue
            assert value.__doc__, f"{module.__name__}.{name}"
