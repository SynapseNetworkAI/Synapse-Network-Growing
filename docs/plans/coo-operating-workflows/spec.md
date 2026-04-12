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
2. review and validate based on real changed projects
3. close, publish, or escalate

Primary roles:

1. `executor`
2. `reviewer`
3. `tester`

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

### Model Decides

1. change shape: docs, code, config, or mixed
2. affected projects within allowed project scope
3. step decomposition
4. concrete implementation and validation tactics

Harness must not overfit content decisions.

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
