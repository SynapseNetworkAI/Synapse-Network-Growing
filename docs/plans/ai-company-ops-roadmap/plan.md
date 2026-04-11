---
created_at: 2026-04-11
updated_at: 2026-04-11
doc_status: active
---

# Execution Plan — AI Company Ops Roadmap

## Scope

Translate the roadmap into the next-stage requirement pool for `Synapse-Network-Growing`.

Execution order:

1. ship P0 first because without policy, validation discipline, and safe delivery, large-scale autonomy is fragile
2. ship P1 second so the system can optimize based on outcomes instead of intuition
3. ship P2 after P0 and P1 signals are trustworthy enough to drive portfolio-level automation

## P0 — Safe Autonomy Foundation

### P0-R1: Project Policy Registry

- **Goal**: Every managed repository has a machine-readable policy contract.
- **Why now**: Multi-project execution already exists, but project-level write, approval, and release boundaries are not explicit enough.
- **Implementation**
  - Add a project policy model and storage layer for repo metadata, writable paths, forbidden paths, required checks, and release permissions.
  - Expose policy read/write APIs and a dashboard view so operators can audit each project’s automation boundary.
  - Make workflow planning and execution load the project policy before running steps.
- **Validation**
  - Create one permissive project policy and one restrictive policy.
  - Verify planning succeeds only when the target scope is allowed.
  - Verify forbidden writes or release actions are blocked with explicit operator-facing reasons.
- **Automated tests**
  - Backend unit tests for policy parsing and path matching.
  - API tests for create/read/update of project policy records.
  - Integration tests that attempt disallowed writes and assert rejection.
  - Frontend tests for policy rendering and editing flows.

### P0-R2: Delivery Contract And Release Gate

- **Goal**: Requirement runs must follow a standard ship path: branch, validation, review surface, publish decision, rollback path.
- **Why now**: The system can modify target repositories, but safe large-scale delivery requires an explicit delivery contract.
- **Implementation**
  - Extend requirement/workflow metadata with delivery mode, branch strategy, mandatory checks, publish policy, and rollback hint.
  - Add release-state artifacts so every workflow records what was changed, what was validated, and why it can or cannot be promoted.
  - Integrate GitHub-facing publish steps behind policy checks instead of letting them be ad hoc.
- **Validation**
  - Run a requirement against a target repo with publish disabled and verify the workflow stops at review-ready.
  - Run another with publish allowed and verify the release gate enforces required checks before promotion.
- **Automated tests**
  - Backend tests for delivery-state transitions.
  - Mocked Git/GitHub workflow tests for blocked vs allowed publish paths.
  - Frontend tests for release-state badges and operator actions.

### P0-R3: Verification Contract And Bugfix Loop Hardening

- **Goal**: Every requirement must carry an explicit validation plan and automatically enter bugfix when checks fail.
- **Why now**: The repository already supports bugfix loops, but they need to become a mandatory delivery protocol for all roadmap work.
- **Implementation**
  - Add structured validation-plan artifacts at planning time.
  - Require each workflow to declare automated checks, manual checks, and bugfix ownership before execution.
  - Add richer bug records so failures can be grouped by project, requirement, workflow step, and verification type.
- **Validation**
  - Seed a failing requirement and verify the system creates bugfix work automatically.
  - Verify the requirement cannot close until the failing automated checks pass.
- **Automated tests**
  - API tests for validation-plan generation and enforcement.
  - Orchestrator tests for bugfix creation, re-run sequencing, and closeout gating.
  - Browser E2E that demonstrates a visible failure → bugfix → pass loop.

### P0-R4: Project Onboarding Pack

- **Goal**: New repositories can be enrolled into the system with policy, context, verification, and memory hooks in one bundle.
- **Why now**: Cross-project support exists informally, but not as a repeatable onboarding workflow.
- **Implementation**
  - Create a project-onboarding wizard or manifest flow covering repo path, docs entrypoints, validation commands, policy defaults, and Agents-Memory naming.
  - Persist onboarding health and missing prerequisites.
  - Add a standard “project readiness” checklist visible in the control plane.
- **Validation**
  - Onboard one existing project and one intentionally incomplete project.
  - Verify missing docs/tests/policy show up as readiness gaps.
- **Automated tests**
  - Backend tests for onboarding manifest validation.
  - Frontend tests for readiness checklist rendering.

## P1 — Measurable Optimization Layer

### P1-R1: Outcome Scorecards

- **Goal**: Track whether the system is improving the business and engineering system, not just completing tasks.
- **Implementation**
  - Add project scorecards for lead time, validation pass rate, bugfix rate, publish latency, reopened work, and automation coverage.
  - Store snapshots so trends can be compared over time.
  - Surface scorecards in the dashboard per project and at org level.
