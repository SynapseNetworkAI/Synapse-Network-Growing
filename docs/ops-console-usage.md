# Synapse Ops Console 使用说明

本文面向 `http://localhost:9700/` 的操作台使用者。

目标有 3 个：

1. 介绍每个页面模块的功能与典型使用方式。
2. 说明整套系统应该如何从首页一路使用到 requirement、task、approval 和回流闭环。
3. 给出一套可以直接照着执行的可用性验证清单，帮助判断当前系统是否真的可用。

推荐把 Synapse Ops Console 理解成一条闭环：

```text
Company Review
→ Optimization Signals
→ Requirement Intake / Planning
→ Workflow Execution
→ Validation / Delivery / Publish
→ Incident / Signal / Next-Cycle Bundle 回流
```

如果你只是想快速判断系统现在能不能用，先看本文的：

1. `6. 系统可用性验证清单`
2. `7. 快速故障排查`

## 1. 页面总览

当前操作台的核心页面有：

1. `/` 组织架构与公司级 review
2. `/requirements` 需求池
3. `/requirements/:id` 需求详情
4. `/optimization-signals` 优化信号
5. `/project-policies` 项目策略与 onboarding
6. `/tasks` 任务看板
7. `/tasks/:id` 任务详情
8. `/approvals` 审批中心

建议按下面的心智模型来理解它们：

1. 首页看“公司现在最该做什么”。
2. 需求池看“哪些事情已经被系统正式接管”。
3. 需求详情看“某件事是怎么被规划、执行、验证、交付的”。
4. 优化信号看“系统自动发现了哪些问题和优化机会”。
5. 项目策略看“系统在每个仓库里被允许做什么”。
6. 任务看板和任务详情看“低层执行到底发生了什么”。
7. 审批中心看“哪些高风险动作需要人来拍板”。

## 1.1 Runtime 选择心智模型

当前系统的 planner 和 task execution 都由 `ORCHESTRATION_BACKEND` 决定。

最常见的三种运行方式是：

1. `openai_responses`
   用 OpenAI API 做 planner + execution
2. `copilot_sdk`
   用 Copilot SDK 做 planner + execution
3. `codex_cli`
   用本机 `codex exec` 做 planner + execution

如果你看到：

1. requirement 规划阶段还在打另一种 provider
2. task runtime backend 和你预期的不一致

优先检查后端启动时真实读取到的 `ORCHESTRATION_BACKEND`，不要先怀疑前端页面。

## 2. 各页面模块功能与使用方式

## 2.1 首页 `/`

### 模块功能

首页是公司级 operating review 面板，用来看整个 portfolio 当前在发生什么。

### 读取后端

1. `GET /api/org`
2. `GET /api/dashboard/stats`
3. `GET /api/company-review`
4. `POST /api/company-review/{id}/materialize-bundle`
5. `GET /api/recurring-workflows`
6. `POST /api/recurring-workflows/{workflow_key}/run`

### 你能做什么

1. 看组织图和 Agent 分组。
2. 看任务、审批、活跃 requirement 等统计。
3. 看 incidents、next-cycle recommendations、requirement bundle。
4. 运行 daily / weekly ritual。
5. 把下一周期推荐 bundle 直接 materialize 成真实 requirement。

### 推荐使用方式

1. 先看 `portfolio summary` 判断哪里最堵。
2. 再看 `Incidents`，按 `incident_family / incident_code / recovery_status` 识别当前 portfolio 最危险的问题类型。
3. 再看 `Next Cycle Recommendations`，确认最值得优先处理的是 requirement、signal 还是 incident。
4. 最后看 `Next Cycle Requirement Bundle` 和 `Operator Review Package`。
5. 如需更新 review，运行 `weekly_operating_review` ritual，而不是手动刷新单独快照。
6. 确认后点 `生成 Bundle`，把推荐项放进需求池。

## 2.2 需求池 `/requirements`

### 模块功能

需求池是系统的顶层入口。所有重要工作都应该先变成 requirement，再进入规划、执行、验证和交付。

### 读取后端

1. `GET /api/requirements`
2. `GET /api/requirements?sort=score`
3. `GET /api/requirements/scheduler`
4. `POST /api/requirements/queue/advance`
5. `POST /api/requirements`
6. `PATCH /api/requirements/{id}`
7. `DELETE /api/requirements/{id}`
8. `POST /api/requirements/{id}/start`
9. `POST /api/requirements/{id}/pause`
10. `POST /api/requirements/scheduler/rebalance`

