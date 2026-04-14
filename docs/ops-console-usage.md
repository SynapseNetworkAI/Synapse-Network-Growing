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
3. Requirement、Execution、Release 三面使用不同的信息密度和页面模板。

## 1. 页面总览

当前正式页面包括：

1. `/requirements`
2. `/requirements/:id`
3. `/executions`
4. `/executions/:id`
5. `/releases`
6. `/releases/:requirementId`
7. `/projects`
8. `/projects/:id`

辅助治理页：

1. `/errors`
2. `/errors/:fingerprintKey`

推荐心智模型：

1. 在 `需求` 定义为什么做
2. 在 `执行` 观察 agent 怎么做、做到什么程度、验证是否通过
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
4. 低风险 requirement 会在后台补齐 acceptance contract 与 execution plan，再自动进入 execution；高风险 requirement 在需求面等待人工批准
5. 跳转到 release 面
6. 高信号错误会自动创建或复用 requirement，并沿同一条主链进入审批、plan 与执行

#### 后端接口

1. `GET /api/requirements`
2. `POST /api/requirements`
3. `PATCH /api/requirements/{id}`
4. `POST /api/requirements/{id}/submit`
5. `POST /api/requirements/{id}/approve`
6. `POST /api/requirements/{id}/reject`
7. `POST /api/requirements/{id}/cancel`
8. `POST /api/executions`

#### 推荐使用方式

1. 标题写结果，不写动作口号
2. 描述里明确目标与约束；requirement 会先保存，随后在后台由 agent 生成真实 acceptance contract 与 execution plan
3. requirement 必须先选择正式 `Project`
4. 路径覆盖只在高级场景使用，不再把裸 `target_project_path` 当作主输入
5. requirement submit 是 requirement 进入 execution 的唯一正式桥接点，并会先确保 acceptance contract 与 execution plan 可用
6. 只有恢复/调试场景才手动创建 execution run
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

1. 先确认 intent、acceptance contract 与 execution plan 写对
2. 再跳去 execution 看 agent 执行
3. verification agent 给出 passed verdict 后再跳去 release 做交付与发布

## 3. 执行面

### 3.1 `/executions`

#### 页面职责

执行列表展示当前系统中的 execution run；同一 requirement 任何时刻只有一条当前执行主链。

#### 页面布局

1. 顶部说明 execution console 的治理边界
2. 主工作区是 run queue
3. 每个 execution item 都必须突出 status、mode、summary
4. 右侧 inspector 提供每条 run 的 compact summary

#### 典型动作

1. 查看 execution mode
2. 查看复杂度与 validation profile
3. 启动 queued execution
4. 对 failed / blocked run 创建新 run 重试
5. 跳转到 requirement 或 release

#### 后端接口

1. `GET /api/executions`
2. `POST /api/executions`
3. `POST /api/executions/{id}/start`

### 3.2 `/executions/:id`

#### 页面职责

Execution detail 是当前唯一 execution 主链的工作面。

#### 页面布局

1. 顶部是 run header、KPI 与控制动作
2. Execution Plan 区展示当前 run 的计划摘要
3. Runtime 区展示当前 run 的 node / task 表格
4. Files 区展示当前 run 的改动文件
5. Verification 区展示 verification agent 的验证记录
6. Agent Output 区始终展示原始执行输出
7. Activity 区展示 lifecycle 时间线与 incidents

#### 页面内容

1. execution status
2. execution mode / complexity / validation profile
3. 当前 agent / backend / provider / model
4. 当前 branch / 总 token / 执行时长
5. execution nodes runtime table
6. execution plan
7. changed files / command evidence
8. verification result
9. agent 原始输出
10. activity timeline
11. incidents

#### 典型动作

1. 启动 queued execution
2. 继续 paused execution
3. 对 failed / blocked execution 创建新 run 重试
4. 查看自动 verification 结果
5. 打开改动文件预览，默认先看 `diff`
6. 当结构化 summary 不足时，直接查看 agent 原始输出确认实际执行结果

#### 后端接口

1. `GET /api/executions/{id}`
2. `GET /api/executions/{id}/files/{encoded_path}`
3. `POST /api/executions/{id}/start`
4. `POST /api/executions/{id}/pause`
5. `POST /api/executions/{id}/resume`
6. `POST /api/executions/{id}/retry`
7. `POST /api/executions/{id}/validate`
   主要作为调试 / 重跑入口保留，正常链路由系统在 execution 完成后自动触发 verification agent

#### 推荐使用方式

1. 对简单任务，预期只会看到一个 `execute` 节点
2. 对复杂任务，才会看到 execution graph
3. verification agent 判定失败或需修订时，关注 verification reasoning、bugfix loop 和 incident，而不是回到 requirement 页猜测发生了什么
4. `retry` 会创建新的 execution run；旧 run 不会复活
5. token、branch、agent/model、文件改动和活动流，都只按当前 execution 主链展示，不混入历史 run
6. execution detail 即使缺少 changed files 或 validation，也必须能看到 agent 原始输出

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

planner 和 execution runtime 仍由 `ORCHESTRATION_BACKEND` 决定。

常见 backend：

1. `openai_responses`
2. `copilot_sdk`
3. `codex_cli`

当前原则：

1. planner 只做 shape decision
2. execute 由选定 runtime 驱动
3. verification 与 deliver 由系统治理，不交给模型随意跳过

## 7. 错误日志页（辅助）

### 6.1 `/errors`

1. 聚合高信号错误 fingerprint
2. 展示 linked requirement / execution
3. 展示 occurrence、latest seen 和稳定性摘要

后端接口：

1. `GET /api/errors`
2. `POST /api/errors/intake`

### 6.2 `/errors/:fingerprintKey`

1. 查看单个错误 fingerprint 的事件证据
2. 查看 linked requirement / execution / release
3. 查看 Lark 告警发送历史

后端接口：

1. `GET /api/errors/{fingerprintKey}`

## 8. Lark 通知

当前外部通知统一分三路：

1. requirement 群
   - 新 requirement
   - auto approval 结果
   - manual approval required
2. alert 群
   - error log intake
   - execution error / failure / blocked incident
3. release 群
   - PR 已创建

每条通知都必须包含：

1. 哪个服务 / 应用
2. 发生了什么
3. 什么时候发生
4. 需要做什么
5. requirement / execution / release / errors 相关链接

## 8. 当前正式操作闭环

推荐操作顺序：

1. 在 `/requirements` 创建 requirement
2. 在 `/requirements/:id` 检查 intent、acceptance contract 与 execution plan
3. `submit` requirement，低风险会自动审批、先生成 plan，再自动启动 execution
4. 在 `/executions/:id` 观察执行与 verification verdict
5. verification passed 后，在 `/releases/:requirementId` 做 PR / deploy / rollback
6. 如果来自错误回流，可在 `/errors` 追踪 fingerprint 与通知历史

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
