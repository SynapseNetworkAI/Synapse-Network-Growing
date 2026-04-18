# Synapse Ops Console 使用说明

本文面向 `http://localhost:9700/` 的当前控制台使用者。

当前控制台已经切换到 **Agent-First 三面架构**：

1. `需求`
2. `执行`
3. `发布`
4. `项目`
5. `错误`

默认执行流只有：

```text
intake -> execute -> validate -> deliver
```

这份文档只描述当前正式操作面，不再把旧的 5-step requirement workflow、运营总览、tasks、approvals、deployments 旧页面当作主入口。

当前视觉与布局也采用统一的 **Enterprise Workbench** 规则：

1. 不再把页面组织成同权重卡片拼盘。
2. 页面默认采用简洁 SaaS 结构，优先突出列表、详情和轻量操作。
3. Requirement、Workflow、Release 三面使用不同的信息密度和页面模板。

## 1. 页面总览

当前正式页面包括：

1. `/requirements`
2. `/requirements/:id`
3. `/workflows`
4. `/workflows/:id`
5. `/releases`
6. `/releases/:requirementId`
7. `/projects`
8. `/projects/:id`

辅助治理页：

1. `/errors`
2. `/errors/:fingerprintKey`

推荐心智模型：

1. 在 `需求` 定义为什么做
2. 在 `工作流` 观察状态机、Blackboard、Atom、验证证据与 Human Gate
3. 在 `发布` 处理 branch / PR / deploy / rollback
4. 在 `项目` 统一管理仓库、GitHub、部署与治理配置

当前正式功能范围请同时参考：

`docs/design-docs/current-feature-inventory.md`

### 1.1 页面骨架规则

当前正式工作台骨架统一为：

1. `Page Header`
   用来表达当前页面和主操作。
2. `Primary Workspace`
   承载当前页面的唯一主工作对象。
3. `Secondary Actions`
   承载筛选、搜索、删除确认、toast 等轻量交互。
4. `Context Areas`
   只在确实需要时展示运行态、incident 或 deployment 轨迹。

如果一个页面看起来像“很多大白卡平铺”，说明它偏离了当前正式设计方向。

## 2. 需求面

### 2.1 `/requirements`

#### 页面职责

需求池只负责 requirement intent 和治理入口。

#### 页面布局

1. 顶部是 filter bar 与主操作
2. 主工作区是 requirement table/list
3. `新建` 通过居中浮层完成，`编辑` 通过右侧 Drawer 完成

#### 典型动作

1. 从工具条打开 `新建需求` 浮层
2. 从工具条或列表项打开 `编辑需求` Drawer
3. 提交 requirement
4. 低风险 requirement 会在后台补齐 acceptance brief 与 workflow blackboard，再创建 declarative workflow run；高风险 requirement 在 workflow human gate 等待人工批准
5. workflow 进入高风险 atom 或外部副作用前，必须通过 Risk-Evidence Gate；资金、生产、auth、自修改系统永远人工
6. 跳转到 release 面
7. 高信号错误会自动创建或复用 requirement，并沿同一条主链进入审批、plan 与执行

#### 后端接口

1. `GET /api/requirements`
2. `POST /api/requirements`
3. `PATCH /api/requirements/{id}`
4. `POST /api/requirements/{id}/submit`
5. `POST /api/requirements/{id}/approve`
6. `POST /api/requirements/{id}/reject`
7. `POST /api/requirements/{id}/cancel`
8. `GET /api/workflows/runs`
9. `GET /api/workflows/runs/{id}`

#### 推荐使用方式

1. 标题写结果，不写动作口号
2. 描述里明确目标与约束；requirement 会先保存，随后在后台由 agent 生成轻量 acceptance brief 与 workflow 初始化 blackboard
3. requirement 必须先选择正式 `Project`
4. 路径覆盖只在高级场景使用，不再把裸 `target_project_path` 当作主输入
5. requirement submit 是 requirement 进入 declarative workflow 的唯一正式桥接点，并会创建 active workflow run
6. 不再手动创建 legacy execution run；恢复与重试由 State Machine Runner 和 Human Gate 决定
7. requirement list page 不承载常驻 intake 表单，create / edit 默认走 `Toolbar + Drawer`

### 2.2 `/requirements/:id`

#### 页面职责

需求详情页只展示 requirement 本身，不直接做执行控制和发布控制。

#### 页面布局

