# Synapse Company Ops 系统设计原则

这份文档定义 `Synapse-Network-Growing` 后续设计与实现的硬约束。

后续新增功能、workflow、runtime、UI、测试和自动化策略，**不得违背这些原则**。如果某个实现需要例外，必须在设计文档里明确写出原因、风险和补偿机制。

## 1. 把模型当不稳定部件，不当同事

1. 不允许假设模型会持续正确、持续记住上下文、持续做出稳定判断。
2. 可靠性必须来自 harness：状态机、权限、恢复、验证、回滚、日志和预算。
3. 所有自动化能力都要以“出错也可收口”为前提。

## 2. 错误路径按主路径设计

1. 错误恢复不是异常补丁，而是主路径的一部分。
2. 所有关键 workflow 都必须定义失败分支、恢复分支、熔断条件和 operator 接管点。
3. 不允许出现无限重试、无限 bugfix、无限 resume 这类无预算循环。

## 3. Verification 必须独立于 Implementation

1. implementation 不能自证正确。
2. review / validation / closeout 必须是独立阶段，且默认对 implementation 保持怀疑。
3. “代码存在”不等于“问题解决”；完成定义必须包含验证证据。
4. harness 负责定义验证流程与治理边界，不负责替模型预判“这次应该改文档还是改代码”。
5. requirement 负责给出目标、约束和目标项目；具体改动形态与步骤展开默认由 plan 模型决定。

## 4. 多代理的目标是隔离不确定性

1. 多代理不是堆 worker 数量，而是分离 research、synthesis、implementation、verification 的职责。
2. 各阶段默认隔离上下文、记忆和可变状态，只有明确声明的结果才允许共享。
3. coordinator / orchestrator 必须负责综合，不得把“理解责任”继续外包给下游 worker。

## 5. Runtime / Subagent 必须有生命周期

1. 所有 runtime / subagent 都必须有 start / running / stop / cleanup / abort 传播语义。
2. 要能追踪 transcript、session、artifact、log 和 ownership。
3. 父任务结束时，子任务和后台资源必须可清理、可回收、可复盘。

## 6. 上下文是预算，不是垃圾桶

1. 长期规则、项目 policy、Agents-Memory、会话上下文和临时证据必须分层治理。
2. 需要为 context budget、compact、stale memory verification 预留产品与 runtime 机制。
3. 不允许把未经验证的旧记忆直接当当前事实继续传播。

## 7. 权限是系统器官，不是附属选项

1. shell、git、network、publish、rollback、delete 等高风险能力必须明确授权。
2. capability matrix 和 interrupt policy 必须先于更强自动化能力落地。
3. 越危险的能力，越不能走默认直通。
4. project policy 必须显式声明：
   `shell_access`、`git_read`、`git_write`、`git_push`、`network_access`、`publish`。
5. interrupt policy 必须显式声明：
   哪些动作需要 operator confirmation，哪些事件要自动暂停，哪些事件要自动终止。
6. workflow step 不得隐式继承高风险能力；必须在 planner 输出和 step policy 中可见、可追踪。

## 8. 所有关键自动化都必须可观测

1. requirement、workflow、task、signal、review、publish、rollback 都要有事件日志。
2. 调度决策、熔断原因、恢复动作、operator 接管都应留下结构化证据。
3. 没有 telemetry 的自动化，不应进入默认主路径。

## 9. 先让系统可治理，再让系统更自主

1. 自主性提升必须建立在 policy、validation、delivery、incident 和 observability 已经收口的前提上。
2. 如果治理能力不够，优先补治理，不优先补“更聪明”的自动化。
3. autonomy mode 应始终受 policy、budget 和 operator review 约束。

## 10. 后续实现优先顺序

当前约定的实现顺序如下：

1. 把 `research + synthesis` 显式加进 requirement workflow。
2. 给 tool / shell / git / publish 做 capability matrix 和 interrupt policy。
3. 做 context budget + compact + stale memory verify。
4. 把 runtime / subagent lifecycle 做成 artifacts 和 telemetry。
5. 把 recovery narrative / incident taxonomy 做到详情页和 signal 里。

当前状态：

