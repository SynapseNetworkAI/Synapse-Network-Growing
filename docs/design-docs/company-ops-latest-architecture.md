# Synapse Company Ops 最新架构设计

## 1. Summary

`Synapse-Network-Growing` 现在采用 **Agent-First 三面架构**，默认不再把系统建模成固定的 `research -> plan -> implementation -> validate -> closeout` 流程。

当前正式主线只有一条：

```text
Requirement -> Execution -> Release
```

默认执行流也只保留最小核心形状：

```text
intake -> execute -> validate -> deliver
```

设计目标有 4 个：

1. 让 agent 主导执行内容与步骤展开。
2. 让程序只负责编排、验证、恢复和交付治理。
3. 把 requirement、execution、release 三种职责拆开，不再混在一个页面或一个状态机里。
4. 让简单任务默认走最短路径，复杂任务再按需展开。

补充的正式 UI 约束：

1. 控制台必须采用 Enterprise Workbench，而不是平铺卡片后台。
2. 视觉方向固定为克制型工程工作台，接近 Linear 风格，而不是营销化运营页。
3. Requirement / Execution / Release 三面必须各自有独立页面模板和信息密度策略。

## 2. Topology

### 2.1 Requirement Surface

Requirement 面只回答 3 个问题：

1. 为什么做
2. 要达到什么结果
3. 在什么约束下做

Requirement 保存的核心事实：

1. 标题与描述
2. 验收条件
3. target project / target repos
4. priority / source / family
5. approval need / policy summary
6. 当前 requirement 状态

Requirement 到 Execution 的正式桥接规则：

1. `submit` 时就做 approval decision
2. 低风险 requirement 默认 auto-approve / waive
3. 审批放行后自动创建 execution 并自动启动
4. 高风险 requirement 停在 requirement surface 等待人工批准
5. execution approval 只决定能否执行，不替代 release gate

Requirement 面不再承担：

1. 执行节点控制
2. 运行时 telemetry 明细
3. PR / deploy / rollback 操作
4. 环境状态面板

### 2.2 Execution Surface

Execution 面是 agent 的工作面。

它负责：

1. execution mode
2. direct execute 或 execution graph
3. runtime backend / model / session
4. agent summary / changed files / command evidence
5. validate 结果
6. incident / bugfix / pause / resume / retry

Execution 面的默认策略：

1. 简单任务走单一 `execute`
2. 复杂任务才展开 execution graph
3. `validate` 永远是唯一质量门
4. validate 失败只允许进入 `bugfix -> validate` 闭环

### 2.3 Release Surface

Release 面只负责交付与发布。

它负责：

1. release candidates
2. branch / commit / PR
3. delivery readiness
4. staging / production promotion
5. rollback
6. deployment history

Release candidate 的硬门槛：

1. requirement 已完成执行
2. validate 成功
3. release governance 满足项目策略

### 2.4 Error Loop（辅助治理）

错误发现不再停留在独立日志系统里，而是进入正式主链：

```text
error event -> fingerprint -> requirement -> approval -> execution -> validate -> release
```

规则：

1. 只接高信号错误源：`runtime_log_error`、`task_failure`、`workflow_incident`
2. 同一 fingerprint 同时最多只能有一条未完成 requirement
3. 新错误 requirement 创建后立即 `submit`
4. 低风险自动审批并自动启动 execution
5. 高风险 requirement 停在 requirement 面等待人工批准
6. `/errors` 只作为稳定性治理辅助页，不替代三大主面

## 3. Core Execution Model

### 3.1 Planner Contract

planner 现在是 **执行形状选择器**，不是固定阶段生成器。

它只做一次轻量决策：

1. `execution_mode`
   - `direct`
   - `graph`
   - `deterministic`
2. `complexity`
   - `simple`
   - `standard`
   - `complex`
3. `validation_profile`
4. `delivery_intent`
5. `approval_required`
6. `target_projects`

默认规则：

1. 简单任务直接进入单步 `execute`
2. 多仓或长链路任务才生成 execution graph
3. planner 不再产出固定 research/plan/closeout 仪式步骤

### 3.2 Minimal Artifact Set

当前只保留最小证据集：

1. `requirement_brief`
2. `execution_record`
3. `validation_record`
4. `delivery_record`

可选扩展 artifacts 只在特定场景出现：

1. `bug_report`
2. `incident_record`
3. `context_compaction`
4. `approval_record`

原则：

1. 没有消费方的 artifact 不生成
2. artifact 必须服务于 Requirement、Execution、Release 其中一面
3. 禁止为阶段完整性制造仪式性产物

