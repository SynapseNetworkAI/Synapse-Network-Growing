# Context Loading Map

Use this map after reading `AGENTS.md`, `ARCHITECTURE.md`, and the short `docs/design-docs/system-design-principles.md`.

Do not load every principles file by default. Load only the rows that match the task.

| Task signal | Load | Required |
| --- | --- | --- |
| planning, requirement, candidate, goal, mission, scheduler, workflow definition, acceptance, fail-closed | `principles/planning-lifecycle.md` | yes |
| CI, PR, tests, coverage, quality gate, lint, line count, complexity, dependency audit, branch protection | `principles/quality-gates.md` | yes |
| Ops Console, planning page, human gate UI, raw JSON, decision view, dashboard navigation | `principles/ops-console.md` | yes |
| `/schedules`, recurring workflow, background loop, runtime, subagent, workspace recovery, telemetry, structured logs | `principles/runtime-observability.md` | yes |
| release, deploy, staging, production, rollback, online record, Cloud Run, GitHub Actions deployment | `principles/release-governance.md` | yes |
| `/publishing`, X, social content, trend radar, replies, reposts, content generation, official account | `principles/social-publishing.md` | yes |
| dashboard UI, frontend, modal, workbench, design tokens, page layout, browser validation | `principles/frontend-workbench.md` | yes |
| cross-surface refactor, production safety, auth, funds, settlement, self-modifying deployment | all relevant rows above | yes |

## Loading Defaults

1. Ordinary local bugfix: load only the relevant row.
2. Docs-only change: load this map plus the docs/design row relevant to the touched document.
3. High-risk system change: load all matching rows and cite why a wider sweep was needed.
4. Never solve missing context by blindly importing the whole principles directory.
