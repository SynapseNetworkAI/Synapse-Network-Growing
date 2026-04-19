---
created_at: 2026-04-11
updated_at: 2026-04-11
doc_status: active
---

# Validation

## Delivery Standard

Every roadmap requirement must ship with four validation layers:

1. schema and backend behavior
2. dashboard behavior
3. end-to-end workflow behavior
4. defect recording and re-test evidence

## Automated Validation Baseline

Run these as the default validation stack for roadmap work:

- `/Users/cliff/workspace/agent/.venv/bin/python -m pytest -q`
- `cd dashboard && npm test`
- `cd dashboard && npm run build`
- `cd dashboard && npm run test:e2e`

Use narrower targeted commands during implementation, then re-run the broader suite before closing the requirement.

## Requirement-Level Validation Template

For each roadmap requirement, create a validation plan containing:

1. **backend assertions**
   API behavior, orchestration state transitions, persistence, and policy enforcement
2. **frontend assertions**
   dashboard rendering, controls, warnings, and status explanations
3. **workflow assertions**
   requirement planning, execution, validation, bugfix, and closeout transitions
4. **operator assertions**
   what a human reviewer must confirm when manual approval is required

## Bugfix Loop Protocol

If any automated or manual check fails:

1. record the defect in `docs/archive/evidence/test/bugfix.md`
2. include time, module, failing behavior, and fix summary
3. implement the bugfix as a new step or requirement continuation
4. re-run the exact failing test first
5. re-run the broader impacted suite
6. do not mark the roadmap requirement complete until the validation plan passes

## Completion Gate

A roadmap requirement is only complete when:

1. implementation is merged or otherwise accepted into the intended target path
2. automated checks pass
3. manual checks, if any, are signed off
4. any discovered bug was logged and resolved through the self-repair loop
5. resulting artifacts and evidence are visible in the control plane or linked docs
