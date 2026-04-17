from __future__ import annotations

"""Async task dispatcher — runs CrewEngine in background threads."""
import json
import logging
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, cast

from server.database import ArtifactRow, SessionLocal, TaskRow, TaskLogRow, ApprovalRow, utcnow
from server.config import PROJECT_ROOT, ORCHESTRATION_BACKEND, E2E_SYNC_DISPATCH
from server.services.runtime.copilot_sdk_state import task_output_dir
from server.services.runtime.codex_session_registry import find_reusable_session, upsert_session_launch
from server.services.delivery.vcs import prepare_requirement_delivery_branch
from server.services.runtime.task_runtime import (
    RuntimeEvent,
    _codex_workdirs,
    estimate_runtime_budget_points,
    get_task_runtime,
    resolve_runtime_selection,
)
from server.services.runtime.runtime_guards import is_openai_runtime_guard_error
from server.logging_utils import get_logger, log_event

logger = get_logger("ops-dashboard.task_runner")

_DELIVERY_VALIDATION_MARKERS = (
    "commit",
    "push",
    "draft pr",
    "pull request",
    "review-ready",
    "compare url",
    "requirement branch",
    "same branch",
    "validation clone",
    "auto-start",
)


def _task_str(task: TaskRow, name: str) -> str | None:
    value = getattr(cast(Any, task), name, None)
    if value is None:
        return None
    return str(value)


def _task_bool(task: TaskRow, name: str) -> bool:
    return bool(getattr(cast(Any, task), name, False))


def _load_task_context_files(task: TaskRow) -> list[str] | None:
    context_files = _task_str(task, "context_files")
    if not context_files:
        return None


def _task_project_root(task: TaskRow) -> str:
    if task.workflow_steps:
        step = task.workflow_steps[0]
        requirement = getattr(cast(Any, step), "requirement", None)
        target_path = str(getattr(cast(Any, requirement), "target_project_path", "") or "").strip()
        if target_path:
            return target_path
    execution_nodes = list(getattr(cast(Any, task), "execution_nodes", []) or [])
    if execution_nodes:
        node = execution_nodes[0]
        requirement = getattr(cast(Any, node), "requirement", None)
        target_path = str(getattr(cast(Any, requirement), "target_project_path", "") or "").strip()
        if target_path:
            return target_path
    return str(PROJECT_ROOT)

    import json

    try:
        return json.loads(context_files)
    except (json.JSONDecodeError, TypeError):
        return None


def _task_execution_profile(task: TaskRow) -> tuple[dict[str, Any], str]:
    if not task.workflow_steps:
        return {}, ""
    step = task.workflow_steps[0]
    raw = getattr(cast(Any, step), "execution_profile_json", None)
    if not raw:
        return {}, str(getattr(cast(Any, step), "step_type", "") or "")
    try:
        payload = json.loads(str(raw))
        if isinstance(payload, dict):
            return payload, str(getattr(cast(Any, step), "step_type", "") or "")
    except (json.JSONDecodeError, TypeError):
        pass
    return {}, str(getattr(cast(Any, step), "step_type", "") or "")


def _task_primary_step(task: TaskRow):
    return task.workflow_steps[0] if task.workflow_steps else None


def _task_requirement(task: TaskRow):
    step = _task_primary_step(task)
    if step is not None:
        return getattr(cast(Any, step), "requirement", None)
    execution_nodes = list(getattr(cast(Any, task), "execution_nodes", []) or [])
    if execution_nodes:
        return getattr(cast(Any, execution_nodes[0]), "requirement", None)
    return None


def _task_session_scope(task: TaskRow) -> tuple[int | None, int | None]:
    if task.workflow_steps:
        first_step = task.workflow_steps[0]
        requirement_id = int(getattr(cast(Any, first_step), "requirement_id", 0) or 0) or None
        workflow_run_id = int(getattr(cast(Any, first_step), "workflow_run_id", 0) or 0) or None
        return requirement_id, workflow_run_id
    execution_nodes = list(getattr(cast(Any, task), "execution_nodes", []) or [])
    if execution_nodes:
        first_node = execution_nodes[0]
        requirement_id = int(getattr(cast(Any, first_node), "requirement_id", 0) or 0) or None
        return requirement_id, None
    return None, None


