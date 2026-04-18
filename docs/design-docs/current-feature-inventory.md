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
   - declarative workflow 通过 State Machine Runner 进入 verification state。
   - verification agent 读取 acceptance brief、workflow blackboard、changed files、raw output 与 harness evidence，先生成晚绑定 verification plan。
   - Harness 执行 verification plan 中 required commands 并记录 cwd、exit code、日志路径、耗时和 stdout/stderr excerpt，verification agent 再基于权威 evidence 产出正式 verdict。
   - 旧 execution validate endpoint 已从正式 API surface 退役；验证重跑应通过 workflow state / human gate 继续。
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
12. plan agent provider adapter。
   - `PLANNER_BACKEND` 可独立选择 `openai / claude / copilot / codex_cli / codex_sdk`
   - 未配置时兼容从 `ORCHESTRATION_BACKEND` 推导
   - Codex CLI/SDK adapter 支持项目级 planner session 复用
   - 普通 LLM adapter 不写 Codex session registry
13. execution 当前 / 历史 run 语义与原因解释。
   - execution API 返回 `is_current_execution`
   - execution API 返回 `queue_reason`
   - execution API 返回 `blocking_reason_code / blocking_reason_message`
   - 页面会直接展示“等待启动 / 等待审批 / 启动失败：dirty worktree / verification needs revision”等原因
14. 运行态清理脚本：

```bash
/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_execution_runtime.py --yes
```

15. canonical workflow 状态机清库脚本：

```bash
/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_workflow_state.py --yes
```

## 3. Release 面

当前已具备：

1. Release candidate 列表。
2. Release detail。
3. Workflow passed 后进入交付准备。
4. PR / release 面只信任 workflow run 的 verification verdict 与 human gate 决策。
5. 高风险 delivery、production deploy、外部发布动作必须进入 human gate。
6. delivery / verification 修复不再派生旧 execution；统一表现为 declarative workflow run 内的 state transition、blackboard 更新与 atom invocation。
7. release 与 deployment 配置从正式 Project 主数据读取。
8. Declarative Workflow Factory 已成为新执行真相。
   - `workflow_runs.current_state` 表达当前状态
   - blackboard 保存跨状态共享上下文
   - `workflow_state_events` 和 `atom_invocations` 保存证据链
   - fixed-step execution / bugfix / delivery repair 只作为历史删除对象，不再是 fallback

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
5. Requirement Intake Fingerprint Gate。
   - 使用 `requirement_intake_fingerprints` 治理“错误是否 materialize 为新需求”
   - 已有 active requirement / workflow 时，同 fingerprint 只复用原 requirement
   - requirement 已终态但未 release/observing resolved 时，重复错误进入 `suppressed`
   - release/observing resolved 后，同 fingerprint 再出现会创建 `Regression:` requirement
   - 该 gate 与 Lark notification suppression 分表，避免通知投递策略承担业务副作用
6. 错误自修复 v1 范围固定为 defect self-healing。
   - 包含：runtime error、external log center、task failure、workflow incident、verification 暴露的系统性缺陷
   - 不包含：机会发现、新增功能自动发现、市场/运营信号
7. requirement execution approval 已采用 `approval agent 先审，人兜底` 口径。
   - 低风险高置信度自动放行
   - 高风险或低置信度转人工
   - 运行时是否必须人工审核只由 requirement `approval_contract` 与 approval router / hard rules 决定。
   - project policy 的 `requires_manual_approval` 只作为项目审批偏好信号，不再是运行时 blanket gate。
   - 会强制人工审核的 hard rules 固定为：
     - `publish_or_delivery_impact`
     - `critical_incident_recovery`
     - `max_tier_execution`
     - `over_budget_execution`
     - `multi_project_high_risk_work`

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
   - approval channel
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
4. 统一通知队列。
   - 业务模块写入 `notification_events`
   - dispatcher 更新 `notification_fingerprints`
   - cooldown 内重复事件累计 `suppressed_count`
   - 实际 Lark 投递写入 `notification_deliveries`
5. Notification Dispatcher 后台 loop。
   - 服务启动时按配置启动
   - 周期性消费 queued notification events
   - 暴露 queued、dead letter、open fingerprints、suppressed fingerprints、last tick、last error

## 7.1 定时任务与后台自动化

当前已具备：

1. `/schedules` 定时任务管理页。
   - Health Overview
   - Recurring Workflow Registry
   - Run History
   - Result Inspector
2. 内置 recurring workflow registry。
   - `bug_log_sweep`
   - `morning_intake_sweep`
   - `dispatcher_loop`
   - `closeout_and_compact_sweep`
   - `weekly_operating_review`
   - `approval_sweep`
   - `requirement_family_cleanup_sweep`
3. recurring workflow 手动运行。
   - `Dry Run`
   - `Run Now`
   - Run Now 对可能创建 requirement 的任务有确认保护
   - 默认 `auto_start=false`
4. recurring workflow 运行历史。
   - `recurring_workflow_runs`
   - status、triggered_by、dry_run、params、result、error、duration
5. Bug Log Sweep Scheduler 健康快照。
   - enabled
   - running
   - interval
   - last tick
   - last run
   - last error
   - scheduler lock owner / expires_at / stale 状态
6. `bug_log_sweep` 数据库级防并发锁。
   - 后台 scheduler 和手动 Run Now 共用 `scheduler:bug_log_sweep`
   - 无法获得 lock 时 run history 记录 `skipped_locked`
   - stale lock 过期后可由新 worker 抢占
7. `/api/recurring-workflows/health` 聚合后台健康状态。
8. `/api/recurring-workflows/{workflow_key}/runs` 返回最近运行历史。

## 8. 前端交互规范

当前已具备：

1. Requirement 列表为简洁 SaaS 风格列表，不再是常驻内联大表单。
2. 新建 requirement 使用居中浮层。
3. 编辑 requirement 使用原位编辑或右侧 Drawer。
4. 删除等危险动作使用统一确认弹窗。
5. 成功 / 失败反馈使用统一 toast。
6. 定时任务页只做观测、手动 dry run / run now 和运行历史，不开放自定义任务编辑器。

## 9. 当前正式主导航

当前控制台正式导航为：

1. `需求`
2. `执行`
3. `定时任务`
4. `发布`
5. `项目`
6. `错误`

## 10. 后续维护要求

后续每轮正式迭代，至少同步检查这 4 份文档：

1. `docs/design-docs/current-feature-inventory.md`
2. `docs/design-docs/company-ops-latest-architecture.md`
3. `docs/design-docs/system-design-principles.md`
4. `docs/ops-console-usage.md`

如果代码中的正式能力发生变化，而这份功能清单没有更新，应视为文档不完整。
