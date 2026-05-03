---
id: codex-python-sdk-runtime-architecture
title: Codex Python SDK Runtime Architecture
role: dev_rel
status: draft
created_at: 2026-04-16
updated_at: 2026-04-16
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing
---

# Codex Python SDK Runtime Architecture

## Summary

Codex Python SDK is the preferred long-term integration path for Synapse OPS Codex automation because it gives the Python backend first-class thread, resume, streaming, interrupt, and structured-output APIs.

This does not mean removing the Codex runtime. The Python SDK is currently experimental and still depends on `codex app-server` / `codex-cli-bin`. For that reason, the safe rollout is:

1. Add a new `codex_sdk` backend.
2. Keep the current `codex_cli` backend as fallback.
3. Migrate planner execution first.
4. Migrate workflow task execution after planner stability is proven.

Current implementation state:

1. `codex_sdk` is accepted as an explicit `ORCHESTRATION_BACKEND`.
2. Planner plan-brief calls can use the Codex Python SDK bridge.
3. Plan brief generation reuses Codex planner sessions by target project through `codex_sessions`.
4. Workflow task execution falls back to `codex_cli` until the SDK stream monitor is implemented.
5. The `codex_cli` monitor starts when `ORCHESTRATION_BACKEND=codex_sdk` so fallback tasks still complete.

Official basis:

