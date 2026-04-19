# AGENTS

Remember: you are not a passive tool. You are a careful operator in a system whose goal is to build OPS that can discover requirements, optimize projects, evolve workflows, and complete tasks safely. Go Cyber Brothers.

<!-- agents-memory:read-order:start -->
## Agents-Memory Read Order

Generated for the `python-service` profile. Treat the files below as the source of truth.

1. `.github/instructions/agents-memory-bridge.instructions.md`
2. `.github/instructions/agents-memory/standards/python/base.instructions.md`
3. `.github/instructions/agents-memory/standards/python/tdd.instructions.md`
4. `.github/instructions/agents-memory/standards/python/dry.instructions.md`
5. `.github/instructions/agents-memory/standards/python/project-structure.instructions.md`
6. `.github/instructions/agents-memory/standards/docs/docs-sync.instructions.md`
7. `.github/instructions/agents-memory/standards/planning/harness-engineering.md`
8. `.github/instructions/agents-memory/standards/planning/spec-kit.md`
9. `.github/instructions/agents-memory/standards/planning/review-checklist.md`

## Notes

- Keep project-specific notes outside this managed block.
- Re-run `amem enable . --full` or `amem standards-sync .` after profile-managed standard changes.
<!-- agents-memory:read-order:end -->

## Codex / Architecture Read Order

Codex reads `AGENTS.md` reliably, but it must not assume `.github/instructions/*.instructions.md` are loaded implicitly. Treat this section as the explicit bridge from Codex to repo instructions.

Before substantial analysis or edits, read in this order:

1. `/Users/cliff/workspace/agent/llms.txt`
2. `AGENTS.md`
3. `.github/instructions/agents-memory-bridge.instructions.md`
4. `.github/instructions/architecture-constraints.instructions.md`
5. `ARCHITECTURE.md`
6. `docs/design-docs/system-design-principles.md`

If the task touches workflow, planning lifecycle, scheduler, release, notification, runtime, auth, finance, settlement, or production safety, also read the relevant design doc linked from `ARCHITECTURE.md`.

If the task touches Ops Console frontend, also read:

1. `docs/design-docs/frontend-control-plane-figma-implementation.md`
2. `docs/design-docs/workflow-factory-frontend-control-plane.md`
3. `docs/ops-console-page-map-and-e2e-validation.md`
4. `docs/front/stitch_declarative_agent_factory/obsidian_protocol/DESIGN.md`

## Operating Protocol

This repository is the Company Ops control plane. New work should align to the current chain:

```text
Operating Manifest
-> RequirementCandidate
-> Requirement
-> Declarative Workflow Run
-> Atom Invocations
-> Evidence
-> Human Gate / Release
```

Rules:

1. Do not create a God Agent that controls global workflow.
2. Agent atoms produce structured output; deterministic runners own state transitions.
3. Planner Sweep creates candidates, not official requirements, unless operator-approved materialization is explicit.
4. Drop Goal stops future investment and safe-halts unfinished work; it never reverts delivered releases.
5. Production deploy, funds, settlement, contract, auth, external paid spend, and self-modifying deployment require human gate.
6. Legacy `/api/tasks` and `/api/approvals` public routes are retired. Remaining fixed-step execution internals are deletion candidates, not valid extension points.
7. Frontend must remain a Human-Agent Control Plane. Do not reintroduce flat CRUD navigation, detached candidate queues, or raw JSON as the primary operator surface.

## Capability Profiles

Roles under `roles/` are capability profiles and context packs, not traditional departments. They should be loaded into agent atoms only when their expertise is useful for a workflow state.

Standard profiles:

1. `roles/dev_rel/`: developer experience, demos, technical writing, integration examples.
2. `roles/growth_lead/`: growth strategy, campaign planning, community traction, provider acquisition.
3. `roles/content_writer/`: landing copy, emails, outreach, user-facing text.
4. `roles/seo_strategist/`: technical SEO, AI SEO, structured content, competitor pages.
5. `roles/cro_optimizer/`: funnel analysis, activation, analytics, experimentation.
6. `roles/launch_strategist/`: launch sequencing, pricing, referral, sales enablement.

Execution convention:

```text
Workflow State
-> Capability Profile
-> Skill Context
-> Agent Atom Prompt
-> Structured Output
-> Deterministic Runner Transition
```

## Marketing Skills

Before marketing or growth work, read `.agents/product-marketing-context.md` for product context, then load only the relevant skill from `.agents/skills/`.

Dispatch protocol:

1. Load capability profile from `roles/<role>/prompts/persona.md`.
2. Load skill from `.agents/skills/<skill-name>/SKILL.md`.
3. Produce the requested artifact with explicit path, format, and KPI or review criteria.

Full playbook: `docs/marketing-skills-playbook.md`.

## Browser Automation

Browser automation uses `.agents/skills/agent-browser/SKILL.md`.

Systematic QA and evidence capture uses `.agents/skills/dogfood/SKILL.md`.

Conventions:

1. Reuse repository `agent-browser.json`.
2. Standard browser flow: `open` -> `snapshot -i` -> interact via element refs -> refresh snapshot.
3. Temporary browser artifacts stay under `.agent-browser/`.
4. Evidence worth keeping should be placed under `docs/archive/evidence/` or a current validation path, not random docs roots.
5. First-time setup: `agent-browser install`.

## Product Map

All work must attach to real Synapse system surfaces:

1. `/Users/cliff/workspace/agent/Synapse-Network-Growing`: Company Ops control plane.
2. `/Users/cliff/workspace/agent/Synapse-Network`: main product, gateway, settlement, risk, admin.
3. `/Users/cliff/workspace/agent/Synapse-Network-Sdk`: developer and agent integration SDK.
4. `/Users/cliff/workspace/agent/Synapse-Network-Provider`: provider runtime.
5. `/Users/cliff/workspace/agent/Agents-Memory`: memory, constraints, reusable records.

Always check `project_key`, `target_project_path`, and project policy before assuming which repository should be changed.

## Docs Lifecycle

Concrete delivery docs should use YAML frontmatter:

```yaml
---
id: <unique-id>
title: <document title>
role: <dev_rel | growth_lead | content_writer | seo_strategist | cro_optimizer | launch_strategist>
status: <draft | review | ready | published>
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
author: <agent-id or human-name>
target_repo: <optional target repo>
---
```

Docs rules:

1. Current architecture docs live in `docs/design-docs/`.
2. Historical evidence and old plans live in `docs/archive/`.
3. Do not add new root-level historical plans.
4. If a feature changes, update `docs/design-docs/current-feature-inventory.md`.
5. If a workflow or planning rule changes, update `ARCHITECTURE.md` or the relevant canonical design doc.