1. 页面收敛成单列主内容
2. 主工作区展示 intent、agent 生成的 acceptance contract 与 execution plan
3. 编辑只在未执行 requirement 上开放

#### 页面内容

1. 标题、描述、验收契约、执行计划
2. 所属项目 / source / priority
3. 顶部执行 / 发布动作
4. 仅在人工审批场景显示审批提示

#### 页面不负责

1. 运行时 telemetry 明细
2. deploy / rollback
3. 环境状态

#### 推荐使用方式

1. 先确认 intent、acceptance brief 与目标项目写对。
2. submit 后跳到 `/workflows/:id` 看状态机执行，而不是旧 execution 页面。
3. verification / repair / delivery 都必须表现为同一个 declarative workflow run 内的状态流转。
4. Agent 只在 atom 内做推理或产出结构化 payload；Harness / runner 负责状态推进和证据保存。
5. 所有 retry loop 必须有预算，超过预算进入 `awaiting_operator` 或失败终态。
6. 高风险动作永远进入 Human Gate，即使机器证据完全通过。
7. 新建需求弹层支持类似 Codex 的附件输入：可拖拽文件、粘贴截图、选择图片或文档，附件会作为 requirement context 持久化并进入后续 workflow。
8. requirement 创建后会先保存，再初始化 workflow 上下文；资产仍在生成时，需求面会显示“正在生成计划”，并禁用提交按钮。

## 3. 工作流面

#### 页面职责

工作流列表展示当前系统中的 declarative workflow run。新执行真相是 `workflow_key/current_state/status/resolution/blackboard`，不再展示 fixed execution steps 作为主形状。

#### 页面布局

1. 顶部说明 Workflow Factory / State Machine Runner 的治理边界
2. 主工作区是 active workflow run queue
3. 每个 workflow item 突出 `workflow_key`、`current_state`、`status`、`risk_level`、pending human gate
4. 详情页展示 state timeline、Blackboard 摘要、Atom invocations、Artifacts 和 Human Gates

#### 典型动作

1. 查看 workflow key 与当前状态
2. 查看 Blackboard 和 atom 证据
3. 对 pending human gate 做 `approve/reject/continue_retry`
4. 跳转到 requirement 或 release
5. 观察 `patch -> verify` loop 是否消耗 retry budget

#### 状态说明

1. 同一 requirement 任意时刻只有一个 active declarative workflow run
2. State transition 只由 deterministic runner 决定，Agent atom 只能写 structured output
3. 所有 loop 必须有 counter guard；预算耗尽进入 `awaiting_operator`
4. 高风险 atom 即使 evidence 高，也必须 human gate
5. 旧 execution API 和 fixed-step execution UI 已退役，不再作为 operator 主入口

#### 后端接口

1. `GET /api/workflows/runs`
2. `GET /api/workflows/runs/{id}`
3. `GET /api/workflows/runs/{id}/events`
4. `POST /api/workflows/runs/{id}/human-gates/{gate_id}/decide`

### 3.2 `/workflows/:id`

#### 页面职责

Workflow detail 是当前唯一 declarative workflow 主链的工作面。

#### 页面内容

1. workflow key / current state / status / resolution
2. retry counters
3. Blackboard summary
4. state transition timeline
5. atom invocations
6. artifacts
7. pending / decided human gates
8. requirement / release 跳转

#### 推荐使用方式

1. 简单任务可以只有 `execute -> done` 的最小状态机。
2. 复杂任务使用 `diagnose -> patch -> verify -> gate -> deliver/observe` 等声明式状态。
3. verification 判定失败或需修订时，关注 timeline、blackboard、atom invocation 和 command evidence。
4. `approval_blocked / manual_pause / runtime_recovery_blocked` 这类环境阻塞必须停在当前 workflow run 上等待 human gate 或恢复动作。
5. `verify_failed` 默认通过 state machine loop 回到 `patch`，复用同一个 run；自动修复 2 次仍失败后 `route_to_human`。
6. 人工选择继续重试时写入 human gate decision，然后 runner 从当前 blackboard 恢复。
7. token、branch、agent/model、文件改动和活动流，都按当前 workflow run 展示，不回退到旧 fixed steps。
8. Workflow detail 即使缺少 changed files 或 validation，也必须能看到 agent 原始输出 artifact。
9. Verification plan 是执行后的晚绑定产物；acceptance brief 只负责说明完成标准、范围约束和期望证据，不提前写死最终测试方案。
11. verification plan 中的 required commands 由 Harness 统一执行并落库为权威 evidence；execution agent 自己跑过的测试只作为参考证据，不能单独打开 PR gate
12. requirement detail 会展示 intake attachments；图片可直接预览打开，普通文件可下载查看

