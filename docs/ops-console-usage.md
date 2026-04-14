# Synapse Ops Console 使用说明

本文面向 `http://localhost:9700/` 的当前控制台使用者。

当前控制台已经切换到 **Agent-First 三面架构**：

1. `需求`
2. `执行`
3. `发布`

默认执行流只有：

```text
intake -> execute -> validate -> deliver
```

这份文档只描述当前正式操作面，不再把旧的 5-step requirement workflow、运营总览、tasks、approvals、deployments 旧页面当作主入口。

## 1. 页面总览

当前正式页面只有 6 个：

1. `/requirements`
2. `/requirements/:id`
3. `/executions`
4. `/executions/:id`
5. `/releases`
6. `/releases/:requirementId`

推荐心智模型：

1. 在 `需求` 定义为什么做
2. 在 `执行` 观察 agent 怎么做、做到什么程度、验证是否通过
3. 在 `发布` 处理 branch / PR / deploy / rollback

## 2. 需求面

### 2.1 `/requirements`

#### 页面职责

需求池只负责 requirement intent 和治理入口。

#### 典型动作

1. 创建 requirement
2. 编辑 requirement
3. 提交 requirement
4. 创建 execution run
5. 跳转到 release 面

#### 后端接口

1. `GET /api/requirements`
2. `POST /api/requirements`
3. `PATCH /api/requirements/{id}`
4. `POST /api/requirements/{id}/submit`
5. `POST /api/requirements/{id}/revise`
6. `POST /api/requirements/{id}/cancel`
7. `POST /api/executions`

#### 推荐使用方式

1. 标题写结果，不写动作口号
2. 描述里明确目标、约束、验收条件
3. target project 尽量明确
4. requirement ready 之后再创建 execution run

### 2.2 `/requirements/:id`

#### 页面职责

需求详情页只展示 requirement 本身，不直接做执行控制和发布控制。

#### 页面内容

1. 标题、描述、验收条件
2. target project / source / priority
3. policy / approval 摘要
4. latest execution link
5. release link

#### 页面不负责

1. pause / resume execution graph
2. 运行时 telemetry 明细
3. deploy / rollback
4. 环境状态

#### 推荐使用方式

1. 先确认 intent 与 acceptance 写对
2. 再跳去 execution 看 agent 执行
3. validate 成功后再跳去 release 做交付与发布

## 3. 执行面

### 3.1 `/executions`

#### 页面职责

执行列表展示所有 execution run，而不是 requirement 列表。

#### 典型动作

1. 查看 execution mode
2. 查看复杂度与 validation profile
3. 启动 queued execution
4. 跳转到 requirement 或 release

#### 后端接口

1. `GET /api/executions`
2. `POST /api/executions`
3. `POST /api/executions/{id}/start`

### 3.2 `/executions/:id`

#### 页面职责

Execution detail 是 agent 工作面。

#### 页面内容

1. execution status
2. execution mode / complexity / validation profile
3. execution nodes
4. agent summary
5. changed files / command evidence
6. validation result
7. incidents

#### 典型动作

1. 启动执行
2. 暂停执行
3. 重试执行
4. 触发 validate

#### 后端接口

1. `GET /api/executions/{id}`
2. `POST /api/executions/{id}/start`
3. `POST /api/executions/{id}/pause`
4. `POST /api/executions/{id}/resume`
5. `POST /api/executions/{id}/retry`
6. `POST /api/executions/{id}/validate`

#### 推荐使用方式

1. 对简单任务，预期只会看到一个 `execute` 节点
2. 对复杂任务，才会看到 execution graph
3. validate 失败时，关注 bugfix loop 和 incident，而不是回到 requirement 页猜测发生了什么

## 4. 发布面

### 4.1 `/releases`

#### 页面职责

Release 列表只展示当前可发布候选。

#### 候选规则

只有 validate 成功的 requirement 才会进入 release candidates。

#### 后端接口

1. `GET /api/releases/candidates`

### 4.2 `/releases/:requirementId`

#### 页面职责

Release detail 负责交付与发布操作。

#### 页面内容

1. branch / commit / PR 状态
2. delivery readiness
3. deployment records
4. rollback history

#### 典型动作

1. `prepare`
2. `open-pr`
3. `deploy-staging`
4. `deploy-production`
5. `rollback`

#### 后端接口

1. `GET /api/releases/{requirementId}`
2. `POST /api/releases/{requirementId}/prepare`
3. `POST /api/releases/{requirementId}/open-pr`
4. `POST /api/releases/{requirementId}/deploy/staging`
5. `POST /api/releases/{requirementId}/deploy/production`
6. `POST /api/releases/{requirementId}/rollback`

#### 推荐使用方式

1. 只有 validate 通过后才进入 release 面做交付
2. requirement 页只看 intent，不在那边做发布决策
3. 发布、promotion、rollback 都在 release 面统一处理

## 5. Runtime 选择心智模型

planner 和 execution runtime 仍由 `ORCHESTRATION_BACKEND` 决定。

常见 backend：

1. `openai_responses`
2. `copilot_sdk`
3. `codex_cli`

当前原则：

1. planner 只做 shape decision
2. execute 由选定 runtime 驱动
3. validate 与 deliver 由系统治理，不交给模型随意跳过

## 6. 当前正式操作闭环

推荐操作顺序：

1. 在 `/requirements` 创建 requirement
2. 在 `/requirements/:id` 检查 intent 与 acceptance
3. 创建 execution run
4. 在 `/executions/:id` 观察执行与 validate
5. validate 成功后，在 `/releases/:requirementId` 做 PR / deploy / rollback

## 7. 快速验证清单

如果你只是想判断系统是否可用，按下面做一轮最小验证：

1. 创建一条 requirement
2. 提交 requirement
3. 创建 execution run
4. 启动 execution
5. 触发 validate
6. 确认 release candidate 出现在 `/releases`
7. 打开 release detail，确认可以执行 `prepare` 和 `open-pr`

## 8. 故障排查

### 8.1 requirement 有了，但 execution 没出现

先检查：

1. requirement 是否已经 `submit`
2. 是否已经显式创建 execution run

### 8.2 execution 卡住

先看：

1. execution status
2. incidents
3. runtime backend
4. validation profile

### 8.3 release 里没有候选

先检查：

1. validate 是否成功
2. requirement 是否完成执行
3. release governance 是否满足项目策略

## 9. 说明

以下能力如果仍在仓库中存在，也不再是当前正式控制台主入口：

1. `/tasks`
2. `/tasks/:id`
3. `/deployments`
4. `/approvals`
5. 运营总览首页与 company review 旧页面

它们可以作为历史实现或低层支撑继续存在，但不代表当前推荐的日常操作路径。
