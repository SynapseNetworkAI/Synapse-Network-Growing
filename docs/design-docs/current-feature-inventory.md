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
   - 仅 requirement 前置阶段允许删除。
   - 一旦已有 execution 主链，就不再允许 delete。
5. requirement submit。
   - submit 是 requirement 进入 execution 的唯一正式桥接点。
   - approval 放行后会先确保 acceptance contract 与 execution plan 可用，再在目标项目上 prepare branch，随后创建并自动启动 execution。
6. requirement 自动审批与人工审批分流。
   - 低风险自动批准，并在 plan 生成后自动启动 execution。
   - 高风险停在 requirement 面等待人工批准。
7. requirement 详情页。
   - 展示需求意图、acceptance contract、execution plan、所属项目。
   - 顶部提供执行 / 发布跳转动作。
8. requirement 始终只跟踪最新 execution run。
   - replacement run 创建后，旧 run 会降级为历史 run。
   - requirement 的执行态只由最新 run 派生。

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
6. execution 恢复路径已经按 blocker 类型分流。
   - `branch_preparation_blocked / approval_blocked / manual_pause / runtime_recovery_blocked` 这类环境阻塞会在**同一个 current execution** 上 `start / resume`。
   - `verification_needs_revision / verification_failed / task_failed` 这类执行失败才会 `retry` 创建 replacement run，并立即自动尝试启动。
   - 历史 run 只保留查看能力，不再暴露 `retry / start / pause / resume / open_pr`。
7. validate。
   - execution 完成后默认自动触发 verification agent。
   - verification agent 读取 acceptance contract、execution plan、changed files、raw output 与 checks，先生成晚绑定 verification plan，再产出正式 verdict。
   - `POST /api/executions/{id}/validate` 仍保留为调试 / 重跑入口。
8. execution evidence、validation summary、incident 展示。
9. verification result 展示。
   - verdict
   - verification plan
   - reasoning
   - evidence_used
   - suggested_next_action
10. requirement composer 支持 Codex 式附件输入。
   - 拖拽文件
   - 粘贴截图
   - 图片/文件预览卡片
   - attachments 进入 requirement context，并被 plan / execution / verification 读取
11. requirement 资产状态治理。
   - requirement 创建后先保存，再后台异步生成 acceptance contract 与 execution plan
   - `assets_status = pending | ready | failed`
   - 资产未 ready 前不能 submit
   - 失败后可重新生成 requirement assets
12. execution 当前 / 历史 run 语义与原因解释。
   - execution API 返回 `is_current_execution`
   - execution API 返回 `queue_reason`
   - execution API 返回 `blocking_reason_code / blocking_reason_message`
   - 页面会直接展示“等待启动 / 等待审批 / 启动失败：dirty worktree / verification needs revision”等原因
12. 运行态清理脚本：

```bash
/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_execution_runtime.py --yes
```

13. canonical workflow 状态机清库脚本：

```bash
/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_workflow_state.py --yes
```

## 3. Release 面

当前已具备：

1. Release candidate 列表。
2. Release detail。
3. execution approval 放行后自动 prepare branch。
4. verification passed 后自动 commit / push / open PR。
5. delivery gate 自修复。
   - 本地 `git push` 被 pre-push hook / `ci:pr` / `docs_checks` 等 gate 挡住时，会把 blocker 分类成 `repo_gate_failed / workspace_blocked / git_auth_failed / remote_rejected / network_failed / branch_conflict / unknown_delivery_failure`。
   - 可修复的 `repo_gate_failed` 会自动创建 `delivery_repair` child execution。
   - child execution 使用独立 `repair_plan`；父 `requirement_plan` 只作为 reference，不会被覆盖。
   - repair #2 必须读取 repair #1 的失败摘要、commands run、evidence 与最新 blocker 重新规划。
   - repair 成功后继续主任务的 `re-verification -> re-delivery -> open PR`，不是重跑整个 implementation。
   - 两次 repair 都失败时，父 requirement 进入 `failed`。
   - dirty worktree、git 权限、网络、远端拒绝等不可自动修复 blocker 会停在 `release_blocked` 并转人工。
5. staging deploy。
6. production deploy。
7. rollback。
8. deployment history 展示。
9. release 与 deployment 配置从正式 Project 主数据读取。
10. workflow v2 canonical state 已落地。
   - `Requirement.state = draft / planning / awaiting_approval / ready / executing / delivering / ready_for_merge / awaiting_operator / failed / completed / cancelled`
   - `ExecutionAttempt.state = queued / preparing_workspace / executing / verifying / blocked / failed / succeeded / cancelled`
   - `Delivery.state = pending / preparing_branch / pushing / opening_pr / repairing / blocked / pr_open / merged / abandoned`

## 3.1 Error Discovery / Self-Healing 面

当前已具备：

1. 统一错误发现入口。
   - `/api/errors/intake`
   - `/api/bugs/intake/log-center`
   - `bug_log_sweep`
2. 统一 discovery pipeline。
   - 错误先形成 `error_fingerprint / bug_record`
   - 再由 discovery recommendation 与硬规则决定是否 materialize requirement
3. discovery recommendation 正式字段。
   - `auto_materialize`
   - `queue_for_operator`
   - `ignore_as_noise`
4. Error Fingerprint / Bug Record 会返回：
   - `discovery_status`
   - `discovery_recommendation`
   - `materialized_requirement_id`
   - `last_discovery_at`
5. 错误自修复 v1 范围固定为 defect self-healing。
   - 包含：runtime error、external log center、task failure、workflow incident、verification 暴露的系统性缺陷
   - 不包含：机会发现、新增功能自动发现、市场/运营信号
6. requirement execution approval 已采用 `approval agent 先审，人兜底` 口径。
   - 低风险高置信度自动放行
   - 高风险或低置信度转人工

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
