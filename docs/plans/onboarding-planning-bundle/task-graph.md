---
created_at: 2026-04-19
updated_at: 2026-04-19
doc_status: active
---

# Task Graph

## Work Items

1. 基础设施或模板改动
2. 核心代码改动
3. 测试改动
4. 文档改动
5. 收尾清理

## Dependencies

- 哪些任务必须先完成？
- 哪些任务可以并行？

## Exit Criteria

- 任务完成时必须满足哪些条件？

## Onboarding Task Steps
```json
[
  {
    "group": "Planning",
    "priority": "required",
    "key": "planning_bundle",
    "status": "FAIL",
    "detail": "docs/plans/ai-company-ops-roadmap/README.md missing required phrases: planning bundle",
    "action": "Repair the planning bundle so the repository has a valid spec-first execution package.",
    "command": "amem plan-check .",
    "verify_with": "amem plan-check .",
    "done_when": "`amem doctor .` shows `[OK] planning_bundle`.",
    "safe_to_auto_execute": false,
    "approval_required": true,
    "approval_reason": "plan-check only diagnoses issues; actual planning repairs should be reviewed before editing tracked docs",
    "next_command": "amem doctor ."
  }
]
```
