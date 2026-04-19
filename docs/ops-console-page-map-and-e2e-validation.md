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
| `/requirements` | Requirement pool and workflow readiness queue | Requirement filters, new requirement form, project selection | Requirement rows with workflow status and actions | `requirements`, active `workflow_runs` | Create, edit, submit, or open workflow |
| `/requirements/:id` | Requirement detail and workflow readiness | Requirement id, acceptance, workflow assets | Workflow readiness, generated acceptance/plan, active workflow link | `requirements`, workflow readiness projection | Generate/start workflow or inspect active run |
| `/planning` | Goal-centric Mission Control | Active Operating Manifest, goals, budgets, Planner Sweep | RequirementCandidates grouped under goals | `operating_manifests`, `requirement_candidates` | Run sweep, approve/reject/materialize candidate, drop goal |
| `/workflows` | Workflow Operations Center | Workflow filters, tab selection | Active, human-gated, failed, completed, archived runs and definitions | `workflow_runs`, `atom_invocations`, `workflow_artifacts`, `human_gate_requests` | Inspect run, process gate, archive completed run |
| `/workflows/:id` | Explainable Step Workbench | Workflow run id | Outcome, step inputs/outputs, evidence, gates, debug payload | Workflow run detail projection | Open PR, review gate, create follow-up, inspect failure |
| `/schedules` | Scheduled Jobs Control Plane | Registry, health, run-now/dry-run controls | Run history, dispatcher health, scheduler status | `recurring_workflows`, `recurring_workflow_runs`, notification queue health | Dry run, run now, inspect failed background task |
| `/releases` | Release candidate queue | Release filters | Requirement release readiness and PR/deploy state | `release_records`, validation/deployment records | Open release detail |
| `/releases/:requirementId` | Release detail and delivery control | Requirement id, release action notes | Branch, PR, deploy, rollback records | `release_records`, `deployment_records` | Prepare branch, open PR, deploy, rollback |
| `/projects` | Project registry | Project filters and create/edit actions | Active project and delivery policy rows | `projects`, `project_policies` | Create/edit project, open project detail |
| `/projects/:id` | Project and policy detail | Project id | Project metadata, GitHub/deploy policy | `projects`, `project_policies` | Save project or governance policy |
| `/errors` | Error fingerprint queue | Error filters and search | Fingerprints linked to requirements/workflows | `error_fingerprints`, `requirement_intake_fingerprints` | Inspect error detail or linked workflow |
| `/errors/:fingerprintKey` | Error evidence and notification history | Fingerprint key | Error events, linked requirement/workflow, notification delivery history | `error_events`, `notification_deliveries` | Open linked requirement/workflow or inspect suppression |

## Page Test Matrix

Every page needs three levels of validation:

1. Render smoke: page loads with representative API data.
2. Click behavior: primary buttons, tabs, filters, drawers, and links work.
3. Data proof: API or DB state changes match the visible UI.

| Page | Render smoke | Click checks | Data proof |
|---|---|---|---|
| `/requirements` | Requirement list and empty state render | New requirement, edit drawer, refresh, workflow link | Created requirement exists and selected project id persists |
| `/requirements/:id` | Workflow readiness panel renders | Generate assets, start workflow, navigate to `/workflows/:id` | Requirement `active_workflow_run_id` is set |
| `/planning` | Mission Control, goal lanes, history/debug tabs render | Run Planner Sweep, approve/reject/materialize candidate, raw drawer, history tab | Candidate and requirement inherit `manifest_id` and `goal_key` |
| `/workflows` | Stats, filters, tabs and definitions render | Active/Needs Human/Failed/Completed/Archived/Definitions tabs | Completed run appears in completed tab and can be archived |
| `/workflows/:id` | Overview and step rail render | Steps/Evidence/Gates/Debug tabs, human gate decision | Step artifacts, events and atom invocations exist |
| `/schedules` | Health cards, registry and run history render | Dry Run, Run Now confirmation, select workflow | Run history row is created with dry-run/result payload |
| `/releases` | Release candidates render | Filters, open detail link | Release candidate links to requirement/workflow |
| `/releases/:requirementId` | Release state and validation render | Prepare branch, open PR, deploy buttons, rollback prompt | Release/deployment rows update or return guarded errors |
| `/projects` | Project table renders | Create/edit/open detail | Project and policy persist |
| `/projects/:id` | Project form and policy form render | Save project, save governance | `projects` and `project_policies` update |
| `/errors` | Fingerprint table renders | Filters, open linked requirement/workflow | Linked requirement/workflow ids match fingerprint |
| `/errors/:fingerprintKey` | Evidence, linked objects, notifications render | Back, open requirement, open workflow | Notification and intake suppression state is visible |

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
-> POST /api/planning/candidates/{id}/approve
-> POST /api/planning/candidates/{id}/materialize
-> POST /api/requirements/{id}/workflow/start
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
