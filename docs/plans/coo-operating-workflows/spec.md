# Spec

## Goal

Make `Synapse-Network-Growing` behave like the COO system of an AI-native company:

1. work enters through stable intake channels instead of ad-hoc chat
2. roles own recurring responsibilities instead of only one-off prompts
3. daily and weekly operating rhythms continuously generate, route, execute, and review requirements
4. humans stay at goal-setting, boundary-setting, budget, and exception handling
5. requirement approval stays separate from workflow execution state

## Core Design

### 1. Requirement Pool As Company Backlog

The requirement pool should become the single operating backlog for:

1. strategic goals entered by operator / CEO / CTO
2. optimization signals derived from runtime evidence
3. incident recovery follow-ups
4. company review recommendations and bundles
5. onboarding / governance / policy gaps

The pool should not depend on manual creation alone.

Every requirement should also carry an execution-approval contract:

1. who must approve before autonomous execution starts
2. whether the system may auto-approve low-risk work
3. when the requester / operator must be pulled back in

Every requirement should also keep a first-class source contract:

1. `source`
2. `source_ref`
3. `intake_metadata`

The source contract is not only for display. It is later used to decide:

1. approval routing
2. validation strictness
3. default priority posture
4. whether the system may auto-intake or auto-approve
5. how company review attributes requirement creation back to upstream operations

### 2. Agent Roles As Jobs, Not Personas Only

Each role should define:

1. mission
2. input signals
3. owned workflow steps
4. expected outputs
5. decision rights
6. handoff rules
7. success metrics

Recommended base role families:

1. intake and triage
2. planning and research
3. execution
4. review and validation
5. portfolio and operator support

### 3. Workflow Families

The COO system should run five workflow families.

#### A. Morning Intake Workflow

Purpose:

1. refresh optimization signals
2. refresh company review state
3. identify top candidates for intake
4. auto-create requirement drafts when confidence is high

Primary roles:

1. `ops_intake_manager`
2. `signal_analyst`

#### B. Requirement Planning Workflow

Purpose:

1. convert new requirements into executable step graphs
2. assign complexity tiers, budgets, and escalation rules
3. propose affected projects and expected outputs

Primary roles:

1. `planner`
2. `researcher`
3. `solution_architect`

#### C. Execution Workflow

Purpose:

1. implement the requirement
2. validate based on real changed projects
3. package delivery / PR / publish readiness and close or escalate

Primary roles:

1. `executor`
2. `validator`
3. `delivery_operator`

#### D. Incident Recovery Workflow

Purpose:

1. detect incidents from runtime, validation, delivery, or governance artifacts
2. generate recovery requirements
3. stabilize or escalate the affected path

Primary roles:

1. `incident_commander`
2. `runtime_reliability_engineer`

#### E. Weekly Operating Review Workflow

Purpose:

1. summarize completion, cost, gates, escalations, and incidents
2. generate next-cycle recommendations and bundle items
3. identify automation opportunities and budget posture

Primary roles:

1. `portfolio_operator`
2. `company_reviewer`

### 4. Operating Rhythm

#### Daily

1. morning intake sweep
2. scheduler dispatch loop
3. closeout / compact / summary sweep

#### Weekly

1. cycle planning review
2. mid-week budget and blocker review
3. weekly operating review and next-cycle bundle generation

#### Event-Driven

1. incident detected
2. publish blocked
3. budget exceeded
4. repeated human gate hotspot
5. stale or stuck requirement

## Design Boundaries

### Harness Decides

1. project scope
2. capability matrix
3. interrupt policy
4. budget guardrails
5. approval gates
6. delivery safety

Harness should decide whether a requirement may start automatically, but it should not decide the content of the implementation plan.

### Approval Router Decides

Before a requirement enters execution, the system should run an approval router.

The router is deterministic and evaluates:

1. requirement source and source_ref
2. target project count
3. complexity tier
4. budget cap and estimated spend
5. incident or bug recovery flags
6. publish / delivery impact

The router outputs:

1. `approval_source`
   1. `auto`
   2. `agent`
   3. `human`
   4. `waived`
2. `approval_recommendation`
3. `required_approver_roles`
4. whether a human gate is mandatory

This keeps policy deterministic while still allowing agent help.

### Agent Approval Layer

The system should support agent-assisted approval without making approval fully free-form.

An approval agent or approval roles should:

1. evaluate whether the requirement is sufficiently specified
2. confirm that execution inputs are complete
3. judge whether the requirement is low-risk enough for autonomous execution
4. recommend one of:
   1. `approve`
   2. `revise`
   3. `route_to_human`

The agent layer should not replace hard rules.

Hard rules still force human review for:

1. multi-project high-risk work
2. publish or production-impacting work
3. critical incidents
4. over-budget or max-tier execution
5. cross-project bug recovery

### Model Decides

