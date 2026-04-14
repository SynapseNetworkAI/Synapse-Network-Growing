from __future__ import annotations

import ast
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

WARN_LINE_LIMIT = 500
HARD_LINE_LIMIT = 900
WARN_LIMIT_EXCEPTIONS = {
    "server/services/workflows/orchestrator/__init__.py": "orchestrator facade is still carrying legacy lifecycle debt while deeper slices continue to move out",
    "server/services/reviews/company_review.py": "company review still holds high-level aggregation glue that has not been fully peeled into reviews helpers",
    "server/services/workflows/planner.py": "planner facade still owns plan assembly and compatibility entrypoints after provider split",
    "server/services/runtime/task_runtime.py": "runtime selection and backend contract glue are still concentrated in the primary runtime surface",
    "server/services/scheduling/recurring_workflows.py": "recurring workflow registry still bundles multiple ritual definitions and summaries",
    "server/services/signals/optimization_signals.py": "signal ingestion and requirement materialization remain in one service while taxonomy stabilizes",
    "server/services/workflows/orchestrator/artifacts.py": "artifact payload rendering and context snapshot assembly are still mid-split",
    "server/services/requirements/sources.py": "source registry and backlog materialization have not been fully split apart yet",
    "server/services/scheduling/portfolio_scheduler.py": "cross-project score calculation and scheduler execution still live together",
    "server/services/projects/intelligence.py": "project routing and serialization helpers still share one orchestration-facing module",
    "server/services/runtime/task_runner.py": "sync/async dispatch code paths still share one runner surface",
    "server/services/runtime/codex_session_registry.py": "session lifecycle and reuse bookkeeping are still coupled",
    "server/services/runtime/codex_cli.py": "CLI invocation and plugin sanitization remain in one runtime module",
    "server/services/runtime/codex_cli_monitor.py": "monitor, resume, and timeout recovery still share one monitor module",
    "server/services/delivery/deployment_governance.py": "deployment trigger, history, and overview aggregation still share one module",
}
HARD_LIMIT_EXCEPTIONS = {
    "server/services/workflows/orchestrator/__init__.py": "remaining top-level orchestrator lifecycle still exceeds the hard split threshold",
    "server/services/reviews/company_review.py": "company review glue still exceeds the hard split threshold",
    "server/services/workflows/planner.py": "planner facade still exceeds the hard split threshold",
    "server/services/runtime/task_runtime.py": "task runtime still exceeds the hard split threshold",
    "server/services/scheduling/recurring_workflows.py": "recurring workflow registry still exceeds the hard split threshold",
    "server/services/signals/optimization_signals.py": "optimization signal ingestion and taxonomy still exceed the hard split threshold while signal families stabilize",
}


def test_service_packages_include_readme_and_init() -> None:
    for relative in PACKAGE_DIRS:
        package_dir = SERVICES_ROOT / relative
        assert package_dir.is_dir(), relative
        assert (package_dir / "__init__.py").exists(), relative
        assert (package_dir / "README.md").exists(), relative


def test_service_package_readmes_include_boundary_sections() -> None:
    for relative in PACKAGE_DIRS:
        readme = (SERVICES_ROOT / relative / "README.md").read_text(encoding="utf-8")
        assert "迁移映射" in readme, relative
        assert "依赖边界" in readme, relative
        assert "禁止依赖" in readme, relative


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


def test_service_file_size_budgets_are_explicitly_governed() -> None:
    oversize_warn: list[str] = []
    oversize_hard: list[str] = []
    for path in SERVICES_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        line_count = sum(1 for _ in path.open(encoding="utf-8"))
        if line_count > WARN_LINE_LIMIT and rel not in WARN_LIMIT_EXCEPTIONS:
            oversize_warn.append(f"{rel}:{line_count}")
        if line_count > HARD_LINE_LIMIT and rel not in HARD_LIMIT_EXCEPTIONS:
            oversize_hard.append(f"{rel}:{line_count}")
    assert not oversize_warn, f"missing warn-limit exception entries: {oversize_warn}"
    assert not oversize_hard, f"missing hard-limit exception entries: {oversize_hard}"


def test_router_imports_only_service_facades() -> None:
    violations: list[str] = []
    for path in (REPO_ROOT / "server" / "routers").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            module = str(node.module)
            if not module.startswith("server.services."):
                continue
            parts = module.split(".")
            if len(parts) > 4:
                violations.append(f"{path.relative_to(REPO_ROOT)} imports deep service module {module}")
            for alias in node.names:
                if alias.name.startswith("_"):
                    violations.append(f"{path.relative_to(REPO_ROOT)} imports private service symbol {module}.{alias.name}")
    assert not violations, "\n".join(violations)


def test_server_and_tests_do_not_use_removed_flat_service_paths() -> None:
    violations: list[str] = []
    banned_modules = {f"server.services.{Path(name).stem}" for name in REMOVED_FLAT_MODULES}
    for base in ("server", "tests"):
        for path in (REPO_ROOT / base).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for module in banned_modules:
                if module in text:
                    violations.append(f"{path.relative_to(REPO_ROOT)} still references {module}")
    assert not violations, "\n".join(violations)


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
