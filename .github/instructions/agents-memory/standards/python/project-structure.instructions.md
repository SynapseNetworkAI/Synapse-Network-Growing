---
created_at: 2026-03-26
updated_at: 2026-04-07
doc_status: active
---

# Project Structure Baseline

## 分层约束

1. `commands/` 只做 CLI 参数映射
2. `services/` 只做业务逻辑
3. `integrations/agents/` 只做 agent 插件适配
4. `runtime.py` 只做上下文和路径 bootstrap
5. `templates/` 只放静态模板和公开 example

## 禁止事项

1. 不要在 README 或文档里定义真实运行逻辑
2. 不要在 wrapper 脚本中重新实现业务逻辑
3. 不要把 profile 或 standards 规则写死在命令分支里