1. change shape: docs, code, config, or mixed
2. affected projects within allowed project scope
3. step decomposition
4. concrete implementation and validation tactics

Harness must not overfit content decisions.

## Execution Shape

### Default Step Model

The default requirement workflow is now a 5-step, Markdown-first flow:

1. `research`
2. `plan`
3. `implementation`
4. `validate`
5. `closeout`

The controller owns the deterministic flow and only `implementation` is mutating by default.

Additional rules:

1. standalone `synthesis` is merged into `plan`
2. standalone `review` and `test` are merged into `validate`
3. `bugfix` may branch only from `validate`
4. `bugfix` always re-enters `validate` before `closeout`
5. `closeout` only packages delivery evidence, branch/PR state, and publish readiness

### Markdown-First Prompt Contract

Agent-facing execution no longer receives raw template JSON or full contract payloads.

The runtime now sends compact Markdown packets only:

1. `requirement_brief`
2. `step_brief`
3. `validate_brief`
4. `closeout_brief`

The bootstrap brief is emitted once per requirement/session and later steps only receive delta context:

1. current goal
2. allowed actions
3. required output
4. prior handoff summary
5. changed files / unresolved blockers when relevant

Internal JSON remains for persistence, APIs, and deterministic gates only.

### Requirement Family Dedupe

Requirement intake now runs through a family layer before creating new work.

Rules:

1. every intake item gets a `family_key` and `family_category`
2. only one active requirement is allowed per family
3. duplicate signals reuse the existing active requirement instead of creating a new one
4. validation-only experiment requirements may be soft-archived automatically by cleanup sweep
5. real bug / incident / release families are merged or reopened, not hard-deleted

This keeps the requirement pool from exploding with the same class of issue.

## Target State

### Requirement Sources

The system should continuously generate requirements from:

1. `manual`
2. `optimization_signal`
3. `incident_followup`
4. `company_review_bundle`
5. `project_onboarding_gap`

### Role Operating Contract

Every role should eventually expose:

1. `role_id`
2. `mission`
3. `input_channels`
4. `workflow_ownership`
5. `handoff_targets`
6. `success_metrics`

Approval-capable roles should also expose:

1. `approval_ownership`
2. `approval_scope`
3. `approval_escalation_targets`
4. `approval_evidence_expectations`

Recommended approval roles:

1. `request_owner`
2. `reviewer`
3. `tester`
4. `portfolio_operator`
5. domain owner roles for special projects

### Requirement Source Registry

The source registry should be explicit and queryable.

Recommended source keys:

1. `manual`
2. `optimization_signal`
3. `incident_followup`
4. `company_review_bundle`
5. `automation_candidate`
6. `bug_intake`
7. `project_onboarding_gap`

Each source definition should declare:

1. intake trigger
2. default priority
3. dedupe scope
4. approval default
5. validation default
6. whether auto materialization is allowed

### Workflow Automation Contract

Every recurring workflow should define:

1. trigger type: scheduled or event-driven
2. owner role
3. input queries / sources
4. output artifact or requirement creation behavior
5. escalation rule
6. validation signal

## Non-Goals

This phase does not require:

1. full autonomous company operation without operator review
2. real-time bidding across all model vendors
3. replacing the requirement workflow with free-form agent swarms

## Detailed Approval Operating Model

### Requirement Approval State

Requirement approval should remain independent from workflow execution status.

Recommended approval states:

1. `pending_approval`
2. `approved`
3. `rejected`
4. `waived`

Recommended review signals:

1. `approval_source`
2. `approval_recommendation`
3. `approval_reason`
4. `approval_decided_by`
5. `approval_decided_at`

### Approval Contract

Every requirement should carry an approval contract with:

1. `approval_mode`
   1. `auto_or_human`
   2. `manual_required`
   3. `waived`
2. `required_approver_roles`
3. `fallback_reviewer`
4. `auto_approve`
   1. `max_priority`
   2. `max_complexity_tier`
   3. `single_project_only`
   4. `allow_incident_recovery`
5. `agent_review`
   1. `enabled`
   2. `approval_role`
   3. `route_to_human_on_low_confidence`
   4. `minimum_confidence`

### Approval Decision Flow

The expected approval flow should be:

1. requirement created with source contract
2. approval router evaluates deterministic risk
3. if low-risk and allowed, system auto-approves
4. otherwise, approval agent/roles review and emit recommendation
5. if still ambiguous or policy requires it, human approval is created
6. only `approved / waived` requirements may auto-plan and auto-start

### Why This Split Matters

This design keeps each layer narrow:

1. source contract explains where the requirement came from
2. approval router applies hard policy
3. approval agent helps reduce human workload
4. human approval handles expensive or risky branches

Without this split:

1. low-risk work creates too much manual approval load
2. high-risk work can be over-delegated to the model
3. company review cannot explain why requirements were allowed to run