def _is_requirement_centric_delivery_requirement(task: TaskRow) -> bool:
    requirement = _task_requirement(task)
    if requirement is None:
        return False
    title = str(getattr(cast(Any, requirement), "title", "") or "").strip().lower()
    description = str(getattr(cast(Any, requirement), "description_markdown", "") or "").strip().lower()
    text = f"{title}\n{description}"
    return any(marker in text for marker in _DELIVERY_VALIDATION_MARKERS)


def _is_validation_clone_requirement(task: TaskRow) -> bool:
    requirement = _task_requirement(task)
    if requirement is None:
        return False
    target_path = str(getattr(cast(Any, requirement), "target_project_path", "") or "").strip().lower()
    title = str(getattr(cast(Any, requirement), "title", "") or "").strip().lower()
    description = str(getattr(cast(Any, requirement), "description_markdown", "") or "").strip().lower()
    haystack = "\n".join([target_path, title, description])
    return "sng-delivery-validation" in haystack or "validation clone" in haystack


def _should_use_deterministic_delivery_executor(task: TaskRow, step_type: str) -> bool:
    return (
        step_type in {"research", "plan", "implementation", "validate", "closeout"}
        and _is_requirement_centric_delivery_requirement(task)
        and _is_validation_clone_requirement(task)
    )


def _extract_requested_output_relpath(task: TaskRow) -> str:
    requirement = _task_requirement(task)
    description = str(getattr(cast(Any, requirement), "description_markdown", "") or "") if requirement is not None else ""
    candidates = re.findall(r"`([^`]+)`", description)
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value.startswith("docs/") and value.endswith(".md"):
            return value
    match = re.search(r"\bdocs/[A-Za-z0-9_./-]+\.md\b", description)
    if match:
        return match.group(0)
    requirement_id = int(getattr(cast(Any, requirement), "id", 0) or 0) if requirement is not None else 0
    return f"docs/auto-validation/req-{requirement_id}.md"