- **Validation**
  - Simulate workflows with pass/fail mixes and confirm scorecards update deterministically.
- **Automated tests**
  - Aggregation tests for metric correctness.
  - API tests for scorecard queries.
  - Frontend tests for scorecard widgets.

### P1-R2: Optimization Signal Ingestion

- **Goal**: Convert observed defects, repeated failures, manual overrides, and coordination friction into structured optimization candidates.
- **Implementation**
  - Add ingestion pipelines from task logs, bug records, memory records, and workflow anomalies.
  - Normalize them into “optimization signals” with source, severity, confidence, and affected project.
  - Build a signal review panel that can turn signals into requirements.
- **Validation**
  - Generate repeated failure events and confirm they produce deduplicated optimization signals.
- **Automated tests**
  - Signal normalization tests.
  - Deduplication tests.
  - UI tests for signal-to-requirement creation.

### P1-R3: Requirement Scoring v2

- **Goal**: Rank optimization work using impact, risk, confidence, urgency, and implementation cost.
- **Implementation**
  - Extend requirement scoring inputs beyond priority and age.
  - Include project scorecard gaps, bug frequency, failed validation history, and manual escalation frequency.
  - Show score breakdown in the requirement pool UI.
- **Validation**
  - Create competing requirements with different signals and verify ordering matches the scoring model.
- **Automated tests**
  - Backend scoring tests for weighted ranking.
  - Frontend tests for score explanation display.

### P1-R4: Optimization Requirement Templates

- **Goal**: Standardize how the system creates requirements for code quality, process quality, release safety, and growth opportunities.
- **Implementation**
  - Add requirement templates for defect reduction, test coverage gaps, onboarding friction, release bottlenecks, and docs drift.
  - Let signals or operators instantiate requirements from templates with machine-readable acceptance criteria.
- **Validation**
  - Create one requirement from each template type and verify the planner receives structured acceptance data.
- **Automated tests**
  - API tests for template-driven requirement creation.
  - Planner tests for template payload normalization.

## P2 — Portfolio Autopilot

### P2-R1: Multi-Project Scheduler

- **Goal**: Schedule work across repositories by value, urgency, and available agent capacity.
- **Implementation**
  - Add portfolio-level queues and scheduling rules.
  - Support capacity windows, project-level quotas, and emergency overrides.
  - Expose why a requirement was started, delayed, or preempted.
- **Validation**
  - Simulate competing high-priority and low-priority requirements across repos and verify ordering decisions.
- **Automated tests**
  - Scheduler tests for quota, priority, and preemption behavior.

### P2-R2: Autopilot Policy Modes

- **Goal**: Let each project choose how autonomous it wants the system to be.
- **Implementation**
  - Add modes such as `observe`, `recommend`, `execute_with_approval`, and `execute_autonomously`.
  - Bind these modes to allowed actions, approval gates, and publish permissions.
- **Validation**
  - Verify the same requirement behaves differently under each autonomy mode.
- **Automated tests**
  - Policy-mode enforcement tests across planning, execution, and release phases.

### P2-R3: Company-Level Operating Review

- **Goal**: Replace manual status sync with a persistent operating review generated from live system data.
- **Implementation**
  - Create org-level review artifacts summarizing blocked work, scorecard trends, incidents, and highest-leverage optimizations.
  - Generate a recommended next requirement set for the following cycle.
- **Validation**
  - Feed mixed project data and verify the operating review highlights the correct bottlenecks.
- **Automated tests**
  - Aggregation tests for review generation.
  - UI tests for org review presentation.

## Delivery Protocol For Every Requirement In This Roadmap

For each roadmap requirement, the implementation lifecycle must be:

1. create or update the requirement in the pool
2. produce a structured implementation plan
3. define automated and manual validation before execution starts
4. implement the feature
5. run automated tests
6. run browser or operator validation when needed
7. if any check fails, record the defect in `docs/test/bugfix.md`
8. create or continue the bugfix loop until the validation plan passes
9. only then mark the requirement complete

## Recommended Immediate Execution Order

1. P0-R1 `Project Policy Registry`
2. P0-R3 `Verification Contract And Bugfix Loop Hardening`
3. P0-R2 `Delivery Contract And Release Gate`
4. P0-R4 `Project Onboarding Pack`
5. P1-R1 `Outcome Scorecards`
6. P1-R2 `Optimization Signal Ingestion`
7. P1-R3 `Requirement Scoring v2`
8. P1-R4 `Optimization Requirement Templates`
9. P2-R1 `Multi-Project Scheduler`
10. P2-R2 `Autopilot Policy Modes`
11. P2-R3 `Company-Level Operating Review`
