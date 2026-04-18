# Synapse Company Ops 系统设计原则

这份文档定义 `Synapse-Network-Growing` 当前的硬约束。

后续新增功能、流程、API、页面和自动化策略，默认都必须遵守这些原则。例外只能通过专门设计文档说明原因、风险和补偿机制。

## 1. 把模型当不稳定部件，不当同事

1. 不允许假设模型会持续正确、持续稳定、持续理解上下文。
2. 可靠性必须来自状态机、权限、验证、恢复、日志和预算。
3. 自动化必须以“失败也能收口”为前提。

## 2. 错误路径按主路径设计

1. 恢复不是补丁，而是主路径的一部分。
2. 每条核心执行链都必须定义失败分支、恢复分支、熔断条件和 operator 接管点。
3. 禁止无限重试、无限 self-repair、无限 resume。

## 3. Verification 必须独立于 Execute

1. execute 不能自证正确。
2. validate 必须独立于 execute，并默认由独立 verification agent 执行。
3. “代码存在”不等于“问题解决”；完成定义必须包含验证证据。
4. deliver 只能发生在 validate 成功之后。

## 4. 默认 workflow 必须最小化

1. 当前正式核心流只有：
   `intake -> execute -> validate -> deliver`
2. simple task 不得被治理框架强制扩成多步流程。
3. 复杂任务才允许展开 execution graph。
4. `research / plan / review / test / closeout` 不再是默认一等 workflow step。

## 5. Agent 主导执行，程序只做治理

1. agent 决定执行内容、研究顺序、实现路径和按需展开的复杂度。
2. 程序不替 agent 生成仪式性计划，不替 agent 规定固定执行阶段数。
3. 程序当前只拥有 5 类职责：
   - 需求治理
   - 运行时治理
   - 稳定性治理
   - 自动化编排
   - 发布治理
4. 任何新能力如果让程序重新变成“执行内容裁判”而不是“治理与守门者”，都应视为架构倒退。
5. requirement submit 是 requirement 进入 execution 的唯一正式桥接点；程序应在 submit 时完成审批判定、确保 acceptance / execution plan 可用、自动创建 execution、并在放行后自动启动。
6. 高信号错误必须自动回流到 requirement 主链，错误发现、审批、自动执行、verification、PR、release 必须保持在同一条治理链上。

## 6. Planner 是执行形状选择器，不是阶段生成器

1. planner 只负责 shape decision：
   - execution mode
   - complexity
   - validation profile
   - delivery intent
   - approval requirement
2. planner 不得强制生成固定 research/plan/closeout 仪式。
3. harness 不负责替 agent 决定执行顺序。

## 6.5 声明式复杂 Workflow 必须由确定性 Runner 治理

1. 复杂 workflow 可以由 Meta-Builder Agent 生成声明式 State Machine YAML，但只能组合受控 atom。
2. workflow 不得退回到隐藏在 Python `if-else` 中的多阶段过程式编排。
3. Agent Atom 负责推理、生成、诊断、修复建议和内容创作，但不允许直接改变 workflow state。
4. State transition 必须由 deterministic runner 基于 schema、evidence、policy、budget 和 guard 判断。
5. 所有 loop 必须有 retry budget、terminal state 和 operator fallback。
6. Agent Atom 输出必须 schema 化；解析失败最多自修一次，原始输出必须落 artifact。
7. 下游 deterministic atom 只能读取 parsed payload，不能把非结构化模型输出当作可信输入。
8. 高风险 atom 必须进入 human gate；资金、结算、合约、auth、生产部署和外部付费动作不得自动放行。

## 6.6 No Legacy Workflow Compatibility

1. 新复杂执行链的唯一真相是 declarative workflow run：`workflow_definitions`、`workflow_runs`、`workflow_state_events`、`workflow_artifacts`、`blackboard_snapshots`、`atom_invocations`、`human_gate_requests`。
2. 历史 `workflow_steps`、fixed-step orchestrator、旧 agent-first bugfix loop、旧 delivery repair loop 只允许作为删除对象或只读历史残留，不得作为新链路 fallback。
3. `WorkflowRunRow/WorkflowStepRow/active_workflow_run_id/current_plan_version` 的旧语义不再参与新执行链设计；新业务只能读取 declarative state machine 的 `workflow_key/current_state/status/resolution/blackboard`。
4. `workflow_artifacts.workflow_run_id` 必须直接外键到新 declarative run，不得再绕到旧 `ArtifactRow.workflow_run_id` 或把 execution id 塞进 artifact payload 伪关联。
5. Requirement submit 后只应创建 declarative workflow run；planner 只选择 `workflow_key` 与初始化 blackboard，不再生成固定 `research/plan/implementation/validate/closeout` steps。
6. Agent 只能写 structured output 与 artifact；state transition、retry budget、terminal state、human gate 由 deterministic runner 决定。

