---
id: ops-console-page-map-and-e2e-validation
title: Ops Console Page Map and E2E Validation
role: dev_rel
status: ready
created_at: 2026-04-19
updated_at: 2026-04-19
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing
---

# Ops Console Page Map and E2E Validation

This document is the operator-facing map for `http://localhost:9700/`.

The console must prove the current Company Ops design can run end to end:

```text
Operating Manifest
-> Planner Sweep
-> RequirementCandidate
-> Requirement
-> Declarative Workflow Run
-> Atom Invocations + Evidence
-> Human Gate / Release / Done
```

The console is not a database object browser. Each page must explain what it is for, what it reads, what it writes, and what the operator should do next.

## Page Map

| Page | Purpose | Primary inputs | Primary outputs | Source of truth | Next action |
|---|---|---|---|---|---|
| `/command-center` | Global Human-Agent control plane | Dashboard stats, workflow summary, active manifest, scheduler health | Desired state summary, blockers, active fronts, next operator action | `requirements`, `workflow_runs`, `operating_manifests`, scheduler health projections | Open Planning, Gates, or Workflow Operations |
| `/intake` | Requirement discovery entry point | Error, watcher, forum, planner signal sources | Signal routing map and links to concrete queues | `error_fingerprints`, `requirement_intake_fingerprints`, `requirement_candidates` | Open errors, planning, or schedules |
| `/gates` | Human Oracle queue | Pending human gates and failed workflows | High-risk decisions with evidence links | `human_gate_requests`, `workflow_runs` | Review gate in `/workflows/:id` |
| `/requirements` | Requirement pool and workflow readiness queue | Requirement filters, new requirement form, project selection | Requirement rows with workflow status and actions | `requirements`, active `workflow_runs` | Create, edit, submit, or open workflow |
| `/requirements/:id` | Requirement detail and workflow readiness | Requirement id, acceptance, workflow assets | Workflow readiness, generated acceptance/plan, active workflow link | `requirements`, workflow readiness projection | Generate/start workflow or inspect active run |
| `/planning` | Goal-centric Mission Control | Active Operating Manifest, goals, budgets, Planner Sweep | RequirementCandidates grouped under goals | `operating_manifests`, `requirement_candidates` | Run sweep, approve-and-run/reject/stage candidate, drop goal |
| `/workflows` | Workflow Operations Center | Workflow filters, tab selection | Active, human-gated, failed, completed, archived runs and definitions | `workflow_runs`, `atom_invocations`, `workflow_artifacts`, `human_gate_requests` | Inspect run, process gate, archive completed run |
| `/workflows/:id` | Explainable Step Workbench | Workflow run id | Outcome, step inputs/outputs, evidence, gates, debug payload | Workflow run detail projection | Open PR, review gate, create follow-up, inspect failure |
| `/schedules` | Scheduled Jobs Control Plane | Registry, health, run-now/dry-run controls | Run history, dispatcher health, scheduler status | `recurring_workflows`, `recurring_workflow_runs`, notification queue health | Dry run, run now, inspect failed background task |
| `/releases` | Release candidate queue, Release Task management, and successful Online Records | Release filters, Release Task form, PR gate state, online record filters | Requirement release readiness, PR/deploy state, manual/requirement-flow Release Tasks, successful DeploymentRecord ledger | `release_records`, `release_tasks`, `deployment_records`, validation records | Open release detail, submit PR, inspect task details, deploy staging after PR checks, inspect successful deployment evidence |
| `/releases/:requirementId` | Release detail and delivery control | Requirement id, release action notes | Branch, PR, deploy, rollback records | `release_records`, `deployment_records` | Prepare branch, open PR, deploy, rollback |
| `/publishing` | Human-reviewed official social publishing | Operator prompt, product marketing context, social-content skill, account projection, content policy result | Codex-generated X title/body drafts, approved X posts, failed publish root cause, publish event history | `social_accounts`, `social_post_drafts`, `social_publish_events` | Generate draft, edit/reject, explicitly publish to X |
| `/publishing/trends` | X trend radar result search | Date range, keyword, source kind, author handle | Paginated trend results and centered source detail Modal | `social_trend_items` from `x_social_trend_radar_sweep` | Inspect source, distinguish X original posts from local seeds |
| `/projects` | Project registry | Project filters and create/edit actions | Active project and delivery policy rows | `projects`, `project_policies` | Create/edit project, open project detail |
| `/projects/:id` | Project and policy detail | Project id | Project metadata, GitHub/deploy policy | `projects`, `project_policies` | Save project or governance policy |
| `/errors` | Error fingerprint queue | Error filters and search | Fingerprints linked to requirements/workflows | `error_fingerprints`, `requirement_intake_fingerprints` | Inspect error detail or linked workflow |
| `/errors/:fingerprintKey` | Error evidence and notification history | Fingerprint key | Error events, linked requirement/workflow, notification delivery history | `error_events`, `notification_deliveries` | Open linked requirement/workflow or inspect suppression |
| `/factory/workflows` | Read-only workflow factory | Workflow definitions | State machine specs, states, transitions, limits, risk policy | workflow definitions projection | Inspect states or copy spec |
| `/factory/atoms` | Read-only atom registry | Workflow definitions | Agent/deterministic/terminal atom catalog | workflow definition states | Inspect where an atom is used |
| `/knowledge` | Knowledge and SOP entry point | Workflow evidence and future SOP ledger | Artifacts/SOP direction and workflow evidence links | `workflow_artifacts`, future SOP ledger | Open workflow evidence or build SOP rules |
| `/system/notifications` | Notification queue observability | Dispatcher health | Queue, dead letter, open fingerprint status | notification queue health projection | Inspect notification health or schedules |

