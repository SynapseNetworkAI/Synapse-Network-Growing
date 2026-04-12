# Synapse Company Ops 最新架构设计

## 1. 目标

`Synapse-Network-Growing` 现在不是单一 dashboard，而是整个 Synapse 体系的公司级编排中枢。

它的职责是把这几层接起来：

1. 公司级 review 与 portfolio 决策
2. optimization signal 发现与转 requirement
3. requirement-first workflow orchestration
4. task runtime 与 approval 治理
5. project policy / onboarding / budget / rebalance
6. 结果回流到 signal、company review 和下一周期 bundle

## 1.1 设计原则边界

系统级硬约束已沉淀到：

1. `/Users/cliff/workspace/agent/Synapse-Network-Growing/docs/design-docs/system-design-principles.md`

后续所有设计与实现默认必须满足这些原则，尤其是：

1. 把模型当不稳定部件，不当同事
2. 错误路径按主路径设计
3. verification 独立于 implementation
4. 多代理用于隔离不确定性
5. runtime / subagent 必须有生命周期与 cleanup
6. 上下文必须按 budget / compact / stale verify 治理

## 1.2 新增的执行约束层

现在 `project policy` 不再只负责路径和发布模式，还负责显式执行约束。

每个项目策略现在都包含两组控制面：

1. `capability_matrix`
2. `interrupt_policy`

### capability matrix

当前统一字段为：

1. `shell_access`
2. `git_read`
3. `git_write`
4. `git_push`
5. `network_access`
6. `publish`

它们的作用不是“给 UI 展示一下”，而是直接进入：

1. planner output
2. workflow step `approval_policy`
3. delivery contract 的 `auto_publish_allowed`
4. step dispatch 前的 policy interrupt

### interrupt policy

当前统一字段为：

1. `operator_confirmation_actions`
2. `auto_pause_on_events`
3. `auto_abort_on_events`

它定义了：

1. 哪些动作必须转 operator confirmation
2. 哪些事件要把 workflow 自动暂停
3. 哪些事件要直接终止并转入 revision / incident 路径

### 当前已接入的行为

当前系统已经做到：

1. planner 会把 capability/interrupt 约束写入每个 workflow step
2. step prompt 会显式展示 capability contract，而不是让 agent 猜
3. 如果某个 step 所需能力被 policy 禁用，dispatch 前会生成 `capability_interrupt` artifact
4. 触发 `capability_denied` 时，workflow 会按 interrupt policy 自动 `pause / block`
5. delivery contract 的 auto publish 只会在 `git_push + publish` 都允许、且不要求 operator confirmation 时开启

## 1.3 新增的上下文治理层

在 capability / interrupt 之后，当前系统又新增了一层显式的 context governance。

这一层的目标不是“让 prompt 更漂亮”，而是约束：

1. 每个 workflow step 最多能看到多少上下文
2. 什么时候必须 compact
3. 哪些 artifact 需要做 stale verify
4. 发现陈旧上下文时是否阻断 dispatch

### step-level context policy

现在 planner 会为每个 step 输出独立的 `context_policy`，当前统一字段为：

1. `max_prompt_chars`
2. `compact_after_chars`
3. `max_artifact_body_chars`
4. `max_handoff_chars`
5. `stale_after_minutes`
6. `stale_sensitive_artifact_types`
7. `block_on_stale_memory`

这些策略会持久化到 `workflow_steps.context_policy_json`，不再依赖隐式默认行为。

### deterministic compaction

dispatch 前，orchestrator 会按固定顺序构造 step context：

1. requirement summary
2. target project + project policy summary
3. capability contract
4. done_when
5. predecessor handoff
6. bound artifacts

如果上下文超过预算：

1. 先按 handoff / artifact 的上限截断
2. 再生成结构化 compact 结果
3. 仍超限时再收敛到 `max_prompt_chars`

整个过程会生成 `context_compaction` artifact，记录：

1. `raw_chars`
2. `final_chars`
3. `compacted`
4. `binding_summaries`
5. `section_summaries`

### stale memory verification

dispatch 前还会生成 `stale_memory_verification` artifact。

当前会重点检查：

1. 关键 artifact 是否属于当前 workflow run
2. stale-sensitive artifact 是否超过允许时间窗口
3. requirement 是否在 workflow 创建后发生了需要重新审视的大幅更新

