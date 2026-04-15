# Parent Plan + Child Repair Model

## Goal

Make delivery self-healing fully AI-first without losing the original requirement plan.

The system must:

1. Keep the parent `requirement_plan` immutable.
2. Create a child `delivery_repair` task when local delivery gates fail.
3. Feed the latest blocker and previous repair failure result into the next repair agent.
4. Retry at most 2 repair attempts.
5. Resume the main requirement flow on success.
6. Mark the parent requirement as `failed` when the repair budget is exhausted.

## Core Model

### Parent

- `Requirement`
- owns the immutable `requirement_plan`
- keeps the original goal, scope, acceptance, implementation approach, verification strategy, and risks

### Child

- `ExecutionAttempt(kind=delivery_repair)`
- owns a derived `repair_plan`
- references:
  - parent requirement
  - source delivery record
  - previous repair attempt
  - latest blocker excerpt / raw output

## Repair Loop

1. `implementation` attempt succeeds
2. verification passes
3. delivery `git push` / PR open is blocked by a repairable repo gate
4. system creates `delivery_repair #1`
5. if `delivery_repair #1` fails:
   - collect changed files, commands run, verification summary, reasoning, raw output
   - read the latest blocker again
   - create `delivery_repair #2` with a newly generated repair plan
6. if `delivery_repair #2` succeeds:
   - run lightweight re-verification
   - re-enter delivery
   - continue to PR open
7. if `delivery_repair #2` also fails:
   - `Requirement.state = failed`
   - `Requirement.failure_reason = delivery_repair_budget_exhausted`
   - `Delivery.state = blocked`
   - `Delivery.next_action = route_to_human`

## Repair Plan Requirements

Every `delivery_repair` plan must include:

1. `plan_kind = delivery_repair`
2. `goal_summary`
3. `failed_gate_name`
4. `blocker_type`
5. `blocker_excerpt`
6. `repair_scope`
7. `success_criteria`
8. `verification_checks`
9. `attempt_index`
10. `attempt_budget`
11. `parent_plan_reference_summary`
12. `repair_context`
    - latest blocker excerpt
    - previous attempt summary
    - previous failure summary

## Operator / UI Expectations

Execution detail must show:

1. current repair plan
2. parent requirement plan reference
3. failed gate name
4. repair attempt index / budget
5. previous repair attempt summary

Requirement detail must show:

1. parent plan summary
2. current delivery status
3. repair attempt count
4. failure reason if the parent requirement has terminated