## Page Test Matrix

Every page needs three levels of validation:

1. Render smoke: page loads with representative API data.
2. Click behavior: primary buttons, tabs, filters, drawers, and links work.
3. Data proof: API or DB state changes match the visible UI.

| Page | Render smoke | Click checks | Data proof |
|---|---|---|---|
| `/command-center` | Stats, active goals, blockers, scheduler health render | Planning/Gates/Workflow links | Values come from stats, workflow summary, planning mission control |
| `/intake` | Signal source cards render | Errors/Planning/Schedules links | Concrete queues remain source-specific |
| `/gates` | Pending gate and failed run cards render | Review Gate opens workflow detail | Pending gates match workflow run summaries |
| `/requirements` | Requirement list and empty state render | New requirement, edit drawer, refresh, workflow link | Created requirement exists and selected project id persists |
| `/requirements/:id` | Workflow readiness panel renders | Generate assets, start workflow, navigate to `/workflows/:id` | Requirement `active_workflow_run_id` is set |
| `/planning` | Mission Control, goal lanes, history/debug tabs render | Run Planner Sweep, approve-and-run/reject/stage candidate, raw drawer, history tab | Candidate, requirement and workflow inherit `manifest_id` and `goal_key` |
| `/workflows` | Stats, filters, tabs and definitions render | Active/Needs Human/Failed/Completed/Archived/Definitions tabs | Completed run appears in completed tab and can be archived |
| `/workflows/:id` | Overview and step rail render | Steps/Evidence/Gates/Debug tabs, human gate decision | Step artifacts, events and atom invocations exist |
| `/schedules` | Health cards, registry and run history render | Dry Run, Run Now confirmation, select workflow | Run history row is created with dry-run/result payload |
| `/releases` | Release candidates render | Filters, open detail link | Release candidate links to requirement/workflow |
| `/releases/:requirementId` | Release state and validation render | Prepare branch, open PR, deploy buttons, rollback prompt | Release/deployment rows update or return guarded errors |
| `/publishing` | X account drafts render | Generate from prompt, edit, reject, publish confirmation | Real Codex E2E proves generated body is not prompt-copy; publish requires approved status and records external post id or bounded failure |
| `/publishing/trends` | Trend result filters and list render | Search, source kind filter, author filter, pagination, centered detail Modal | Query API returns only matching `social_trend_items`; local seeds show non-repost guidance |
| `/projects` | Project table renders | Create/edit/open detail | Project and policy persist |
| `/projects/:id` | Project form and policy form render | Save project, save governance | `projects` and `project_policies` update |
| `/errors` | Fingerprint table renders | Filters, open linked requirement/workflow | Linked requirement/workflow ids match fingerprint |
| `/errors/:fingerprintKey` | Evidence, linked objects, notifications render | Back, open requirement, open workflow | Notification and intake suppression state is visible |
| `/factory/workflows` | Definition registry and selected state machine render | Select definition, copy spec | Definitions API returns selected workflow states |
| `/factory/atoms` | Atom catalog renders | Type filters work | Atom list derives from workflow definition states |
| `/knowledge` | Knowledge entry point renders | Workflow evidence link works | Artifacts remain attached to workflow runs |
| `/system/notifications` | Dispatcher cards render | Refresh works | Values come from recurring workflow health |

## Requirement Lifecycle Guardrails

