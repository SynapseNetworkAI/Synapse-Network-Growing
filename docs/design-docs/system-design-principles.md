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
3. 后续新增设计默认必须复用这套约束，而不是绕开它重新做“隐式直通”能力。