如果当前 step 的 policy 指定 `block_on_stale_memory = true` 且验证结果不是 `fresh`，系统会：

1. 阻断该 step dispatch
2. 创建或复用 `stale_memory_review` approval
3. 将 workflow 暂停
4. 将 requirement 标为 `blocked`

### UI 与 operator 可见性

`/requirements/:id` 详情页现在新增了 `Context Governance` 面板，可直接查看：

1. 当前 step 的 context policy
2. 最近一次 compaction 结果
3. 最近一次 stale memory verification 状态

这样 operator 不再需要靠猜测判断“agent 到底看到了什么上下文”。

## 1.4 新增的 runtime lifecycle / telemetry 层

在 context governance 之后，当前 requirement workflow 又新增了一层运行期治理。

目标是把 runtime / subagent 的生命周期从“散落在 task logs 和 monitor 里”提升成可复盘的 workflow artifact。

### 当前新增的 artifact

现在每个进入 dispatch 的 workflow step，都会开始产出两类 artifact：

1. `runtime_lifecycle`
2. `runtime_telemetry`

### runtime_lifecycle

用于记录 step 对应 runtime 的状态切换，当前已覆盖：

1. `dispatch_requested`
2. `running`
3. `waiting_approval`
4. `completed`
5. `failed`
6. `paused`

artifact payload 会记录：

1. `runtime_backend`
2. `runtime_session_id`
3. `runtime_selected_agent`
4. `task_status`
5. `step_status`
6. `skill_name`
7. `started_at / completed_at`
8. `last_error_message`

### runtime_telemetry

用于汇总运行期证据，当前会聚合：

1. `task_logs` 中的 runtime/subagent/tool/permission/user_input 事件
2. subagent 的 selected / started / completed / failed 计数
3. runtime session state snapshot
4. transcript 是否已经产生

这样 requirement 详情页、incident 分析、optimization signal 都可以读同一份结构化 telemetry，而不必各自重新解析日志。

### 运行期状态来源

当前这层治理使用三类来源：

1. `TaskRow` 上的 backend / session / selected_agent / status
2. `TaskLogRow` 中的 runtime / subagent 事件
3. Copilot SDK detached runtime 的 state file

其中：

1. task runner 负责写原始 task log
2. monitor 负责持续同步 detached runtime state
3. workflow orchestrator 负责把它们归档成 requirement-level artifact

### UI 与 operator 可见性

`/requirements/:id` 详情页现在新增了 `Runtime Lifecycle` 面板，可查看：

1. 最新 lifecycle snapshot
2. telemetry summary
3. recent runtime events
4. subagent 计数

这一步的意义是：operator 终于能直接回答“这个 requirement 现在到底卡在 runtime 的哪一层”，而不是同时翻 task logs、session state 和 workflow 状态。

## 1.5 新增的 incident taxonomy / recovery narrative 层

在 runtime telemetry 之后，当前系统又补上了一层统一的 incident view。

这层的目标是：

1. 把分散的 failure artifact 统一归类
2. 为 operator 生成可执行的 recovery narrative
3. 让 requirement detail 和 optimization signals 读同一套事故视图

### 当前统一接入的 incident 来源

当前 incident taxonomy 会归一这些 artifact：

1. `bug_report`
2. `capability_interrupt`
3. `stale_memory_verification`
4. `bugfix_circuit_breaker`
5. `runtime_lifecycle`

### incident record 的统一字段

每个 incident 至少包含：

1. `incident_family`
2. `incident_code`
3. `severity`
4. `recovery_status`
5. `summary`
6. `recommended_action`
7. `source_artifact_type`
8. `source_artifact_id`

### 当前 taxonomy family

目前系统已经覆盖这些 family：

1. `verification`
2. `governance`
3. `context_integrity`
4. `recovery_loop`
5. `runtime_orchestration`

### requirement detail 如何使用它

`/requirements/:id` 现在新增了 `Recovery Narrative & Incidents` 面板。

operator 可以直接看到：

1. 当前 requirement 最近的重要 incident
2. 事故属于哪一类 taxonomy
3. 当前 recovery status 是什么
4. 推荐动作是什么

### optimization signals 如何使用它

optimization signal 现在除了原来的：

1. `bug_report`
2. `delivery_blocker`
3. `manual_override`

还会生成：

1. `workflow_incident`

这类 signal 会直接附带：

