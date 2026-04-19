---
id: planning-lifecycle-operating-manifest
title: Planning Lifecycle Operating Manifest
role: dev_rel
status: draft
created_at: 2026-04-19
updated_at: 2026-04-19
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing
---

# Planning Lifecycle Operating Manifest

## Summary

Planning Lifecycle v1.2 gives the OPS system a real upstream control plane:

1. One active `OperatingManifest` defines the company’s current goals, budgets and global constraints.
2. A stateless Planner Sweep reads the active manifest and creates `RequirementCandidate` records.
3. The operator approves, rejects or materializes candidates into requirements.
4. `goal_key` and `operating_manifest_id` flow through candidates, requirements, workflow runs and release records.
5. `Drop Goal` stops future investment and safely halts unfinished work, but never rolls back already delivered artifacts.

This keeps the Planner from becoming a long-lived PM agent. The lifecycle is data-driven: SQL joins, rollups and UI surfaces track progress; agents only evaluate the current snapshot and propose the next useful work.

## Core Objects

### OperatingManifest

`operating_manifests` is the company’s active strategic config.

Key rules:

1. Exactly one manifest is active through `active_slot="global"`.
2. Active manifest supports minor revisions for small adjustments.
3. `Archive & Start New Cycle` creates an immutable historical snapshot and carries only active goals into the next cycle.
4. Archived history is not capped to the last 12 records; it is paginated and searchable.

### Goal

Goals live inside `OperatingManifest.payload.goals`.

Minimal lifecycle:

```text
active -> achieved
active -> dropped
```

`goal_key` must be stable. It is the lineage key that connects candidates, requirements, workflow runs and release records.

### RequirementCandidate

`requirement_candidates` is the buffer between autonomous planning and the official requirement pool.

Candidate statuses:

```text
pending | approved | rejected | materialized | suppressed | stale
```

Planner Sweep creates candidates, not requirements. This prevents agent-generated noise from polluting the requirement pool.

### PlannerSweep

`planner_sweeps` records each top-down planning evaluation.

Planner Sweep is stateless:

1. It reads active manifest.
2. It reads aggregated goal progress.
3. It proposes candidates for active goals.
4. It ignores dropped goals.
5. It exits.

It does not poll every workflow as a PM, does not interrupt workers directly and does not create release actions.

## History Pagination

The history endpoint returns all manifest history through pagination:

```http
GET /api/planning/manifests/history?page=1&page_size=20&status=archived&search=provider
```

Search matches:

1. `manifest_key`
2. `version_name`
3. `cycle_label`
4. `status`
5. manifest payload text, including `goal_key`

The `/planning` UI must show all history with pagination. It must not silently truncate to the most recent 12 cycles.

## Drop Goal Semantics

`Drop Goal` means:

```text
Stop future investment in this goal.
Safely halt unfinished work.
Retain delivered artifacts.
Never rollback automatically.
```

It does not mean:

```text
Revert commits.
Rollback deployment.
Delete database changes.
Unpublish external content.
Undo customer-visible actions.
```

The API requires a reason:

```http
POST /api/planning/manifest/{id}/goals/{goal_key}/drop
```

Payload:

```json
{
  "reason": "strategy changed",
  "operator": "operator",
  "halt_mode": "safe_halt"
}
```

## Cascading Halt

When a goal is dropped, the system performs a safe cascade:

1. Pending candidates become `suppressed` with `suppression_reason="goal_dropped"`.
2. Approved but unmaterialized candidates become `suppressed`.
3. Draft / ready / pending-approval requirements become `cancelled`.
4. Running or awaiting workflow runs move to `awaiting_operator` with `resolution="goal_dropped_safe_halt"`.
5. Workflow blackboard receives `goal_drop_decision`.
6. A workflow state event `goal_dropped_halt_requested` is recorded.
7. A pending human gate `goal_dropped_halt` is created.
8. Release-ready but undelivered records become `blocked`.
9. Delivered or released records are retained unchanged.

The halt summary is returned to the operator:

```json
{
  "suppressed_candidates": 2,
  "cancelled_requirements": 1,
  "paused_workflows": 1,
  "blocked_releases": 1,
  "delivered_artifacts_retained": 3,
  "rollback_triggered": false
}
```

## Rollback Boundary

Drop Goal never triggers rollback.

Rollback is only allowed through release / deployment safety paths:

1. Observing failed and matched rollback policy.
2. Deployment failed.
3. Kill switch triggered.
4. Operator manually requested rollback.

Rollback must write release / deployment events. It must not be a side effect of planning goal lifecycle.

## Decommission Rule

If the operator wants to remove already delivered functionality, the system should create a new decommission requirement:

```text
Safely decommission <feature>, including code, migrations, config, docs and user-facing cleanup.
```

That requirement must bind to an active maintenance goal and go through the normal workflow:

```text
requirement -> workflow -> verification -> human gate -> release
```

This avoids treating strategic goal changes as unsafe physical rollbacks.

## API Surface

Current v1.2 endpoints:

```text
GET  /api/planning/manifest/active
PUT  /api/planning/manifest/active
GET  /api/planning/manifests/history
POST /api/planning/manifest/{id}/archive-and-start-cycle
POST /api/planning/manifest/{id}/goals/{goal_key}/drop
GET  /api/planning/manifest/{id}/goals/{goal_key}/rollup
POST /api/planning/sweeps/run
GET  /api/planning/candidates
POST /api/planning/candidates/{id}/approve
POST /api/planning/candidates/{id}/reject
POST /api/planning/candidates/{id}/materialize
```

## UI Surface

`/planning` is the operator control plane and must be a goal-centric mission control surface.

It contains:

1. Global Steering Wheel: current version, revision, cycle, Planner Sweep actions, archive cycle action, focus weights, global budget and global constraints.
2. Goal Mission Control: one lane per goal, with rollups and candidates nested under the owning `goal_key`.
3. History & Archive: a separate tab or secondary surface with paginated/searchable manifest history.
4. Debug: raw manifest JSON and planner sweep payloads behind progressive disclosure only.
5. Halt Summary after a goal is dropped.

### Planning Console UX Contract

1. `/planning` must organize work by `goal_key`; candidates must not appear as a detached global queue in the primary view.
2. Candidate approval, rejection and materialization must happen inside the relevant goal lane so the operator sees the business context.
3. Raw Manifest JSON must not be the default editing surface. Use form controls for `focus_weights`, `global_budget` and `global_constraints`.
4. Raw JSON is allowed only in a Debug tab or drawer for fields not covered by the structured controls.
5. Manifest History must be paginated and searchable, and must not crowd the Mission Control primary surface.
6. The primary view should answer: what goal is this for, what is pending, what is running, what shipped, and what should the operator decide next.

The Drop Goal modal must explicitly say:

1. Pending candidates will be suppressed.
2. Unstarted requirements will be cancelled.
3. Running workflows will be paused or sent to human gate.
4. Release-ready artifacts may be blocked.
5. Delivered artifacts are retained.
6. No rollback or revert will happen automatically.

## Test Plan

Required tests:

1. Manifest history pagination and search over all archived records.
2. Planner Sweep ignores dropped goals.
3. Planner Sweep creates candidates for active goals with capacity.
4. Candidate materialization preserves `operating_manifest_id`, `goal_key` and `requirement_candidate_id`.
5. Drop Goal requires reason.
6. Drop Goal suppresses candidates.
7. Drop Goal cancels unstarted requirements.
8. Drop Goal pauses active workflow and creates human gate.
9. Drop Goal retains delivered release records.
10. Drop Goal never calls rollback or creates revert commits.
