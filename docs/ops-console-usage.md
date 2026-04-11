# Synapse Ops Console 使用说明

本文面向 `http://localhost:9700/` 的操作台使用者，解释为什么 `/requirements` 看起来可能没有需求，以及各个页面分别做什么、读哪些后端接口、应该怎么用。

## 1. 为什么 `/requirements` 页面看起来没有需求

先说结论：

1. 当前本地数据库里的 `requirements` 表并不为空。
2. `/requirements` 页“看起来没有需求”，更像是接口响应慢或失败，而不是数据不存在。
3. 当前页面对加载异常的提示不够明显，所以用户容易误判成“需求池为空”。

### 1.1 当前本地数据事实

以当前本机环境为例，`server/ops.db` 里实际有 44 条 requirement：

```bash
sqlite3 /Users/cliff/workspace/agent/Synapse-Network-Growing/server/ops.db 'select count(*) from requirements;'
```

返回值是：

```text
44
```

也就是说，需求池的数据源本身是有内容的。

### 1.2 `/requirements` 页面真正依赖的后端接口

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

### 1.3 当前本机观察到的问题

同样是当前这份数据：

1. 直接在后端 Python 进程内调用 `list_requirements(sort="score")`，约 4.5 秒可以算出 44 条 requirement。
2. 但通过 HTTP 访问 `http://127.0.0.1:9600/api/requirements?sort=score`，8 秒内没有收到任何响应字节。

也就是说，页面上“没有需求”的更准确解释是：

```text
需求列表接口响应过慢或卡住，前端没有把这个错误明确展示出来，
于是用户感知成了“需求池为空”。
```

### 1.4 如何快速排查

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

### 1.5 还要注意的一点

需求池显示的是 `requirements`，不是 `tasks`，也不是 `optimization_signals`。

所以：

1. `tasks` 很多，不代表需求池一定很多。
2. `optimization_signals` 很多，也不代表它们已经自动转成 requirement。
3. 只有真正创建到 `requirements` 表里的对象，才会出现在 `/requirements`。

## 2. 页面总览

当前操作台的核心页面有：

1. `/` 组织架构与公司级 review
2. `/requirements` 需求池
3. `/requirements/:id` 需求详情
4. `/optimization-signals` 优化信号
5. `/project-policies` 项目策略与 onboarding
6. `/tasks` 任务看板
7. `/tasks/:id` 任务详情
8. `/approvals` 审批中心

推荐把它理解成一条链路：

```text
公司级 review / 优化信号
→ requirement intake
→ requirement planning / delivery / validation
→ workflow step 落到 tasks
→ 高风险动作进入 approvals
→ 结果、bug、阻塞再回流成 signal 和下一周期 bundle
```

## 3. 各页面如何使用

## 3.1 首页 `/`

### 页面作用

首页是公司级 operating review 面板，用来看整个 portfolio 当前在发生什么。

### 读取后端

1. `GET /api/org`
2. `GET /api/dashboard/stats`
3. `GET /api/company-review`
4. `POST /api/company-review/refresh`
5. `POST /api/company-review/{id}/materialize-bundle`

### 你能做什么

1. 看组织图和 Agent 分组。
2. 看当前任务、审批、活跃 requirement 等统计。
3. 刷新 company review。
4. 把下一周期推荐 bundle 直接 materialize 成真实 requirement。

### 典型使用方式

1. 先看 `portfolio summary` 判断哪里最堵。
2. 看 `Next Cycle Requirement Bundle` 和 `Operator Review Package`。
3. 确认后点 `生成 Bundle`，把推荐项放进需求池。

## 3.2 需求池 `/requirements`

### 页面作用

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
2. 填目标项目路径，或者留空让系统自动路由。
3. 指定依赖关系。
4. 通过智能排序看当前最值得做的需求。
5. 用顶部搜索框按 requirement 标题、项目路径、`source_ref` 或 requirement id 搜索。
6. 触发 scheduler、queue advance、rebalance。
7. 暂停、恢复、编辑、删除 requirement。

### 新建 requirement 的建议写法

标题写结果，不写动作。

推荐：

```text
[Tech] Gateway 结算幂等性验证 — 重复调用不双扣
```

不推荐：

```text
修一下代码
```

描述里建议写 4 个部分：

1. 目标
2. 约束
3. 验收条件
4. 影响项目

### 什么时候填 `target_project_path`

1. 已经明确只改某个仓库时，直接填写。
2. 需要跨仓执行时，一行一个路径。
3. 还不确定做在哪个仓时，可以留空，交给自动路由。

### 什么时候用依赖

当某个 requirement 必须建立在另一个 requirement 完成后，才应该加依赖。

比如：

1. 先做 SDK 接入能力
2. 再做 Provider onboarding E2E 验证

这种场景就应该把后者依赖前者。

## 3.3 需求详情 `/requirements/:id`

### 页面作用

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
4. 看 artifacts，包括 implementation plan、validation plan、bug report。
5. 发起修订。
6. 在满足 release gate 时执行 publish。

### 正确使用方式