1. `incident_family`
2. `incident_code`
3. `recovery_status`
4. `recovery_narrative`

因此 signal 不再只是“有问题”，而是会明确告诉 operator“这是哪类事故，以及建议怎样收口”。

## 2. 当前推荐的数据库策略

## 2.1 是否要立刻换成更强的数据库

短答案：

1. 当前 `/api/requirements` 的慢，不是第一优先级的数据库类型问题。
2. 先优化查询路径和计算方式，比先把 SQLite 换成 PostgreSQL 更划算。

这次排查里看到的主要瓶颈是：

1. `GET /api/requirements?sort=score` 会对每条 requirement 计算 score。
2. 旧实现里这些 score 计算会重复构建 `project catalog`、重复查 routing / signal 上下文。
3. 这更像是“单请求内重复全量扫描”，不是 SQLite 单纯扛不住。

所以当前优先级建议是：

1. 先做单请求级别的上下文复用与缓存。
2. 再做关键查询日志和慢请求观测。
3. 当并发用户、后台调度线程、审批流和 review 刷新都明显增多后，再迁移 PostgreSQL。

## 2.2 推荐路线

### 阶段 A：继续使用 SQLite，但把查询做对

适用于当前本地单机、单 operator、开发环境。

先做：

1. 单请求复用 `project_catalog`
2. 单请求复用 signal-derived score context
3. 关键接口打点日志
4. 必要时把 `requirements` 的 score snapshot 物化
5. 对慢 aggregation 改成定时刷新而不是每次在线重算

### 阶段 B：迁移 PostgreSQL

适用于：

1. 多人同时操作 dashboard
2. 多个后台 worker 并发写入
3. review / scheduler / signals 高频刷新
4. 需要更稳定的锁、索引、并发事务与分析查询

迁移时建议：

1. 保持 SQLAlchemy model 不变
2. 先让 local 继续 SQLite，prod 改 PostgreSQL
3. 把 signal summary / company review / requirement score snapshot 做成可重建表

## 2.3 最终建议

现在不建议因为 `/requirements` 慢就立刻换库。

更合理的顺序是：

1. 先优化计算路径
2. 先加日志和慢请求观测
3. 再看 PostgreSQL 是否成为必要投入

## 3. 服务端日志设计

## 3.1 当前新增的日志模块

新增了统一日志工具：

1. `/Users/cliff/workspace/agent/Synapse-Network-Growing/server/logging_utils.py`

它负责：

1. 配置控制台日志
2. 配置滚动文件日志
3. 统一 key=value 风格事件日志
4. 统一 timed operation 打点

日志配置来自：

1. `/Users/cliff/workspace/agent/Synapse-Network-Growing/server/config.py`

默认日志文件位置：

```text
/Users/cliff/workspace/agent/Synapse-Network-Growing/server/logs/ops-dashboard.log
```

## 3.2 当前已经记录的关键信息

### HTTP 层

通过 `server/main.py` 记录：

1. `request_id`
2. `method`
3. `path`
4. `query`
5. `status`
6. `duration_ms`

### requirement 层

重点记录：

1. `requirements_list`
2. `requirement_created`
3. `requirement_planned`
4. `requirement_started`
5. `requirement_paused`
6. `requirement_closed`
7. `requirement_published`
8. `requirement_deleted`
9. `requirement_revised`
10. `requirement_queue_advanced`
11. `requirement_queue_idle`

### optimization signal 层

重点记录：

1. `optimization_signals_refresh`
2. `optimization_signal_converted`
3. `optimization_signal_auto_intake`
4. `optimization_signals_list`

### company review 层

重点记录：

1. `company_review_get`
2. `company_review_refresh`
3. `company_review_refreshed`
4. `company_review_materialize_bundle`
5. `company_review_bundle_materialized`

## 3.3 下一步建议继续补的日志

如果你要继续增强可观测性，下一批最值得补的是：

1. planner 生成耗时与 step 数量
2. scheduler 每个 candidate 的决策原因摘要
3. approval 决策耗时和 backlog 大小
4. task runtime 的 provider / model / deferred session 状态
5. `Agents-Memory` ingest 成功率和延迟

## 4. Optimization Signal 的数据源

optimization signal 不是凭空生成的，它来自当前系统已经存在的执行证据。

当前主要有三类来源：

## 4.1 `bug_report`

来源：

1. `artifacts` 表里 `artifact_type = bug_report`

