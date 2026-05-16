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

## Navigation Model

The desktop shell uses Top Header Navigation, not persistent secondary navigation rails. The only primary entries are:

```text
Command Center | Planning | Publishing | Releases
```

`Needs Human` is a top-level badge that links to `/gates`. `Cmd+K / Search` is the sanctioned entry for low-frequency pages such as `/requirements`, `/workflows`, `/schedules`, `/projects`, `/errors`, `/factory/workflows`, `/factory/atoms`, and `/knowledge`. These routes remain valid deep links, but they must not reappear as persistent secondary navigation.

## Page Map

| Page | Purpose | Primary inputs | Primary outputs | Source of truth | Next action |
|---|---|---|---|---|---|
| `/command-center` | Read-only Mission Dashboard | Dashboard stats, workflow summary, nested mission board | Active goal card, public-preview traction proof, product/growth/engineering lane summary, unassigned red light, next operator action | `/api/planning/mission-board`, stats and workflow summary projections | Open Planning, Publishing, Releases, or Needs Human |
| `/intake` | Requirement discovery entry point | Error, watcher, forum, planner signal sources | Signal routing map and links to concrete queues | `error_fingerprints`, `requirement_intake_fingerprints`, `requirement_candidates` | Open errors, planning, or schedules |
| `/gates` | Human Oracle queue | Pending human gates and failed workflows | High-risk decisions with evidence links | `human_gate_requests`, `workflow_runs` | Review gate in `/workflows/:id` |
| `/requirements` | Requirement pool and workflow readiness queue | Requirement filters, new requirement form, project selection | Requirement rows with workflow status and actions | `requirements`, active `workflow_runs` | Create, edit, submit, or open workflow |
| `/requirements/:id` | Requirement detail and workflow readiness | Requirement id, acceptance, workflow assets | Workflow readiness, generated acceptance/plan, active workflow link | `requirements`, workflow readiness projection | Generate/start workflow or inspect active run |
| `/planning` | Operational planning queues | Active Operating Manifest, goals, product opportunities, Requirement-first Task Board, Mission Workbench hierarchy, budgets, Planner Sweep | Linear-style Task Board columns, TreeGrid + Stage Rail hierarchy, Product Opportunity review, Business Goals, Engineering Queue, Unassigned active records, History/Debug | `requirements` via `/api/planning/task-board`, plus `operating_manifests`, `planning_goals`, `product_opportunities`, `requirement_candidates`, `/api/planning/mission-workbench` | Open cards by Requirement status, inspect latest WorkflowRun evidence in Modal, create Goal from opportunity, defer/reject opportunity, fix unassigned lineage, run sweep, approve-and-run/reject/stage candidate, drop goal |
| `/workflows` | Workflow Operations Center | Workflow filters, tab selection | Active, human-gated, failed, completed, archived runs and definitions | `workflow_runs`, `atom_invocations`, `workflow_artifacts`, `human_gate_requests` | Inspect run, process gate, archive completed run |
| `/workflows/:id` | Explainable Step Workbench | Workflow run id | Outcome, step inputs/outputs, evidence, gates, debug payload | Workflow run detail projection | Open PR, review gate, create follow-up, inspect failure |
| `/schedules` | Scheduled Jobs Control Plane | Registry, health, run-now/dry-run controls | Run history, dispatcher health, scheduler status | `recurring_workflows`, `recurring_workflow_runs`, notification queue health | Dry run, run now, inspect failed background task |
| `/releases` | Release candidate queue, Release Task management, Cloud Run Jobs publishing, and successful Online Records | Release filters, URL-backed `tab` selection, Release Task form, PR / production gate state, scheduled-job filters, single-job release task form, online record filters | Requirement release readiness, PR/deploy state, manual/requirement-flow Release Tasks, Human-Gated production deploy tasks, two-step Cloud Run Job release tasks, GitHub Actions failed-step excerpts, successful DeploymentRecord ledger | `release_records`, `release_tasks`, `scheduled_job_release_tasks`, linked `deployment_records`, validation records, GitHub Actions run logs when permitted | Open release detail, submit PR, inspect task details, deploy staging after PR checks, create production task after staging success, confirm `YES`, create a scheduled-job release task, sync Actions result, inspect failed Actions root cause, inspect successful deployment evidence |
| `/releases/:requirementId` | Release detail and delivery control | Requirement id, release action notes | Branch, PR, deploy, rollback records | `release_records`, `deployment_records` | Prepare branch, open PR, deploy, rollback |
| `/publishing` | Human-reviewed Social Ops + Developer Distribution Center | Content asset source material, product marketing context, sampled trend/product/metrics signals, tagged source contexts, distribution account registry, canonical URL and platform rules | Grouped asset tasks for X / HN / Reddit / V2EX / DEV / Hashnode, serial platform drafts, task events, manual live/removed records, local metrics summaries, parse/tag failure diagnostics | `social_content_assets`, `social_distribution_tasks`, `social_distribution_events`, `social_distribution_accounts`, `social_trend_items`, `social_watchlist_accounts`, `social_post_metrics` | Run Asset Planner, approve Asset and generate grouped platform tasks in-place, inspect task modal, copy content, mark non-X live/removed, human-gated X task handling, fail closed on invalid Agent JSON or missing `@synapse-context` tags |
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
2. Click behavior: primary buttons, tabs, filters, centered modals, and links work.
3. Data proof: API or DB state changes match the visible UI.

