---
created_at: 2026-04-08
updated_at: 2026-04-08
doc_status: active
---

# Refactor hotspot: scripts/verify_frontmatter.py::main

这是当前任务的 planning bundle。

建议使用顺序：

1. 先写 `spec.md`
2. 再补 `plan.md`
3. 再确认 `task-graph.md`
4. 最后在 `validation.md` 里写最小验证路线

## Refactor Hotspot
- hotspot: `scripts/verify_frontmatter.py::main`
- hotspot token: `hotspot-9c6441ed2adf`
- current rank index: `1`
- line: `42`
- status: `WARN`
- issues: `branches=6>5, nesting=4>=4, locals=9>8, missing_guiding_comment`
- bundle entry command: `amem refactor-bundle . --token hotspot-9c6441ed2adf`
- verify with: `amem doctor .`