由 requirement workflow 在这些步骤失败时产生：

1. `review`
2. `test`
3. `bugfix` 后重测失败

Signal service 会按这些信息聚合：

1. `failed_checks`
2. `step_type`
3. `requirement`
4. `project root`

形成：

1. `signal_type = bug_report`

## 4.2 `delivery_blocker`

来源：

1. `artifacts` 表里 `artifact_type = delivery_state`

当 delivery state 里出现：

1. `publish_status = blocked` 或 `review_ready`
2. `publish_blockers` 非空

Signal service 会把这些 blocker 聚合成：

1. `signal_type = delivery_blocker`

## 4.3 `manual_override`

来源有两类：

1. `approval_requests`
2. `approvals`

也就是：

1. requirement 级人工审批请求
2. task 级人工审批记录

当某个项目反复把人拉进来做决策时，就会形成：

1. `signal_type = manual_override`

## 4.4 当前还没有直接接入但值得接入的来源

## 5. 从 Harness Engineering 可以直接借鉴什么

参考：

1. `https://harness-books.agentway.dev/book1-claude-code/preface.html`
2. `https://harness-books.agentway.dev/book1-claude-code/chapter-07-multi-agent-and-verification.html`
3. `https://harness-books.agentway.dev/book1-claude-code/chapter-09-ten-principles.html`
4. `https://harness-books.agentway.dev/book1-claude-code/appendix-a-checklists.html`

它和我们现在的方向高度一致，但也给了几条更具体的约束原则。

### 5.1 可以直接借鉴的核心判断

1. 不要把模型当同事，要把模型当不稳定部件。
2. Prompt 不是人格设定，而是控制面的一部分。
3. Query loop、恢复分支、权限、验证和回滚都应该算主路径，不是异常补丁。
4. 多代理的价值不是“多开几个 worker”，而是把 research / implementation / verification 的不确定性隔离开。
5. verification 必须独立成阶段，不能让 implementation 自证正确。
6. 子代理和后台 runtime 都有生命周期，必须有 start / stop / cleanup / transcript / abort 传播。
7. 错误恢复最怕设计成死循环，所以错误路径本身也要有预算与熔断。

### 5.2 对 Synapse Company Ops 最值得落地的改进

#### A. 把 Harness 约束显式化

现在我们已经有：

1. project policy
2. validation contract
3. delivery contract
4. scheduler / rebalance / budget

下一步建议再补：

1. requirement 级 execution budget
2. step 级 max tool-call / max bugfix / max resume 次数
3. “谁可以动 shell / git / publish / network”的 capability matrix
4. 对高风险动作的统一 interrupt / abort 语义

#### B. 把错误恢复做成产品功能

这次 requirement `#40` 的事故说明，我们已经需要更强的恢复设计。

建议继续补：

1. circuit breaker 后自动创建 `operator review` 与 `infra incident` requirement
2. 将重复错误、孤儿任务、runtime stale session 做成标准 incident taxonomy
3. 在 RequirementDetail 与 OptimizationSignals 中单独展示 `recovery narrative`
4. 对 paused / failed / circuit-broken workflow 增加“下一步建议动作”

#### C. 把多代理真正分层

现在 requirement workflow 已经有 implementation / review / test / closeout，但还可以更像 harness：

1. 增加 `research` 与 `synthesis` 的显式阶段
2. coordinator 负责收束 worker 结果，不允许把理解责任继续外包
3. verification worker 必须和 implementation worker 隔离 runtime session / memory scope
4. subagent transcript 与 cleanup 状态进入 artifact 和日志

#### D. 把上下文治理从“能用”升级到“可治理”

建议继续做：

1. requirement / task / agent session 的 context budget 指标
2. compact 触发条件与 compact 后摘要 artifact
3. stale memory / stale assumption 的 verify-and-rewrite 机制
4. 在 Agents-Memory 中区分长期规则、会话记忆、临时证据

### 5.3 现在最应该优先做的 P-next

1. `Research + Synthesis` 显式阶段化
2. runtime / subagent lifecycle artifacts 与 cleanup telemetry
3. capability matrix + dangerous tool interrupt policy
4. recovery narrative 面板与 incident taxonomy
5. context budget / compact / stale memory verification

下一步可以继续接这些来源：

1. test flakiness
2. queue starvation
3. runtime timeout
4. repeated rollback
5. low validation coverage
6. docs drift
7. onboarding friction

