"""Artifact and step-context helpers extracted from workflow orchestrator."""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from server.database import (
    ArtifactRow,
    RequirementRow,
    StepInputBindingRow,
    WorkflowStepDependencyRow,
    WorkflowStepRow,
    utcnow,
)
from server.services.runtime.copilot_sdk_state import parse_runtime_timestamp
from server.services.projects.policy import project_policy_summary_markdown
from server.services.workflows.orchestrator.handoff import _compact_task_description_from_snapshot


def _truncate_text(value: str, limit: int) -> str:
    """Trim long markdown blocks while keeping the tail of the truncation visible."""

    text = str(value or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    head = max(0, limit - 80)
    return text[:head].rstrip() + f"\n\n[truncated {len(text) - head} chars]"


def _format_artifact_for_context(artifact: ArtifactRow) -> tuple[str, str]:
    """Render an artifact into a step-context section title and body."""

    from server.services.workflows.orchestrator import (
        _delivery_contract_artifact_to_markdown,
        _plan_artifact_to_markdown,
        _validation_plan_artifact_to_markdown,
    )

    if artifact.artifact_type == "implementation_plan":
        return "Implementation Plan", _plan_artifact_to_markdown(artifact)
    if artifact.artifact_type == "delivery_contract":
        return "Delivery Contract", _delivery_contract_artifact_to_markdown(artifact)
    if artifact.artifact_type == "validation_plan":
        return "Validation Contract", _validation_plan_artifact_to_markdown(artifact)
    title = f"{artifact.artifact_type}: {artifact.content_summary or ''}".strip(": ").strip()
    body = str(artifact.human_readable_body or artifact.content_summary or "").strip()
    return title or artifact.artifact_type, body


def _prompt_cacheable_binding(binding: dict[str, Any]) -> bool:
    """Return whether a binding should be summarized into the prompt cache profile."""

    artifact_type = str(binding.get("artifact_type") or "").strip()
    return artifact_type in {
        "implementation_plan",
        "delivery_contract",
        "validation_plan",
        "routing_decision",
        "requirement_snapshot",
        "project_change_summary",
    }


def _prompt_cache_payload(sections: list[dict[str, Any]], binding_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the reusable prompt-cache profile derived from a step context snapshot."""

    reusable_sections: list[dict[str, Any]] = []
    seen_reusable_keys: set[str] = set()
    reused_chars = 0
    reusable_artifact_count = 0
    reusable_section_count = 0
    for section in sections:
        kind = str(section.get("kind") or "")
        if kind not in {"project", "capability", "done_when"}:
            continue
        body = str(section.get("body") or "").strip()
        if not body:
            continue
        title = str(section.get("title") or "")
        summary = _truncate_text(body, 240)
        reusable_key = hashlib.sha1(f"{kind}\n{title}\n{summary}".encode("utf-8")).hexdigest()
        if reusable_key in seen_reusable_keys:
            continue
        seen_reusable_keys.add(reusable_key)
        reusable_section_count += 1
        reused_chars += max(0, len(body) - len(summary))
        reusable_sections.append(
            {
                "kind": kind,
                "title": title,
                "summary": summary,
                "raw_chars": len(body),
                "summary_chars": len(summary),
            }
        )
    for binding in binding_summaries:
        if not _prompt_cacheable_binding(binding):
            continue
        body = str(binding.get("body") or "").strip()
        if not body:
            continue
        artifact_type = str(binding.get("artifact_type") or "")
        title = str(binding.get("title") or "")
        summary = _truncate_text(body, 240)
        reusable_key = hashlib.sha1(f"{artifact_type}\n{title}\n{summary}".encode("utf-8")).hexdigest()
        if reusable_key in seen_reusable_keys:
            continue
        seen_reusable_keys.add(reusable_key)
        reusable_artifact_count += 1
        reused_chars += max(0, len(body) - len(summary))
        reusable_sections.append(
            {
                "kind": "artifact",
                "artifact_type": artifact_type,
                "title": title,
                "summary": summary,
                "raw_chars": len(body),
                "summary_chars": len(summary),
            }
        )
    digest_source = "\n".join(
        f"{item.get('kind')}::{item.get('title')}::{item.get('summary')}"
        for item in reusable_sections
    )
    return {
        "cache_key": hashlib.sha1(digest_source.encode("utf-8")).hexdigest() if digest_source else "",
        "reusable_sections": reusable_sections,
        "reusable_section_count": reusable_section_count,
        "reusable_artifact_count": reusable_artifact_count,
        "reused_chars": reused_chars,
        "cache_applied": bool(reusable_sections),
    }


def _prompt_cache_profile_markdown(payload: dict[str, Any]) -> str:
    """Render a human-readable prompt-cache profile artifact."""

    lines = [
        "# Prompt Cache Profile",
        "",
        f"- cache key: `{payload.get('cache_key') or '-'}`",
        f"- cache applied: `{payload.get('cache_applied')}`",
        f"- reusable sections: `{payload.get('reusable_section_count') or 0}`",
        f"- reusable artifacts: `{payload.get('reusable_artifact_count') or 0}`",
        f"- deduped bindings: `{payload.get('deduped_binding_count') or 0}`",
        f"- raw chars: `{payload.get('raw_chars') or 0}`",
        f"- final chars: `{payload.get('final_chars') or 0}`",
        f"- saved chars before compaction: `{payload.get('cached_chars_saved') or 0}`",
    ]
    reusable_sections = payload.get("reusable_sections") or []
    if isinstance(reusable_sections, list) and reusable_sections:
        lines.extend(["", "## Reusable Context"])
        for item in reusable_sections:
            if not isinstance(item, dict):
                continue
            label = str(item.get("title") or item.get("artifact_type") or item.get("kind") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if not label or not summary:
                continue
            lines.append(f"- {label}: {summary}")
    return "\n".join(lines)


def _binding_relevant_for_step(step: WorkflowStepRow, binding: StepInputBindingRow, artifact: ArtifactRow) -> bool:
    """Filter artifact bindings down to the context that matters for the current step type."""

    step_type = str(step.step_type or "").strip().lower()
    purpose = str(getattr(binding, "purpose", "") or "").strip().lower()
    artifact_type = str(artifact.artifact_type or "").strip().lower()

    if step_type == "research":
        if purpose in {"delivery_contract", "validation_contract", "review_context", "test_context"}:
            return False
        if artifact_type in {"implementation_plan", "delivery_contract", "validation_plan", "review_report", "test_report"}:
            return False
    elif step_type == "plan":
        if purpose in {"delivery_contract", "validation_contract", "review_context", "test_context"}:
            return False
        if artifact_type in {"implementation_plan", "delivery_contract", "validation_plan", "validation_report"}:
            return False
    elif step_type in {"implementation", "bugfix"}:
        if purpose in {"delivery_contract", "validation_contract", "review_context", "test_context"}:
            return False
        if artifact_type in {"delivery_contract", "validation_plan", "validation_report"}:
            return False
    if step_type == "plan" and artifact_type == "research_report":
        return False
    if step_type in {"implementation", "bugfix"} and artifact_type == "plan_brief":
        return False
    return True


def _is_requirement_centric_delivery_requirement(requirement: RequirementRow | None) -> bool:
    """Identify delivery-only requirements that should avoid broad repository context."""

    if requirement is None:
        return False
    title = str(getattr(requirement, "title", "") or "").strip().lower()
    description = str(getattr(requirement, "description_markdown", "") or "").strip().lower()
    text = f"{title}\n{description}"
    strong_markers = (
        "commit",
        "push",
        "draft pr",
        "pull request",
        "review-ready",
        "compare url",
        "requirement branch",
        "same branch",
        "branch delivery",
        "review surface",
        "validation clone",
    )
    return any(marker in text for marker in strong_markers)


def _step_execution_guidance(db: Session, step: WorkflowStepRow) -> str:
    """Return the step-specific execution guidance inserted into the prompt packet."""

    from server.services.workflows.orchestrator import _require_requirement

    step_type = str(step.step_type or "").strip().lower()
    requirement = _require_requirement(db, step.requirement_id)
    delivery_requirement = _is_requirement_centric_delivery_requirement(requirement)
    if step_type == "research":
        if delivery_requirement:
            return "\n".join(
                [
                    "- Treat this as a branch-delivery preflight, not a general repository investigation.",
                    "- Limit commands to high-signal checks such as `git status --short --branch`, `git branch --show-current`, `git remote -v`, `ls docs`, and targeted reads of `README.md` or the requested output path parent.",
                    "- Do not scan unrelated source trees, test suites, or service internals in this step.",
                    "- Stop once you know the current branch, remote, required target path, and any blockers to creating exactly the requested tracked file.",
                    "- Do not edit production code in this step.",
                ]
            )
        return "\n".join(
            [
                "- Limit exploration to the highest-signal files only; avoid broad repo surveys.",
                "- Stop once you have a plausible root cause, 3-6 relevant files, and concrete implementation options.",
                "- Do not edit production code in this step.",
            ]
        )
    if step_type == "plan":
        if delivery_requirement:
            return "\n".join(
                [
                    "- Build the execution plan from the delivery contract, git preflight, and requested output path only.",
                    "- Do not re-scan broad parts of the repository; synthesize from the known branch/remote state and the requested tracked file scope.",
                    "- Keep the plan anchored to one branch, one tracked file, commit/push, and draft PR sync.",
                    "- Do not edit production code in this step.",
                ]
            )
        return "\n".join(
            [
                "- Build the execution plan from the research findings; do not re-scan large unrelated parts of the repo.",
                "- Only inspect extra files when they are strictly needed to finalize sequencing or validation.",
                "- Do not edit production code in this step.",
            ]
        )
    if step_type in {"implementation", "bugfix"}:
        return "\n".join(
            [
                "- Keep changes tightly scoped to the target project and files already identified by research/plan unless new evidence requires expansion.",
                "- Prefer minimal diffs that directly satisfy the stated goal and validation contract.",
                "- Do not run dependency installation/bootstrap commands such as `npm install`, `pnpm install`, or `yarn install` unless the requirement explicitly asks for dependency changes.",
                "- Reuse the repository's existing lockfile and scripts; if a required check cannot run without new installs, fail fast and report the blocker instead of broad environment setup.",
            ]
        )
    if step_type == "validate":
        return "\n".join(
            [
                "- Treat validate as the single final quality gate for this requirement.",
                "- Reuse plan and implementation evidence instead of repeating the whole requirement.",
                "- Make the result binary: either validated and ready for closeout, or specific enough to trigger bugfix.",
                "- Do not make new source edits in this step unless a policy artifact explicitly allows it.",
            ]
        )
    return ""


def _step_includes_predecessor_handoff(step: WorkflowStepRow) -> bool:
    """Return whether predecessor handoff summaries should be threaded into this step."""

    return str(step.step_type or "").strip().lower() not in {"implementation", "bugfix"}


def _normalize_file_hint(path_hint: str) -> str | None:
    """Normalize a markdown file hint into a filesystem-like path token."""

    value = str(path_hint or "").strip().strip("`").strip()
    if not value:
        return None
    value = value.split("#L", 1)[0]
    if ":" in value:
        prefix, suffix = value.rsplit(":", 1)
        if suffix.isdigit() or ("-" in suffix and suffix.replace("-", "").isdigit()):
            value = prefix
    value = value.strip()
    if "/" not in value:
        return None
    return value or None


def _extract_file_hints_from_text(markdown: str, *, limit: int = 6) -> list[str]:
    """Extract likely file-path references from markdown content."""

    text = str(markdown or "")
    hints: list[str] = []
    seen: set[str] = set()
    for match in re.findall(r"`([^`]+)`", text):
        normalized = _normalize_file_hint(match)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        hints.append(normalized)
        if len(hints) >= limit:
            return hints
    for match in re.findall(r"\b[\w./-]+\.[A-Za-z0-9_]+\b", text):
        normalized = _normalize_file_hint(match)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        hints.append(normalized)
        if len(hints) >= limit:
            return hints
    return hints


def _step_relevant_file_hints(db: Session, step: WorkflowStepRow, *, limit: int = 6) -> list[str]:
    """Return a compact list of suggested files to keep the step focused."""

    from server.services.workflows.orchestrator import _as_int, _latest_artifact, _require_requirement

    step_type = str(step.step_type or "").strip().lower()
    requirement = _require_requirement(db, step.requirement_id)
    delivery_requirement = _is_requirement_centric_delivery_requirement(requirement)
    if step_type not in {"implementation", "bugfix", "validate", "review", "test"} and not (
        delivery_requirement and step_type in {"research", "plan"}
    ):
        return []
    if delivery_requirement and step_type in {"research", "plan"}:
        hints: list[str] = []
        seen: set[str] = set()
        description = str(getattr(requirement, "description_markdown", "") or "")
        for candidate in _extract_file_hints_from_text(description, limit=limit):
            if candidate in seen:
                continue
            seen.add(candidate)
            hints.append(candidate)
            if len(hints) >= limit:
                return hints
        for candidate in ("README.md", "docs/", "docs/auto-validation/"):
            if candidate in seen:
                continue
            seen.add(candidate)
            hints.append(candidate)
            if len(hints) >= limit:
                return hints
        return hints
    requirement_id = _as_int(step.requirement_id)
    artifact_types = ["research_report", "plan_brief", "implementation_plan"]
    hints: list[str] = []
    seen: set[str] = set()
    for artifact_type in artifact_types:
        artifact = _latest_artifact(db, requirement_id, artifact_type)
        if not artifact:
            continue
        bodies = [
            str(getattr(artifact, "human_readable_body", "") or ""),
            str(getattr(artifact, "content_summary", "") or ""),
        ]
        for body in bodies:
            for hint in _extract_file_hints_from_text(body, limit=limit):
                if hint in seen:
                    continue
                seen.add(hint)
                hints.append(hint)
                if len(hints) >= limit:
                    return hints
    return hints


def _effective_done_when_markdown(step: WorkflowStepRow, requirement: RequirementRow, target_path: str | None) -> str:
    """Resolve the effective done-when contract for the current step."""

    from server.services.workflows.orchestrator import _requirement_prefers_engineering_contract

    done_when = str(step.done_when_markdown or "").strip()
    step_type = str(step.step_type or "").strip().lower()
    title = str(step.title or "").strip().lower()
    step_key = str(step.step_key or "").strip().lower()
    if (
        _requirement_prefers_engineering_contract(requirement)
        and step_type in {"implementation", "bugfix"}
        and "do not write implementation code" in done_when.lower()
    ):
        if any(marker in f"{title} {step_key}" for marker in {"verify", "validation", "regression", "test"}):
            done_when = (
                "SCOPE: Implement automated validation for the incident recovery path. "
                "You may add or modify tests and supporting harness code that proves the failure path is now closed.\n\n"
                "Add or update regression validation that reproduces the incident conditions and proves the new guard holds."
            )
        else:
            done_when = (
                "SCOPE: Implement a minimal engineering fix in code or supporting runtime/test harness files. "
                "Do NOT stop at documentation-only output.\n\n"
                "Apply the smallest safe change that closes the runtime failure path, and record root cause/recovery notes in task output or handoff."
            )
        if target_path:
            done_when += f"\nTarget project: {target_path}"
    return done_when


def _step_context_snapshot(db: Session, step: WorkflowStepRow) -> dict[str, Any]:
    """Build the full step-context snapshot consumed by runtimes and artifacts."""

    from server.services.workflows.orchestrator import (
        _approval_policy_markdown_lines,
        _as_int,
        _effective_target_project_path,
        _json_loads,
        _latest_artifact,
        _normalize_utc_datetime,
        _require_requirement,
    )

    requirement = _require_requirement(db, step.requirement_id)
    target_path = _effective_target_project_path(db, requirement, step_type=str(step.step_type or ""))
    effective_done_when = _effective_done_when_markdown(step, requirement, target_path)
    context_policy = _json_loads(getattr(step, "context_policy_json", None), {})
    max_artifact_body_chars = int(context_policy.get("max_artifact_body_chars") or 2200)
    max_handoff_chars = int(context_policy.get("max_handoff_chars") or 1200)
    requirement_summary = _truncate_text(str(requirement.description_markdown or "").strip(), 900)

    sections: list[dict[str, Any]] = [
        {
            "kind": "base",
            "title": "Step",
            "body": "\n".join(
                [
                    f"[workflow_step:{step.step_type}] {step.title}",
                    f"Requirement #{requirement.id}: {requirement.title}",
                    requirement_summary,
                ]
            ).strip(),
        }
    ]
    if target_path:
        project_lines = [f"Target project path: {target_path}"]
        project_lines.append("IMPORTANT: Write actual source code files in the target project, not just documentation.")
        project_policy_summary = project_policy_summary_markdown(db, target_path)
        if project_policy_summary:
            project_lines.append(project_policy_summary)
        sections.append({"kind": "project", "title": "Project Context", "body": "\n".join(project_lines)})

    approval_policy = _json_loads(getattr(step, "approval_policy_json", None), {})
    capability_lines = _approval_policy_markdown_lines(approval_policy)
    if capability_lines:
        sections.append({"kind": "capability", "title": "Capability Contract", "body": "\n".join(capability_lines)})

    sections.append({"kind": "done_when", "title": "Done When", "body": effective_done_when})
    execution_guidance = _step_execution_guidance(db, step)
    if execution_guidance:
        sections.append({"kind": "guidance", "title": "Execution Guidance", "body": execution_guidance})
    relevant_files = _step_relevant_file_hints(db, step)
    if relevant_files:
        sections.append(
            {
                "kind": "file_hints",
                "title": "Suggested File Scope",
                "body": "\n".join(f"- {path}" for path in relevant_files),
            }
        )

    if _step_includes_predecessor_handoff(step):
        deps = db.query(WorkflowStepDependencyRow).filter(WorkflowStepDependencyRow.step_id == step.id).all()
        for dep in deps:
            pred = db.query(WorkflowStepRow).filter(WorkflowStepRow.id == dep.depends_on_step_id).first()
            if pred and pred.handoff_summary_markdown:
                sections.append(
                    {
                        "kind": "handoff",
                        "title": f"Prior Step: {pred.title}",
                        "body": _truncate_text(str(pred.handoff_summary_markdown), max_handoff_chars),
                    }
                )

    binding_summaries: list[dict[str, Any]] = []
    seen_binding_keys: set[str] = set()
    deduped_binding_count = 0
    bindings = db.query(StepInputBindingRow).filter(StepInputBindingRow.step_id == step.id).all()
    total_binding_count = len(bindings)
    for binding in bindings:
        artifact = db.query(ArtifactRow).filter(ArtifactRow.id == binding.artifact_id).first()
        if not artifact:
            continue
        if not _binding_relevant_for_step(step, binding, artifact):
            continue
        title, body = _format_artifact_for_context(artifact)
        truncated_body = _truncate_text(body, max_artifact_body_chars)
        dedupe_key = hashlib.sha1(f"{title}\n{truncated_body}".encode("utf-8")).hexdigest()
        if dedupe_key in seen_binding_keys:
            deduped_binding_count += 1
            continue
        seen_binding_keys.add(dedupe_key)
        binding_summaries.append(
            {
                "artifact_id": _as_int(artifact.id),
                "artifact_type": str(artifact.artifact_type),
                "title": title,
                "body": truncated_body,
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
                "workflow_run_id": int(artifact.workflow_run_id) if artifact.workflow_run_id is not None else None,
            }
        )
        sections.append({"kind": "artifact", "title": title, "body": truncated_body})

    prompt_cache = _prompt_cache_payload(sections, binding_summaries)
    cache_key = str(prompt_cache.get("cache_key") or "")
    reusable_sections = list(prompt_cache.get("reusable_sections") or [])
    cache_applied = bool(prompt_cache.get("cache_applied"))
    raw_prompt_before_cache = "\n\n".join(
        f"## {section['title']}\n{section['body']}".strip()
        for section in sections
        if str(section.get("body") or "").strip()
    ).strip()
    raw_chars_before_cache = len(raw_prompt_before_cache)
    if cache_applied:
        compact_lines = [
            f"Cache key: `{cache_key}`",
            "Reusable context summary:",
        ]
        for item in reusable_sections:
            compact_lines.append(
                f"- {item.get('title') or item.get('artifact_type') or item.get('kind')}: {item.get('summary') or ''}"
            )
        sections = [
            section
            for section in sections
            if not (
                str(section.get("kind") or "") in {"project", "capability"}
                or (
                    str(section.get("kind") or "") == "artifact"
                    and any(
                        str(item.get("title") or "") == str(section.get("title") or "")
                        and str(item.get("summary") or "") == _truncate_text(str(section.get("body") or ""), 240)
                        for item in reusable_sections
                    )
                )
            )
        ]
        sections.insert(1, {"kind": "prompt_cache", "title": "Cached Context Profile", "body": "\n".join(compact_lines)})

    raw_prompt = "\n\n".join(
        f"## {section['title']}\n{section['body']}".strip()
        for section in sections
        if str(section.get("body") or "").strip()
    ).strip()

    max_prompt_chars = int(context_policy.get("max_prompt_chars") or 12000)
    compact_after_chars = int(context_policy.get("compact_after_chars") or max_prompt_chars)
    compacted = len(raw_prompt) > compact_after_chars
    final_prompt = raw_prompt
    if compacted:
        compact_header = [
            "## Context Compact Summary",
            f"- Raw prompt chars: {len(raw_prompt)}",
            f"- Compacted to stay under budget `{max_prompt_chars}`.",
        ]
        compact_sections: list[str] = []
        for section in sections:
            body = str(section.get("body") or "").strip()
            if not body:
                continue
            compact_sections.append(f"### {section['title']}\n{_truncate_text(body, max(400, max_prompt_chars // max(1, len(sections) + 2)))}")
        final_prompt = "\n\n".join(compact_header + compact_sections)
        if len(final_prompt) > max_prompt_chars:
            final_prompt = _truncate_text(final_prompt, max_prompt_chars)

    stale_after_minutes = max(1, int(context_policy.get("stale_after_minutes") or 30))
    cutoff = _normalize_utc_datetime(utcnow() - timedelta(minutes=stale_after_minutes))
    stale_sensitive_types = {
        str(item).strip()
        for item in context_policy.get("stale_sensitive_artifact_types") or []
        if str(item).strip()
    }
    lineage_only_types = {"requirement_snapshot", "implementation_plan"}
    stale_findings: list[str] = []
    for binding in binding_summaries:
        artifact_type = str(binding.get("artifact_type") or "")
        created_at = _normalize_utc_datetime(parse_runtime_timestamp(str(binding.get("created_at") or "")))
        workflow_run_id = int(binding.get("workflow_run_id") or 0)
        if workflow_run_id and workflow_run_id != int(step.workflow_run_id):
            stale_findings.append(f"{artifact_type} comes from workflow run #{workflow_run_id}, not the active run #{step.workflow_run_id}")
            continue
        if artifact_type in lineage_only_types:
            continue
        if artifact_type in stale_sensitive_types and created_at is not None and cutoff is not None and created_at < cutoff:
            stale_findings.append(
                f"{artifact_type} is older than stale-memory threshold ({stale_after_minutes} min)"
            )

    verification_status = "fresh" if not stale_findings else "stale"
    return {
        "requirement": requirement,
        "context_policy": context_policy,
        "raw_chars_before_cache": raw_chars_before_cache,
        "raw_prompt": raw_prompt,
        "prompt": final_prompt,
        "raw_chars": len(raw_prompt),
        "final_chars": len(final_prompt),
        "compacted": compacted,
        "sections": sections,
        "binding_summaries": binding_summaries,
        "prompt_cache": prompt_cache,
        "cache_applied": cache_applied,
        "total_binding_count": total_binding_count,
        "unique_binding_count": len(binding_summaries),
        "deduped_binding_count": deduped_binding_count,
        "cached_chars_saved": max(0, raw_chars_before_cache - len(raw_prompt)),
        "verification_status": verification_status,
        "stale_findings": list(dict.fromkeys(stale_findings)),
    }


def _approval_policy_markdown_lines(policy: dict[str, Any]) -> list[str]:
    """Render a compact markdown summary for the step approval contract."""

    if not isinstance(policy, dict) or not policy:
        return []
    lines: list[str] = []
    required = [str(item) for item in policy.get("required_capabilities") or [] if str(item).strip()]
    if required:
        lines.append(f"- Required capabilities: {', '.join(required)}")
    approval_scope = str(policy.get("approval_scope") or "").strip()
    if approval_scope:
        lines.append(f"- Human gate scope: {approval_scope}")
    matrix = policy.get("capability_matrix") or {}
    if isinstance(matrix, dict) and matrix:
        summary = ", ".join(
            f"{key}={'yes' if bool(matrix.get(key)) else 'no'}"
            for key in ("shell_access", "git_read", "git_write", "git_push", "network_access", "publish")
        )
        lines.append(f"- Effective matrix: {summary}")
    confirmation = [str(item) for item in policy.get("operator_confirmation_actions") or [] if str(item).strip()]
    if confirmation:
        lines.append(f"- Operator confirmation actions: {', '.join(confirmation)}")
    deny_reasons = [str(item) for item in policy.get("deny_reasons") or [] if str(item).strip()]
    if deny_reasons:
        lines.append(f"- Denied actions: {'; '.join(deny_reasons)}")
    interrupt_policy = policy.get("interrupt_policy") or {}
    if isinstance(interrupt_policy, dict):
        pause_events = ", ".join(str(item) for item in interrupt_policy.get("auto_pause_on_events") or [] if str(item).strip()) or "none"
        abort_events = ", ".join(str(item) for item in interrupt_policy.get("auto_abort_on_events") or [] if str(item).strip()) or "none"
        lines.append(f"- Interrupt policy: pause on {pause_events}; abort on {abort_events}")
    return lines


def _step_required_capabilities_for_type(step_type: str) -> list[str]:
    """Return the capability set the step needs before dispatch can proceed."""

    required = ["git_read"]
    if step_type in {"research", "plan", "validate", "synthesis", "review", "test", "implementation", "bugfix"}:
        required.append("shell_access")
    if step_type in {"implementation", "bugfix"}:
        required.append("git_write")
    ordered: list[str] = []
    for key in ("shell_access", "git_read", "git_write", "git_push", "network_access", "publish"):
        if key in required and key not in ordered:
            ordered.append(key)
    return ordered


def _derived_approval_policy(
    step_type: str,
    base_policy: dict[str, Any],
    *,
    execution_profile: dict[str, Any] | None = None,
    requirement: RequirementRow | None = None,
) -> dict[str, Any]:
    """Combine project capability policy with step-level approval requirements."""

    from server.services.workflows.planner import _operator_confirmation_actions_for_step

    if not isinstance(base_policy, dict):
        base_policy = {}
    capability_matrix = dict(base_policy.get("capability_matrix") or {})
    interrupt_policy = dict(base_policy.get("interrupt_policy") or {})
    required_capabilities = _step_required_capabilities_for_type(step_type)
    denied = [name for name in required_capabilities if capability_matrix and not bool(capability_matrix.get(name))]
    confirmation, approval_scope = _operator_confirmation_actions_for_step(
        step_type=step_type,
        required_capabilities=required_capabilities,
        interrupt_policy=interrupt_policy,
        execution_profile=execution_profile,
        requirement=requirement,
    )
    return {
        "required_capabilities": required_capabilities,
        "capability_matrix": capability_matrix,
        "interrupt_policy": interrupt_policy,
        "approval_scope": approval_scope,
        "requires_operator_confirmation": bool(confirmation),
        "operator_confirmation_actions": confirmation,
        "deny_execution": bool(denied),
        "deny_reasons": [f"{name} disabled by project capability matrix" for name in denied],
    }


def _prompt_cache_payload_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Project a context snapshot into the persisted prompt-cache artifact shape."""

    return {
        **snapshot["prompt_cache"],
        "cache_applied": snapshot["cache_applied"],
        "raw_chars_before_cache": snapshot["raw_chars_before_cache"],
        "raw_chars": snapshot["raw_chars"],
        "final_chars": snapshot["final_chars"],
        "cached_chars_saved": snapshot["cached_chars_saved"],
        "total_binding_count": snapshot["total_binding_count"],
        "unique_binding_count": snapshot["unique_binding_count"],
        "deduped_binding_count": snapshot["deduped_binding_count"],
        "section_count": len(snapshot["sections"]),
    }


def _step_context_payload(step: WorkflowStepRow, snapshot: dict[str, Any], prompt_cache_payload: dict[str, Any]) -> dict[str, Any]:
    """Build the machine-readable payload written for step-context artifacts."""

    from server.services.workflows.orchestrator import _as_int

    return {
        "step_id": _as_int(step.id),
        "step_key": str(step.step_key),
        "step_type": str(step.step_type),
        "context_policy": snapshot["context_policy"],
        "raw_chars_before_cache": snapshot["raw_chars_before_cache"],
        "raw_chars": snapshot["raw_chars"],
        "final_chars": snapshot["final_chars"],
        "compacted": snapshot["compacted"],
        "section_count": len(snapshot["sections"]),
        "binding_summaries": snapshot["binding_summaries"],
        "prompt_cache": prompt_cache_payload,
        "total_binding_count": snapshot["total_binding_count"],
        "unique_binding_count": snapshot["unique_binding_count"],
        "deduped_binding_count": snapshot["deduped_binding_count"],
        "cached_chars_saved": snapshot["cached_chars_saved"],
    }


def _write_step_context_artifacts(
    db: Session,
    step: WorkflowStepRow,
    snapshot: dict[str, Any],
    *,
    prompt_cache_payload: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    """Persist prompt-cache, compaction, and stale-memory artifacts for a step."""

    from server.services.workflows.orchestrator import _create_artifact, _create_or_update_artifact

    _create_or_update_artifact(
        db,
        requirement_id=step.requirement_id,
        workflow_run_id=step.workflow_run_id,
        step_id=step.id,
        producer_step_id=step.id,
        artifact_type="prompt_cache_profile",
        content_summary=f"prompt cache profile for step {step.step_key}",
        human_readable_body=_prompt_cache_profile_markdown(prompt_cache_payload),
        machine_readable_payload=prompt_cache_payload,
    )
    if snapshot["compacted"]:
        _create_artifact(
            db,
            requirement_id=step.requirement_id,
            workflow_run_id=step.workflow_run_id,
            step_id=step.id,
            producer_step_id=step.id,
            artifact_type="context_compaction",
            content_summary=f"context compacted for step {step.step_key}",
            human_readable_body=snapshot["prompt"],
            machine_readable_payload=payload,
        )
    _create_artifact(
        db,
        requirement_id=step.requirement_id,
        workflow_run_id=step.workflow_run_id,
        step_id=step.id,
        producer_step_id=step.id,
        artifact_type="stale_memory_verification",
        content_summary=f"{snapshot['verification_status']} context verification for step {step.step_key}",
        human_readable_body="\n".join(
            [
                f"Verification status: {snapshot['verification_status']}",
                *(f"- {item}" for item in snapshot["stale_findings"]),
            ]
        ).strip(),
        machine_readable_payload={
            **payload,
            "verification_status": snapshot["verification_status"],
            "stale_findings": snapshot["stale_findings"],
        },
    )


def _materialize_step_context(db: Session, step: WorkflowStepRow) -> dict[str, Any]:
    """Build a step context snapshot and persist its artifact chain."""

    snapshot = _step_context_snapshot(db, step)
    snapshot["task_description"] = _compact_task_description_from_snapshot(step, snapshot)
    prompt_cache_payload = _prompt_cache_payload_from_snapshot(snapshot)
    payload = _step_context_payload(step, snapshot, prompt_cache_payload)
    _write_step_context_artifacts(
        db,
        step,
        snapshot,
        prompt_cache_payload=prompt_cache_payload,
        payload=payload,
    )
    return snapshot


def _create_artifact(*args: Any, **kwargs: Any) -> Any:
    """Compatibility export until generic artifact writers are split out further."""

    from server.services.workflows.orchestrator import _create_artifact as _legacy_create_artifact

    return _legacy_create_artifact(*args, **kwargs)


def _record_project_change_summary_artifact(*args: Any, **kwargs: Any) -> Any:
    """Compatibility export for project-change summary persistence."""

    from server.services.workflows.orchestrator import (
        _record_project_change_summary_artifact as _legacy_record_project_change_summary_artifact,
    )

    return _legacy_record_project_change_summary_artifact(*args, **kwargs)


def _record_step_event(*args: Any, **kwargs: Any) -> Any:
    """Compatibility export for workflow step event persistence."""

    from server.services.workflows.orchestrator import _record_step_event as _legacy_record_step_event

    return _legacy_record_step_event(*args, **kwargs)


__all__ = [
    "_truncate_text",
    "_format_artifact_for_context",
    "_prompt_cache_payload",
    "_prompt_cache_profile_markdown",
    "_binding_relevant_for_step",
    "_step_execution_guidance",
    "_step_includes_predecessor_handoff",
    "_step_relevant_file_hints",
    "_effective_done_when_markdown",
    "_step_context_snapshot",
    "_approval_policy_markdown_lines",
    "_step_required_capabilities_for_type",
    "_derived_approval_policy",
    "_prompt_cache_payload_from_snapshot",
    "_step_context_payload",
    "_write_step_context_artifacts",
    "_materialize_step_context",
    "_create_artifact",
    "_record_project_change_summary_artifact",
    "_record_step_event",
]
