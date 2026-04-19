# Ops Console Dark Unification Dogfood Report

## Summary

- Target URL: `http://localhost:9700/`
- Session: `ops-console-dark-unification`
- Date: `2026-04-19`
- Scope: all sidebar routes, major detail routes, safe buttons, tabs, modals/drawers, and computed-style white-surface scan.
- External side effects: disabled by test discipline. No real Lark send, no production deploy, no rollback, no funds movement, no merge.
- Final verdict: `passed`

## Code / Product Fixes Applied During Dogfood

- Added a global legacy light-utility compatibility map in `dashboard/src/index.css` so future old MVP classes such as `bg-white`, `bg-slate-50`, `border-slate-200`, and light pastel badges render as cockpit dark surfaces instead of white SaaS surfaces.
- Migrated existing page/component source away from forbidden light utilities; remaining matches are limited to the intentional compatibility map in `index.css` and allowed transparent glass classes such as `bg-white/[0.03]`.
- Fixed Factory pages that blanked after navigation. Root cause: `/api/workflows/definitions` returns canonical `spec.states` as an object, while the UI expected a normalized `states[]` array. `dashboard/src/api.ts` now normalizes workflow definitions before pages consume them.
- Removed the duplicate root `DESIGN.md`; canonical design guidance remains at `docs/front/stitch_declarative_agent_factory/obsidian_protocol/DESIGN.md`.

## Screenshot Evidence

| Page | Screenshot |
| --- | --- |
| Command Center | `screenshots/01-command-center.png` |
| Planning | `screenshots/02-planning.png` |
| Requirements | `screenshots/03-requirements.png` |
| Requirement Detail | `screenshots/04-requirement-detail.png` |
| Workflows | `screenshots/05-workflows.png` |
| Workflow Detail Overview | `screenshots/06-workflow-detail-overview.png` |
| Workflow Detail Steps | `screenshots/07-workflow-detail-steps.png` |
| Workflow Detail Evidence | `screenshots/08-workflow-detail-evidence.png` |
| Workflow Detail Gates | `screenshots/08b-workflow-detail-gates.png` |
| Gates | `screenshots/09-gates.png` |
| Factory Workflows | `screenshots/10-factory-workflows.png` |
| Factory Atoms | `screenshots/11-factory-atoms.png` |
| Schedules | `screenshots/12-schedules.png` |
| Releases | `screenshots/13-releases.png` |
| Projects | `screenshots/14-projects.png` |
| Errors | `screenshots/15-errors.png` |
| System Notifications | `screenshots/16-system-notifications.png` |
| Knowledge | `screenshots/17-knowledge.png` |
| Release Detail | `screenshots/18-release-detail.png` |
| Project Detail | `screenshots/19-project-detail.png` |

## Menu Click Verification

All sidebar menu items were clicked through the browser and routed correctly:

| Menu | Expected Route | Result |
| --- | --- | --- |
| 司令部 | `/command-center` | pass |
| 经营规划 | `/planning` | pass |
| 门禁审批 | `/gates` | pass |
| 信号入口 | `/intake` | pass |
| 需求池 | `/requirements` | pass |
| 运行轨迹 | `/workflows` | pass |
| 发布交付 | `/releases` | pass |
| 状态机定义 | `/factory/workflows` | pass |
| 原子能力库 | `/factory/atoms` | pass |
| 知识资产 | `/knowledge` | pass |
| 定时任务 | `/schedules` | pass |
| 通知队列 | `/system/notifications` | pass |
| 项目治理 | `/projects` | pass |
| 错误指纹 | `/errors` | pass |

Raw log: `menu-clicks.log`.

## Button / Interaction Verification

Safe interactions passed:

- `/command-center`: `调整目标`, `处理门禁`, `查看运行` route to the expected areas.
- `/planning`: `Dry Run Planner`, `History`, `Debug`, and `Edit raw JSON` open/click without white modal regression.
- `/requirements`: `新建需求`, `刷新`, and first `查看` work.
- `/workflows`: `Active`, `Needs Human`, `Failed`, `Completed`, `Archived`, `Definitions` tabs work.
- `/workflows/3`: `Overview`, `Steps`, `Evidence`, `Gates & Delivery`, `Debug` tabs work.
- `/gates`: `Review Gate` click is safe and does not trigger external side effects.
- `/schedules`: `Dry Run` click works.
- `/releases`: `刷新` and first `查看` work.
- `/projects`: `新建项目` and first `查看` work.
- `/factory/workflows`: `Copy Spec` works.
- `/factory/atoms`: `all`, `agent`, `deterministic`, `terminal` filters work.
- `/system/notifications`: `刷新` works.

Expected data-dependent result:

- `/errors`: `刷新` works. `查看` was not present because the local DB currently has no error fingerprint rows, so error detail click was not applicable.

Raw log: `button-clicks.log`.

## Computed-Style White Surface Scan

Scanner looked for large elements with these computed backgrounds:

- `rgb(255, 255, 255)`
- `rgb(248, 250, 252)`
- `rgb(241, 245, 249)`

Result:

| Route Count | Bad Count |
| --- | --- |
| 19 scanned routes/details | 0 |

All scanned routes returned `badCount: 0`.

Raw log: `computed-style-scan.log`.

## Console / Network Notes

- After fixing Factory normalization and clearing old logs, Factory pages no longer produce the React blank-page warning.
- Browser console still includes normal Vite development messages and React DevTools suggestion; these are not product failures.
- No real external notification, deployment, rollback, funds, settlement, or merge action was executed.

## Fixed Finding

### ISSUE-001: Factory pages blank after navigation

Severity: high

Category: Functional / Console

Status: fixed

Repro before fix:

1. Open `/factory/workflows`.
2. Browser displayed a blank dark page.
3. Console warned that an error occurred in `<WorkflowDefinitionsPage>`.
4. Same issue appeared in `<AtomRegistryPage>`.

Root cause:

- Frontend assumed workflow definitions had top-level `states[]`.
- Backend returned canonical workflow spec shape with `spec.states` as an object.

Fix:

- Added `normalizeWorkflowDefinition` in `dashboard/src/api.ts` to derive `states[]`, `initial_state`, `limits`, `risk_policy`, and `blackboard` from `spec`.

Verification:

- `/factory/workflows` screenshot: `screenshots/10-factory-workflows.png`.
- `/factory/atoms` screenshot: `screenshots/11-factory-atoms.png`.
- Menu click verification now passes for both pages.

## Residual Risks

- The compatibility map remains in `index.css` as a safety net for future regressions; it should stay until all new UI work consistently uses shared control-plane primitives.
- Error detail route was not fully exercised because local data has no error fingerprint rows.

## Verification Commands

```bash
cd /Users/cliff/workspace/agent/Synapse-Network-Growing/dashboard
npm test -- --run
npm run build

cd /Users/cliff/workspace/agent/Synapse-Network-Growing
git diff --check
```