### 你能做什么

1. 新建 requirement。
2. 优先从项目策略里直接选择目标项目；不明确时可以留空让系统自动路由。
3. 指定依赖关系。
4. 通过智能排序看当前最值得做的需求。
5. 用顶部搜索框按 requirement 标题、项目路径、`source_ref` 或 requirement id 搜索。
6. 触发 scheduler、queue advance、rebalance。
7. 暂停、恢复、编辑、删除 requirement。

### 推荐使用方式

1. 先确认需求标题写的是“结果”，不是“动作”。
2. 描述里尽量包含目标、约束、验收条件、影响项目。
3. 明确目标仓库时，优先勾选受管项目策略；只有高级场景再手动补充路径。
4. 不明确时留空让系统自动路由。
5. 通过排序和搜索先找到当前最有价值的 requirement，再进入详情页。

## 2.3 需求详情 `/requirements/:id`

### 模块功能

需求详情页是 requirement 的执行面板，负责看 workflow、validation、delivery、artifacts 和 bugfix 闭环。

### 读取后端

1. `GET /api/requirements/{id}`
2. `GET /api/requirements`
3. `POST /api/requirements/{id}/start`
4. `POST /api/requirements/{id}/pause`
5. `POST /api/requirements/{id}/revise`
6. `POST /api/requirements/{id}/publish`

### 你能做什么

1. 看当前 requirement 的状态、依赖、目标项目。
2. 看 workflow run 和 step 执行情况。
3. 看 validation plan、manual checks、automated checks。
4. 看 Context Governance，包括当前 step 的 context policy、最近一次 compaction 和 stale memory verification。
5. 看 Runtime Lifecycle，包括 runtime backend / session / selected agent、recent runtime events、subagent 计数。
6. 看 Recovery Narrative & Incidents，理解为什么 requirement 被阻断、暂停或转 incident。
7. 看 artifacts，包括 implementation plan、validation plan、bug report、context_compaction、stale_memory_verification、runtime_lifecycle、runtime_telemetry。
8. 发起修订。
9. 在满足 release gate 时执行 publish。

### 推荐使用方式

1. 先确认 requirement 本身描述是对的。
2. 再看 workflow 是否合理。
3. `Steps` 面板里前两步通常是 `Research context → Synthesize plan`，中间 implementation 子步骤的数量、标题和作用域默认由 plan 模型决定，而不是由 harness 固定写死。
4. `planning_mode` 默认优先走 agent full-plan；只有 agent 无法产出结构化 step JSON 时，才会退回 generic fallback。
5. target project 的顺序默认按 requirement 原样保留，不再由 harness 自动改写“主仓”；模型会在这些目标项目范围内决定改代码、改文档或混合改动。
6. review/test 会结合实现阶段产出的 `project_change_summary` 看本次到底改到了哪些项目，再决定验证重点。
7. 再看 Context Governance，确认 agent 看到的上下文没有失控，也没有吃到陈旧记忆。
7. 再看 Runtime Lifecycle，确认 runtime/backend/session/subagent 没卡死。
8. 再看 `Recovery Narrative & Incidents`，确认系统给出的事故分类和恢复建议是否合理。
9. 最后才看 validation 与 delivery gate，决定是否继续执行、re-plan 或 publish。

## 2.4 优化信号 `/optimization-signals`

### 模块功能

这个页面用来管理系统自动发现的问题与优化机会。

### 读取后端

1. `GET /api/optimization-signals`
2. `POST /api/optimization-signals/refresh`
3. `POST /api/optimization-signals/auto-intake`
4. `POST /api/optimization-signals/{id}/create-requirement`
5. `POST /api/optimization-signals/{id}/dismiss`

### 你能做什么

1. 刷新 signal。
2. 看 signal 的 score、severity、project、evidence。
3. 看 workflow incident 派生出的 recovery narrative。
4. 手动把 signal 转成 requirement。
5. 让系统自动 intake 当前最值得做的 signal。
6. dismiss 明显不值得跟进的 signal。

### 推荐使用方式

1. 当系统反复出 bug、审批摩擦、交付阻塞或上下文事故时，先看这里。
2. 尽量把“问题”转成“可治理的 requirement”，不要直接跳到 task 层临时修。

## 2.5 项目策略 `/project-policies`

### 模块功能

这个页面负责定义“系统对每个项目可以做什么，不可以做什么”。

### 读取后端

1. `GET /api/project-policies`
2. `GET /api/project-onboarding`
3. `POST /api/project-onboarding`
4. `PATCH /api/project-policies/{id}`

