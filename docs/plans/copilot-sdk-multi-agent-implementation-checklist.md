---
id: copilot_sdk_multi_agent_implementation_checklist
title: Copilot SDK Multi-Agent Implementation Checklist
status: completed
created_at: 2026-04-09
updated_at: 2026-04-09
author: github-copilot
target_repo: cliff-personal/Synapse-Network-Growing
---

# Copilot SDK Multi-Agent Implementation Checklist

## Scope

Implement a first working Copilot SDK multi-agent path in this repository while preserving the current task APIs.

## Step 1: Documentation

- [x] Add architecture doc under `docs/design-docs/`
- [x] Add implementation checklist under `docs/plans/`
- [x] Add test plan after code stabilizes

## Step 2: Runtime abstraction

- [x] Add a runtime adapter interface for task execution
- [x] Keep the current `CrewEngine` path as `legacy`
- [x] Add a `copilot_sdk` runtime path
- [x] Add config flags to switch runtime backend

## Step 3: Node runner

- [x] Add a small Node runner around `@github/copilot-sdk`
- [x] Accept JSON input from Python
- [x] Build `customAgents` for `researcher`, `editor`, and `db-analyst`
- [x] Collect session and sub-agent events
- [x] Return normalized JSON output to Python

## Step 4: Python integration

- [x] Add Python service to invoke the Node runner
- [x] Normalize runner output into task results and logs
- [x] Map persona + skill + context into parent session input
- [x] Persist runtime metadata on task/log records

## Step 5: Backend API compatibility

- [x] Preserve `POST /api/tasks`
- [x] Preserve `POST /api/tasks/{id}/run`
- [x] Preserve retry and approval flows
- [x] Ensure low-confidence resolution behavior remains unchanged

## Step 6: Frontend updates

- [x] Surface runtime backend/session info in task detail drawer
- [x] Show sub-agent activity in task logs or detail view
- [x] Keep existing run, retry, and approval interactions intact

## Step 7: Automated testing

- [x] Add backend unit tests for runtime adapter behavior
- [x] Add backend integration tests for task execution with mocked SDK runner
- [x] Add frontend tests for runtime log rendering
- [x] Run pytest
- [x] Run Vitest

## Step 8: UI validation and bugfix loop

- [x] Start backend and dashboard locally
- [x] Execute browser-based validation of task flow
- [x] Record defects in `docs/test/bugfix.md`
- [x] Fix defects
- [x] Re-run browser validation

## Completion criteria

- [x] Tasks can run through the Copilot SDK runtime path
- [x] Sub-agent events are visible in backend logs and UI
- [x] Existing legacy path remains available
- [x] Automated backend and frontend tests pass
- [x] Browser validation passes after bugfixes
