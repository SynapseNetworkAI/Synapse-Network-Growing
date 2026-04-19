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

## Refactor Work Items
```json
[
  {
    "step": 1,
    "title": "Map decision branches and data mutations",
    "done_when": "Current control flow is documented in spec.md."
  },
  {
    "step": 2,
    "title": "Extract or simplify the hotspot",
    "done_when": "Complexity drivers are reduced without behavior regression."
  },
  {
    "step": 3,
    "title": "Re-run validation",
    "done_when": "`amem doctor .` shows a smaller refactor_watch surface."
  }
]
```