## 6.7 后台任务必须一等可观测

1. 任何会定期运行、后台轮询、延迟重试或自动推进系统状态的机制，都必须在 Ops Console 中可见。
2. 后台任务不能只存在于 thread、daemon、log、cron 或隐式请求副作用中。
3. 每次后台运行必须记录 run history，包括 triggered_by、dry_run、params、result、error、started_at、completed_at 和 duration。
4. 高风险 recurring workflow 默认不得 auto-start requirement、delivery、deploy、funds、auth、contract 或外部付费动作。
5. `Dry Run` 是验证 recurring workflow 配置的默认方式；`Run Now` 必须有明确确认与可追踪结果。
6. Notification Dispatcher 这类可靠性后台 loop 必须暴露 queue、dead letter、suppression、last tick 和 last error。

## 7. Requirement / Execution / Release 必须分面治理

### 6.1 Requirement

Requirement 只负责：

1. 为什么做
2. 要达到什么结果
3. 在什么约束下做

Requirement 不得直接承载：

1. 运行时 telemetry 明细
2. deploy / rollback 控制
3. 环境状态面板

### 6.2 Execution

Execution 负责：

1. agent 工作过程
2. execution graph 或 direct execute
3. validate 结果
4. incidents / pause / resume / retry

### 6.3 Release

Release 负责：

1. branch / commit / PR
2. delivery readiness
3. deployment promotion
4. rollback

凡是环境视角或发布视角能力，默认进入 release surface，不得回灌到 requirement 页面。

### 6.4 Errors（辅助治理页）

`/errors` 是稳定性治理辅助面，不是第四个主业务面。

它只负责：

1. 高信号错误事件与 fingerprint 聚合
2. linked requirement / execution / release 的追踪
3. 告警发送历史

它不得承担：

1. requirement 意图编辑
2. execution 主控制入口
3. release 主决策入口

## 7.5 Project 是正式主对象

1. Requirement 必须挂到正式 `Project`，不再把 `target_project_path` 当作用户侧主输入。
2. `Project` 是 GitHub、默认分支、部署策略、环境标签和仓库根路径的主入口。
3. `project policy` 是挂在 `Project` 上的治理子配置，不再代表项目本身。
4. Requirement 创建默认先选项目，只在高级场景允许填写 `target_project_path_override`。
5. Release / Deployment 必须以 Project 为边界执行，不得再从 requirement 零散字段拼接仓库与环境配置。

## 8. Execution 必须只有一条当前主链

1. 同一 requirement 任何时刻只允许一条当前 execution 主链。
2. `queued / running / paused / validating` 是唯一活跃 execution 状态。
3. 已完成、已失败、已验证的 run 不能再次 `start`。
4. `retry` 必须创建新的 execution run，不得复活旧 run。
5. requirement、execution、release 三面的读模型必须指向同一条当前 execution 主链。
6. 旧 execution / release 脏数据不做兼容；需要时直接重置运行态数据。

## 9. Artifact 必须面向消费方

当前默认只保留最小证据集：

1. `requirement_brief`
2. `execution_record`
3. `validation_record`
4. `delivery_record`

规则：

1. 没有消费方的 artifact 不生成。
2. artifact 必须明确服务于 Requirement、Execution、Release 其中一面。
3. 禁止制造“为了阶段完整性而存在”的仪式性 artifact。

## 10. Release Candidate 只接受 Validate 成功的 Requirement

1. release candidate 不得来自未验证 requirement。
2. publish、deploy、rollback 必须在 release surface 处理。
3. requirement 面只能展示 release 摘要与跳转入口。
4. requirement execution approval 只负责执行许可，不替代 release / deployment gate。
5. 高风险 requirement 的人工 execution approval 必须保留；它控制的是“是否允许 agent 开始高风险动作”，不能被 PR merge 替代。
6. execution approval 放行后，系统必须先在目标项目上基于最新 `main` 准备 requirement branch，再启动 execution；不得把 branch / PR 完全拖到流程末端。
7. acceptance contract 只负责定义完成标准、范围约束和期望证据；最终 verification plan 必须在 execution 完成后由 verification agent 基于真实执行证据生成，harness 不得提前写死完整测试方案。
8. verification agent 负责决定怎么验，Harness 负责权威执行 required commands 并记录 cwd、exit code、日志路径、耗时和 stdout/stderr excerpt；execution agent 自述测试结果不能单独作为最终 gate。
9. 错误发现 v1 必须优先于机会发现。
   - 本阶段只自动化 defect self-healing，不自动化新增功能发现。
   - 错误信号必须先进入统一 discovery pipeline，再决定是否 materialize requirement。
