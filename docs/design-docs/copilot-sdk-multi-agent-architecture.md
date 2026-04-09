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

Replace the current single-shot LLM execution path with a Copilot SDK runtime that supports:

1. Custom agents with scoped tools
2. Runtime agent inference and sub-agent delegation
3. Optional MCP attachment per agent
4. Session and sub-agent event logging
5. Backward-compatible task creation, approvals, retries, and dashboard views

## Current state

The current execution path is:

1. `server/routers/tasks.py` creates and runs tasks
2. `server/services/task_runner.py` dispatches background execution
3. `server/services/crew_engine.py` assembles persona + skill + context into a single prompt
4. `server/services/llm_adapter.py` sends one provider request

This gives prompt-driven role simulation, but not true runtime multi-agent orchestration.

## Target architecture

The target system keeps the existing task API and dashboard, but swaps the runtime under the hood.

### Layer 1: Task orchestration

Existing components remain the entrypoint:

1. `server/routers/tasks.py`
2. `server/services/execution_resolver.py`
3. `server/services/task_runner.py`

Responsibilities:

1. Resolve preferred agent and skill at task creation time
2. Collect context files and approval requirements
3. Persist task status and logs
4. Start background execution

### Layer 2: Runtime adapter

Add a runtime abstraction that supports two backends:

1. `legacy` runtime: current `CrewEngine` single-call behavior
2. `copilot_sdk` runtime: Node-based Copilot SDK runner invoked from Python

Responsibilities:

1. Build runtime session config
2. Convert repo personas and skills into Copilot SDK custom agent config
3. Execute a session and return normalized events/results
4. Surface errors in a provider-agnostic shape

### Layer 3: Copilot SDK runner

Use a small Node runner around `@github/copilot-sdk`.

Responsibilities:

1. Start a `CopilotClient`
2. Create a session with `customAgents`
3. Subscribe to session and sub-agent events
4. Auto-approve allowed tool requests inside the runtime
5. Return final content, runtime metadata, and event stream as JSON

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
3. The runtime creates a parent Copilot SDK session
4. The runtime registers `researcher`, `editor`, and `db-analyst` as `customAgents`
5. The parent prompt includes:
   - selected role persona
   - selected skill text
   - task description
   - context files
6. The runtime collects events and final content
7. Task logs are appended as normalized lifecycle records
8. Task output and timing are stored on the task row

## Event model

Copilot SDK runtime events are persisted into `task_logs`.

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

This avoids changing the dashboard log viewer contract while still surfacing sub-agent activity.

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
5. optional DB analyst MCP environment variables

The default remains `legacy` so the repository stays runnable without the SDK.

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