### 3.3 Execution Lifecycle

Execution 现在采用严格的单主链模型：

1. 同一 requirement 同时只允许一条当前 execution 主链
2. `queued / running / paused / validating` 才算当前活跃 execution
3. 已完成、已失败、已验证的 run 不能再次 `start`
4. `retry` 不会复活旧 run，而是创建一条新的 execution run
5. requirement、execution、release 三面都只按当前唯一主链解释
6. 旧脏 execution / release 运行态数据不做兼容，直接通过重置脚本删除

### 3.4 Runtime Governance

程序保留的 deterministic 职责只有：

1. 项目边界与 project policy
2. approval / permission / interrupt policy
3. runtime lifecycle
4. validate 守门
5. delivery / release 记录
6. incident / recovery / bugfix loop

程序不再负责：

1. 固定执行阶段数
2. 强制先 research 再 plan
3. 强制输出长篇结构化计划
4. 用阶段名驱动 artifact 生成

## 4. Data Model

当前一等对象分为三组：

### 4.1 Requirement

1. `requirements`
2. requirement 只记录业务意图、约束与治理字段

### 4.2 Execution

1. `execution_runs`
2. `execution_nodes`
3. `validation_records`
4. `incidents`

### 4.3 Release

1. `release_records`
2. `deployment_records`

这意味着旧的固定 `workflow_run / workflow_step` 5-step 语义已经退出正式主线，不再作为当前架构的中心对象。

## 5. Product Surface

当前控制台正式导航只保留三面：

1. `/requirements`
2. `/executions`
3. `/releases`

页面职责：

1. `/requirements`
   requirement 列表、创建、编辑、提交、取消
2. `/requirements/:id`
   requirement 意图、验收与顶部执行/发布动作
3. `/executions`
   execution run 列表与当前主链入口
4. `/executions/:id`
   execution 节点、状态、evidence、validate、pause、继续执行、创建新 run 重试
5. `/releases`
   release candidate 列表
6. `/releases/:requirementId`
   prepare branch、open PR、deploy、rollback、deployment history

辅助治理页：

1. `/errors`
2. `/errors/:fingerprintKey`

它们只承担错误聚合、关联 requirement/execution 和通知历史展示。

### 5.1 Runtime Reset

当前不兼容旧脏 execution 数据。需要重置运行态时，使用：

```bash
/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_execution_runtime.py --yes
```

该命令会清空：

1. `execution_runs`
2. `execution_nodes`
3. `validation_records`
4. `release_records`

并把 requirement 状态重置回可重新推导的基线。

### 5.2 Frontend Surface Anatomy

当前页面骨架必须遵守下面的简洁 SaaS 结构：

1. `shell`
   负责全局导航、环境感和页面边界。
2. `page header`
   负责页面定位、主说明和单页 focus strip。
3. `primary workspace`
   负责主要工作对象：
   - requirement intent
   - execution evidence / graph
   - release timeline
4. `secondary actions`
   负责筛选、搜索、确认弹窗和轻量反馈。
5. `context areas`
   只在确实需要时展示 incidents、deployment records 和系统轨迹。

禁止的工作台模式：

1. 同权重大白卡瀑布流
2. 每个 section 都用圆角白卡包裹
3. 依赖 chips/pills 代替真正的信息层级
4. Requirement 页面重新混入 deploy / rollback 控制

不再作为当前正式主入口的页面：

1. 运营总览首页
2. company review
3. role kpis
4. autonomy
5. recurring workflows
6. tasks / approvals / deployments 旧式控制台

这些能力如果仍保留为内部支撑或历史设计记录，也不再代表当前正式操作面。

## 6. System Guardrails

当前架构必须遵守这些硬约束：

1. 默认 workflow 必须最小化
2. simple task 不得被治理框架强制扩成多步
3. Requirement / Execution / Release 必须分面治理
4. planner 是形状选择器，不是阶段生成器
5. validate 必须独立于 execute
6. deliver 只能发生在 validate 成功之后
7. release candidate 只接受 validate 成功的 requirement
8. requirement、alert、release 三类 Lark 通知必须统一走结构化交互卡片

## 7. Current Status

当前代码已经采用以下实现方向：

1. requirements、executions、releases 已拆成独立 API surface
2. 前端导航已切成三面
3. requirement 页面不再混入 deploy / rollback 控制
4. release 页面负责 branch / PR / deploy promotion
5. optimization signals、company review、requirement source materialization 已改用新的 requirement intake 入口

后续新增能力默认必须接入这条三面主线，而不是把旧的固定 step workflow 再引回来。
