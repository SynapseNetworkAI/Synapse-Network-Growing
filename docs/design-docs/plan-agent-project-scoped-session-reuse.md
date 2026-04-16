---
id: plan-agent-project-scoped-session-reuse
title: Plan Agent Project-Scoped Session Reuse
role: dev_rel
status: ready
created_at: 2026-04-16
updated_at: 2026-04-16
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing
---

# Plan Agent Project-Scoped Session Reuse

## Summary

Plan agent sessions should be reused by target project, not by individual requirement, because the planner repeatedly needs the same repository topology, policies, conventions, runtime constraints, and past delivery context for that project.

This design only changes the planner session scope. Execution, review, test, and bugfix agents should stay requirement-scoped unless a later design proves project-level execution reuse is safe.

Core decision:

1. Planner session scope becomes `project`.
2. Planner registry identity is `role_key="planner"`, `project_root=<canonical project root>`, `requirement_id=None`.
3. Execution session scope remains `requirement`.
4. Existing `codex_sessions` is reused. No database migration is required.

## Current Behavior

Plan brief generation currently has limited session reuse:

1. `_generate_plan_brief_markdown_with_agent(...)` reads `planning_session_id` from the requirement's previous `execution_plan`.
2. That means replanning the same requirement can resume the previous planner thread.
3. Different requirements in the same project do not share a planner thread.

Execution runtime already has scoped session reuse:

1. `codex_sessions.session_key` is built from `role_key + project_root + requirement_id`.
2. `find_reusable_session(...)` only reuses sessions in safe terminal/resumable states.
3. TTL, turn count, cached input token, and input token thresholds rotate old sessions.
4. This is correct for execution because different requirements can require different working tree assumptions and different implementation constraints.

## Decision

Use project-scoped planner sessions for Codex-based planner calls.

Planner sessions should reuse the same Codex thread for a project so the planner can accumulate stable project context across requirements:

1. Repository layout.
2. Project policy and verification commands.
3. Repeated failure modes.
4. Runtime and delivery conventions.
5. Common files and ownership boundaries.

Do not project-scope execution agents in this phase.

Execution agents write code and inspect mutable working tree state. Reusing execution context across unrelated requirements risks stale assumptions, scope bleed, and accidental carryover of prior implementation details.

## Session Scope Matrix

| Runtime role | Scope | Registry key | Reason |
| --- | --- | --- | --- |
| Planner | Project | `planner + project_root + None` | Same project context is useful across requirements. |
| Acceptance planner | Requirement | Requirement metadata or explicit prior plan id | Acceptance criteria should reflect the current request. |
| Execution agent | Requirement | `agent role + project_root + requirement_id` | Code-writing context must stay isolated per requirement. |
| Review agent | Requirement | `reviewer role + project_root + requirement_id` | Review should reason from the current diff and evidence. |
| Test agent | Requirement | `tester role + project_root + requirement_id` | Test context should follow the current delivery scope. |
| Bugfix agent | Requirement | `bugfix role + project_root + requirement_id` | Bugfix should be bound to one failing delivery loop. |

## Data Model

Reuse the existing `codex_sessions` table.

Planner project-scoped row:

```text
role_key       = "planner"
project_root   = canonical absolute target project root
requirement_id = NULL
thread_id      = Codex thread id
status         = active | completed | resumable | expired | rotated
metadata_json  = planner metadata and usage counters
```

The existing `build_session_key(role_key, project_root, requirement_id)` behavior remains valid. `requirement_id=None` already normalizes to the project-level key space, so the planner can use the same helper without a schema change.

Implementation requirements:

1. `project_root` must be canonicalized with `Path(...).expanduser().resolve()`.
2. Planner project sessions must use `role_key="planner"`, not a business role such as `dev_rel` or `software_engineer`.
3. Metadata should include `planning_session_scope="project"`.
4. Metadata should keep `planning_requirement_id` so operators can see which requirement last used the project planner session.
5. Execution metadata should continue to include `requirement_id` in the registry key.

Recommended planner metadata:

```json
{
  "planning_session_scope": "project",
  "planning_project_root": "/absolute/project/root",
  "planning_session_key": "<sha1 key>",
  "planning_requirement_id": 123,
  "planning_resumed_from_session_id": "thread_x",
  "planning_target_roots": ["/absolute/project/root"],
  "planning_backend": "codex_cli|codex_sdk",
  "planning_model": "gpt-5.4"
}
```

## Runtime Behavior

Planner start/resume flow:

1. Resolve the requirement target project root.
2. Compute the planner session key with `role_key="planner"` and `requirement_id=None`.
3. Call `find_reusable_session(...)` for the project planner session.
4. Pass the reusable `thread_id` as `raw_resume_session_id` to the Codex planner bridge.
5. After a successful planner call, upsert the planner session row with the returned `planning_session_id`.
6. Store planning metadata on both the requirement execution plan and the project planner session row.

Rotation and expiry should reuse existing registry rules:

1. Expire by `CODEX_CLI_SESSION_REUSE_TTL_SECONDS`.
2. Rotate by `CODEX_CLI_SESSION_MAX_TURNS`.
3. Rotate by cached input token and input token thresholds.
4. Start a new planner thread when the previous session is expired, rotated, missing, or not safely resumable.

Fallback behavior:

1. If Codex SDK resume fails, surface the runtime error and recommend fallback to `ORCHESTRATION_BACKEND=codex_cli`.
2. If Codex CLI resume fails because the thread is gone, mark the planner session `expired` or `rotated` and retry once with a new thread.
3. Do not silently keep retrying the same broken thread.

## Implementation State

Implemented behavior:

1. Planner project-session helpers exist in the Codex session registry.
2. Plan brief generation looks up a project-scoped planner session before falling back to requirement-local `planning_session_id`.
3. Successful plan brief generation writes `role_key="planner"`, canonical `project_root`, `requirement_id=NULL`, `current_task_id=NULL`, and planner metadata to `codex_sessions`.
4. Provider metadata records planner backend and model for both Codex CLI and Codex SDK planner paths.
5. Registry diagnostics accept project planner rows without task binding.

Remaining implementation work:

1. Codex SDK execution streaming remains a separate migration after planner stability.

## Implementation Plan

Add small registry helpers around the existing generic helpers:

1. `build_planner_project_session_key(project_root)`.
2. `find_reusable_planner_project_session(db, project_root)`.
3. `upsert_planner_project_session(db, project_root, thread_id, status, metadata)`.

Update plan brief generation:

1. In `_generate_plan_brief_markdown_with_agent(...)`, resolve the canonical target project root.
2. Look up a reusable project planner session before reading requirement-local `planning_session_id`.
3. Prefer the project planner thread when available.
4. Fall back to the requirement-local previous `planning_session_id` only when no project planner session exists.
5. Upsert the project planner session after a successful Codex planner call.

Update diagnostics:

1. Include planner project sessions in `validate_codex_session_registry(...)`.
2. Allow planner sessions to have `current_task_id=None`.
3. Report stale planner sessions by heartbeat or last-used age, but do not require task status matching.

## Risks

Context contamination:

Planner sessions may carry assumptions from an older requirement. Mitigation: keep planner output as plan-only, require explicit requirement and acceptance context in every prompt, and rotate sessions by TTL and token thresholds.

Token growth:

Project planner sessions may accumulate too much context. Mitigation: reuse existing turn/token rotation settings and add planner-specific thresholds later if needed.

Wrong project root:

Relative paths, symlinks, or multi-target requirements can split or merge sessions incorrectly. Mitigation: always use canonical absolute project roots and record `planning_target_roots`.

Resume failure:

Codex CLI or SDK sessions can disappear. Mitigation: mark broken sessions expired/rotated and create a new thread instead of repeatedly resuming the same id.

Execution scope bleed:

Project-scoped execution sessions would be risky. Mitigation: this design explicitly keeps execution requirement-scoped.

## Validation

Documentation validation:

1. This document has AGENTS-compatible frontmatter.
2. README and ops console docs link to this design.
3. Codex SDK runtime docs mention planner project-scoped registry usage.
4. Existing role-session reuse docs identify this design as the newer planner-specific direction.

Implementation tests to add later:

1. `build_session_key(role_key="planner", project_root=..., requirement_id=None)` is stable for one canonical project.
2. Two requirements in the same project reuse the same planner session key.
3. Two different projects do not share planner sessions.
4. TTL, turn count, cached input token, and input token thresholds rotate planner sessions.
5. Planner provider receives `raw_resume_session_id` when a project planner thread exists.
6. Execution runtime still includes `requirement_id` in the session key.
7. Registry diagnostics accept planner rows with `current_task_id=None`.

## Assumptions

1. Plan brief project-session reuse is implemented and planner workflow shape is deterministic.
2. Project-scoped planner session reuse applies to Codex CLI and Codex SDK planner paths.
3. Non-Codex providers can continue without session registry reuse until they expose equivalent resumable session semantics.
4. `codex_sessions` remains the source of truth for runtime thread registry state.