1. 先确认 requirement 本身描述是对的。
2. 再看 workflow 是否合理。
3. 再看 validation contract 是否覆盖关键风险。
4. 最后再做 publish，而不是跳过验证直接关单。

## 3.4 优化信号 `/optimization-signals`

### 页面作用

这个页面用来管理系统自动发现的问题与优化机会，比如：

1. bug report
2. manual override
3. delivery blocker
4. 其他流程摩擦信号

### 读取后端

1. `GET /api/optimization-signals`
2. `POST /api/optimization-signals/refresh`
3. `POST /api/optimization-signals/auto-intake`
4. `POST /api/optimization-signals/{id}/create-requirement`
5. `POST /api/optimization-signals/{id}/dismiss`

### 你能做什么

1. 刷新 signal。
2. 看 signal 的 score、severity、project、evidence。
3. 手动把 signal 转成 requirement。
4. 让系统自动 intake 当前最值得做的 signal。
5. dismiss 明显不值得跟进的 signal。

### 什么时候用它

当系统出现反复 bug、审批摩擦、交付阻塞、预算异常、流程异常时，不要直接跳到 task 层修，先看这里能否转成可治理的 requirement。

## 3.5 项目策略 `/project-policies`

### 页面作用

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
5. 设置 capability matrix：
   `shell / git_read / git_write / git_push / network / publish`
6. 设置 interrupt policy：
   哪些动作要人工确认、哪些事件自动暂停、哪些事件自动终止。
7. 设置 release mode、manual approval、autonomy mode。
8. 设置 scheduler weight、max parallel requirements、budget。

### 正确使用方式

新项目不要直接进需求池，先做 onboarding。

先把下面这些信息补齐：

1. docs 入口
2. validation commands
3. memory namespace
4. write scope
5. forbidden scope
6. release policy
7. capability matrix
8. interrupt policy

这样 requirement planner、scheduler 和 delivery gate 才能安全地自动工作。

### capability matrix 怎么配

推荐默认值：

1. `shell_access` 开
2. `git_read` 开
3. `git_write` 开
4. `git_push` 关
5. `network_access` 关
6. `publish` 关

只有当某个项目真的准备好了自动发布链路时，再打开 `git_push` 和 `publish`。

### interrupt policy 怎么配

推荐默认值：

1. `operator_confirmation_actions` 包含 `git_push`、`publish`
2. `auto_pause_on_events` 包含 `capability_denied`、`policy_violation`、`missing_required_checks`
3. `auto_abort_on_events` 包含 `forbidden_write`、`publish_without_gate`

如果某个 workflow step 需要的能力被禁用，系统会在调度前创建 `capability_interrupt` artifact，并把 requirement 收口到 `blocked / paused`，而不是硬跑。

## 3.6 任务看板 `/tasks`

### 页面作用

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

### 什么时候用任务看板

1. 你在调 runtime 或 Agent 执行行为时。
2. 你在排查某个 workflow step 为什么失败时。
3. 你在需要人工新建一次低层执行任务时。

如果你处理的是业务目标、交付结果或 bugfix 闭环，优先去 requirement 页面，而不是直接沉到 task。

## 3.7 任务详情 `/tasks/:id`

### 页面作用

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

### 什么时候看这里

当你要证明“Agent 到底做了什么、改了什么、失败在哪”时，看任务详情最合适。

## 3.8 审批中心 `/approvals`

### 页面作用

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

### 正确使用方式

审批应该处理高风险边界，而不是代替普通执行。

推荐让审批只覆盖这些场景：

1. 发布动作
2. 高风险写入
3. 大范围 rebalance / preemption
4. 预算超限后的继续执行

## 4. 推荐操作路径

如果你是 operator，推荐按下面的顺序使用系统：

1. 在首页看 company review，判断最值得推进的事项。
2. 去 `/optimization-signals` 看是否已有高价值 signal。
3. 把 signal 转成 requirement，或直接在 `/requirements` 新建 requirement。
4. 在 requirement detail 中确认 workflow、validation 和 delivery contract。
5. 如果需要看低层执行，再去 `/tasks` 和 `/tasks/:id`。
6. 有高风险动作时，在 `/approvals` 做决策。
7. 完成后回到首页看下一周期 bundle 和 operator package。

## 5. 常见问题

### 5.1 为什么任务很多，但需求池还是空的

因为任务不是需求。任务只是 requirement 的执行单元或兼容层对象。

### 5.2 为什么优化信号很多，但需求池没增加

因为 signal 只有在手动转换或自动 intake 后，才会生成 requirement。

### 5.3 为什么 requirement 创建了，但没开始执行

常见原因有：

1. requirement 还没 plan
2. requirement 被依赖阻塞
3. project policy 不允许执行
4. scheduler 判断当前项目没有预算或槽位
5. release / validation / approval 治理条件不满足

### 5.4 为什么页面看起来像空白

先不要默认是没有数据，先检查：

1. 后端是否启动
2. `/api/*` 是否超时
3. 当前筛选器是否把数据过滤掉
4. 当前页面是否其实在空态或错误态

## 6. 相关文件

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
