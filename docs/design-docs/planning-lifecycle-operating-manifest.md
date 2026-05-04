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

1. One active `OperatingManifest` defines the company’s current budget, focus weights and global constraints.
2. First-class `PlanningGoal` records hold business intent, long Markdown PRDs, success metrics and workflow/project binding.
3. A stateless Planner Sweep reads compact steering and goal-map data, then creates `RequirementCandidate` records.
4. The operator approves, rejects or materializes candidates into requirements.
5. `goal_key` and `operating_manifest_id` flow through candidates, requirements, workflow runs and release records.
6. `Drop Goal` stops future investment and safely halts unfinished work, but never rolls back already delivered artifacts.

This keeps the Planner from becoming a long-lived PM agent. The lifecycle is data-driven: SQL joins, rollups and UI surfaces track progress; agents only evaluate the current snapshot and propose the next useful work.

## Core Objects

### OperatingManifest

`operating_manifests` is the company’s active steering config.

Key rules:

1. Exactly one manifest is active through `active_slot="global"`.
2. Active manifest supports minor revisions for small adjustments.
3. The manifest payload is control plane only: `global_budget`, `focus_weights`, `global_constraints` and other short steering fields.
4. It must not contain `payload.goals`, long Markdown, PRDs or execution acceptance text.
5. `PUT /api/planning/manifest/active` rejects payloads containing `goals`; operators must use `/api/planning/goals`.
6. `Archive & Start New Cycle` creates an immutable historical snapshot and carries only active goals into the next cycle by copying `planning_goals` rows.
7. Archived history is not capped to the last 12 records; it is paginated and searchable.

### PlanningGoal

Goals live in the first-class `planning_goals` table. They are not embedded in manifest JSON.

Core fields:

1. `manifest_id`
2. `goal_key`
3. `title`
4. `intent_markdown`
5. `success_metric`
6. `domain`
7. `status`
8. `workflow_key`
9. `project_key`
10. `priority`
11. `risk_level`
12. `weight`
13. `acceptance_kind`
14. `execution_acceptance_steps_json`

Minimal lifecycle:

```text
active -> achieved
active -> dropped
```

`goal_key` must be stable. It is the lineage key that connects candidates, requirements, workflow runs and release records.

Long goal context belongs in `intent_markdown`, not Raw Manifest JSON. `/planning` edits it through the Goal detail API:

```http
GET /api/planning/goals/{id}
PUT /api/planning/goals/{id}
```

`GET /api/planning/mission-control` is intentionally lightweight. It returns goal lanes with a backend-generated `intent_excerpt` truncated to 200 characters and never returns full `intent_markdown`. This keeps the operator dashboard and Planner map fast.

## Progressive Context

Give agents the map first, not the whole manual.

Planner Sweep reads:

1. Active manifest steering payload.
2. Active goal map: `id`, `goal_key`, `title`, `domain`, `success_metric`, `status`, `weight`, `intent_excerpt`.
3. Aggregated rollups for candidates, requirements, workflow runs and releases.

When generating a candidate for one goal, the service injects only that single goal's `intent_markdown` and acceptance data. It must not stuff every goal's PRD into the Planner snapshot.

Planner Agent v1.1 turns that single-goal Markdown PRD into a structured candidate. Its output is not trusted until it passes:

1. strict JSON parsing, with at most two repair turns for formatting/schema mistakes.
2. workflow key enum validation against the registered workflow definitions.
3. fail-closed acceptance validation, including safe `required_commands` allowlist / denylist checks.

If any gate fails, the candidate stays in `validation_failed`; it must not become a Requirement or start a Workflow.

Planner Agent must also declare the delivery expectation before execution starts:

```text
expected_outcome = code_delivery | verification_only
```

`code_delivery` means the Requirement must produce repository changes before delivery handoff. If the delivery atom sees no diff, the workflow must fail closed instead of claiming success.

`verification_only` is only valid when the Goal can be proven by evidence-bound commands and artifacts against the current repository state. It may complete without a PR, but only if the verification evidence bundle is complete. The workflow runner may not decide this at the end as an escape hatch; it must come from the Planner Candidate.

When an operator uses `Supersede & Retry Planner` on a no-change/bootstrap dead end, the new sweep receives a temporary `context_hint`. This hint explains why the previous Requirement/Workflow was superseded and asks Planner to re-evaluate the current repository state, including whether a `verification_only` candidate is now appropriate. The hint is stored in that sweep's input snapshot and must not permanently mutate Goal PRD Markdown.

### RequirementCandidate

`requirement_candidates` is the buffer between autonomous planning and the official requirement pool.

Candidate statuses:

```text
pending | approved | rejected | materialized | suppressed | stale
```

Planner Sweep creates candidates, not requirements. This prevents agent-generated noise from polluting the requirement pool.

Fresh candidates pass through a deterministic Candidate Risk Router before any automatic promotion:

