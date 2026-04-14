# Synapse Ops 当前功能清单

本文记录 `Synapse-Network-Growing` 当前已经正式具备的功能，作为后续迭代的基线清单。

使用规则：

1. 每次新增、删除或重构正式功能时，必须同步更新这份清单。
2. 这份清单描述“当前系统真的能做什么”，不记录临时设想或候选方案。
3. 历史计划、草稿和 bugfix 记录不能替代这份正式功能清单。

## 1. Requirement 面

当前已具备：

1. Requirement 列表、搜索、状态筛选。
2. 新建 requirement。
   - 最小输入为标题、所属项目、需求描述、优先级。
   - 验收标准默认由 agent 创建后自动生成真实 acceptance contract。
3. 编辑 requirement。
   - 仅未进入 execution 主链的 requirement 可编辑。
   - 可修改标题、项目、描述、验收标准、优先级与高级路径覆盖。
4. 删除 requirement。
5. requirement submit。
   - submit 是 requirement 进入 execution 的唯一正式桥接点。
   - approval 放行后会先确保 acceptance contract 与 execution plan 可用，再在目标项目上 prepare branch，随后创建并自动启动 execution。
6. requirement 自动审批与人工审批分流。
   - 低风险自动批准，并在 plan 生成后自动启动 execution。
   - 高风险停在 requirement 面等待人工批准。
7. requirement 详情页。
   - 展示需求意图、acceptance contract、execution plan、所属项目。
   - 顶部提供执行 / 发布跳转动作。

## 2. Execution 面

当前已具备：

1. Execution run 列表。
2. Execution detail。
   - 顶部展示当前主链 run 的 `agent / backend / provider / model / branch / tokens_used_total / elapsed_ms`
   - 展示当前 run 关联的 execution plan
   - Runtime 区展示每个 node / task 的 token、时长和运行时元信息
   - Files 区展示当前 run 的改动文件
   - 点击文件可打开预览浮层，默认看 `diff`
   - Agent Output 区始终展示原始 task 输出
   - Activity 区展示结构化时间线
3. 单 requirement 单 execution 主链治理。
4. queued run 启动。
5. paused run 恢复。
6. failed / blocked run 通过 `retry` 创建新 run。
7. validate。
   - execution 完成后默认自动触发 verification agent。
   - verification agent 读取 acceptance contract、execution plan、changed files、raw output 与 checks 产出正式 verdict。
   - `POST /api/executions/{id}/validate` 仍保留为调试 / 重跑入口。
8. execution evidence、validation summary、incident 展示。
9. verification result 展示。
   - verdict
   - reasoning
   - evidence_used
   - suggested_next_action
9. 运行态清理脚本：

```bash
/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_execution_runtime.py --yes
```

## 3. Release 面

当前已具备：

1. Release candidate 列表。
2. Release detail。
3. execution approval 放行后自动 prepare branch。
4. verification passed 后自动 commit / push / open PR。
5. staging deploy。
6. production deploy。
7. rollback。
8. deployment history 展示。
9. release 与 deployment 配置从正式 Project 主数据读取。

## 4. Project 面

当前已具备：

1. 正式 Project 列表与详情页。
2. 新建项目。
3. 编辑项目基础信息。
   - `project_key`
   - `display_name`
   - `root_path`
   - `status`
4. GitHub 与交付配置管理。
   - `repo_full_name`
   - `default_branch`
   - `deploy_repo_full_name`
   - `deploy_strategy`
   - `deploy_trigger_enabled`
   - `staging_host_label`
   - `production_host_label`
   - `staging_workflow_file`
   - `production_workflow_file`
5. Project 绑定治理策略。
   - 当前采用 `Project : ProjectPolicy = 1 : 1`
6. requirement 必须挂到 Project。
7. `target_project_path_override` 只作为 requirement 的高级覆盖字段保留。

## 5. Error Loop 与稳定性治理

当前已具备：

1. `/errors` 与 `/errors/:fingerprintKey` 错误聚合页。
2. 高信号错误 intake：
   - `runtime_log_error`
   - `task_failure`
   - `workflow_incident`
3. 错误指纹聚合与去重。
4. 同一 fingerprint 只允许一条未完成 requirement。
5. 错误自动回流为 requirement。
6. 回流 requirement 自动 submit 并进入审批 / execution 主链。
   - 自动审批放行后同样先生成 execution plan，再自动执行。
7. 错误、执行失败、PR 打开等 Lark 通知。

## 6. 审批与治理

当前已具备：

1. requirement execution approval。
2. 低风险自动审批。
3. 高风险 requirement 人工审批。
4. approve / reject 入口。
5. project policy 驱动的执行与发布治理。
6. execution 运行态单主链约束。
7. verification/manual review 已移除；verification agent verdict 是 release 前唯一正式验证信号。

## 7. 通知与日志

当前已具备：

1. 统一 Lark 通知结构。
   - requirement channel
   - alert channel
   - release channel
2. Python 结构化日志。
   - `structlog + logging`
   - `stdout` JSON 主输出
   - 本地 `JSONL` 按天切分备份
3. 关键链路结构化日志字段。
   - `request_id`
   - `task_id`
   - `requirement_id`
   - `execution_id`
   - `release_id`
   - `fingerprint_key`

## 8. 前端交互规范

当前已具备：

1. Requirement 列表为简洁 SaaS 风格列表，不再是常驻内联大表单。
2. 新建 requirement 使用居中浮层。
3. 编辑 requirement 使用原位编辑或右侧 Drawer。
4. 删除等危险动作使用统一确认弹窗。
5. 成功 / 失败反馈使用统一 toast。

## 9. 当前正式主导航

当前控制台正式导航为：

1. `需求`
2. `执行`
3. `发布`
4. `项目`
5. `错误`

## 10. 后续维护要求

后续每轮正式迭代，至少同步检查这 4 份文档：

1. `docs/design-docs/current-feature-inventory.md`
2. `docs/design-docs/company-ops-latest-architecture.md`
3. `docs/design-docs/system-design-principles.md`
4. `docs/ops-console-usage.md`

如果代码中的正式能力发生变化，而这份功能清单没有更新，应视为文档不完整。
