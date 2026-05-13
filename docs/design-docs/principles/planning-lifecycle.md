# Planning Lifecycle Principles

Load this when touching planning, requirements, candidates, goals, workflow definitions, acceptance, validation, or declarative execution.

## Agent And Planner Boundaries

1. Agent decides execution content, research order, implementation path, and needed complexity.
2. The program governs requirements, runtime, stability, orchestration, and release; it must not become an execution-content judge.
3. Planner only chooses execution shape: mode, complexity, validation profile, delivery intent, and approval requirement.
4. Planner must not force ritual research/plan/closeout stages; the formal default remains `intake -> execute -> validate -> deliver`.

## Declarative Workflow Governance

1. Complex workflow may be generated as declarative state-machine YAML, but only from controlled atoms.
2. Agent atoms produce reasoning, diagnostics, content, and structured output; deterministic runners own state transitions.
3. All loops need retry budget, terminal state, and operator fallback.
4. Atom output must be schema-validated; parse failure can self-repair at most once, and raw output must land as artifact.
5. Blackboard stores only final KV needed for continuation; do not write raw artifact maps, long logs, transition history, or state output dumps into `blackboard_json`.
6. Funds, settlement, contracts, auth, production deploy, external paid actions, and official-account publish/delete must enter Human Gate or explicit operator click.

## No Legacy Workflow Compatibility

1. Declarative workflow run is the only truth for new complex execution: workflow definitions, runs, state events, artifacts, blackboard snapshots, atom invocations, and human gates.
2. Do not restore fixed-step orchestrator, old agent-first bugfix loop, old delivery repair loop, or old task runner fallback.
3. Requirement submit creates declarative workflow run; planner selects `workflow_key` and initial blackboard, not fixed research/plan/implementation/validate/closeout steps.
4. Workflow detail defaults to chronological timeline. Raw Blackboard and Raw Artifacts belong in debug details only.
5. Human Gate decision is state-machine input. After decision write, Runner must wake and converge to next state, new gate, or terminal failure.
6. Human Override reduces manual acceptance friction; technical terminal state is not business done unless structured acceptance is confirmed.

## Fail-Closed Acceptance

1. RequirementCandidate cannot materialize without valid `execution_acceptance_steps`.
2. Each acceptance step must declare `required_commands` or allowed `required_evidence_types`; `required_db_lineage` is explanatory only.
3. Acceptance validates business outcome, not just object creation.
4. Missing, vague, invalid, or unparseable acceptance enters validation failure or operator review; do not auto-fill fallback criteria.
5. Planner JSON can repair schema/format errors at most twice; dangerous commands, unknown workflow, or privilege risk fail closed.
6. Planner commands must pass allowlist/denylist. Production, funds, deploy, delete, external network, permission, or destructive commands fail closed.
7. Dashboard E2E can only use controlled project scripts. Do not allow arbitrary `playwright`, `npx`, network, or shell.
8. Planner pytest commands must target explicit files or selectors; recursive full pytest belongs to Final Regression CI runner.
9. Git evidence commands are read-only, such as `git diff --check` and `git diff --stat`.
10. Planner can only select registered workflow definitions.
11. Verification `inconclusive` is not `passed`.
12. `code_delivery` without repository diff fails closed. `verification_only` may no-op only with complete evidence matrix.
13. Supersede retry must carry one-use `context_hint` explaining the previous no-change or bootstrap dead end.
14. Required evidence types are closed vocabulary: `workflow_command_result`, `project_change_summary`, `git_diff_summary`, `frontend_validation_result`, `coverage_report`, `docs_sync_review`, `workflow_agent_raw_output`.
15. Acceptance evidence must belong to the same workflow run. Do not reuse old artifacts across runs.
16. Acceptance commands use deterministic hard timeout. Heartbeat and log activity are diagnostic only.
17. Acceptance failure writes `failure_summary` and becomes next patch context.

## Planning Lifecycle And Goal Governance

1. There is one active Operating Manifest at `active_slot="global"`.
2. Manifest stores budgets, weights, global constraints, and short steering fields; long goal markdown lives on `planning_goals`.
3. Mission-control APIs return compact goal map and excerpts; full goal markdown is loaded per goal.
4. `goal_key` must flow through candidates, requirements, workflow runs, and release records.
5. Planner Sweep is stateless. It reads active manifest and compact progress, then generates candidates.
6. Candidate is a buffer between automated planning and formal requirement pool; operator approval is required before it becomes official unless deterministic policy explicitly allows it.
7. Drop Goal stops future investment and safe-halts unfinished work. It never rolls back, reverts, deletes data, retracts external publication, or changes delivered releases.
8. Decommission and rollback are new requirements or release actions, not implicit side effects of dropping a goal.
9. Risk router decides auto-materialize/start from workflow allowlist, risk level, project policy, and atom risk profile.
10. Product planning sweeps are proposal-only; formal goals are operator-reviewed.
11. Planning Task Board is requirement-first; WorkflowRun, PR, and Release are evidence in card detail, not duplicate main cards.
12. Task Board does not support drag-to-change business state.

## Requirement / Execution / Release Surfaces

1. Requirement owns why, desired result, and constraints. It does not own telemetry, deploy, rollback, or environment panels.
2. Execution owns agent work process, execution graph, validation result, incidents, pause/resume/retry.
3. Release owns branch, commit, PR, delivery readiness, deployment promotion, and rollback.
4. `/errors` is auxiliary stability governance, not a fourth primary business surface.
5. Project is the formal primary object for repository, default branch, deployment strategy, environment labels, and root path.
6. Each requirement has one current execution chain. Retry creates a new run; do not revive completed, failed, or validated runs.
7. Artifacts must serve a consumer. Default evidence set is requirement brief, execution record, validation record, and delivery record.
8. Do not create ritual artifacts for stage completeness.

## Governance Defaults

1. Current feature inventory is maintained in `docs/design-docs/current-feature-inventory.md`.
2. Any formal feature add/delete/refactor updates the current feature inventory.
3. Feature inventory describes real current capability, not candidate ideas, plans, or bugfix drafts.
4. If code changed but feature inventory did not, the design-doc update is incomplete.
5. Autonomy increases only after policy, validation, delivery, incident handling, and observability are closed.
6. When governance is weak, improve governance before adding stronger autonomous decision-making.
7. Default implementation order remains Requirement intent/governance, Execution closure, Release delivery, incident/recovery observability, then more complex deterministic runtime capability.
8. Designs that move the system back toward a giant all-in-one console or fixed multi-stage ritual workflow violate the current architecture.
