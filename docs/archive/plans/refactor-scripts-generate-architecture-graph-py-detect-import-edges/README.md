---
created_at: 2026-04-19
updated_at: 2026-04-19
doc_status: active
---

# Refactor hotspot: scripts/generate_architecture_graph.py::detect_import_edges

这是当前任务的 planning bundle。

建议使用顺序：

1. 先写 `spec.md`
2. 再补 `plan.md`
3. 再确认 `task-graph.md`
4. 最后在 `validation.md` 里写最小验证路线

## Refactor Hotspot
- hotspot: `scripts/generate_architecture_graph.py::detect_import_edges`
- hotspot token: `hotspot-0e89c9d2bec2`
- current rank index: `1`
- line: `307`
- status: `WARN`
- issues: `lines=56>40, branches=19>5, nesting=5>=4, locals=16>8, missing_guiding_comment`
- bundle entry command: `amem refactor-bundle . --token hotspot-0e89c9d2bec2`
- verify with: `amem doctor .`
