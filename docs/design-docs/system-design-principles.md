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
3. 禁止无限重试、无限 bugfix、无限 resume。

## 3. Verification 必须独立于 Execute

1. execute 不能自证正确。
2. validate 必须独立于 execute。
3. “代码存在”不等于“问题解决”；完成定义必须包含验证证据。
4. deliver 只能发生在 validate 成功之后。

## 4. 默认 workflow 必须最小化

1. 当前正式核心流只有：
   `intake -> execute -> validate -> deliver`
2. simple task 不得被治理框架强制扩成多步流程。
3. 复杂任务才允许展开 execution graph。
4. `research / plan / review / test / closeout` 不再是默认一等 workflow step。

## 5. Planner 是执行形状选择器，不是阶段生成器

1. planner 只负责 shape decision：
   - execution mode
   - complexity
   - validation profile
   - delivery intent
   - approval requirement
2. planner 不得强制生成固定 research/plan/closeout 仪式。
3. harness 不负责替 agent 决定执行顺序。

## 6. Requirement / Execution / Release 必须分面治理

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

## 7. Artifact 必须面向消费方

当前默认只保留最小证据集：

1. `requirement_brief`
2. `execution_record`
3. `validation_record`
4. `delivery_record`

规则：

1. 没有消费方的 artifact 不生成。
2. artifact 必须明确服务于 Requirement、Execution、Release 其中一面。
3. 禁止制造“为了阶段完整性而存在”的仪式性 artifact。

## 8. Release Candidate 只接受 Validate 成功的 Requirement

1. release candidate 不得来自未验证 requirement。
2. publish、deploy、rollback 必须在 release surface 处理。
3. requirement 面只能展示 release 摘要与跳转入口。

## 9. 服务层必须按功能面治理

1. `server/services` 不允许继续回到平铺式万能目录。
2. requirement、release、runtime、review、project policy、signal、bug intake 必须分面拆分。
3. 新服务文件 `> 500 行` 进入预警，`> 900 行` 必须拆分。
4. 每个服务分包都必须有 `README.md`，说明职责、入口、依赖边界和禁止依赖。
5. router 只能依赖 facade 或稳定公开入口，不得直接抓私有 helper。

## 10. 防膨胀工程约束

### 10.1 单一职责

1. 一个模块只能服务一个业务面。
2. requirement、release、runtime、review、signal、project policy 不得混写进同一个主文件。

### 10.2 接口隔离

1. 每个分包必须有最小公开入口。
2. `routers/` 只能依赖 facade，不得跨目录点对点抓内部函数。

### 10.3 迪米特法则

1. 禁止跨两层以上目录直接取内部实现。
2. 出现这种需要时，应补 facade 或提取公共 helper。

### 10.4 合成复用优先

1. 新能力优先通过 helper / service / policy 组合实现。
2. 默认不通过复杂继承树做扩展。

### 10.5 依赖倒转

1. 上层编排只依赖稳定 facade 和 schema。
2. 不得依赖底层实现拆分文件。

## 11. 上下文是预算，不是垃圾桶

1. 长期规则、项目 policy、会话上下文和临时证据必须分层治理。
2. 需要为 context budget、compaction 和 stale-memory verification 预留机制。
3. 不允许把未经验证的旧记忆直接继续传播为当前事实。

## 12. Runtime / Subagent 必须有生命周期

1. 所有 runtime 都必须可 start、running、pause、fail、cleanup、abort。
2. transcript、session、artifact、log 和 ownership 必须可追踪。
3. 父执行结束时，子资源必须可收口、可复盘。

## 13. 所有关键自动化都必须可观测

1. requirement、execution、release、incident、publish、rollback 都必须留下结构化证据。
2. 调度决策、熔断原因、恢复动作、operator 接管都应有日志。
3. 没有 telemetry 的自动化，不应进入默认主路径。

## 14. 治理优先于更强自主性

1. 自主性提升必须建立在 policy、validation、delivery、incident、observability 已经收口的前提上。
2. 如果治理能力不足，优先补治理，不优先补更复杂的 agent 自主决策。

## 15. 当前正式实现顺序

后续默认优先顺序为：

1. Requirement 面的意图与治理收口
2. Execution 面的最小执行闭环
3. Release 面的交付与发布闭环
4. incident / recovery 的可观察性
5. 更复杂的 execution graph 与 deterministic runtime 能力

任何新设计如果会把系统重新拉回“大而全的单页面控制台”或“固定多阶段仪式流程”，都应视为违反当前正式架构。