## 4. 发布面

### 4.1 `/releases`

#### 页面职责

Release 列表只展示当前可发布候选。

#### 页面布局

1. 顶部是 release candidate 过滤与状态说明
2. 主工作区展示候选列表
3. 每个候选右侧显示 compact release summary

#### 候选规则

只有 verification agent 判定 `passed` 的 requirement 才会进入 release candidates。

#### 后端接口

1. `GET /api/releases/candidates`

### 4.2 `/releases/:requirementId`

#### 页面职责

Release detail 负责交付与发布操作。

#### 页面布局

1. 主工作区是 release controls
2. 右侧 inspector 是当前 release record 与环境门槛
3. 底部 activity 区展示 deployment history

#### 页面内容

1. branch / commit / PR 状态
2. delivery readiness
3. deployment records
4. rollback history

#### 典型动作

1. 查看自动 prepare branch / auto PR 的结果
2. 必要时手动重试 `prepare`
3. 必要时手动重试 `open-pr`
4. `deploy-staging`
5. `deploy-production`
6. `rollback`

#### 后端接口

1. `GET /api/releases/{requirementId}`
2. `POST /api/releases/{requirementId}/prepare`
3. `POST /api/releases/{requirementId}/open-pr`
4. `POST /api/releases/{requirementId}/deploy/staging`
5. `POST /api/releases/{requirementId}/deploy/production`
6. `POST /api/releases/{requirementId}/rollback`

#### 推荐使用方式

1. 只有 verification agent 判定通过后才进入 release 面做交付
2. requirement 页只看 intent，不在那边做发布决策
3. 发布、promotion、rollback 都在 release 面统一处理

## 5. 项目面

### 5.1 `/projects`

#### 页面职责

项目列表页是正式项目中心，负责管理仓库、GitHub 与部署配置。

#### 页面内容

1. 项目标识与显示名称
2. root path
3. GitHub repo / default branch
4. deploy strategy / env label
5. 项目状态

### 5.2 `/projects/:id`

#### 页面职责

项目详情页负责查看和更新单个 Project 的基础配置与治理配置。

#### 推荐使用方式

1. 先在项目中心录入正式 Project
2. 再在 requirement 创建时选择项目
3. release / deployment 默认从项目配置读取 repo、分支和环境标签

## 6. Runtime 选择心智模型

### 6.1 Python runtime

Ops Dashboard 后端本地与生产启动都要求 Python 3.14+。推荐使用 Homebrew Python：

```bash
/opt/homebrew/bin/python3.14 -m venv /Users/cliff/workspace/agent/.venv
/Users/cliff/workspace/agent/.venv/bin/pip install -r requirements.txt
```

`scripts/local/*.sh` 与 `scripts/prod/*.sh` 会在启动前执行 `scripts/python_runtime_guard.sh`。如果当前 venv 仍是 macOS Python 3.9，脚本会提前失败并给出重建 venv 的命令，而不是等到 Pydantic import 阶段报错。

### 6.2 Backend selection

planner 和 execution runtime 已经分离。`ORCHESTRATION_BACKEND` 决定 execution runtime；`PLANNER_BACKEND` 可单独决定 plan agent / acceptance / verification 的模型入口。

常见 execution backend：

1. `openai_responses`
2. `copilot_sdk`
3. `codex_cli`
4. `codex_sdk`

常见 planner adapter：

1. `openai`
2. `claude`
3. `copilot`
4. `codex_cli`
5. `codex_sdk`

当前原则：

1. planner 只做 shape decision
2. execute 由选定 runtime 驱动
3. verification 与 deliver 由系统治理，不交给模型随意跳过

如果 `PLANNER_BACKEND` 留空，planner 会从 `ORCHESTRATION_BACKEND` 兼容推导；推荐新配置显式使用 `PLANNER_BACKEND=codex_sdk` 或 `PLANNER_BACKEND=codex_cli`。详细设计见 [Planner Adapter Architecture](design-docs/planner-adapter-architecture.md)。

`codex_sdk` 是 Codex Python SDK 的推荐演进方向，用于替代裸 `codex exec` subprocess 管理，但上线前必须保留 `codex_cli` fallback。详细设计见 [Codex Python SDK Runtime Architecture](design-docs/codex-python-sdk-runtime-architecture.md)。