1. `research + synthesis` 已落地。
2. capability matrix + interrupt policy 已落地到 `project policy -> planner -> workflow step -> delivery contract` 链路。
3. `context budget + compact + stale memory verify` 已落地到 `planner -> workflow step -> orchestrator -> artifacts -> requirement detail` 链路。
4. `runtime / subagent lifecycle` 已落地到 `task logs -> runtime state -> workflow artifacts -> requirement detail` 链路。
5. `recovery narrative / incident taxonomy` 已落地到 `failure artifacts -> unified incident view -> requirement detail / optimization signals` 链路。
6. 后续新增设计默认必须复用这套约束，而不是绕开它重新做“隐式直通”能力。

## 11. Context Governance 落地要求

为了保证第 6 条原则不是停留在口号层，后续所有 workflow / runtime 设计都要满足下面这些实现要求。

### 11.1 每个 workflow step 都必须声明 context policy

至少应显式声明：

1. `max_prompt_chars`
2. `compact_after_chars`
3. `max_artifact_body_chars`
4. `max_handoff_chars`
5. `stale_after_minutes`
6. `stale_sensitive_artifact_types`
7. `block_on_stale_memory`

不允许再使用“默认把所有 artifact 和历史描述拼进 prompt”这种隐式上下文策略。

### 11.2 Compact 必须是确定性的

1. compact 的输入来源、截断规则和摘要结构必须可复盘。
2. compact 不是任意删减，而是按照 requirement / policy / handoff / artifact 分层收敛。
3. compact 结果必须留下 artifact 证据，便于 operator 追查“为什么这次 agent 看到的是这一版上下文”。

### 11.3 Stale Memory Verify 必须先于 dispatch

1. stale memory verification 必须发生在 step dispatch 前，而不是失败后补做。
2. 发现陈旧上下文时，默认先阻断 step，再转 operator review。
3. `implementation`、`review`、`test` 这类关键阶段默认应开启 `block_on_stale_memory`。

### 11.4 Context Governance 必须可见

1. requirement detail 必须能看到当前 step 的 context policy。
2. requirement detail 必须能看到最近一次 `context_compaction` 的结果。
3. requirement detail 必须能看到最近一次 `stale_memory_verification` 的状态与发现。

### 11.5 后续能力不得绕开这套治理

后续新增的 runtime、subagent、memory、scheduler、signal、incident 模块：

1. 不得绕开 step-level context policy。
2. 不得绕过 compact artifact。
3. 不得省略 stale memory verification。

## 12. Runtime / Subagent Lifecycle 落地要求

为了保证第 5 条原则可执行，运行期治理必须满足下面这些要求。

### 12.1 生命周期必须有结构化证据

每个 workflow step 对应的 runtime，至少要能记录这些阶段：

1. `dispatch_requested`
2. `running`
3. `waiting_approval`
4. `completed`
5. `failed`
6. `paused`

这些状态不能只存在于日志字符串里，必须沉淀成 artifact。

### 12.2 Telemetry 必须汇总 subagent 事件

1. runtime backend / session id / selected agent 必须可见。
2. subagent 的 selected / started / completed / failed 计数必须可追踪。
3. 最近 runtime event 必须可回放到 requirement 详情页和后续 incident / signal 流程。

### 12.3 Cleanup 与 abort propagation 必须可复盘

1. pause / cancel / abort 时，要能看到 cleanup 何时被请求。
2. 如果 runtime backend 支持外部 state，state snapshot 也应进入 telemetry。
3. operator 需要能从 artifact 判断“这次是正常结束，还是被中断收口”。

## 13. Recovery Narrative / Incident Taxonomy 落地要求

为了保证错误路径是真正的主路径，事故与恢复信息必须满足下面这些要求。

### 13.1 Incident taxonomy 必须统一

不能让 `bug_report`、`capability_interrupt`、`stale_memory_verification`、`bugfix_circuit_breaker`、`runtime_lifecycle` 各说各话。

后续设计必须把这些证据归一到统一 incident 视图，至少包含：

1. `incident_family`
2. `incident_code`
3. `severity`
4. `recovery_status`
5. `recommended_action`

### 13.2 Recovery narrative 必须面向 operator

1. narrative 要回答“发生了什么、为什么值得停下来、下一步该怎么处理”。
2. narrative 不能只是把原始错误字符串复读一遍。
3. incident summary 要能直接进入 requirement detail、optimization signal 和 company review。

### 13.3 Signal 必须能读 incident

1. optimization signal 不只看 bug / blocker / approval，也要能看 workflow/runtime/context incident。
2. signal 里的 taxonomy 与 detail 页必须一致，不能出现两套分类规则。
3. incident signal 默认应导向 recovery / stabilization 类型 requirement，而不是把所有事故都粗暴映射成“修 bug”。
