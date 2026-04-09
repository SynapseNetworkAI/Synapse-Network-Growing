---
created_at: 2026-04-09
updated_at: 2026-04-09
doc_status: completed
---

# Execution Plan — Phase 1 Full Closure

## Scope

Complete all actionable Phase 1–4 gaps identified in the design doc gap analysis.
Items explicitly deferred to Phase 2+ (AI planner, multi-tenant, DAG parallelism, external sync) are out of scope.

## Completed (Previous Passes)

- [x] Requirement Pool CRUD + dependencies + blocking
- [x] Deterministic planner → structured plan output
- [x] Workflow orchestrator: step scheduling, bugfix loop, closeout
- [x] Revision lifecycle with cancel-replan
- [x] Dynamic org chart from roles/* discovery
- [x] Full database schema (all 10 tables from DB design doc)
- [x] RequirementPool UI: create, plan, start, revision, dependencies, steps, artifacts, acceptance checks
- [x] OrgChart UI: dynamic agent groups
- [x] Backend tests: 111 passed
- [x] Frontend tests: 39 passed
- [x] Playwright smoke + real E2E: 8 passed

## Remaining Work

### WS-1: Database Indexes (§5 DB Design Doc)
- [x] Add recommended secondary indexes to all 10 tables in database.py

### WS-2: Workflow Step Events (§16 Observability)
- [x] Write events to `workflow_step_events` on step state transitions in orchestrator
- [x] Populate `handoff_summary_markdown` when step completes (§3.6 Structured Handoff)

### WS-3: Missing API Endpoints (§18)
- [x] `PATCH /api/requirements/{id}` — partial field update
- [x] `POST /api/requirements/{id}/close` — manual close with governance check

### WS-4: Requirement Pool Scoring (§8)
- [x] Implement priority+aging scoring formula for requirement list sorting

### WS-5: Step State Completeness (§14.1)
- [x] Add missing step states: `ready`, `blocked` to step lifecycle

### WS-6: Tests for New Behavior
- [x] Backend tests for new endpoints + events + scoring
- [x] Frontend test coverage for any UI changes

## Out of Scope (Phase 2+)

- AI-driven planner (LLM replaces deterministic planner)
- Agent Context Contract (§11 structured 3-layer context)
- Step Context JSON Schema (§10.6)
- Structured Verifier Output (§13.1)
- Recovery & Idempotency (§14.3-14.4)
- Observability APIs (timeline, lineage, evidence views)
- Step-level APIs (run/retry/logs/context/approve per step)
- File scope enforcement at runtime
- Approval gates (pre_execution, pre_publish, manual_close)
- Multi-tenant isolation, DAG parallel scheduling, external sync