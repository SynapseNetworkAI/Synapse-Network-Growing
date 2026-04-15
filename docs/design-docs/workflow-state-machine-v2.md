# Workflow State Machine V2

## Goal

V2 drops the mixed `status / phase / approval_status / release status` model and standardizes the workflow around four objects with a single canonical `state` each.

## Canonical Objects

### Requirement

- `draft`
- `planning`
- `awaiting_approval`
- `ready`
- `executing`
- `delivering`
- `ready_for_merge`
- `awaiting_operator`
- `completed`
- `cancelled`

Requirement expresses goal progress only. It does not mirror the outcome of a single execution attempt.

### ApprovalDecision

- `not_required`
- `pending`
- `approved`
- `rejected`
- `superseded`

### ExecutionAttempt

- `queued`
- `preparing_workspace`
- `executing`
- `verifying`
- `blocked`
- `failed`
- `succeeded`
- `cancelled`

Supporting fields:

- `attempt_kind = implementation | delivery_repair`
- `blocker_kind`
- `failure_kind`
- `resume_mode = restart_current | retry_new_attempt | operator_only`

### Delivery

- `pending`
- `preparing_branch`
- `pushing`
- `opening_pr`
- `repairing`
- `blocked`
- `pr_open`
- `merged`
- `abandoned`

Supporting fields:

- `blocker_kind`
- `repairability = repairable | manual_only`
- `repair_attempt_count`

## Transition Summary

1. Requirement creation: `draft -> planning -> awaiting_approval | ready`
2. Approval passed: `awaiting_approval -> ready`
3. New implementation attempt: `ready -> executing`
4. Attempt success: `executing -> delivering`
5. PR opened: `delivering -> ready_for_merge`
6. Merge completed: `ready_for_merge -> completed`
7. Restartable blocker: `ExecutionAttempt.blocked` while Requirement stays `ready` or `executing`
8. Retry-required failure: `ExecutionAttempt.failed` and Requirement returns to `ready`
9. Manual-only delivery blocker: `Delivery.blocked` and Requirement moves to `awaiting_operator`

## Operator Takeover Rules

- `blocked + restart_current`: operator may restart the current attempt
- `failed + retry_new_attempt`: operator may create a new attempt
- `awaiting_operator`: operator must intervene before the workflow continues

## Budgets

- implementation retry budget: `1`
- delivery repair budget: `1`

## Reset / Cutover

To switch cleanly to V2 and discard historical workflow runtime state:

```bash
/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_workflow_state.py --yes
```

This reset preserves project and policy configuration while clearing workflow history such as requirements, approvals, execution attempts, validations, releases, runtime sessions, and error-to-requirement links.