1. Operating Manifest stays business intent only; it does not contain auto-execution policy.
2. Low/normal risk candidates on allowlisted workflows may be auto-materialized and auto-started.
3. High/critical risk, forbidden atoms, production, funds, auth, contract, public posting or project-policy-gated work remains in operator review.
4. Router decisions are written to candidate metadata and planner sweep output.

### PlannerSweep

`planner_sweeps` records each top-down planning evaluation.

Planner Sweep is stateless:

1. It reads active manifest.
2. It reads aggregated goal progress.
3. It calls Planner Agent once per active goal with capacity.
4. It ignores dropped goals.
5. It validates Planner Agent output before materialization.
6. It routes fresh valid candidates through deterministic risk policy.
7. It exits.

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
5. planning goal text, including `goal_key`, `title`, `intent_markdown` and status

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
POST /api/planning/goals/{id}/drop
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
GET  /api/planning/goals
GET  /api/planning/goals/{id}
POST /api/planning/goals
PUT  /api/planning/goals/{id}
POST /api/planning/goals/{id}/drop
GET  /api/planning/manifest/{id}/goals/{goal_key}/rollup
POST /api/planning/sweeps/run
GET  /api/planning/candidates
POST /api/planning/candidates/{id}/approve
POST /api/planning/candidates/{id}/approve-and-run
POST /api/planning/candidates/{id}/reject
POST /api/planning/candidates/{id}/materialize
```

`approve-and-run` is the default operator path for normal candidate handling:

```text
RequirementCandidate(pending)
-> approve candidate
-> materialize Requirement
-> start Declarative WorkflowRun immediately
-> stop at workflow Human Gate when risk policy requires it
```

This is not legacy requirement-level approval. Requirement pre-execution approval remains retired; human decisions happen inside workflow `human_gate_requests`.

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
2. Candidate approval, rejection, approve-and-run and materialization must happen inside the relevant goal lane so the operator sees the business context.
3. Raw Manifest JSON must not be the default editing surface. Use form controls for `focus_weights`, `global_budget` and `global_constraints`.
4. Raw JSON is allowed only in a Debug tab, centered modal, or `<details>` block for fields not covered by the structured controls.
5. Manifest History must be paginated and searchable, and must not crowd the Mission Control primary surface.
6. Pending candidates should expose `Approve & Run` as the primary action and `Approve only` as an explicit staging action.
7. `Approve & Run` must not bypass workflow risk policy; high-risk candidates must still stop at Human Gate.
8. Goal creation is intent-first: operator writes `title`, `goal_key`, `domain`, `success_metric` and full `intent_markdown` in a Write / Preview Markdown editor.
9. Goal creation must not expose `execution_acceptance_steps` JSON; Planner/Candidate generation owns evidence-bound acceptance, and invalid candidates fail closed.
10. Advanced goal settings such as workflow, project, risk, weight and `acceptance_kind` must be collapsed by default.
11. Goal Markdown editors must warn before closing with unsaved changes.
12. The primary view should answer: what goal is this for, what is pending, what is running, what shipped, and what should the operator decide next.
13. Goal lanes must render as compact battlefront cards: title, domain, weight, success metric, clamped intent excerpt, primary actions, and grouped candidates.
14. Candidate display order is `Action Required -> Materialized -> Planner Intercepts -> Quiet History`.
15. `validation_failed` candidates must not be rendered as normal candidate cards. They belong in a collapsed Planner Intercepts section with the Fail-Closed reason first.
16. Full Goal PRD, Candidate `description_markdown`, Planner raw output and metadata dumps must be behind centered modals or `<details>` progressive disclosure.
17. Goal lanes must be grouped as `Active / Achieved / Dropped`: Active goals stay expanded at the top, while historical Achieved and Dropped goals stay collapsed by default.
18. Historical goal groups must support local filtering and virtualized history when the group grows large; do not use table-style pagination for the primary mission control surface.
19. Planner Intercepts must use deduped planner intercepts by Fail-Closed reason signature. Repeated identical failures should render as one diagnostic group with an attempt count, not as a wall of duplicate drafts.
20. Planning timestamps must render in browser local time while preserving the original UTC value through the underlying `<time>` element or tooltip.

Recommended Goal lane shape:

```text
Goal title
Domain: ops | Weight: 50% | Success Metric: Pending
Intent: <short excerpt> [view full PRD]
[Edit Intent] [Edit Settings] [Trace Path] [Drop Goal]

Candidates (2 Materialized, 3 Failed)
Materialized: <candidate title> [Requirement #6] [Workflow Completed]
Planner Intercepts: collapsed fail-closed drafts
```

Historical goal group shape:

```text
Active Goals: expanded battlefront cards
Achieved Goals: collapsed header -> searchable compact rows -> virtualized history when large
Dropped Goals: collapsed header -> searchable compact rows -> virtualized history when large
Planner Intercepts: [3x Failed] latest local time - Fail Closed reason -> attempts hidden in details
```

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
