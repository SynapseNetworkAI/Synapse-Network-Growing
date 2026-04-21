---
id: growing-quality-gate-goal-monitoring
title: Growing Quality Gate Goal Monitoring Runbook
role: dev_rel
status: ready
created_at: 2026-04-21
updated_at: 2026-04-21
author: codex
target_repo: Synapse-Network-Growing
---

# Growing Quality Gate Goal Monitoring Runbook

This runbook monitors the `growing_2026_04_20_gate` style objective until it is truly satisfied, not merely mechanically completed.

## Objective Truth

A quality-gate goal is complete only when `GET /api/planning/goals/{id}/trace` returns:

```text
objective_status = satisfied
missing_evidence = []
```

Workflow `done` is not enough. The latest chain must also include:

```text
Goal PRD
-> Planner Candidate
-> Requirement
-> Workflow Run
-> changed files
-> command evidence for hard gates
-> PR / delivery evidence
```

For `agent_self_repair`, required hard-gate evidence includes:

```text
scripts/ci/agent_guardrails.sh
backend pytest evidence
dashboard npm test evidence
dashboard npm run build evidence
docs-sync / diff hygiene evidence
changed files evidence
PR evidence
```

## Monitoring Loop

1. Open `/planning` and locate the target Goal lane.
2. Open `Trace Path`.
3. Read `objective_status` and `missing_evidence`.
4. If there is no active candidate, requirement, or workflow, run `goal_planner_sweep` from `/schedules` or the Planning command bar.
5. If the latest candidate is `validation_failed`, read the Fail-Closed reason. Fix only by updating PRD, command safety policy, or the underlying system bug. Do not approve a validation-failed candidate around the guardrail.
6. If workflow succeeded but `objective_status=incomplete`, open `/workflows/{id}?tab=evidence` and verify which hard-gate evidence is missing.
7. If evidence is missing because the old workflow only ran a compile check, generate a follow-up self-repair requirement to wire the missing guardrails.
8. Stop when Trace reports `objective_status=satisfied` and the PR has reached the required human review / merge boundary.

## Failure Conditions

Stop automatic monitoring and route to operator if:

```text
workflow status = failed
workflow state = awaiting_operator with no safe automatic recovery
validation_failed repeats beyond the sweep retry budget
scheduler tick stops writing run history
hard-gate scripts themselves are missing or cannot run
```

## Scheduler Check

For recurring workflows, trust explicit scheduler fields:

```text
scheduler_mode
auto_tick_enabled
last_scheduler_tick_at
overdue_reason
```

Manual-only workflows are not overdue. Auto workflows that miss `next_run_at` must write a scheduler-triggered run or appear in `/schedules` Attention Required.
