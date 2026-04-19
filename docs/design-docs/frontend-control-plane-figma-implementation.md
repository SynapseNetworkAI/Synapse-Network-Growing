---
id: frontend-control-plane-figma-implementation
title: Figma Driven Human-Agent Control Plane Frontend
role: dev_rel
status: draft
created_at: 2026-04-19
updated_at: 2026-04-19
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing
---

# Figma Driven Human-Agent Control Plane Frontend

## Summary

Growing 的前端不是 Jira、Trello 或数据库对象浏览器。它是 Human-Agent Control Plane：

```text
Human Intent
-> Requirement Discovery
-> Declarative Workflow Run
-> Blackboard / Atom Evidence
-> Human Gate
-> Release / Knowledge
```

`docs/front/growing原型.fig` 是当前前端视觉方向的来源。当前会话没有 Figma MCP 的 `get_design_context/get_screenshot`，所以 v1 使用降级路径：结合 `.fig` thumbnail、Stitch HTML/screenshot 和 `obsidian_protocol/DESIGN.md` 实现深色 cockpit 高保真近似。后续接入 Figma Desktop/MCP 后，再逐 frame 做 1:1 校准。

## Navigation Model

主导航必须按 operator 决策路径组织：

```text
Command Center
Planning
Intake
Oracle Gates
Execution
Delivery
Factory
Knowledge
System Ops
```

当前路由映射：

| Route | Control Plane Domain | Purpose |
|---|---|---|
| `/command-center` | Command Center | Global desired state, blockers, active runs |
| `/planning` | Planning | Operating Manifest, goals, candidates |
| `/intake` | Intake | Error, forum, watcher, planner signal entry |
| `/gates` | Oracle Gates | Pending human gates and failed/blocked runs |
| `/requirements` | Execution | Requirement pool and workflow readiness |
| `/workflows` | Execution | Workflow Operations Center |
| `/workflows/:id` | Execution | Run Explorer / Blackboard |
| `/releases` | Delivery | PR, release, deployment, observing |
| `/factory/workflows` | Factory | Read-only workflow definitions |
| `/factory/atoms` | Factory | Read-only atom registry |
| `/knowledge` | Knowledge | Artifacts and SOP Ledger entry point |
| `/schedules` | System Ops | Scheduled jobs and background task health |
| `/system/notifications` | System Ops | Notification queue and suppression health |
| `/projects` | System Ops | Project governance and policies |
| `/errors` | Intake | Error fingerprints and requirement intake gate |

## Visual Contract

- The primary UI uses the Figma / Obsidian dark cockpit style.
- Main surfaces use deep layers: `#10131a`, `#191c22`, `#272a31`.
- Human-readable UI uses Inter/Fira Sans; machine data uses JetBrains Mono/Fira Code.
- AI output is rendered as a Reasoning Card with an accent rail.
- High-risk gates use amber or rose treatments and must expose evidence.
- Raw JSON must not be the primary UI; it belongs in Debug drawers/tabs.

## Readability Contract

Dark cockpit pages must be readable before they are visually clever. Any frontend change to Ops Console must follow these rules:

- Do not place dark text on remapped light surfaces. Legacy Tailwind classes such as `text-slate-900`, `text-gray-900`, `text-black`, and `prose` content must resolve to `--ops-text-title` or `--ops-text-body`.
- Do not use `opacity-50/60/70` as the primary disabled or secondary-text treatment. Disabled controls must still explain their state with `--ops-text-caption` and an explicit label.
- Markdown and rich text blocks must use dark-mode prose tokens. Requirement descriptions, acceptance criteria, done criteria, expected evidence, and scope constraints must be readable on `--ops-panel`.
- Warning/status pills must use dark cockpit surfaces plus high-contrast text. Do not depend on pastel `bg-*-50` colors being visible.
- Buttons that create new business objects must use operator language. For example, use `创建后续需求` with helper text instead of the ambiguous `Create Follow-up Requirement`.
- `Open PR` must link to a real GitHub PR URL when delivery is real. If delivery is simulated, the page must say so clearly and must not imply an external PR exists.
- Workflow verification must display command evidence. A completed run without command evidence is not considered fully observable.

## Page Contracts

### Command Center

Shows the company operating state at a glance:

- active requirements
- running workflows
- pending human gates
- failed workflows
- active goals
- background scheduler / notification health

### Oracle Gates

Shows only decisions that require human judgment:

- pending human gates
- high-risk workflows
- failed and blocked runs
- evidence link to `/workflows/:id`

Agent recommendations are advisory; the UI must never imply the Agent has already approved a high-risk action.

### Workflow Run Explorer

The run detail page must answer:

- What did the workflow try to do?
- What did each Agent Atom output?
- What files changed?
- What commands ran?
- What evidence proves the outcome?
- Is delivery real or simulated?
- Is a human gate pending?

### Factory

Factory pages are read-only in v1:

- workflow definitions
- state transitions
- atom registry
- risk policy

Online YAML editing is blocked until spec versioning, schema validation, sandbox execution, and human approval are implemented.

## Implementation Rule

Do not paste exported Figma/Stitch HTML directly into the app. Convert the prototype into project components and data-bound pages:

```text
prototype frame
-> design tokens
-> reusable component
-> existing API data
-> dogfood screenshot
```

## Validation

Required checks:

```bash
cd dashboard && npm test -- --run
cd dashboard && npm run build
cd dashboard && npm run test:e2e
git diff --check
```

Dogfood should use `agent-browser` screenshots for:

- `/command-center`
- `/planning`
- `/gates`
- `/workflows`
- `/workflows/:id`
- `/factory/workflows`
- `/factory/atoms`
- `/system/notifications`