| Page | Render smoke | Click checks | Data proof |
|---|---|---|---|
| `/command-center` | Active goal card, three mission lanes, blockers, unassigned red light render | Planning/Publishing/Releases/Needs Human links; no Create/Reject/Defer actions | Values come from nested `/api/planning/mission-board` and summary projections |
| `/intake` | Signal source cards render | Errors/Planning/Schedules links | Concrete queues remain source-specific |
| `/gates` | Pending gate and failed run cards render | Review Gate opens workflow detail | Pending gates match workflow run summaries |
| `/requirements` | Requirement list and empty state render | New requirement, edit modal, refresh, workflow link | Created requirement exists and selected project id persists |
| `/requirements/:id` | Workflow readiness panel renders | Generate assets, start workflow, navigate to `/workflows/:id` | Requirement `active_workflow_run_id` is set |
| `/planning` | Task Board, Hierarchy, Product Opportunities, Business Goals, Engineering Queue, Unassigned, history/debug tabs render | Open Task Board card Modal, follow Requirement / Workflow links, expand/collapse Goal -> Lane -> Task rows in Hierarchy, create Goal from opportunity, defer/reject opportunity, Run Planner Sweep, approve-and-run/reject/stage candidate, centered modal debug, history tab | Task Board comes from `/api/planning/task-board` with Requirement as primary card; Mission Workbench comes from nested `/api/planning/mission-workbench`; Product Opportunity creates a Goal only after operator action; candidate, requirement and workflow inherit `manifest_id` and `goal_key`; active missing lineage appears in Unassigned |
| `/workflows` | Stats, filters, tabs and definitions render | Active/Needs Human/Failed/Completed/Archived/Definitions tabs | Completed run appears in completed tab and can be archived |
| `/workflows/:id` | Overview and step rail render | Steps/Evidence/Gates/Debug tabs, human gate decision | Step artifacts, events and atom invocations exist |
| `/schedules` | Health cards, registry and run history render | Dry Run, Run Now confirmation, select workflow | Run history row is created with dry-run/result payload |
| `/releases` | Release candidates, Release Tasks, scheduled Cloud Run Jobs, SDK packages and Online Records render | URL-backed tabs survive refresh, filters, open detail modal, scheduled-job create modal selects environment, branch, and job name; requested staging row exposes `发布到 staging`; `admin-front/user-front/docs-front` staging detail can attach a prebuilt `image@sha256` digest; production row exposes `发布到 production` only after main commit has matching staging success; failed deployment detail shows GitHub Actions failed-step excerpt or permission diagnostic | Release candidate links to requirement/workflow; production deploy creates `DeploymentRecord(environment=production, trigger_source=release_task)` and dispatches the service-specific production workflow (`deploy-production-gateway.yml`, `deploy-production-admin.yml`, `deploy-production-frontends.yml`, or Provider `deploy-production-provider.yml`); prebuilt frontend staging deploy passes `prebuilt_image_digest` to `deploy-staging-frontends.yml` so Actions skips Cloud Build and deploys the validated digest; scheduled-job create only writes `scheduled_job_release_tasks(status=requested)`; row publish creates linked `DeploymentRecord(trigger_source=scheduled_job_release)` and dispatches `deploy-staging-jobs.yml`; sync updates records and notes/metadata contain bounded Actions failure detail when GitHub permissions allow log reads |
| `/releases/:requirementId` | Release state and validation render | Prepare branch, open PR, deploy buttons, rollback prompt | Release/deployment rows update or return guarded errors |
| `/publishing` | X account drafts, reply queue, repost candidates, published-effect daily metrics, distribution accounts, and distribution campaigns render | Generate from prompt, edit, reject, publish confirmation, generate reply, reply confirmation, date-filter metrics, page metric rows, open centered metric detail Modal, edit distribution account, create campaign, generate targets, copy title/body, mark live/removed | Real Codex E2E proves generated body is not prompt-copy; reply drafts are generated by `social_reply_agent_v1` with no template fallback; publish/reply/repost require operator confirmation and record external ids or bounded failures; published-effect UI reads local metrics only and does not trigger X read; distribution targets never call external posting APIs and require operator-pasted `published_url` for `live` |
| `/publishing/trends` | Trend result filters and list render | Search, source kind filter, author filter, pagination, centered detail Modal | Query API returns only matching `social_trend_items`; local seeds show non-repost guidance |
| `/projects` | Project table renders, including `Synapse-Network-MCP-Server` | Create project with `owner/repo`, HTTPS git URL, or SSH git URL; open detail | Project and policy persist; source repo is normalized to `owner/repo` and deploy repo remains independent |
| `/projects/:id` | Project form and policy form render | Save project, save governance, preserve current deploy strategy values | `projects` and `project_policies` update; editing deploy repo does not overwrite source GitHub repo |
| `/errors` | Fingerprint table renders | Filters, open linked requirement/workflow | Linked requirement/workflow ids match fingerprint |
| `/errors/:fingerprintKey` | Evidence, linked objects, notifications render | Back, open requirement, open workflow | Notification and intake suppression state is visible |
| `/factory/workflows` | Definition registry and selected state machine render | Select definition, copy spec | Definitions API returns selected workflow states |
| `/factory/atoms` | Atom catalog renders | Type filters work | Atom list derives from workflow definition states |
| `/knowledge` | Knowledge entry point renders | Workflow evidence link works | Artifacts remain attached to workflow runs |
| `/system/notifications` | Dispatcher cards render | Refresh works | Values come from recurring workflow health |

