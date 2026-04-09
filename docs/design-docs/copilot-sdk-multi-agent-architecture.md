---
id: copilot_sdk_multi_agent_architecture
title: Copilot SDK Multi-Agent Orchestration Architecture
status: draft
created_at: 2026-04-09
updated_at: 2026-04-09
author: github-copilot
target_repo: cliff-personal/Synapse-Network-Growing
---

# Copilot SDK Multi-Agent Orchestration Architecture

## Goal

The repository now supports a Copilot SDK runtime that keeps the existing task API and dashboard contract, but changes execution from a blocking single-shot flow to a resumable long-task pipeline.

This design covers:

1. Custom agents with scoped tools
2. Runtime agent inference and sub-agent delegation
3. Optional MCP attachment per agent
4. Detached session execution with durable state files
5. Backend-side event ingestion, completion, and stale-session recovery
6. Backward-compatible task creation, approvals, retries, and dashboard views

## Implemented state

The runtime has four layers.

### Layer 1: Task orchestration

Entrypoints remain:

1. `server/routers/tasks.py` creates and runs tasks
2. `server/services/task_runner.py` dispatches background execution
3. `server/services/execution_resolver.py` resolves agent and skill metadata

Responsibilities:

1. Resolve preferred business agent and skill
2. Collect context files and approval requirements
3. Persist task status, runtime metadata, and normalized logs
4. Keep deferred `copilot_sdk` tasks in `running` until the monitor finishes them

### Layer 2: Runtime adapter

The runtime abstraction still supports two backends:

1. `legacy`: synchronous `CrewEngine` execution
2. `copilot_sdk`: detached Node worker around `@github/copilot-sdk`

Current implementation lives in:

1. `server/services/task_runtime.py`
2. `server/services/copilot_sdk_bridge.py`
3. `server/services/copilot_sdk_state.py`

Responsibilities:

1. Build the Copilot SDK session payload
2. Convert repository personas and skills into Copilot custom-agent config
3. Launch detached workers through `start_session()` or `resume_session()`
4. Return immediate runtime metadata to Python without blocking on final completion

### Layer 3: Detached Copilot SDK worker

The Node runner is implemented in `copilot-sdk-runner/run_session.mjs`.

It supports three modes:

1. one-shot compatibility mode for the legacy synchronous bridge
2. `start` for detached long-task execution
3. `resume` for stale-session recovery

Responsibilities:

1. Start or resume a Copilot session
2. Register `customAgents`
3. Persist session state, heartbeat, stdout, stderr, final output, and runtime metadata into the task output directory
4. Append raw runtime events into `copilot-session-events.jsonl`
5. Write assistant output and final status into durable files that can survive process restarts

Per-task runtime artifacts are stored under the task output directory, for example:

1. `copilot-session-state.json`
2. `copilot-session-events.jsonl`
3. `copilot-session.stdout.log`
4. `copilot-session.stderr.log`
5. `output.md`
6. `metadata.json`

### Layer 4: Background monitor and recovery

`server/services/copilot_sdk_monitor.py` is started from the FastAPI lifespan in `server/main.py` when:

1. `ORCHESTRATION_BACKEND=copilot_sdk`
2. `COPILOT_SDK_MONITOR_ENABLED=true`

Responsibilities:

1. Poll running tasks with active Copilot session ids
2. Incrementally ingest new runtime events using `TaskRow.runtime_event_cursor`
3. Sync `output.md`, `metadata.json`, stdout, and stderr back into the task row
4. Mark tasks `completed`, `failed`, or `pending_approval`
5. Detect stale heartbeats and resume sessions through `resumeSession()`
6. Recover already-idle sessions even when the idle event was not durably persisted

## Agent model

There are two agent concepts in this repository and they should remain separate.

### Business agents

Business agents are the repository roles discovered from `roles/*/prompts/persona.md`.

Examples:

1. `growth_lead`
2. `content_writer`
3. `seo_strategist`
4. `launch_strategist`

These remain user-facing and continue to drive task routing.

### Runtime agents

Runtime agents are Copilot SDK `customAgents` used inside a session.

Initial runtime set:

1. `researcher`
2. `editor`
3. `db-analyst`

These are operational specialists, not replacements for the business roles.

## Runtime agent definitions

### researcher

Purpose:

1. Explore code, docs, and task context
2. Summarize patterns
3. Prepare implementation plans

Tool scope:

1. `view`
2. `grep`
3. `glob`

Infer:

1. `true`

### editor

Purpose:

1. Implement targeted changes
2. Run local validation commands
3. Produce final output or file edits

Tool scope:

1. `view`
2. `grep`
3. `glob`
4. `edit`
5. `bash`

Infer:

1. `true`

### db-analyst

Purpose:

1. Analyze schema and data workflows
2. Reason about SQL and migrations
3. Use database-specific MCP servers when configured

Tool scope:

1. `view`
2. `grep`
3. `glob`
4. optional MCP tools only

Infer:

1. `true`

MCP:

1. attach only when DB MCP settings are configured

## How repository data maps to the runtime

### Persona mapping

`server/services/agent_loader.py` remains the source of truth for business agents.

The selected business role contributes:

1. parent session prompt framing
2. domain-specific goal and tone
3. skill compatibility and routing metadata

### Skill mapping

`server/services/skill_loader.py` remains the source of truth for skills.

Skills do not become runtime agents.

Instead, the selected skill contributes:

1. task constraints
2. output expectations
3. domain hints that improve runtime agent inference

## Execution flow

### Task creation

1. `POST /api/tasks` calls `suggest_task_execution()` when needed
2. The chosen business role and skill are stored on the task
3. Task status remains `pending`

### Task run

1. `POST /api/tasks/{id}/run` resolves the full business persona
2. `task_runner` invokes the selected runtime backend
3. `CopilotSDKTaskRuntime.execute()` writes the predicted output paths and launches a detached worker
4. The detached worker creates or resumes a parent Copilot SDK session
5. The worker registers `researcher`, `editor`, and `db-analyst` as `customAgents`
6. The parent prompt includes:
   - selected role persona
   - selected skill text
   - task description
   - context files
7. Python returns immediately with `deferred=True`, and the task remains `running`
8. The monitor ingests new runtime events and syncs task metadata on each poll
9. When the worker finishes, the monitor writes final output, timing, and status to the task row
10. If the worker stops updating heartbeat for longer than `COPILOT_SDK_STALE_AFTER_SEC`, the monitor starts a `resume` worker for the same session id

## Event model

Copilot SDK runtime events are persisted into `task_logs` after normalization.

Normalized event types:

1. `runtime_started`
2. `runtime_session_created`
3. `subagent_selected`
4. `subagent_started`
5. `subagent_completed`
6. `subagent_failed`
7. `assistant_output`
8. `runtime_completed`
9. `runtime_failed`

`assistant_output_chunk` and other low-level tool chatter can exist in the raw worker event file, but the TaskBoard primary transcript now renders only normalized `assistant_output` entries so the UI stays human-readable.

Incremental ingestion is tracked with `TaskRow.runtime_event_cursor`, which keeps monitor polling idempotent.

## Approvals model

Current approval rows remain final-output approvals.

For this implementation phase:

1. runtime tool permissions are auto-approved inside the allowed tool scope
2. final task approval continues to use `ApprovalRow`

Future work:

1. add a dedicated permission queue for dangerous runtime requests
2. separate tool permission approvals from final content approvals

## Configuration

New backend settings:

1. `ORCHESTRATION_BACKEND=legacy|copilot_sdk`
2. `COPILOT_SDK_NODE_BIN`
3. `COPILOT_SDK_RUNNER_PATH`
4. `COPILOT_SDK_MODEL`
5. `COPILOT_SDK_TIMEOUT`
6. `COPILOT_SDK_MONITOR_ENABLED`
7. `COPILOT_SDK_POLL_INTERVAL_SEC`
8. `COPILOT_SDK_STALE_AFTER_SEC`
9. optional DB analyst MCP environment variables

The default remains `legacy` so the repository stays runnable without the SDK.

## Dashboard contract

The TaskBoard keeps the same task drawer, but the runtime-specific UX now follows two rules:

1. Runtime transcript panels render human-readable `assistant_output` only
2. Execution duration is shown as a live elapsed timer while a task is `running`, then falls back to the final stored `execution_time_ms` when complete

This keeps the dashboard useful for operators without exposing raw low-level runtime noise by default.

## Testing strategy

### Backend

1. unit test runtime config generation
2. unit test subprocess result parsing and error handling
3. integration test task runner with mocked Copilot SDK runner
4. API test task status/log/output transitions for `copilot_sdk`

### Frontend

1. extend `TaskBoard` tests to assert sub-agent log rendering
2. extend drawer tests to assert runtime badges and event timeline
3. add UI regression coverage for retries and error states

### Browser validation

1. run the local dashboard
2. create and run a task through the UI
3. inspect task drawer and log modal
4. record any defects in `docs/test/bugfix.md`
5. fix defects and rerun validation

## Rollout plan

Phase 1:

1. docs
2. runtime abstraction
3. Node SDK runner
4. backend task integration
5. backend tests

Phase 2:

1. TaskBoard runtime UI updates
2. frontend tests
3. browser-based validation and bugfix loop
