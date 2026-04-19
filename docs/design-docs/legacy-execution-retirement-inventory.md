---
id: legacy-execution-retirement-inventory
title: Legacy Execution Retirement Inventory
role: dev_rel
status: ready
created_at: 2026-04-18
updated_at: 2026-04-18
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing
---

# Legacy Execution Retirement Inventory

## Summary

The Company Ops control plane has hard-switched to Declarative Workflow Factory semantics:

```text
Requirement -> Declarative Workflow Run -> State Machine -> Blackboard -> Atom Invocations -> Human Gate / Release
```

The old fixed-step execution surface is no longer an operator-facing product path. It must not be used as fallback for new requirements, new UI, new tests, or new docs.

## Removed From The Main Surface

1. Frontend routes for the legacy execution list and detail pages were removed from the dashboard router.
2. Frontend pages for the legacy execution list and detail views were deleted.
3. Frontend API client methods that called the legacy execution endpoints were deleted.
4. Frontend unit tests that asserted fixed workflow steps, old execution pages, or bugfix branch semantics were deleted.
5. The FastAPI app no longer registers the legacy execution router, so the old execution endpoints are no longer part of the active API surface.
6. Error notifications now link to workflow runs instead of legacy execution pages.
7. Ops docs now describe `/workflows` and `/workflows/:id` as the execution observation surface.

## Retired Test Families

The following test families were removed because they validated deleted UI or old orchestration semantics:

1. Legacy execution page observability tests.
2. Fixed workflow step panel tests.
3. Bugfix branch UI tests.
4. Historical E2E specs that expected `workflow-steps-panel`.
5. Stale page tests importing pages that no longer exist in the current dashboard.

Current frontend coverage is intentionally smaller and aligned to the new truth:

1. Requirement pool workflow state summary.
2. Workflow run detail timeline, blackboard, atom invocations, artifacts, and human gates.
3. Agent-first page smoke tests for requirement, release, project, and error surfaces.

## Completed Destructive Retirement

The destructive backend cleanup has landed. The active codebase no longer declares or imports these historical ORM models:

1. `ExecutionRunRow`
2. `ExecutionNodeRow`
3. `WorkflowStepRow`
4. `WorkflowStepDependencyRow`
5. `StepInputBindingRow`
6. `TaskRow`
7. `TaskLogRow`
8. `ApprovalRow`
9. `ValidationLeaseRow`

The old `agent_first.py`, fixed-step planner helpers, task backfill script, and workflow orchestrator package have also been removed from the active tree.

## Database Boundary

Do not create new business logic that writes through the historical execution tables. New runtime state belongs in:

1. `workflow_definitions`
2. `workflow_runs`
3. `workflow_state_events`
4. `workflow_artifacts`
5. `blackboard_snapshots`
6. `atom_invocations`
7. `human_gate_requests`

Old physical SQLite tables can still exist in a developer's local database file until that database is reset or archived. They are no longer represented by active SQLAlchemy models and must not be queried by application code.

Use these local reset scripts when a developer wants to clear runtime residue:

```bash
/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_execution_runtime.py --yes
/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_workflow_state.py --yes
```

## Remaining Compatibility Names

Some response schemas still expose historical field names such as `execution_run_id` inside validation summaries for UI compatibility. These fields are now inert identifiers, not foreign keys to an active execution model.

The rule remains strict: new workflows must use declarative workflow runs, state events, atom invocations, blackboard snapshots, workflow artifacts, and human gates as the only execution truth.