### 你能做什么

1. onboarding 新项目。
2. 定义项目根路径。
3. 定义允许写入与禁止写入范围。
4. 定义 required checks。
5. 设置 capability matrix：`shell / git_read / git_write / git_push / network / publish`
6. 设置 interrupt policy：哪些动作要人工确认、哪些事件自动暂停、哪些事件自动终止。
7. 设置 release mode、manual approval、autonomy mode。
8. 设置 scheduler weight、max parallel requirements、budget。
9. 删除不再需要的自定义项目策略。

### 推荐使用方式

1. 新项目不要直接进需求池，先做 onboarding。
2. 先补齐 docs、validation commands、write scope、forbidden scope、release policy。
3. 默认先保守配置 `git_push` 和 `publish`，等链路跑顺后再放开。
4. 删除策略前，先确认没有 active requirement 仍指向该项目；默认内置策略不能直接删除，建议改成 `disabled`。

### backend 配置建议

如果你要让整套系统走本机 Codex，而不是 OpenAI API：

```env
ORCHESTRATION_BACKEND=codex_cli
LLM_PROVIDER=codex
LLM_MODEL=gpt-5-codex
CODEX_CLI_MODEL=gpt-5-codex
```

这时：

1. requirement 的 planner full-plan 会直接调用 `codex exec`
2. task runtime 也会直接调用 `codex exec`
3. 任务详情页里的 `runtime backend` 会显示 `codex_cli`

## 2.6 任务看板 `/tasks`

### 模块功能

任务看板是 workflow step 的兼容执行层，用来看具体执行任务，而不是业务目标本身。

### 读取后端

1. `GET /api/tasks`
2. `GET /api/agents`
3. `GET /api/skills`
4. `POST /api/tasks`
5. `POST /api/tasks/suggest-execution`
6. `POST /api/tasks/{id}/run`
7. `POST /api/tasks/{id}/retry`
8. `POST /api/tasks/bulk-retry`
9. `GET /api/tasks/{id}/logs`

### 你能做什么

1. 看任务分页、搜索、筛选。
2. 按项目、Agent、状态查看任务。
3. 新建任务。
4. 让系统推荐最合适的执行 Agent 和 skill。
5. 运行、重试、批量重试任务。
6. 看运行日志和异常。

### 推荐使用方式

1. 调 runtime 或 Agent 执行行为时用它。
2. 排查某个 workflow step 为什么失败时用它。
3. 如果你处理的是业务目标、交付结果或 bugfix 闭环，优先去 requirement 页面，而不是直接沉到 task。

## 2.7 任务详情 `/tasks/:id`

### 模块功能

任务详情页是单个 task 的证据面板。

### 读取后端

1. `GET /api/tasks`
2. `GET /api/tasks/{id}/logs`
3. `GET /api/tasks/{id}/history`
4. `GET /api/tasks/{id}/file-changes`
5. `GET http://localhost:10100/api/search`

### 你能做什么

1. 看任务状态和执行时长。
2. 看完整日志。
3. 看 retry history。
4. 看文件 diff。
5. 看 Agents-Memory 召回结果。
6. 从任务跳回上游 requirement。

## 2.8 审批中心 `/approvals`

### 模块功能

审批中心负责处理需要人工决策的执行结果。

### 读取后端

1. `GET /api/approvals`
2. `POST /api/approvals/{id}/decide`
3. `POST /api/approvals/bulk-decide`

### 你能做什么

1. 查看待审批项。
2. 单个 approve / reject。
3. 批量 approve / reject。
4. 填审批意见。

### 推荐使用方式

审批应该只覆盖高风险边界，而不是代替普通执行。

## 3. 系统如何使用

如果你是 operator，推荐按下面的顺序使用系统：

1. 先打开首页 `/`，看 company review，理解当前 portfolio 的 bottleneck、incident 和 next-cycle recommendation。
2. 去 `/optimization-signals`，看系统自动发现的 bug、delivery blocker、manual override、workflow incident。
3. 去 `/project-policies`，确认目标项目的 policy、capability、interrupt policy 和 validation commands 是完整的。
4. 去 `/requirements`，把高价值工作正式纳入 requirement pool。
5. 打开 `/requirements/:id`，确认 workflow、validation、delivery、context governance、runtime lifecycle 和 incident narrative。
6. 需要低层排障时，再去 `/tasks` 和 `/tasks/:id`。
7. 有高风险动作或 operator gate 时，去 `/approvals` 做决策。
8. requirement 关闭、发布或失败后，再回首页看 company review 是否已更新，signal 和 incident 是否已经收敛。

