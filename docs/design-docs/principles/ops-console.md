# Ops Console Principles

Load this when touching Ops Console surfaces, planning pages, human gates, workflow details, raw/debug panels, dashboard navigation, decision views, or operator actions.

## Decision-First Console

1. Operator pages show status, reason, and next action before JSON, tables, logs, or object lists.
2. Planning Console must preserve `goal_key` lineage across goal, candidate, requirement, workflow, and release.
3. Candidate approval happens in goal context, not as an isolated global queue.
4. Raw payload, raw JSON, raw artifact, raw manifest, and planner output belong in Debug tabs, details, or centered modals, not the default operation panel.
5. History, archive, and debug data are separate from the current decision surface.
6. Planning priority order: actionable candidates, materialized work, fail-closed intercepts, then rejected/suppressed history.
7. Long PRD, Candidate Markdown, raw planner output, and metadata dumps must not overpower current action.
8. `validation_failed` is planning diagnostic draft, not execution blocker. Show fail-closed reason first; raw agent output stays secondary.
9. Active goals expand first; Achieved and Dropped goals default collapsed. Large history needs local filtering or virtualization.
10. Repeated Planner Fail-Closed errors should aggregate by reason signature.
11. Display times in browser local time and keep UTC for log debugging. Do not hardcode one geography as the only display timezone.

## Human Gate And Workflow Detail

1. Human Gate default view is executive decision board: what happened, root-cause summary, recommendation, and decision buttons.
2. State, resolution, fingerprint, Lark payload, and blackboard JSON belong in Technical details or Debug.
3. Decision buttons must have debounce plus loading/disabled state.
4. `approve` in a failure path must use neutral language such as confirm/release, not "all green".
5. Human Gate decision can wake Runner asynchronously. Without WebSocket, frontend polls workflow detail after decision until it progresses, completes, or blocks again.
6. Workflow Delivery Summary must verify delivery/release status before showing PR, branch, or compare fields.
7. Do not render stale historical branch/PR URLs as trustworthy delivery state.

## Page Testability

1. Every main page needs docs for page responsibility, inputs, outputs, next actions, and evidence location.
2. Page tests must cover primary buttons, tabs, centered modal/dialog, detail navigation, or empty-state explanation; render-only tests are insufficient.
3. Product E2E keeps dogfood evidence: screenshots, reproduction steps, browser console/network notes, and DB lineage summary.
4. Architecture proof should trace `Operating Manifest -> RequirementCandidate -> Requirement -> WorkflowRun -> Evidence`.
5. Tests and dogfood must not trigger real Lark, production publish, funds, auth, contract, or external paid side effects.

## Surface Boundaries

1. Requirement, Execution, and Release each have separate page templates and decision surfaces.
2. `/errors` is stability governance helper only. It links errors to requirement/execution/release but does not become the main control surface.
3. `/command-center` is read-only monitoring and navigation. Product Opportunity create/reject/defer actions belong in `/planning`.
4. `/planning` is operation handling and should expose task board, hierarchy, product opportunities, business goals, engineering queue, unassigned, history/debug.
5. Task Board state is projected from business truth. Do not add drag-to-change that bypasses validation, Human Gate, or deterministic workflow transitions.
