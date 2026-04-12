---
created_at: 2026-04-08
updated_at: 2026-04-08
doc_status: active
---

# Shared Engineering Brain onboarding: onboarding

这是当前任务的 planning bundle。

建议使用顺序：

1. 先写 `spec.md`
2. 再补 `plan.md`
3. 再确认 `task-graph.md`
4. 最后在 `validation.md` 里写最小验证路线

## Onboarding State
- state file: `.agents-memory/onboarding-state.json`
- bootstrap ready: `no`
- bootstrap complete: `no`
- next group: `Planning`
- next key: `planning_bundle`
- next command: `amem plan-check .`
- verify with: `amem plan-check .`
- done when: `amem doctor .` shows `[OK] planning_bundle`.