## 4. 为什么 `/requirements` 页面看起来没有需求

先说结论：

1. 当前本地数据库里的 `requirements` 表并不为空。
2. `/requirements` 页“看起来没有需求”，更像是接口响应慢或失败，而不是数据不存在。
3. 当前页面对加载异常的提示不够明显，所以用户容易误判成“需求池为空”。

### 4.1 当前本地数据事实

以当前本机环境为例，`server/ops.db` 里实际有 44 条 requirement：

```bash
sqlite3 /Users/cliff/workspace/agent/Synapse-Network-Growing/server/ops.db 'select count(*) from requirements;'
```

返回值是：

```text
44
```

也就是说，需求池的数据源本身是有内容的。

### 4.2 `/requirements` 页面真正依赖的后端接口

需求池页面不是只读一条接口，它在加载时会同时做这几件事：

1. `GET /api/requirements?sort=score`
   读取需求列表。
2. `GET /api/requirements/scheduler`
   读取多项目调度面板。
3. `POST /api/requirements/queue/advance`
   首屏自动尝试推进队列，启动下一个可执行 requirement。

其中真正决定“需求列表能不能显示”的关键接口是：

```text
GET /api/requirements?sort=score
```

### 4.3 当前本机观察到的问题

同样是当前这份数据：

1. 直接在后端 Python 进程内调用 `list_requirements(sort="score")`，约 4.5 秒可以算出 44 条 requirement。
2. 但通过 HTTP 访问 `http://127.0.0.1:9600/api/requirements?sort=score`，8 秒内没有收到任何响应字节。

也就是说，页面上“没有需求”的更准确解释是：

```text
需求列表接口响应过慢或卡住，前端没有把这个错误明确展示出来，
于是用户感知成了“需求池为空”。
```

### 4.4 如何快速排查

先检查数据库里是否真的没有 requirement：

```bash
sqlite3 /Users/cliff/workspace/agent/Synapse-Network-Growing/server/ops.db 'select count(*) from requirements;'
```

再检查后端接口是否超时：

```bash
curl -sS -m 8 -w '\nHTTP %{http_code} in %{time_total}s\n' 'http://127.0.0.1:9600/api/requirements?sort=score'
```

如果这里超时或拿不到 `200`，那页面空白就不是数据问题，而是接口问题。

再确认本地服务是否正常启动：

```bash
cd /Users/cliff/workspace/agent/Synapse-Network-Growing
sh scripts/local/start.sh
cd dashboard
npm run dev
```

### 4.5 还要注意的一点

需求池显示的是 `requirements`，不是 `tasks`，也不是 `optimization_signals`。

所以：

1. `tasks` 很多，不代表需求池一定很多。
2. `optimization_signals` 很多，也不代表它们已经自动转成 requirement。
3. 只有真正创建到 `requirements` 表里的对象，才会出现在 `/requirements`。

## 5. 需求详情重点面板说明

## 5.1 Runtime Lifecycle 面板怎么用

这个面板主要回答 3 个问题：

1. 当前 step 的 runtime 现在在哪个阶段
2. 它到底跑在哪个 backend / session / selected agent 上
3. 最近是哪些 runtime / subagent 事件导致它变成现在这个状态

如果你看到：

1. `phase = dispatch_requested`
2. 很久没有进入 `running`

优先怀疑 dispatch / runtime bridge。

如果你看到：

1. `phase = running`
2. recent events 长时间只有 resume / heartbeat，没有 completed

优先怀疑 session 卡住、tool 卡死或 worker 无法收口。

如果你看到：

1. `phase = paused`
2. runtime state 里出现 cleanup / abort 相关信息

说明 requirement 是被系统或 operator 主动收口，而不是正常完成。

### Recovery Narrative & Incidents 面板怎么用

这个面板会把 requirement 里最近的重要事故归类出来，当前会覆盖：

1. verification failure
2. capability/policy interrupt
3. stale memory block
4. bugfix circuit breaker
5. runtime failure / abnormal pause

推荐阅读顺序：

1. 先看 `incident_family / incident_code`，判断这是验证问题、治理问题、上下文问题还是运行期问题。
2. 再看 `recovery_status`，判断当前应该继续自动修复、重新规划，还是转 operator review。
3. 最后看 `recommended_action`，决定是 revise、re-plan、修 policy，还是处理 follow-up incident requirement。

