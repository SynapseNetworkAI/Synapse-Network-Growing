---
id: legacy-execution-retirement-inventory
title: Legacy Execution Retirement Inventory
role: dev_rel
status: draft
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

## Remaining Historical Code

Some backend modules still contain historical classes and helpers:

1. `ExecutionRunRow`
2. `ExecutionNodeRow`
3. `WorkflowStepRow`
4. legacy execution response models
5. old agent-first execution helpers used by historical tests and cleanup routines

These are not part of the active product surface after the router was unregistered. They remain only because physical deletion requires a destructive database migration and a broader backend test rewrite.

## Database Boundary

Do not create new business logic that writes through the historical execution tables. New runtime state belongs in:

1. `workflow_definitions`
2. `workflow_runs`
3. `workflow_state_events`
4. `workflow_artifacts`
5. `blackboard_snapshots`
6. `atom_invocations`
7. `human_gate_requests`

Historical execution tables can be dropped only after:

1. release records no longer carry historical execution foreign keys,
2. validation records are rekeyed to workflow runs,
3. old tests are deleted or rewritten,
4. cleanup endpoints no longer query old rows,
5. local operators have accepted that historical execution details will no longer be readable.

## Follow-Up Destructive Migration

The next cleanup should be a deliberate destructive migration, not an opportunistic refactor. Its expected scope:

1. Drop old execution API module and internal service helpers that only served that API.
2. Remove old execution response schemas from `server/schemas.py`.
3. Remove old execution foreign keys from release and validation projections.
4. Remove old fixed-step orchestration helpers once no current services import them.
5. Add migration notes for local database reset and production archive strategy.

Until that migration lands, the rule is strict: old tables may be read for historical cleanup only, but new workflows must never use them as source of truth.