Plan agent session 推荐按目标项目复用：`role_key="planner"`、`project_root=<canonical target project root>`、`requirement_id=NULL`。Execution Agent 继续按需求隔离，但同一 requirement 的 implementation 与 verification repair turns 复用同一个 runtime session，避免修复阶段重新理解上下文。详细设计见 [Plan Agent Project-Scoped Session Reuse](design-docs/plan-agent-project-scoped-session-reuse.md)。

Execution / Verification 的同 run self-repair 闭环由 [Declarative Agent Workflow Factory](design-docs/declarative-agent-workflow-factory.md) 统一表达。

Workflow Factory 是复杂执行流的新入口，用于从 human intent / desired state 生成或选择声明式 workflow spec，并把执行收敛到 State Machine YAML + Blackboard。active workflow 必须先通过 sandbox fixtures 验证并经过 human approval；高风险 atom（funds、settlement、contract、auth、production、external paid spend）永远进入 human gate。详细设计见 [Declarative Agent Workflow Factory](design-docs/declarative-agent-workflow-factory.md)。

新工作流 API：

1. `GET /api/workflows/definitions`
2. `POST /api/workflows/runs`
3. `GET /api/workflows/runs/{id}`
4. `GET /api/workflows/runs/{id}/events`
5. `POST /api/workflows/runs/{id}/human-gates/{gate_id}/decide`

Workflow 页面展示 declarative workflow run 的 state timeline、blackboard 摘要、atom invocations、artifacts 和 human gate；旧 fixed execution 页面不再作为主入口。

## 7. 错误日志页（辅助）

### 6.1 `/errors`

1. 聚合高信号错误 fingerprint
2. 展示 linked requirement / execution
3. 展示 occurrence、latest seen 和稳定性摘要
4. 展示 discovery recommendation，明确当前 fingerprint 是：
   - `auto_materialize`
   - `queue_for_operator`
   - `ignore_as_noise`

后端接口：

1. `GET /api/errors`
2. `POST /api/errors/intake`

统一 discovery 语义：

1. `/api/errors/intake` 不再自己单独决定 requirement 策略。
2. 它会先形成 `error_fingerprint` 与 `error_event`。
3. 然后由 discovery recommendation 与 system rules 决定：
   - 是否自动 materialize requirement
   - 是否只排入 operator backlog
   - 是否视为噪声忽略
4. 已 materialize 的 fingerprint 会继续进入 requirement → execution → verification → PR 主链。

### 6.2 `/errors/:fingerprintKey`

1. 查看单个错误 fingerprint 的事件证据
2. 查看 linked requirement / execution / release
3. 查看 Lark 告警发送历史
4. 查看 discovery recommendation 与当前 self-healing 决策

后端接口：

1. `GET /api/errors/{fingerprintKey}`

## 8. Lark 通知

当前外部通知统一分四路：

1. requirement / workflow notifications 群
   - 新 requirement
   - workflow run started / succeeded / low-risk failed
   - auto approval 结果
   - workflow assets ready / failed
2. alert 群
   - P0/P1 error log intake
   - runner crash / stale / retry budget exhausted
   - funds / settlement / contract / auth / production 风险
   - kill switch 或高风险 workflow failure
3. approval 群
   - human gate created
   - risk evidence gate requires human
   - manual approval required
   - approve / reject / continue_retry 回执
4. release 群
   - PR 已创建或创建失败
   - branch pushed / release ready / release blocked
   - CI / deploy / observing 结果

每条通知都必须包含：

1. 哪个服务 / 应用
2. 发生了什么
3. 什么时候发生
4. 需要做什么
5. requirement / workflow / release / errors 相关链接

Lark 只承担高信号提醒与入口跳转，完整黑板、atom invocation、transition、artifact 和 gate 真相仍以 `/workflows/:id` 为准。普通 state transition、atom success、artifact created、blackboard snapshot 不发送 Lark，只在 Workflow Detail 中展示。

通知发送采用统一队列：

1. 业务模块只写入 `notification_events`。
2. Dispatcher 按 fingerprint 更新 `notification_fingerprints`。
3. 同类告警在 cooldown 内只累计 `suppressed_count`，不重复刷群。
4. 真正发往 Lark 的记录写入 `notification_deliveries`。
5. Workflow Detail 的 Lark Notifications 区块会显示 fingerprint、occurrence、suppressed count 和 cooldown。

核心配置：

