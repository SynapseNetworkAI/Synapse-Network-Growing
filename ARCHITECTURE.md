# Synapse-Network-Growing Architecture Constraints

This file is the short, tool-neutral constitution for AI coding assistants working in this repository.

Read it before changing workflow, planning, scheduler, release, notification, runtime, security, auth, finance, settlement, or production-delivery code.

Canonical sources:

1. `AGENTS.md`
2. `docs/design-docs/system-design-principles.md`
3. `docs/design-docs/declarative-agent-workflow-factory.md`
4. `docs/design-docs/planning-lifecycle-operating-manifest.md`
5. `docs/design-docs/recurring-workflow-control-plane.md`
6. `docs/design-docs/workflow-factory-frontend-control-plane.md`
7. `docs/design-docs/frontend-control-plane-figma-implementation.md`
8. `docs/design-docs/current-feature-inventory.md`

Historical plans, validation notes, and retired design drafts live under `docs/archive/`. Archived files are evidence, not active requirements.

## 1. Core Philosophy

1. Agent is the engine. Declarative state machine spec is the rail. Human operator is the high-risk gate.
2. The system must carry non-deterministic intelligence on deterministic rails.
3. Fail closed. If policy, evidence, schema, budget, or state is unclear, route to `awaiting_operator`.
4. Do not build a God Agent that owns global control flow.

## 2. Role Boundaries

1. Watcher may read signals, logs, metrics, webhooks and schedules.
2. Watcher may create or update `RequirementCandidate`, `Requirement`, error fingerprints, notification events, and run history.
3. Watcher must not write code, patch files, move funds, deploy, approve gates, or publish external content.
4. Planner Sweep is stateless. It reads active Operating Manifest and aggregate progress, then creates `RequirementCandidate` records only.
5. Planner must not directly create official requirements unless the candidate was operator-approved and explicitly materialized.
6. Agent Atom may reason, diagnose, draft, patch, summarize, or recommend through structured output.
7. Agent Atom must not mutate workflow state directly.
8. Deterministic Runner owns state transitions, retry budget, terminal state, evidence persistence, and human gate routing.
9. Oracle is the operator-facing control plane. Agents may recommend approval decisions but must not write final approval status.

## 3. Workflow Constraints

1. Complex workflow control flow must be represented as declarative state machine spec.
2. New complex flows must not be hidden inside long Python `if/else` orchestration.
3. Built-in Python specs are acceptable only as implementation detail while the YAML/spec loader matures; the behavior must still be inspectable as a state machine.
4. Every loop must have a retry budget, terminal state, and operator fallback.
5. Verification must be independent from execution.
6. Execution self-repair must stay in the same workflow run/session and stop after budget exhaustion.
7. Raw agent output must be persisted as artifact; downstream deterministic atoms may only trust parsed/schema-valid payload.
8. Legacy `/api/tasks`, `/api/approvals`, fixed-step orchestrator, and old task runner are retired. Do not reintroduce TaskBoard-style execution or fixed `workflow_steps` as product behavior.

## 4. Planning Lifecycle Constraints

1. There must be exactly one active Operating Manifest, represented by `active_slot="global"`.
2. Goals only use `active | achieved | dropped`.
3. `goal_key` is stable lineage and must flow through goal-derived candidates, requirements, workflow runs, and release records.
4. Do not make Planner a long-lived PM agent. Rollups must be computed from database lineage.
5. Dropped goals must not generate new candidates.
6. Drop Goal means stop future investment and safe-halt unfinished work.
7. Drop Goal never triggers rollback, revert, database deletion, unpublish, or delivered release mutation.
8. Decommissioning delivered functionality is a new requirement with normal workflow, verification, human gate, and release.
9. Planning UI is goal-centric. Do not reintroduce flat Manifest JSON plus detached Candidate queue as the primary surface.

## 5. Human Gate And Kill-Switch Constraints

These actions always require a human gate:

1. Production deploy.
2. Funds movement, refund, withdrawal, settlement, ledger, vault, or USDC transfer.
3. Settlement logic change.
4. Smart contract interaction or contract change.
5. Auth, credential, permission, or secret changes.
6. External paid spend.
7. Self-modifying system deployment.
8. Any action above the active manifest budget threshold.

High evidence does not bypass high risk.

## 6. Observability Constraints

1. Every background loop, recurring workflow, scheduler, dispatcher, retry, and queue must be visible in Ops Console.
2. Every automation run must write run history, status, inputs, result, error excerpt, started/completed timestamps, and duration.
3. Do not send ordinary state transitions, atom success, artifacts, or blackboard snapshots to Lark.
4. P0/P1 interruption goes to alert. Human gate goes to approval. PR/release goes to release. Workflow summary goes to workflow notification.
5. Notification suppression and requirement materialization suppression are separate systems.

## 7. Frontend Constraints

1. Frontend is a Human-Agent Control Plane, not a mosaic of equal white cards or a CRUD admin clone.
2. Dangerous actions must use explicit confirmation UI, not browser-native `alert` or `confirm`.
3. Pages must explain purpose, inputs, outputs, evidence, current state, and next action.
4. Raw JSON belongs in debug views, not the default operator path.
5. Figma/Stitch prototypes define the current visual direction: dark cockpit, restrained density, machine-readable evidence, and clear Human Oracle gates.
6. Workflow detail must expose Agent outputs, command evidence, file changes, blackboard summaries, delivery status, and pending human gates.
7. Factory pages are read-only until workflow spec versioning, schema validation, sandbox execution, and human approval are production-ready.

## 8. When In Doubt

1. Prefer smaller deterministic control surfaces over stronger autonomous agents.
2. Prefer candidate buffers over direct side effects.
3. Prefer human gate over silent automation for high-risk paths.
4. Prefer docs + tests + observable evidence over prose-only policy.