### 当 requirement 被 stale memory 阻断时怎么办

如果详情页里看到：

1. `stale_memory_verification.status = stale`
2. 当前 step 状态是 `blocked`
3. requirement 状态变成 `blocked`

说明系统判断当前上下文已经不可靠，主动拦住了继续执行。

推荐处理顺序：

1. 先看 `stale_memory_verification` 里的 findings，确认是哪个 artifact 或 handoff 失效。
2. 如有必要，先 revise requirement 或重新生成 plan。
3. 确认最新 plan / policy / requirement 内容已经稳定后，再重新 start。
4. 不要直接忽略这个阻断继续硬跑，否则很容易把旧记忆当成当前事实。

## 5.2 Runtime 配置与 OpenAI 切换

如果你现在已经不用 Copilot，而是要让系统走 OpenAI runtime，最重要的是把 provider、model、execution mode 和 orchestration backend 这 4 个键对齐。

推荐配置：

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_EXECUTION_MODE=session
ORCHESTRATION_BACKEND=openai_responses
OPENAI_API_KEY=你的真实 key
```

还建议保留 runtime 告警：

```env
OPS_RUNTIME_AUTH_ALERTS_ENABLED=true
OPS_LARK_BOT_WEBHOOK_URL=你的 Lark webhook
OPS_LARK_BOT_KEYWORD=告警
```

### 常见误配

1. `LLM_PROVIDER` 想用 `openai`，但 `ORCHESTRATION_BACKEND` 还停在 `copilot_sdk`
   结果：系统仍会继续派发 Copilot worker。
2. `LLM_MODEL=openai`
   结果：这不是模型名，而是 provider 名；应改成真实模型 id，例如 `gpt-4o`。
3. `OPENAI_API_KEY` 为空
   结果：即使 provider 和 backend 都改对了，runtime 仍无法真正执行。

### 切换后怎么验证

1. 重启后端：

```bash
cd /Users/cliff/workspace/agent/Synapse-Network-Growing
./scripts/local/restart.sh
```

2. 看启动日志里 `orchestration_backend` 是否已经变成 `openai_responses`。
3. 新建或启动一个 requirement。
4. 去 `/tasks` 或 `/requirements/:id` 看 `runtime backend` 是否显示 `openai_responses`，而不是 `copilot_sdk`。
5. 如果仍看到 `copilot_sdk`，优先检查 `.env` 里是否还残留 `ORCHESTRATION_BACKEND=copilot_sdk`。

## 6. 系统可用性验证清单

如果你现在想验证 `http://localhost:9700/` 这套系统是否可用，建议按下面顺序做。

## 6.1 先验证服务是否启动

1. 打开首页 `http://localhost:9700/`。
2. 确认页面不是白屏，也不是一直 loading。
3. 同时检查后端接口是否正常：

```bash
curl -sS http://127.0.0.1:9600/api/dashboard/stats
curl -sS http://127.0.0.1:9600/api/company-review
curl -sS 'http://127.0.0.1:9600/api/requirements?sort=score'
```

通过标准：

1. 这 3 条接口都返回 `200`。
2. 首页能看到 stats 和 company review。
3. `/requirements` 页面能看到列表或明确的空态，而不是白屏。

## 6.2 验证页面是否都能读到后端数据

逐页检查：

1. 首页 `/`
   看到 stats、company review、incidents、next-cycle bundle。
2. `/requirements`
   看到 requirement 列表、排序控件、scheduler 面板、搜索框。
3. `/requirements/:id`
   能打开任意 requirement 详情，看到 workflow、artifacts、validation、runtime、incidents。
4. `/optimization-signals`
   能看到 signal 列表，点刷新后数据能更新。
5. `/project-policies`
   能看到项目 policy 和 onboarding 信息。
6. `/tasks`
   能看到任务列表和状态筛选。
7. `/tasks/:id`
   能看到任务日志、history、file changes 或 memory 召回。
8. `/approvals`
   能看到待审批列表或明确空态。

通过标准：

1. 每个页面都能打开。
2. 每个页面都不是静态死页面，而是能读到真实接口返回。
3. 页面失败时有明确错误提示，不是无反馈。

## 6.3 验证核心业务链路

建议做一轮最小闭环：