Requirement states are intentionally separate from workflow and release states. The current canonical states are:

```text
draft
planning
ready
executing / running
awaiting_operator
delivery_ready / ready_for_merge
completed / done
failed / blocked / needs_revision
cancelled
deleted
```

Lifecycle actions:

1. `Close Requirement`
   Moves a pre-workflow requirement to `cancelled`. Closed requirements are read-only and cannot be submitted, regenerated, started as workflow runs, or routed to human gates.
2. `Delete Requirement`
   Soft-deletes a pre-workflow requirement to `deleted`. Deleted requirements are hidden from the default requirement list, visible only through the `deleted` status filter, and cannot enter approval, workflow, human gate, or release paths.
3. Requirements with workflow history are not deleted from the requirement pool. The operator must resolve, pause, retry, or stop the linked workflow in `/workflows/:id`.

Tests for `/requirements` and `/requirements/:id` must verify that `cancelled` and `deleted` rows expose only the `view` action and that backend workflow-start endpoints reject them.

## GoalB E2E Scenario

GoalB is the product-level proof that Growing can discover a goal, split it into a candidate, materialize it into a requirement, and execute it through the new workflow engine.

Goal payload:

```json
{
  "goal_key": "goalb",
  "domain": "ops",
  "status": "active",
  "intent": "验证 Growing 可以根据目标自动拆分任务，转成正式需求，并由 declarative workflow 自动执行跑通。",
  "success_metric": "goalb_demo_workflow_completed == true",
  "workflow_key": "gateway_reliability_repair",
  "project_key": "synapse-network-growing",
  "priority": "normal",
  "risk_level": "normal",
  "weight": 0.1
}
```

Expected chain:

```text
PUT /api/planning/manifest/active
-> POST /api/planning/sweeps/run
-> POST /api/planning/candidates/{id}/approve-and-run
-> GET /api/workflows/runs?tab=completed
```

Required lineage proof:

1. `operating_manifests.payload_json` contains `goalb`.
2. `requirement_candidates.goal_key = "goalb"`.
3. `requirements.goal_key = "goalb"` and `requirement_candidate_id` is set.
4. `workflow_runs.goal_key = "goalb"` and `requirement_id` matches the materialized requirement.
5. `workflow_state_events`, `atom_invocations`, and `workflow_artifacts` contain records for the workflow run.

## Dogfood Evidence Protocol

Use `$dogfood` and `agent-browser` for product-level proof. Do not send real Lark alerts, do not deploy production, and do not depend on a real external PR.

Output directory:

```text
dogfood-output/ops-console-goalb-20260419/
```

Required screenshots:

1. `01-requirements.png`
2. `02-planning-goalb-lane.png`
3. `03-goalb-candidate-approved.png`
4. `04-goalb-requirement-created.png`
5. `05-workflow-run-detail.png`
6. `06-workflows-completed-tab.png`
7. `07-db-verification.png`

Curated evidence should be copied to:

```text
docs/archive/evidence/ops-console-goalb-20260419/screenshots/
```

Current curated screenshots:

Report: [GoalB dogfood report](archive/evidence/ops-console-goalb-20260419/report.md)

1. [Requirement list](archive/evidence/ops-console-goalb-20260419/screenshots/01-requirements.png)
2. [Planning GoalB lane](archive/evidence/ops-console-goalb-20260419/screenshots/02-planning-goalb-lane.png)
3. [GoalB candidate materialized](archive/evidence/ops-console-goalb-20260419/screenshots/03-goalb-candidate-approved.png)
4. [GoalB requirement detail](archive/evidence/ops-console-goalb-20260419/screenshots/04-goalb-requirement-created.png)
5. [Workflow run detail](archive/evidence/ops-console-goalb-20260419/screenshots/05-workflow-run-detail.png)
6. [Completed workflow tab](archive/evidence/ops-console-goalb-20260419/screenshots/06-workflows-completed-tab.png)
7. [DB verification](archive/evidence/ops-console-goalb-20260419/screenshots/07-db-verification.png)

The dogfood report must include:

1. Target URL.
2. Environment flags proving external side effects were disabled.
3. Reproduction steps with screenshot links.
4. Browser console and network errors.
5. GoalB DB lineage summary.
6. Final verdict: `passed`, `failed`, or `inconclusive`.

## Verification Commands

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python -m pytest -q \
  tests/test_goalb_product_flow.py \
  tests/test_planning_lifecycle.py \
  tests/test_workflows_api.py

cd dashboard && npm test -- --run
cd dashboard && npm run build
git diff --check
```