1. [Codex Python SDK README](https://github.com/openai/codex/blob/main/sdk/python/README.md)
2. [Codex Python SDK API reference](https://raw.githubusercontent.com/openai/codex/main/sdk/python/docs/api-reference.md)
3. [Codex Python SDK FAQ](https://raw.githubusercontent.com/openai/codex/main/sdk/python/docs/faq.md)

## Recommended Configuration

```env
ORCHESTRATION_BACKEND=codex_sdk
LLM_PROVIDER=codex
LLM_MODEL=gpt-5.4
CODEX_SDK_MODEL=gpt-5.4
CODEX_SDK_TIMEOUT=0
CODEX_SDK_PLAN_TIMEOUT=300
CODEX_SDK_MAX_ACTIVE_SECONDS=7200
CODEX_SDK_STALE_AFTER_SEC=300
CODEX_SDK_SANDBOX=workspace-write
```

Configuration semantics:

1. Explicit `ORCHESTRATION_BACKEND` keeps highest priority.
2. `ORCHESTRATION_BACKEND=codex_sdk` uses the Python SDK backend.
3. `LLM_PROVIDER=codex` without an explicit backend should continue to resolve to `codex_cli` until `codex_sdk` is proven stable.
4. `CODEX_SDK_TIMEOUT=0` means do not hard-kill by single-turn timeout; it does not mean infinite production execution.
5. `CODEX_SDK_MAX_ACTIVE_SECONDS` and `CODEX_SDK_STALE_AFTER_SEC` remain required safety rails.

## Runtime Model

The `codex_sdk` backend should use `codex_app_server` from Python.

Primary SDK capabilities:

1. `AsyncCodex` is the preferred FastAPI and monitor integration point.
2. `thread_start(...)` creates a new Codex thread.
3. `thread_resume(thread_id)` resumes an existing thread.
4. `thread.run(...)` is the simple turn path when streaming is not needed.
5. `thread.turn(...).stream()` is the long-running path for progress UI, heartbeat, custom timeout logic, and event persistence.
6. `output_schema` should be used for planner structured output.
7. `interrupt()` should be preferred over killing the process when the runtime supports a clean cancellation path.

Known SDK constraints:

1. The Python SDK is experimental.
2. The SDK depends on `codex app-server` / `codex-cli-bin`; it is not a pure Responses API integration.
3. The current experimental build allows only one active turn consumer per client instance.
4. `codex_cli` must remain available as fallback while SDK/runtime packaging is unstable.

## Planner First Migration

Planner execution is the first migration target because the current raw `codex exec` plan-brief path is affected by a short synchronous timeout.

Target behavior:

1. Plan-brief generation uses `thread_start(..., sandbox="read-only")` for new plans.
2. Plan retry/recovery uses `thread_resume(thread_id)` when a previous planning thread id exists.
3. Planner output uses `output_schema` so plan parsing does not depend on free-form markdown.
4. `CODEX_SDK_PLAN_TIMEOUT=300` replaces the current short hard-coded planner timeout.
5. Planning metadata records `planning_session_id`, turn id, usage, status, prompt path, output path, and SDK/runtime errors.

Planner failures should be explicit:

1. SDK initialization failure should recommend checking `codex-cli-bin`, local Codex auth/session, and `codex app-server` compatibility.
2. SDK version/protocol errors should recommend falling back to `ORCHESTRATION_BACKEND=codex_cli`.
3. Structured-output validation errors should preserve the raw final response for debugging.

## Execution Migration

Workflow task execution should move to the SDK after planner stability is verified.

Target execution flow:

1. Task dispatch creates or resumes a Codex SDK thread.
2. The runtime starts a turn and immediately returns `deferred=True`.
3. The monitor consumes stream notifications and persists runtime logs, usage, heartbeat, and output.
4. Task completion writes `output.md` and `metadata.json`.
5. Stale detection first attempts `thread_resume(thread_id)`.
6. If resume fails or max active runtime is exceeded, the workflow enters runtime recovery instead of repeatedly re-dispatching.
7. If an operator or runner uses `Cancel / Kill`, the workspace is marked `dirty_after_kill`; retry/resume must run Workspace Recovery Preflight before starting a new Codex turn.
8. For stdio `codex app-server` processes, backend restart is treated as a hard boundary: startup cleanup may terminate orphaned app-server children, and recovery resumes from database state / trusted checkpoint rather than trying to reconnect to an unmanaged stdio child.

Session storage:

1. `tasks.runtime_backend = "codex_sdk"`.
2. `tasks.runtime_session_id = <codex thread id>`.
3. Declarative workflow atom invocations should store the Codex thread id in atom metadata when the atom uses Codex SDK.
4. `metadata.json` stores turn id, usage, status, model, sandbox, output path, and last event timestamp.
5. Existing `codex_sessions` remains the role/project/requirement-level thread registry.
6. Planner sessions should use the same registry with project scope: `role_key="planner"`, `project_root=<canonical target project root>`, `requirement_id=NULL`.

Workspace recovery contract:

1. `codex_sessions.workspace_trust_state` records `clean`, `dirty_after_kill`, `recovery_required`, or `recovery_failed`.
2. `Retry / Resume` first verifies repo root, branch, project policy, and git locks.
3. Automatic `git reset --hard HEAD && git clean -fd` is allowed only for workflow-owned isolated worktrees or matching `ops/` / `codex/` workflow branches.
4. User main workspace, unknown branches, active git processes, missing project policy, or dirty status after recovery route to Human Review and do not start Codex.

Planner provider selection:

1. Plan agent calls use the shared planner adapter interface documented in [Planner Adapter Architecture](planner-adapter-architecture.md).
2. `PLANNER_BACKEND=codex_sdk` selects the Codex Python SDK adapter.
3. `PLANNER_BACKEND=codex_cli` selects the Codex CLI adapter and remains the fallback path.
4. If `PLANNER_BACKEND` is empty, `ORCHESTRATION_BACKEND=codex_sdk` still maps planner calls to `codex_sdk` for compatibility.

Planner project-scoped session reuse is documented in [Plan Agent Project-Scoped Session Reuse](plan-agent-project-scoped-session-reuse.md). The same scope policy applies to `codex_cli` and `codex_sdk`; only the underlying resume API differs.

## Testing and Validation

Documentation validation:

1. Frontmatter contains the required AGENTS metadata.
2. README and ops console links point to this document.
3. Runtime backend docs include `codex_sdk` without removing `codex_cli`.

Implementation tests:

1. Config parsing recognizes `codex_sdk` and preserves `codex_cli` behavior.
2. Planner tests mock `AsyncCodex.thread_start/run` and verify timeout, thread id, structured output, and failure messaging.
3. Planner project-session tests verify same-project reuse, different-project isolation, project-scoped metadata, and registry diagnostics for planner rows without task binding.
4. Monitor tests mock stream notifications and verify task logs, usage, output, and terminal status sync.
5. Recovery tests verify stale runs call `thread_resume(thread_id)` before marking recovery required.
6. Fallback tests verify SDK initialization failure provides a clear path back to `ORCHESTRATION_BACKEND=codex_cli`.
7. Docs checks verify markdown links and required frontmatter fields.

## Assumptions

1. Phase 1 implementation covers configuration, planner bridging, and task fallback only.
2. Python SDK is the long-term recommended Codex integration for this Python backend.
3. `codex_cli` remains production fallback until SDK stability is proven.
4. Planner migration comes before execution migration because plan-brief timeout is the current pain point.
5. Production should not rely on truly infinite execution; `CODEX_SDK_TIMEOUT=0` still requires max-active and stale-monitor limits.