10. discovery / approval 都采用 `agent recommendation + system rules + human fallback`。
   - agent 负责理解与推荐。
   - system rules 只负责稳定硬边界。
   - 人只处理高风险、低置信度或系统无法稳定收口的 case。
11. 新状态机不再允许一个对象同时存在多个真假难辨的主状态字段。
   - `Requirement`、`ExecutionAttempt`、`Delivery`、`ApprovalDecision` 都必须只有一个 canonical `state`
   - 旧 `status / phase / resolution_path / latest_release_status` 只允许作为过渡读字段，不能继续作为写入真相
12. Declarative workflow 的目标与黑板必须可审计。
   - 原始 intent / acceptance brief 不允许被 repair 覆盖。
   - repair turn 必须从最新 verification result、command evidence 和 blackboard 派生。
   - 第二次 repair 必须读取上一次失败结果，而不是简单重跑旧 prompt。
13. 自主修复必须有严格预算。
   - 所有 workflow loop 必须有 counter guard。
   - verification failure 默认由同一个 workflow run 自循环修复，自动 self-repair 最多 2 次。
   - self-repair 达到预算仍失败时必须 `route_to_human`；人工继续 retry 也复用同一个 run / session，并单独计入 manual retry。

## 11. 服务层必须按功能面治理

1. `server/services` 不允许继续回到平铺式万能目录。
2. requirement、release、runtime、review、project policy、signal、bug intake 必须分面拆分。
3. 新服务文件 `> 500 行` 进入预警，`> 900 行` 必须拆分。
4. 每个服务分包都必须有 `README.md`，说明职责、入口、依赖边界和禁止依赖。
5. router 只能依赖 facade 或稳定公开入口，不得直接抓私有 helper。

## 12. 防膨胀工程约束

### 12.1 单一职责

1. 一个模块只能服务一个业务面。
2. requirement、release、runtime、review、signal、project policy 不得混写进同一个主文件。

### 12.2 接口隔离

1. 每个分包必须有最小公开入口。
2. `routers/` 只能依赖 facade，不得跨目录点对点抓内部函数。

### 12.3 迪米特法则

1. 禁止跨两层以上目录直接取内部实现。
2. 出现这种需要时，应补 facade 或提取公共 helper。

### 12.4 合成复用优先

1. 新能力优先通过 helper / service / policy 组合实现。
2. 默认不通过复杂继承树做扩展。

### 12.5 依赖倒转

1. 上层编排只依赖稳定 facade 和 schema。
2. 不得依赖底层实现拆分文件。

## 13. 前端必须是 Enterprise Workbench，而不是平铺卡片后台

1. 默认禁止整页卡片化；卡片只能用于独立对象，而不是整页每个区块的万能容器。
2. 页面必须先有工作台骨架，再有组件。标准骨架包括：
   - shell
   - page header
   - primary workspace
   - secondary inspector
   - activity/feed rail
   - command bar / filters
3. 一个页面只能有一个主焦点，不得把表单、列表、摘要、状态、日志做成同权重平铺块。
4. Requirement、Execution、Release 三面必须使用各自独立的页面模板，不得继续复用万能卡片页模板。
5. 颜色只承担状态和强调，不承担大面积装饰；工作台不是营销页。
6. 新 UI 必须优先复用统一的 workbench shell、section、inspector、activity feed 和 state badge 结构。
7. 列表页默认不承载常驻 create/edit 大表单；新增与编辑应优先采用 `Toolbar + Drawer` 模式。
8. Requirement create 只采集最小 intent；acceptance 默认由 agent 在创建后生成，并允许在详情页修订。
9. 禁止继续使用浏览器原生 `alert / confirm`；危险操作必须使用统一确认弹窗，成功/失败反馈优先使用统一 toast。

## 14. 前端防回潮约束