1. 在 `/requirements` 新建一个 requirement。
2. 打开 requirement 详情页，确认 workflow 已生成。
3. 点击 `start` 或让系统自动推进。
4. 检查是否生成 workflow steps、artifacts、task 或 runtime 事件。
5. 回到 `/tasks` 或 `/tasks/:id`，确认低层执行证据存在。
6. 如果 requirement 失败，确认是否生成 bug report 或 incident。
7. 回到 `/optimization-signals`，确认问题是否回流成 signal。
8. 回到首页 `/`，刷新 company review，确认 recommendation 或 bundle 是否变化。

通过标准：

1. requirement 能创建。
2. workflow 能规划。
3. 执行状态能推进。
4. 失败会留下可追踪 evidence。
5. 结果能回流到 signal 或 company review。

## 6.4 验证治理边界

这一步用于确认系统不是“会跑”，而是“能被治理地跑”。

建议检查：

1. 在 `/project-policies` 看 capability matrix 和 interrupt policy 是否存在。
2. requirement 详情页里是否能看到 context governance、runtime lifecycle、recovery narrative。
3. 当 requirement 被 block / pause / incident 时，是否能解释原因。
4. `/approvals` 是否能承接高风险动作。

通过标准：

1. 系统遇到风险会暂停、阻断或转审批，而不是默默失败。
2. 你能从页面直接看懂“为什么停住、接下来该怎么办”。

## 6.5 自动化验证命令

如果你想做更严谨的验证，直接跑这些：

```bash
cd /Users/cliff/workspace/agent/Synapse-Network-Growing
/Users/cliff/workspace/agent/.venv/bin/python -m pytest -q
cd dashboard && npm test
cd dashboard && npm run build
cd dashboard && npm run test:e2e
```

通过标准：

1. 后端 pytest 通过。
2. 前端单测通过。
3. 前端 build 通过。
4. e2e 通过。

## 7. 快速故障排查

## 7.1 为什么任务很多，但需求池还是空的

先看 `/api/requirements?sort=score` 是否超时。

## 7.2 为什么首页有 incident，但 requirement 没动

说明问题可能还停留在 signal 或 company review 层，还没 intake 成 requirement。

## 7.3 为什么 requirement 卡在 blocked / paused

优先看：

1. Context Governance
2. Runtime Lifecycle
3. Recovery Narrative & Incidents
4. Approval / capability interrupt

## 7.4 为什么页面看起来没数据

优先分清是：

1. 真空态
2. 接口失败
3. 后端没启动
4. 数据库迁移没跑完
5. 本地旧进程还在读旧 schema

## 8. 常见问题

### 8.1 为什么任务很多，但需求池还是空的

因为任务不是需求。任务只是 requirement 的执行单元或兼容层对象。

### 8.2 为什么优化信号很多，但需求池没增加

因为 signal 只有在手动转换或自动 intake 后，才会生成 requirement。

### 8.3 为什么 requirement 创建了，但没开始执行

常见原因有：

1. requirement 还没 plan
2. requirement 被依赖阻塞
3. project policy 不允许执行
4. scheduler 判断当前项目没有预算或槽位
5. release / validation / approval 治理条件不满足

### 8.4 为什么页面看起来像空白

先不要默认是没有数据，先检查：

1. 后端是否启动
2. `/api/*` 是否超时
3. 当前筛选器是否把数据过滤掉
4. 当前页面是否其实在空态或错误态

## 9. 相关文件

如果要继续排查或修改页面，优先看这些文件：

1. `/Users/cliff/workspace/agent/Synapse-Network-Growing/dashboard/src/pages/OrgChart.tsx`
2. `/Users/cliff/workspace/agent/Synapse-Network-Growing/dashboard/src/pages/RequirementPool.tsx`
3. `/Users/cliff/workspace/agent/Synapse-Network-Growing/dashboard/src/pages/RequirementDetail.tsx`
4. `/Users/cliff/workspace/agent/Synapse-Network-Growing/dashboard/src/pages/OptimizationSignals.tsx`
5. `/Users/cliff/workspace/agent/Synapse-Network-Growing/dashboard/src/pages/ProjectPolicies.tsx`
6. `/Users/cliff/workspace/agent/Synapse-Network-Growing/dashboard/src/pages/TaskBoard.tsx`
7. `/Users/cliff/workspace/agent/Synapse-Network-Growing/dashboard/src/pages/TaskDetail.tsx`
8. `/Users/cliff/workspace/agent/Synapse-Network-Growing/dashboard/src/pages/Approvals.tsx`
9. `/Users/cliff/workspace/agent/Synapse-Network-Growing/server/routers/requirements.py`
10. `/Users/cliff/workspace/agent/Synapse-Network-Growing/server/main.py`