## 5. 模块交互设计

## 5.1 总体数据流

```mermaid
flowchart TD
    A["Project Policies / Onboarding"] --> B["Project Intelligence Catalog"]
    B --> C["Requirement Intake"]
    C --> D["Requirement Pool"]
    D --> E["Workflow Planner"]
    E --> F["Workflow Orchestrator"]
    F --> G["Tasks Runtime Layer"]
    G --> H["Approvals"]
    G --> I["Artifacts / Logs / File Changes"]
    I --> J["Optimization Signals"]
    H --> J
    J --> D
    J --> K["Portfolio Scheduler"]
    B --> K
    D --> K
    K --> L["Company Operating Review"]
    J --> L
    L --> M["Next Cycle Bundle / Operator Package"]
    M --> D
```

## 5.2 各模块职责

### Project Policies / Onboarding

负责定义：

1. 项目根路径
2. 可写范围
3. 禁止范围
4. required checks
5. release mode
6. autonomy mode
7. rebalance / preemption / budget

这些信息被：

1. requirement routing
2. scheduler
3. delivery gate
4. company review

共同使用。

### Project Intelligence

负责把多个底层数据合成项目画像：

1. readiness
2. bug pressure
3. delivery pressure
4. manual override pressure
5. automation coverage

它是这几层的共享输入：

1. requirement score
2. signal score
3. portfolio scheduler
4. company review

### Requirement Pool

需求池是顶层工作对象，系统真正的“要做什么”在这里表达。

requirement 支持：

1. intake
2. routing
3. dependencies
4. planning
5. start / pause / revise / close / publish

### Workflow Planner

负责把 requirement 变成 machine-readable workflow：

1. workflow steps
2. acceptance checks
3. validation plan
4. delivery contract

### Workflow Orchestrator

负责驱动 requirement 从 planned 到 done：

1. 创建 workflow run
2. 派发 task
3. 跟踪步骤状态
4. 生成 artifacts
5. 失败时进入 bugfix loop
6. closeout 后回写 delivery state

### Task Runtime

这里是兼容执行层，负责：

1. 把 workflow step 落到 task
2. 调用真实 runtime
3. 落日志、输出、diff、history

### Approvals

负责高风险动作的人类决策边界，不应该承接普通执行。

### Optimization Signals

负责把执行后的异常、摩擦、阻塞沉淀成可排序、可转 requirement 的 signal。

### Portfolio Scheduler

负责跨项目决定：

1. 谁先做
2. 谁延后
3. 哪些 signal 该 intake
4. 是否 rebalance
5. 是否提示 preempt candidate

### Company Operating Review

负责把当前整个 portfolio 的状态汇总成：

1. summary
2. project highlights
3. bottlenecks
4. incidents
5. next cycle recommendations
6. requirement bundle
7. operator review package

当前这层已经不只是“把 optimization signal 再展示一次”，而是直接消费统一 incident taxonomy。

具体来说：

1. `incidents` 来自统一 incident record，而不是前端自己拼 signal 文本。
2. 每条 incident 都会带 `project_key / project_display_name / incident_family / incident_code / recovery_status`。
3. `next cycle recommendations` 会把 incident 直接作为一类候选项，和 requirement / signal 一起排序。
4. `next cycle requirement bundle` 会优先把 incident recommendation 转成 `incident_recovery` 模板 requirement。
5. `operator review package` 会把高风险 incident 继续收束成 operator 决策，而不是任由系统在事故态里无限自治。

这意味着 portfolio 层现在已经可以直接回答：

1. 当前最值得优先处理的事故在哪个项目。
2. 这是 verification / governance / context / runtime 哪一类问题。
3. 它现在处在 `bugfix_loop_active / operator_review_required / replan_required / runtime_recovery_required` 的哪一种恢复状态。
4. 下一周期应该 intake 一个新 recovery requirement，还是先走 operator approval。

## 6. `/requirements` 慢的当前结论

当前阶段的结论是：

1. 慢主要来自 score/routing 的重复计算。
2. 不是先换库就能自动解决的问题。
3. 当前已经应该优先做：
   1. 单请求上下文复用
   2. 慢请求日志
   3. 关键聚合物化

如果这些做完后仍然因为并发、锁竞争、后台线程和多用户访问带来压力，再进入 PostgreSQL 是顺理成章的下一步。
