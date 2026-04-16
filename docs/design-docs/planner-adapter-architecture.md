---
id: planner-adapter-architecture
title: Planner Adapter Architecture
role: dev_rel
status: ready
created_at: 2026-04-16
updated_at: 2026-04-16
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing
---

# Planner Adapter Architecture

## Summary

Plan agent model calls use a single adapter interface instead of branching directly on Copilot, Codex CLI, Codex SDK, OpenAI, or Claude at each call site.

The adapter layer covers:

1. acceptance contract generation
2. plan brief generation
3. verification agent provider calls

Execution runtime selection remains separate. `ORCHESTRATION_BACKEND` controls task execution; `PLANNER_BACKEND` controls plan agent provider calls.

## Configuration

Planner-specific configuration:

```env
PLANNER_BACKEND=codex_sdk
PLANNER_MODEL=gpt-5.4
PLANNER_TIMEOUT=300
```

Supported planner backends:

1. `openai`
2. `claude`
3. `copilot`
4. `codex_cli`
5. `codex_sdk`

Resolution order:

1. Explicit `PLANNER_BACKEND`.
2. Compatible mapping from `ORCHESTRATION_BACKEND`.
3. Fallback to `LLM_PROVIDER`.

Compatibility mapping:

1. `ORCHESTRATION_BACKEND=codex_sdk` -> `PLANNER_BACKEND=codex_sdk`
2. `ORCHESTRATION_BACKEND=codex_cli` -> `PLANNER_BACKEND=codex_cli`
3. `ORCHESTRATION_BACKEND=copilot_sdk` -> `PLANNER_BACKEND=copilot`
4. `ORCHESTRATION_BACKEND=openai_responses` -> `PLANNER_BACKEND=openai`

## Adapter Interface

The backend exposes one entrypoint:

```python
generate_planner_text(PlannerRequest(...)) -> PlannerResponse
```

Core request fields:

1. `prompt`
2. `system_prompt`
3. `raw_prompt`
4. `cwd`
5. `output_path`
6. `add_dirs`
7. `resume_session_id`
8. `metadata`

Adapters:

1. `LLMPlannerAdapter` handles `openai`, `claude`, and `copilot` via the existing LLM provider interface.
2. `CodexCliPlannerAdapter` handles `codex_cli` via `codex exec`.
3. `CodexSdkPlannerAdapter` handles `codex_sdk` via the Codex Python SDK bridge.

## Session Boundary

Only Codex adapters use planner session resume:

1. `codex_cli` passes `resume_session_id` to Codex CLI.
2. `codex_sdk` passes `resume_session_id` to Codex Python SDK.
3. `openai`, `claude`, and `copilot` do not write Codex session registry rows.

Project-scoped planner session reuse remains:

1. `role_key="planner"`
2. `project_root=<canonical target project root>`
3. `requirement_id=NULL`

Execution agents remain requirement-scoped.

## Extension Rules

New providers should add a planner adapter instead of adding provider-specific branches at call sites.

Minimum implementation requirements:

1. Implement `PlannerAdapter.generate`.
2. Add backend resolution support.
3. Add model resolution default.
4. Add tests for request routing, timeout, model override, and metadata behavior.

## Validation

Required tests:

1. `PLANNER_BACKEND` explicit selection.
2. fallback from `ORCHESTRATION_BACKEND`.
3. `PLANNER_MODEL` override.
4. Codex CLI session metadata.
5. Codex SDK session metadata.
6. LLM adapters without Codex session metadata.