1. UI 变更 PR 必须说明页面属于 Requirement、Execution、Release 哪一面。
2. UI 变更 PR 必须说明是否复用了 workbench 模板与 token。
3. 如果继续引入 dashboard-card mosaic、同权重白卡拼盘、装饰性 chips/pills，应直接视为 review 拒绝项。
4. 前端 token 必须同时支持 surface hierarchy、text hierarchy、stroke hierarchy、state colors 和 layout tokens。
5. 如果在列表页重新引入长驻内联 create/edit 表单，而没有明确的 quick-edit 例外说明，应直接视为 review 拒绝项。

## 15. 上下文是预算，不是垃圾桶

1. 长期规则、项目 policy、会话上下文和临时证据必须分层治理。
2. 需要为 context budget、compaction 和 stale-memory verification 预留机制。
3. 不允许把未经验证的旧记忆直接继续传播为当前事实。

## 16. Runtime / Subagent 必须有生命周期

1. 所有 runtime 都必须可 start、running、pause、fail、cleanup、abort。
2. transcript、session、artifact、log 和 ownership 必须可追踪。
3. 父执行结束时，子资源必须可收口、可复盘。
4. 当 execution 运行态失真时，使用 `/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_execution_runtime.py --yes` 直接重置，不保留旧脏数据兼容逻辑。
5. 当需要切换到新的 canonical workflow 状态机并丢弃历史 workflow 数据时，使用 `/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_workflow_state.py --yes`。
6. verification/manual review 不再是正式主链的一部分；execution 完成后应自动派发 verification agent，并以其 verdict 作为 release 前唯一正式验证信号。
6. verification passed 后应默认自动推进 commit / push / open PR；PR merge 视为最终人工把关。

## 17. 所有关键自动化都必须可观测

1. requirement、execution、release、incident、publish、rollback 都必须留下结构化证据。
2. 调度决策、熔断原因、恢复动作、operator 接管都应有日志。
3. 没有 telemetry 的自动化，不应进入默认主路径。
4. requirement、alert、approval、release 四类对外通知必须使用统一 envelope，至少包含服务、事件类型、优先级、风险等级、发生时间、发生了什么、下一步动作和关联链接。
5. 普通 state transition、atom success、artifact created、blackboard snapshot 不得发送 Lark，只能进入 Ops Console 可观测面；P0/P1 才能进入 alert 群，human gate 才能进入 approval 群。

## 18. Python 日志必须结构化

1. workspace 内的 Python 服务默认使用 `structlog + logging`，不继续把自由文本日志作为主输出。
2. 主输出必须是 `stdout` JSON；本地文件日志只作为备份，采用 `JSONL` 并按天切分。
3. 文件轮转默认按天执行并保留 14 天，除非专门设计文档说明不同保留策略。
4. 新增日志时必须优先绑定链路字段：`request_id`、`task_id`、`requirement_id`、`execution_id`、`release_id`、`fingerprint_key`。
5. 每条结构化日志至少包含基础字段：`ts`、`level`、`event`、`service`、`env`、`logger`、`message`。
6. 运行结果类日志应优先补充：`outcome`、`status`、`duration_ms`、`error_type`、`error_message`。
7. 不允许记录 token、secret、webhook url、authorization header 等敏感信息；traceback 可以保留，但必须避免把敏感配置直接拼进错误消息。
8. 当前阶段先按“各服务内实现、同一规范”落地，不假设已经存在可复用的共享 Python logging 包。

## 19. 正式功能列表必须同步维护

1. 系统当前正式具备的功能，必须维护在 `docs/design-docs/current-feature-inventory.md`。
2. 每次新增、删除、重构正式功能时，必须同步更新功能清单。
3. 功能清单描述的是“当前真实能力”，不是候选想法、计划或 bugfix 草稿。
4. 如果代码已经变更，但功能清单没有同步更新，应视为设计文档未完成。

## 20. 治理优先于更强自主性

1. 自主性提升必须建立在 policy、validation、delivery、incident、observability 已经收口的前提上。
2. 如果治理能力不足，优先补治理，不优先补更复杂的 agent 自主决策。

## 21. 当前正式实现顺序

后续默认优先顺序为：

1. Requirement 面的意图与治理收口
2. Execution 面的最小执行闭环
3. Release 面的交付与发布闭环
4. incident / recovery 的可观察性
5. 更复杂的 execution graph 与 deterministic runtime 能力

任何新设计如果会把系统重新拉回“大而全的单页面控制台”或“固定多阶段仪式流程”，都应视为违反当前正式架构。