```env
OPS_NOTIFICATION_DISPATCHER_ENABLED=true
OPS_NOTIFICATION_ALERT_BURST_PER_MINUTE=5
OPS_NOTIFICATION_DEFAULT_COOLDOWN_SECONDS=900
OPS_NOTIFICATION_P0_COOLDOWN_SECONDS=300
OPS_NOTIFICATION_P1_COOLDOWN_SECONDS=900
OPS_NOTIFICATION_APPROVAL_REMINDER_SECONDS=7200
OPS_NOTIFICATION_MAX_DELIVERY_ATTEMPTS=4
```

## 8. 当前正式操作闭环

推荐操作顺序：

1. 在 `/requirements` 创建 requirement
2. 在 `/requirements/:id` 检查 intent、acceptance brief 与 workflow 初始化信息
3. `submit` requirement，低风险会自动审批并创建 declarative workflow run
4. 在 `/workflows/:id` 观察状态机、Blackboard、Atom、Human Gate 与 verification evidence
5. verification passed 后，在 `/releases/:requirementId` 做 PR / deploy / rollback
6. 如果来自错误回流，可在 `/errors` 追踪 fingerprint 与通知历史

审批标准说明：

1. 运行时“是否必须人工审核”的唯一真相是 requirement `approval_contract` 与 approval router / hard rules。
2. project policy 的 `requires_manual_approval` 只作为项目审批偏好信号，不再直接表示“当前 requirement 必须人工审核”。
3. 会强制人工审核的 hard rules 固定为：
   - `publish_or_delivery_impact`
   - `critical_incident_recovery`
   - `max_tier_execution`
   - `over_budget_execution`
   - `multi_project_high_risk_work`
4. 其余 soft rules 只会把 requirement 从 deterministic auto-approve 降级到 approval agent review，不会直接打回人工审批。

错误自修复 v1 的正式闭环：

1. 线上错误、runtime 日志、task failure、workflow incident 进入统一 discovery pipeline
2. 先形成 `error_fingerprint / bug_record`
3. discovery recommendation 决定：
   - `auto_materialize`
   - `queue_for_operator`
   - `ignore_as_noise`
4. materialized requirement 继续走 acceptance contract、execution plan、execution、verification、PR
5. verification failure 默认优先 `continue_execution`，由同一个 Execution Agent session 自循环修复
6. 自动 self-repair 达到 2 次仍失败、证据不足或风险超出范围时，才走 follow-up requirement 或人工兜底

## 9. 快速验证清单

如果你只是想判断系统是否可用，按下面做一轮最小验证：

1. 创建一条 requirement
2. 提交 requirement
3. 确认自动生成 execution plan，并进入 execution 或人工审批
4. 在执行页继续观察运行状态
5. 等待 verification agent 自动给出 verdict
6. 确认 release candidate 出现在 `/releases`
7. 打开 release detail，确认可以执行 `prepare` 和 `open-pr`

## 10. 故障排查

### 8.1 requirement 有了，但 execution 没出现

先检查：

1. requirement 是否已经 `submit`
2. 是否被人工审批 gate 卡住
3. requirement detail 里是否已有 execution 跳转

### 8.2 execution 卡住

先看：

1. execution status
2. incidents
3. runtime backend
4. validation profile

### 10.3 错误页没有看到新的错误

先检查：

1. 是否通过 `POST /api/errors/intake` 进入系统
2. `source_kind` 是否属于 `runtime_log_error / task_failure / workflow_incident`
3. fingerprint 是否被归并到了已有 requirement
4. alert webhook 是否已在配置中设置

### 10.4 错误已经入库但没有自动创建 requirement

先检查：

1. fingerprint / bug record 的 `discovery_action` 是否为 `queue_for_operator` 或 `ignore_as_noise`
2. 是否已经存在 active requirement，因此被复用而不是重复 materialize
3. 项目是否属于高风险，需要人工审批后才能真正启动 execution
4. 当前 retry budget 是否已耗尽，导致系统保守收口

### 8.3 release 里没有候选

先检查：

1. verification agent 是否判定通过
2. requirement 是否完成执行
3. release governance 是否满足项目策略

## 11. 说明

以下能力如果仍在仓库中存在，也不再是当前正式控制台主入口：

1. `/tasks`
2. `/tasks/:id`
3. `/deployments`
4. `/approvals`
5. 运营总览首页与 company review 旧页面

它们可以作为历史实现或低层支撑继续存在，但不代表当前推荐的日常操作路径。
