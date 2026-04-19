# Synapse-Network-Growing

`Synapse-Network-Growing` is the Company Ops control plane for the Synapse system. Its purpose is to turn goals, signals, incidents, and operator intent into observable agent-first workflows that can plan, execute, verify, request approval, and deliver safely.

The current operating model is:

```text
Operating Manifest
-> Planner Sweep
-> RequirementCandidate
-> Requirement
-> Declarative Workflow Run
-> State Machine Runner
-> Atom Invocations + Blackboard + Evidence
-> Human Gate / Release / Done
```

The key boundary is simple: **Agent is the engine, declarative state machine is the rail, human operator is the high-risk gate.**

## Current Architecture

The repository is no longer centered on legacy TaskBoard / CrewAI / fixed execution steps. New business flow must use:

1. **Operating Manifest**: the single active strategy snapshot and budget/goal control surface.
2. **RequirementCandidate**: the buffer between autonomous planning and the formal requirement pool.
3. **Requirement**: the approved or materialized work item tied to a project, manifest, and goal lineage.
4. **Declarative Workflow Run**: the source of truth for execution, validation, retry, evidence, and delivery.
5. **Blackboard + Artifacts**: shared workflow context and immutable evidence.
6. **Human Gate**: mandatory approval for production, funds, settlement, auth, external spend, and self-modifying deployment.
7. **Recurring Jobs + Watchers**: observable background systems for bug sweep, notification dispatch, recurring workflow registry, and planning sweeps.

Legacy `/api/tasks` and `/api/approvals` public routes have been retired. Any remaining old task/execution internals are deletion candidates, not compatibility surfaces for new work.

## Read First

Coding agents and humans should start here:

1. [ARCHITECTURE.md](ARCHITECTURE.md) - short architecture constitution for coding agents.
2. [AGENTS.md](AGENTS.md) - repo agent operating protocol and capability profile rules.
3. [System Design Principles](docs/design-docs/system-design-principles.md) - canonical engineering constraints.
4. [Declarative Agent Workflow Factory](docs/design-docs/declarative-agent-workflow-factory.md) - state machine, blackboard, atoms, gates.
5. [Planning Lifecycle Operating Manifest](docs/design-docs/planning-lifecycle-operating-manifest.md) - manifest, planner sweep, candidates, drop goal.
6. [Recurring Workflow Control Plane](docs/design-docs/recurring-workflow-control-plane.md) - scheduled jobs and dispatcher observability.
7. [Workflow Factory Frontend Control Plane](docs/design-docs/workflow-factory-frontend-control-plane.md) - operator UI for workflow observability.
8. [Current Feature Inventory](docs/design-docs/current-feature-inventory.md) - implemented capability baseline.
9. [Ops Console Usage](docs/ops-console-usage.md) - local UI/API usage notes.
10. [Ops Console Page Map and E2E Validation](docs/ops-console-page-map-and-e2e-validation.md) - page-by-page function map, tests, and GoalB dogfood validation.

Historical evidence and legacy docs are intentionally moved under `docs/archive/`.

## Main Surfaces

1. `/requirements`: requirement pool and workflow readiness.
2. `/workflows`: declarative workflow run list.
3. `/workflows/:id`: explainable workflow workbench with steps, evidence, gates, delivery, and debug views.
4. `/planning`: active Operating Manifest, planner candidates, goal rollups, drop-goal safe halt, manifest history.
5. `/schedules`: recurring workflow registry, run history, scheduler/dispatcher health.
6. `/errors`: error fingerprints and bug materialization state.
7. `/projects`: project registry and delivery policy configuration.
8. `/releases`: PR, delivery, deploy, and rollback governance.

The current product-level validation target is **GoalB**: the system must show that an Operating Manifest goal can become a `RequirementCandidate`, then a formal `Requirement`, then a completed declarative `WorkflowRun` with evidence. See [Ops Console Page Map and E2E Validation](docs/ops-console-page-map-and-e2e-validation.md).

## Required Runtime

The local backend expects Python 3.14+ through the shared workspace virtualenv:

```bash
/opt/homebrew/bin/python3.14 -m venv /Users/cliff/workspace/agent/.venv
/Users/cliff/workspace/agent/.venv/bin/python -m pip install -U pip setuptools wheel
/Users/cliff/workspace/agent/.venv/bin/pip install -r requirements.txt
```

Common local commands:

```bash
sh scripts/local/restart.sh
/Users/cliff/workspace/agent/.venv/bin/python -m pytest -q
cd dashboard && npm test
cd dashboard && npm run build
```

## Planner And Runtime Config

Recommended planner adapter:

```env
PLANNER_BACKEND=codex_sdk
PLANNER_MODEL=gpt-5.4
PLANNER_TIMEOUT=300
```

Supported planner adapters are:

```text
openai | claude | copilot | codex_cli | codex_sdk
```

Runtime execution can still be configured independently. For local Codex CLI execution:

```env
ORCHESTRATION_BACKEND=codex_cli
LLM_PROVIDER=codex
LLM_MODEL=gpt-5-codex
CODEX_CLI_MODEL=gpt-5-codex
CODEX_CLI_FULL_AUTO=true
```

For OpenAI API usage:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-5.4
ORCHESTRATION_BACKEND=openai_responses
OPENAI_API_KEY=...
```

## Notification Config

Lark delivery is queued, deduplicated, and rate-limited before sending. Configure separate webhooks for alert, approval, workflow notification, and release channels:

```env
OPS_LARK_BOT_WEBHOOK_URL=...
OPS_LARK_BOT_KEYWORD=告警
OPS_LARK_REQUIREMENT_WEBHOOK_URL=...
OPS_LARK_REQUIREMENT_KEYWORD=需求
OPS_LARK_ALERT_WEBHOOK_URL=...
OPS_LARK_ALERT_KEYWORD=告警
OPS_LARK_APPROVAL_WEBHOOK_URL=...
OPS_LARK_APPROVAL_KEYWORD=审批
OPS_LARK_RELEASE_WEBHOOK_URL=...
OPS_LARK_RELEASE_KEYWORD=发布
OPS_LARK_DELIVERY_DRY_RUN=false
OPS_NOTIFICATION_DISPATCHER_ENABLED=true
OPS_NOTIFICATION_ALERT_BURST_PER_MINUTE=5
OPS_NOTIFICATION_DEFAULT_COOLDOWN_SECONDS=900
```

Set `OPS_LARK_DELIVERY_DRY_RUN=true` when running smoke tests against configured webhooks. Dry-run mode still persists notification deliveries and renders Lark cards, but it never calls the Lark webhook.

Routing rules:

1. P0/P1 interruption -> alert.
2. Human gate -> approval.
3. PR / release / deploy -> release.
4. Workflow lifecycle summary -> workflow notification.
5. Ordinary state transitions, atom success, artifacts, and blackboard snapshots stay in Ops Console.

## Docs Layout

1. `docs/design-docs/`: current architecture and formal design docs.
2. `docs/ops/`: operational governance and deployment runbooks.
3. `docs/plans/`: current or strategic planning bundles only.
4. `docs/archive/`: historical evidence, old plans, old design drafts, and retired docs.
5. `docs/assets/`: architecture diagrams used by current docs.

When adding or deleting formal capabilities, update [Current Feature Inventory](docs/design-docs/current-feature-inventory.md) with the same change.