## Postgres Migration And Full-Service Release Validation

The local E2E path is PostgreSQL-only. Use Docker Postgres for app/test runtime; SQLite is only an archived import source for the one-time migration script:

```bash
export OPS_DATABASE_URL="postgresql+psycopg://synapse_growing:synapse_growing_dev@127.0.0.1:54329/synapse_growing_local"
docker-compose -f docker-compose.postgres.yml up -d
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python scripts/db/migrate_sqlite_to_postgres.py --postgres-url "$OPS_DATABASE_URL" --reset-postgres --confirm MIGRATE_SQLITE_TO_POSTGRES
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python scripts/db/validate_postgres_migration.py --sqlite server/ops.db --postgres-url "$OPS_DATABASE_URL"
```

Frontend E2E should then run with `OPS_E2E_DATABASE_URL="$OPS_DATABASE_URL"` so the API and UI read migrated Postgres data. The required smoke scope covers `/command-center`, `/planning`, `/publishing`, `/publishing/trends`, `/releases`, and `/projects`.

Staging release proof is intentionally a real external E2E. It creates and immediately publishes every canonical staging service one at a time, then publishes one non-migration Cloud Run scheduled job:

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python scripts/e2e/release_all_staging_targets.py --base-url http://127.0.0.1:9700 --branch main --confirm RELEASE_ALL_STAGING_TARGETS
```

Success requires completed Release Tasks, succeeded DeploymentRecords, passed health, GitHub Actions URLs, online records for services, and a completed scheduled-job release task. Failures must stay failed with Actions evidence until the root cause is fixed; do not manually mark success.

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