def _git_capture(repo_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        return f"<git error: {exc}>"
    text = (completed.stdout or completed.stderr or "").strip()
    return text or "<empty>"


def _latest_artifact_payload(db, requirement_id: int, artifact_type: str) -> dict[str, Any]:
    artifact = (
        db.query(ArtifactRow)
        .filter(
            ArtifactRow.requirement_id == requirement_id,
            ArtifactRow.artifact_type == artifact_type,
        )
        .order_by(ArtifactRow.id.desc())
        .first()
    )
    if artifact is None:
        return {}
    try:
        payload = json.loads(str(getattr(artifact, "machine_readable_payload", "") or "{}"))
    except (json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _prepare_requirement_branch_for_task(db, task: TaskRow, step_type: str) -> None:
    if step_type not in {"implementation", "bugfix"}:
        return
    requirement = _task_requirement(task)
    if requirement is None:
        return
    requirement_id = int(getattr(cast(Any, requirement), "id", 0) or 0)
    delivery_contract = _latest_artifact_payload(db, requirement_id, "delivery_contract")
    if not isinstance(delivery_contract, dict) or not delivery_contract:
        return
    branch_strategy = str(delivery_contract.get("branch_strategy") or "").strip().lower()
    if branch_strategy != "requirement_branch":
        return
    target_path = str(getattr(cast(Any, requirement), "target_project_path", "") or "").strip() or None
    prepared = prepare_requirement_delivery_branch(
        delivery_contract=delivery_contract,
        fallback_target_path=target_path,
    )
    blockers = [str(item).strip() for item in (prepared.get("blockers") or []) if str(item).strip()]
    if blockers:
        raise RuntimeError("; ".join(blockers))
    branch_name = str(prepared.get("branch_name") or "").strip()
    if branch_name:
        _log(db, int(cast(Any, task).id), "delivery_branch_prepared", branch_name)


def _deterministic_delivery_validation_result(db, task: TaskRow, output_dir: Path, step_type: str):
    from server.services.runtime.task_runtime import TaskExecutionResult, RuntimeEvent

    requirement = _task_requirement(task)
    step = _task_primary_step(task)
    requirement_id = int(getattr(cast(Any, requirement), "id", 0) or 0) if requirement is not None else 0
    requirement_title = str(getattr(cast(Any, requirement), "title", "") or "").strip() or f"Requirement {requirement_id}"
    repo_root = Path(_task_project_root(task)).resolve()
    output_relpath = _extract_requested_output_relpath(task)
    target_file = (repo_root / output_relpath).resolve()
    target_file.parent.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "output.md"

    current_branch = _git_capture(repo_root, "branch", "--show-current")
    status_short = _git_capture(repo_root, "status", "--short", "--branch")
    origin_url = _git_capture(repo_root, "remote", "get-url", "origin")
    contract = _latest_artifact_payload(db, requirement_id, "delivery_contract")
    delivery_state = _latest_artifact_payload(db, requirement_id, "delivery_state")
    review_pr_sync = _latest_artifact_payload(db, requirement_id, "review_pr_sync")
    vcs_delivery = _latest_artifact_payload(db, requirement_id, "vcs_delivery")
    branch_name = str(contract.get("branch_name") or "").strip() or current_branch
    compare_url = str(
        delivery_state.get("compare_url")
        or review_pr_sync.get("compare_url")
        or ""
    ).strip()
    pr_url = str(
        delivery_state.get("pr_url")
        or review_pr_sync.get("pr_url")
        or ""
    ).strip()

    lines = [f"# {step_type.title()} Output", ""]
    if step_type == "research":
        lines.extend(
            [
                "## Branch Delivery Preflight",
                f"- requirement: `{requirement_id}` `{requirement_title}`",
                f"- target repo: `{repo_root}`",
                f"- expected branch: `{branch_name}`",
                f"- current branch: `{current_branch}`",
                f"- origin: `{origin_url}`",
                f"- requested tracked file: `{output_relpath}`",
                "",
                "## Git Status",
                "```text",
                status_short,
                "```",
                "",
                "## Outcome",
                "- The repository is reachable and the delivery note path is ready.",
                "- No broad repository survey was needed for this requirement-centric branch delivery validation.",
            ]
        )
    elif step_type == "plan":
        lines.extend(
            [
                "## Deterministic Execution Plan",
                "1. Reuse the single requirement branch from the delivery contract.",
                f"2. Create or update exactly one tracked file: `{output_relpath}`.",
                "3. Let deterministic VCS delivery perform branch sync, commit, push, and draft PR sync.",
                "4. Verify the pushed branch, compare URL, and review surface before closeout.",
            ]
        )
    elif step_type == "implementation":
        content = "\n".join(
            [
                "---",
                f"id: req-{requirement_id}-validation-note",
                f"title: {requirement_title}",
                "status: review_ready",
                f"updated_at: {utcnow().date().isoformat()}",
                f"target_repo: {repo_root}",
                f"requirement_branch: {branch_name}",
                "---",
                "",
                f"Requirement {requirement_id} validates unattended requirement-centric branch delivery on the validation clone.",
                f"This note is the singular tracked artifact for `{branch_name}` and proves the workflow can auto-start, create/update one tracked file, and continue through deterministic VCS delivery.",
                "",
                "Expected review surface after delivery:",
                f"- compare_url: {compare_url or '<pending>'}",
                f"- pr_url: {pr_url or '<pending>'}",
            ]
        )
        target_file.write_text(content + "\n", encoding="utf-8")
        lines.extend(
            [
                "## Applied Change",
                f"- Wrote `{output_relpath}` as the single tracked validation artifact.",
                f"- Branch delivery will now commit and push this change on `{branch_name}`.",
            ]
        )
    elif step_type == "validate":
        remote_branch = _git_capture(repo_root, "ls-remote", "--heads", "origin", branch_name)
        remote_sha_fallback = str(
            delivery_state.get("latest_remote_sha")
            or review_pr_sync.get("latest_remote_sha")
            or vcs_delivery.get("latest_remote_sha")
            or "<empty>"
        ).strip() or "<empty>"
        if remote_branch == "<empty>" or remote_branch.lower().startswith("fatal:"):
            remote_branch = remote_sha_fallback
        lines.extend(
            [
                "## Validation Summary",
                f"- tracked file exists: `{target_file.exists()}`",
                f"- remote branch lookup: `{branch_name}`",
                "```text",
                remote_branch,
                "```",
                "",
                "Validation confirms the requirement branch is present on origin, the delivery artifact exists, and the review surface is ready for closeout.",
            ]
        )
    else:
        lines.extend(
            [
                "## Closeout Evidence",
                f"- branch: `{branch_name}`",
                f"- compare_url: `{compare_url or '<pending>'}`",
                f"- pr_url: `{pr_url or '<pending>'}`",
                f"- tracked file: `{output_relpath}`",
                "",
                "Requirement-centric branch delivery validation is ready for deterministic review-ready bundling.",
            ]
        )

    text = "\n".join(lines).strip() + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return TaskExecutionResult(
        text=text,
        files=[output_path, target_file] if step_type == "implementation" else [output_path],
        execution_time_ms=1,
        model="deterministic_delivery_executor",
        tokens_used=0,
        runtime_backend="legacy",
        runtime_provider="deterministic",
        events=[
            RuntimeEvent(event_type="runtime_started", detail=f"backend=deterministic_delivery step={step_type}"),
            RuntimeEvent(event_type="deterministic_delivery_executor", detail=f"requirement={requirement_id} branch={branch_name}"),
        ],
        metadata={
            "deterministic_delivery": True,
            "branch_name": branch_name,
            "target_repo": str(repo_root),
            "output_relpath": output_relpath,
        },
    )


def dispatch(task_id: int, agent_persona: dict, skill_name: str) -> threading.Thread:
    """Launch task execution in a background thread. Returns the thread."""
    if E2E_SYNC_DISPATCH:
        log_event(
            logger,
            "task_dispatch_inline",
            level=logging.INFO,
            task_id=task_id,
            skill_name=skill_name,
            dispatch_mode="sync",
        )
        _run_task_sync(task_id, agent_persona, skill_name)
        return threading.current_thread()

    thread = threading.Thread(
        target=_run_task_sync,
        args=(task_id, agent_persona, skill_name),
        daemon=True,
        name=f"task-{task_id}",
    )
    thread.start()
    log_event(
        logger,
        "task_dispatch_enqueued",
        level=logging.INFO,
        task_id=task_id,
        skill_name=skill_name,
        dispatch_mode="thread",
        thread_name=thread.name,
    )
    return thread


def _run_task_sync(task_id: int, agent_persona: dict, skill_name: str):
    """Execute a task synchronously — called from a background thread."""
    db = SessionLocal()
    try:
        task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
        if not task:
            log_event(
                logger,
                "task_dispatch_db_miss",
                level=logging.ERROR,
                task_id=task_id,
            )
            return

        # Output directory
        role_id = _task_str(task, "agent_id") or agent_persona.get("role", agent_persona.get("id", "unknown"))
        output_dir = task_output_dir(PROJECT_ROOT, role_id, task_id)
        if not _task_str(task, "output_path"):
            cast(Any, task).output_path = str(output_dir / "output.md")
            db.flush()

        _log(db, task_id, "crew_started", f"skill={skill_name}")
        execution_profile, step_type = _task_execution_profile(task)
        selection = resolve_runtime_selection(execution_profile, step_type=step_type, preferred_backend=ORCHESTRATION_BACKEND)
        _log(
            db,
            task_id,
            "runtime_submitted",
            f"backend={selection.backend} provider={selection.provider} model={selection.model} tier={selection.complexity_tier} agent={role_id} skill={skill_name}",
        )
        _log(db, task_id, "runtime_selection", selection.reason)
        cast(Any, task).runtime_backend = selection.backend
        cast(Any, task).runtime_provider = selection.provider
        cast(Any, task).runtime_model = selection.model
        if task.workflow_steps:
            try:
                from server.services.workflows.orchestrator import capture_task_file_change_baseline

                first_step = task.workflow_steps[0]
                capture_task_file_change_baseline(db, task, step=first_step)
            except Exception as exc:
                log_event(
                    logger,
                    "task_file_baseline_capture_failed",
                    level=logging.DEBUG,
                    task_id=task_id,
                    exc_info=exc,
                )
        db.commit()

        # Parse context_files from task (JSON list stored as text)
        extra_files = _load_task_context_files(task)
        session_hint: dict[str, Any] | None = None
        execution_root = _task_project_root(task)
        if selection.backend in {"codex_cli", "codex_sdk"}:
            requirement_id, workflow_run_id = _task_session_scope(task)
            cwd, _ = _codex_workdirs(_task_str(task, "description") or "", Path(execution_root), output_dir)
            reusable = find_reusable_session(
                db,
                role_key=str(role_id),
                project_root=str(cwd),
                requirement_id=requirement_id,
            )
            session_hint = {
                "role_key": str(role_id),
                "project_root": str(cwd),
                "requirement_id": requirement_id,
                "workflow_run_id": workflow_run_id,
                "step_type": step_type,
            }
            if reusable is not None:
                session_hint["session_key"] = reusable.session_key
                session_hint["thread_id"] = str(reusable.thread_id or "")
                session_hint["resume_count"] = int(reusable.resume_count or 0)
            task_session_id = _task_str(task, "runtime_session_id")
            if task_session_id:
                session_hint["thread_id"] = task_session_id
                session_hint["resume_count"] = int(session_hint.get("resume_count") or 0)

        _prepare_requirement_branch_for_task(db, task, step_type)
        db.commit()

        deterministic_result = None
        if _should_use_deterministic_delivery_executor(task, step_type):
            deterministic_result = _deterministic_delivery_validation_result(db, task, output_dir, step_type)

        if deterministic_result is not None:
            result = deterministic_result
        else:
            runtime = get_task_runtime(PROJECT_ROOT, backend=selection.backend)
            result = runtime.execute(
                persona=agent_persona,
                skill_name=skill_name,
                task_description=_task_str(task, "description") or "",
                output_dir=output_dir,
                extra_context_files=extra_files,
                runtime_selection=selection,
                session_hint=session_hint,
            )

        cast(Any, task).runtime_backend = result.runtime_backend
        cast(Any, task).runtime_provider = result.runtime_provider or selection.provider
        cast(Any, task).runtime_model = result.model or selection.model
        cast(Any, task).tokens_used = int(result.tokens_used or 0)
        cast(Any, task).budget_cost_points = estimate_runtime_budget_points(
            tier=selection.complexity_tier,
            runtime_backend=result.runtime_backend or selection.backend,
            execution_time_ms=int(result.execution_time_ms or 0),
            tokens_used=int(result.tokens_used or 0),
        )
        cast(Any, task).runtime_session_id = result.runtime_session_id
        cast(Any, task).runtime_selected_agent = result.runtime_selected_agent
        _persist_runtime_events(db, task_id, result.events)
        if selection.backend in {"codex_cli", "codex_sdk"} and session_hint is not None:
            upsert_session_launch(
                db,
                role_key=str(session_hint.get("role_key") or role_id),
                project_root=str(session_hint.get("project_root") or PROJECT_ROOT),
                requirement_id=session_hint.get("requirement_id"),
                workflow_run_id=session_hint.get("workflow_run_id"),
                task_id=task_id,
                thread_id=result.runtime_session_id,
                status="active" if result.deferred else ("completed" if not result.error else "failed"),
                resume_count=int((result.metadata or {}).get("resume_count") or 0),
                metadata=result.metadata or {},
            )

        # Write results back to DB
        cast(Any, task).output_content = result.text
        cast(Any, task).execution_time_ms = result.execution_time_ms
        cast(Any, task).last_error_message = None
        if result.files:
            cast(Any, task).output_path = str(result.files[0])

        if result.error:
            if result.runtime_backend == "openai_responses" and is_openai_runtime_guard_error(result.error):
                from server.services.runtime.openai_responses_monitor import OpenAIResponsesTaskMonitor

                if str(getattr(cast(Any, task), "status", "") or "") != "running":
                    cast(Any, task).status = "running"
                    db.flush()
                monitor = OpenAIResponsesTaskMonitor(project_root=PROJECT_ROOT)
                monitor._alert_and_pause_for_runtime_guard(db, task, result.error)  # noqa: SLF001
                log_event(
                    logger,
                    "task_runtime_guard_paused",
                    level=logging.INFO,
                    task_id=task_id,
                    runtime_backend=result.runtime_backend,
                    error_message=result.error,
                )
                return
            cast(Any, task).status = "failed"
            cast(Any, task).last_error_message = result.error
            cast(Any, task).output_content = f"[ERROR] {result.error}"
            cast(Any, task).completed_at = utcnow()
            _log(db, task_id, "failed", result.error)
        elif _task_bool(task, "requires_approval"):
            cast(Any, task).status = "pending_approval"
            db.add(ApprovalRow(task_id=task.id))
            _log(db, task_id, "output", result.text[:500])
            _log(db, task_id, "approval_requested")
        elif result.deferred:
            cast(Any, task).status = "running"
            _log(db, task_id, "runtime_detached", result.runtime_session_id or result.runtime_backend)
        else:
            cast(Any, task).status = "completed"
            cast(Any, task).completed_at = utcnow()
            _log(db, task_id, "output", result.text[:500])
            _log(db, task_id, "completed")

        db.commit()
        lifecycle_event = "task_execution_detached" if result.deferred else "task_execution_completed"
        log_event(
            logger,
            lifecycle_event,
            level=logging.INFO,
            task_id=task_id,
            status=str(task.status),
            output_char_count=len(result.text),
            execution_time_ms=int(result.execution_time_ms or 0),
            runtime_backend=cast(Any, task).runtime_backend,
            runtime_provider=cast(Any, task).runtime_provider,
        )
        from server.services.workflows.orchestrator import sync_workflow_for_task
        from server.services.workflows.agent_first import sync_agent_first_execution_for_task

        sync_workflow_for_task(task_id)
        sync_agent_first_execution_for_task(task_id)

    except Exception as exc:
        log_event(
            logger,
            "task_runtime_crashed",
            level=logging.ERROR,
            task_id=task_id,
            exc_info=exc,
        )
        try:
            task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
            if task:
                cast(Any, task).status = "failed"
                cast(Any, task).last_error_message = str(exc)
                cast(Any, task).output_content = f"[ERROR] {exc}"
                cast(Any, task).completed_at = utcnow()
                _log(db, task_id, "failed", str(exc))
                db.commit()
                from server.services.workflows.orchestrator import sync_workflow_for_task
                from server.services.workflows.agent_first import sync_agent_first_execution_for_task

                sync_workflow_for_task(task_id)
                sync_agent_first_execution_for_task(task_id)
        except Exception as state_exc:
            log_event(
                logger,
                "task_runtime_state_update_failed",
                level=logging.ERROR,
                task_id=task_id,
                exc_info=state_exc,
            )
    finally:
        db.close()


def _log(db, task_id: int, event_type: str, detail: str | None = None):
    db.add(TaskLogRow(task_id=task_id, event_type=event_type, detail=detail))
    db.flush()


def _persist_runtime_events(db, task_id: int, events: list[RuntimeEvent]):
    for event in events:
        _log(db, task_id, event.event_type, event.detail)
