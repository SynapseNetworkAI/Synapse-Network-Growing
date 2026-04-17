---
id: execution-self-repair-loop-architecture
title: Execution Self-Repair Loop Architecture
role: dev_rel
status: ready
created_at: 2026-04-17
updated_at: 2026-04-17
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing
---

# Execution Self-Repair Loop Architecture

## Summary

Verification failures are now repaired inside the same requirement execution chain. The system no longer creates a separate bugfix execution for normal `failed` or `needs_revision` verification results. Instead, Harness feeds the verification result and command evidence back into the same Execution Agent session, appends a `verification_repair_*` node to the current execution run, and asks the agent to continue from its existing context.

Core loop:

```text
Execution Agent implements
-> Verification Agent plans and judges
-> Harness runs required verification commands
-> failed / needs_revision feeds evidence back to the same Execution Agent session
-> verification_repair_* turn fixes only the failed scope
-> repeat until passed, auto budget exhausted, or route_to_human
```

This keeps the roles clean:

1. Execution Agent is the generator. It writes code, updates tests, runs targeted checks, and repairs failures.
2. Verification Agent is the discriminator. It tries to prove the implementation does not satisfy acceptance and emits repair guidance when it fails.
3. Harness is the game loop. It schedules turns, executes required commands, records artifacts, controls retry budget, and advances state.

## Scope

This design covers verification failures after an implementation turn. It does not replace `delivery_repair`, which remains the separate mechanism for PR delivery or repository gate blockers such as pre-push hooks, branch conflicts, and git authentication failures.

## Core Flow

1. Requirement owns the lightweight Acceptance Brief: done criteria, scope constraints, risk notes, and expected evidence.
2. Plan Agent creates the implementation plan from requirement plus acceptance.
3. Harness starts the Execution Agent turn.
4. Execution Agent implements the change, writes or updates tests, runs useful self-checks, and reports evidence.
5. Verification Agent reads acceptance, plan, changed files, raw output, and self-run evidence to generate `verification_plan.md`.
6. Harness executes required verification commands from the verification plan and writes command evidence.
7. Verification Agent reads authoritative Harness evidence and produces `verification_result.md`.
8. If passed, Harness proceeds to delivery / commit / push / PR.
9. If failed or needs revision and automatic repair budget remains, Harness appends a `verification_repair_*` execution node and starts a new turn in the same Execution Agent session.
10. If the automatic repair count reaches 2 and verification still fails, the execution is marked failed and requirement goes to `route_to_human`.
11. An operator can choose manual retry; that creates another repair turn in the same session and increments `manual_retry_count`.

## State Model

Self-repair state is stored in the execution run `plan_snapshot_json.self_repair` object.

Key fields:

1. `repair_attempt_count`: automatic repair turns after failed verification.
2. `max_auto_repair_attempts`: default `2`.
3. `manual_retry_count`: operator-triggered retries after automatic budget is exhausted.
4. `latest_validation_id`: validation record that triggered the latest repair.
5. `latest_verification_result_path`: latest `verification_result.md`.
6. `latest_verification_evidence_paths`: verification plan, result, and command evidence markdown paths.
7. `latest_repair_prompt`: Markdown prompt fed back to the Execution Agent.
8. `repair_history`: compact summaries of failed verdicts and evidence paths.

The API exposes the visible counters on `ExecutionRunOut`:

1. `repair_attempt_count`
2. `max_auto_repair_attempts`
3. `manual_retry_count`

## Session Reuse

Self-repair must preserve the previous Execution Agent runtime session.

Implementation rules:

1. The initial implementation task owns the first `runtime_session_id`.
2. A `verification_repair_*` node creates a new task with `retry_of_task_id` pointing to the latest completed task in the same run.
3. The new task copies the previous task `runtime_session_id`.
4. The Codex CLI / SDK runtime receives that `runtime_session_id` as the preferred thread id.
5. If the runtime registry cannot resolve a reusable session, task-level `runtime_session_id` still acts as a direct resume hint.

This gives the Execution Agent enough conversational and repository context to repair precisely instead of re-understanding the whole requirement from scratch.

## Verification Artifacts

Verification is Markdown-first with small structured indexes for state transitions.

Artifacts:

1. `verification_plan.md`: required commands, evidence to inspect, non-mutating rules, and verdict rubric.
2. `verification_evidence.md`: Harness command results, exit codes, excerpts, log paths, durations, and timeout status.
3. `verification_result.md`: final verdict, summary, reasoning, resolution path, and repair guidance.

Failed repair prompt shape:

```md
# Verification Failed

## Original Acceptance
<acceptance brief>

## Original Plan
<plan summary>

## Verification Result
<status, summary, reasoning, repair_guidance, artifact paths>

## Failed Harness Commands
<cwd, command, exit_code, log_path>

## Required Repair Behavior
- Continue in the same implementation session.
- Fix only what is needed to satisfy Acceptance.
- Add or update tests when the failure shows missing coverage.
- Run targeted checks and report evidence.
- Do not reset unrelated work.
```

## Resolution Rules

Verification result mappings:

1. `passed` -> `release_ready`
2. `failed` / `needs_revision` and budget remains -> `continue_execution`
3. `failed` / `needs_revision` and budget exhausted -> `route_to_human`
4. `inconclusive` -> `route_to_human`
5. clear out-of-scope or ownership drift -> `create_followup_requirement` or `route_to_human`

The system accepts legacy Verification Agent responses that say `retry_execution`, but normalizes them to `continue_execution` for verification failures.

## GAN-Style Design

Execution Agent and Verification Agent are intentionally adversarial but cooperative:

1. Execution Agent optimizes for satisfying acceptance with real code and tests.
2. Verification Agent optimizes for finding ways the evidence does not satisfy acceptance.
3. Harness prevents either side from becoming judge and player at the same time.
4. The feedback loop improves the implementation while keeping evidence authoritative.

Verification Agent does not write code or tests. Tests are part of the deliverable, so the Execution Agent owns them.

## UI Behavior

Execution detail displays:

1. `self repair: <repair_attempt_count> / <max_auto_repair_attempts>`
2. manual retry count when present
3. `verification_repair_*` nodes in the execution timeline
4. runtime session id for the current agent session
5. verification plan, command evidence, and final verdict

When automatic repair budget is exhausted, the retry button communicates that the operator will continue the same session instead of creating a new replacement run.

## Test Coverage

Current automated coverage verifies:

1. failed verification appends a `verification_repair_*` node instead of creating a new run.
2. repair turns preserve the previous `runtime_session_id`.
3. automatic repair stops after 2 failed verification cycles and routes to human.
4. manual retry after budget exhaustion appends another same-session repair turn.
5. Verification Agent can produce late-bound verification plans with required commands.
6. Harness command results capture exit code, duration, timeout, log path, and output excerpts.
7. legacy `retry_execution` recommendations normalize to `continue_execution`.

## Related Docs

1. [Company Ops Latest Architecture](company-ops-latest-architecture.md)
2. [System Design Principles](system-design-principles.md)
3. [Current Feature Inventory](current-feature-inventory.md)
4. [Plan Agent Project-Scoped Session Reuse](plan-agent-project-scoped-session-reuse.md)
