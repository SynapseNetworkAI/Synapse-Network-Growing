---
id: requirement_pool_workflow_database_design
title: Synapse Ops 需求池与工作流数据库设计
status: proposed
created_at: 2026-04-09
updated_at: 2026-04-09
author: github-copilot
target_repo: cliff-personal/Synapse-Network-Growing
---

# Synapse Ops 需求池与工作流数据库设计

## 1. 目标

本设计文档定义 Requirement Pool 和 Multi-Agent Workflow 的数据库层方案。

它回答四个问题：

1. 需要新增哪些表
2. 每张表的字段、约束、索引如何设计
3. 如何与现有 `agents`、`tasks`、`approvals`、`task_logs` 兼容
4. Phase 1 应该先落哪些表，避免后期返工

本文件是 [docs/design-docs/requirement-pool-multi-agent-workflow-architecture.md](docs/design-docs/requirement-pool-multi-agent-workflow-architecture.md) 的数据库落地 companion doc。

---

## 2. 设计原则

### 2.1 兼容优先，不一次性推翻现有运行时

当前系统已经依赖以下表：

1. `agents`
2. `tasks`
3. `approvals`
4. `task_logs`

Phase 1 不应强制重写现有执行链。

因此数据库设计应遵循：

1. Requirement / Workflow 新增独立表
2. 通过 `workflow_steps.compatibility_task_id` 复用现有 task runtime
3. 新旧表并存一段时间，不做激进迁移

### 2.2 控制面字段结构化，长文本以 Markdown 保存

SQLite 下不应依赖原生 JSON 列能力作为核心前提。

建议规则：

1. 可枚举状态、关系、外键、索引字段单独建列
2. 复杂结构化 payload 以 `TEXT` 保存 JSON 字符串
3. 长文本说明和人类阅读内容以 Markdown 文本保存

### 2.3 追加证据优先于覆盖写入

对执行和验证闭环最重要的是可追溯性。

因此：

1. `artifacts` 更偏追加式存储
2. `workflow_step_events` 更偏事件流
3. requirement / workflow / step 主表只保存当前聚合态

### 2.4 与现有代码风格保持一致

当前仓库数据库层特征是：

1. SQLite
2. SQLAlchemy ORM
3. `Integer` 自增主键用于运行时对象
4. `Text` 保存 JSON 数组或 payload
5. UTC `DateTime`

新表应延续这套风格，避免混用 UUID、复杂 join-table trick 或过度抽象。

---

## 3. 现有表与新表边界

### 3.1 保留的现有表

以下表继续保留：

1. `agents`
2. `tasks`
3. `approvals`
4. `task_logs`

### 3.2 新增的核心表

建议新增：

1. `requirements`
2. `requirement_dependencies`
3. `workflow_runs`
4. `workflow_steps`
5. `workflow_step_dependencies`
6. `artifacts`
7. `step_input_bindings`
8. `requirement_acceptance_checks`
9. `approval_requests`
10. `workflow_step_events`

### 3.3 Phase 1 必需表

如果先做最小闭环，Phase 1 至少需要：

1. `requirements`
2. `requirement_dependencies`
3. `workflow_runs`
4. `workflow_steps`
5. `artifacts`
6. `step_input_bindings`
7. `requirement_acceptance_checks`

`approval_requests` 和 `workflow_step_events` 可以在 Phase 1.5 或 Phase 2 接入，但表结构建议现在就定下来。

---

## 4. 关系总览

主关系如下：

1. 一个 `requirement` 可以有多个 `workflow_runs`
2. 一个 `workflow_run` 可以有多个 `workflow_steps`
3. 一个 `workflow_step` 可以依赖多个其他 `workflow_steps`
4. 一个 `workflow_step` 可以消费多个 `artifacts`
5. 一个 `workflow_step` 可以产出多个 `artifacts`
6. 一个 `requirement` 可以有多个 `requirement_acceptance_checks`
7. 一个 `requirement_acceptance_check` 最终由某个验证 step 关闭

建议的兼容链：

1. `workflow_steps.compatibility_task_id -> tasks.id`
2. 旧的 `approvals.task_id` 和 `task_logs.task_id` 先继续围绕 compatibility task 工作
3. 后续再迁移到 `approval_requests` 和 `workflow_step_events`

---

## 5. 主键与通用字段约定

### 5.1 主键约定

新表默认使用：

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`

理由：

1. 与现有 `tasks`、`approvals`、`task_logs` 一致
2. SQLite 下实现最直接
3. 迁移和 join 成本低

### 5.2 时间字段约定

需要的时间字段尽量统一：

1. `created_at`
2. `updated_at`
3. `started_at`
4. `completed_at`

所有时间均使用 UTC。

### 5.3 状态字段约定

状态字段统一使用 `Text` + 应用层枚举校验。

不建议在 SQLite 上依赖复杂 CHECK 约束表达全部状态机。

### 5.4 JSON 字段约定

以下类型字段统一使用 `Text` 存 JSON 字符串：

1. 文件范围
2. 验证目标
3. 失败策略
4. 审批策略
5. machine-readable artifact payload

原因：

1. 与现有 `skills`、`context_files` 风格一致
2. ORM 映射简单
3. 后续若切到 Postgres，可平滑升级为 `JSONB`

---

## 6. 表设计

## 6.1 requirements

需求池主表。

建议字段：

1. `id` `INTEGER PK`
2. `title` `TEXT NOT NULL`
3. `description_markdown` `TEXT NOT NULL`
4. `status` `TEXT NOT NULL DEFAULT 'draft'`
5. `priority` `TEXT NOT NULL DEFAULT 'normal'`
6. `source` `TEXT NOT NULL DEFAULT 'manual'`
7. `source_ref` `TEXT`
8. `target_project_path` `TEXT` — 需求关联的目标项目路径（绝对路径），用于指导 Agent 在哪个项目中执行代码实现。Planner 根据此字段动态生成 `file_scope`，允许 Agent 读写目标项目目录。
9. `current_plan_version` `INTEGER NOT NULL DEFAULT 0`
10. `planned_roles_json` `TEXT NOT NULL DEFAULT '[]'`
11. `blocked_by_count` `INTEGER NOT NULL DEFAULT 0`
12. `active_workflow_run_id` `INTEGER`
13. `started_at` `DATETIME`
14. `completed_at` `DATETIME`
15. `created_at` `DATETIME NOT NULL`
16. `updated_at` `DATETIME NOT NULL`

索引建议：

1. `INDEX requirements_status_idx(status)`
2. `INDEX requirements_priority_idx(priority)`
3. `INDEX requirements_created_at_idx(created_at)`
4. `INDEX requirements_active_run_idx(active_workflow_run_id)`

说明：

1. `active_workflow_run_id` 用于快速定位当前活跃 run
2. `planned_roles_json` 是 Planner 推荐角色缓存，不是真相源
3. `blocked_by_count` 是加速字段，可由依赖关系反推
4. `target_project_path` 是可选字段。当设置后，Planner 将：
   - 根据项目结构智能拆分实现步骤（方案设计、前端实现、后端实现、测试验证等）
   - 动态生成 `file_scope`，允许 Agent 读写目标项目目录
   - 在 task description 中注入项目路径，使 Agent 知道代码应写在何处

## 6.2 requirement_dependencies

需求级依赖表。

建议字段：

1. `id` `INTEGER PK`
2. `requirement_id` `INTEGER NOT NULL FK requirements.id`
3. `depends_on_requirement_id` `INTEGER NOT NULL FK requirements.id`
4. `dependency_type` `TEXT NOT NULL DEFAULT 'hard_block'`
5. `created_at` `DATETIME NOT NULL`

约束建议：

1. `UNIQUE(requirement_id, depends_on_requirement_id, dependency_type)`
2. 应用层禁止 requirement 依赖自己

索引建议：

1. `INDEX req_dep_requirement_idx(requirement_id)`
2. `INDEX req_dep_depends_on_idx(depends_on_requirement_id)`

## 6.3 workflow_runs

一次规划或重跑对应一个 workflow run。

建议字段：

1. `id` `INTEGER PK`
2. `requirement_id` `INTEGER NOT NULL FK requirements.id`
3. `plan_version` `INTEGER NOT NULL`
4. `status` `TEXT NOT NULL DEFAULT 'pending'`
5. `triggered_by` `TEXT NOT NULL DEFAULT 'system'`
6. `planner_artifact_id` `INTEGER FK artifacts.id`
7. `started_at` `DATETIME`
8. `completed_at` `DATETIME`
9. `created_at` `DATETIME NOT NULL`
10. `updated_at` `DATETIME NOT NULL`

索引建议：

1. `INDEX workflow_runs_requirement_idx(requirement_id)`
2. `INDEX workflow_runs_status_idx(status)`
3. `INDEX workflow_runs_plan_version_idx(requirement_id, plan_version)`

说明：

1. 不建议强制 `UNIQUE(requirement_id, plan_version)`，因为同一 plan version 可能允许重新执行
2. `planner_artifact_id` 指向本次 plan 的结构化输出 artifact

## 6.4 workflow_steps

工作流最核心执行单元。

建议字段：

1. `id` `INTEGER PK`
2. `workflow_run_id` `INTEGER NOT NULL FK workflow_runs.id`
3. `requirement_id` `INTEGER NOT NULL FK requirements.id`
4. `step_key` `TEXT NOT NULL`
5. `step_type` `TEXT NOT NULL`
6. `title` `TEXT NOT NULL`
7. `status` `TEXT NOT NULL DEFAULT 'pending'`
8. `assigned_agent_id` `TEXT FK agents.id`
9. `assigned_workflow_role` `TEXT`
10. `context_scope` `TEXT NOT NULL DEFAULT 'step_private'`
11. `handoff_summary_markdown` `TEXT`
12. `done_when_markdown` `TEXT NOT NULL DEFAULT ''`
13. `file_scope_json` `TEXT NOT NULL DEFAULT '{}'`
14. `validation_targets_json` `TEXT NOT NULL DEFAULT '[]'`
15. `failure_policy_json` `TEXT NOT NULL DEFAULT '{}'`
16. `approval_policy_json` `TEXT NOT NULL DEFAULT '{}'`
17. `runtime_backend` `TEXT NOT NULL DEFAULT ''`
18. `runtime_session_id` `TEXT`
19. `compatibility_task_id` `INTEGER FK tasks.id`
20. `retry_count` `INTEGER NOT NULL DEFAULT 0`
21. `started_at` `DATETIME`
22. `completed_at` `DATETIME`
23. `created_at` `DATETIME NOT NULL`
24. `updated_at` `DATETIME NOT NULL`

约束建议：

1. `UNIQUE(workflow_run_id, step_key)`

索引建议：

1. `INDEX workflow_steps_run_idx(workflow_run_id)`
2. `INDEX workflow_steps_requirement_idx(requirement_id)`
3. `INDEX workflow_steps_status_idx(status)`
4. `INDEX workflow_steps_assigned_agent_idx(assigned_agent_id)`
5. `INDEX workflow_steps_compat_task_idx(compatibility_task_id)`

说明：

1. `compatibility_task_id` 是 Phase 1 兼容现有 runtime 的关键桥接字段
2. `assigned_agent_id` 可为空，因为 Planner 初期可能只先分配 workflow role
3. `context_scope` 应用层枚举建议：`global_shared`、`step_private`、`verification`

## 6.5 workflow_step_dependencies

step 级依赖关系表。

建议字段：

1. `id` `INTEGER PK`
2. `step_id` `INTEGER NOT NULL FK workflow_steps.id`
3. `depends_on_step_id` `INTEGER NOT NULL FK workflow_steps.id`
4. `dependency_kind` `TEXT NOT NULL`
5. `required_artifact_types_json` `TEXT NOT NULL DEFAULT '[]'`
6. `is_blocking` `BOOLEAN NOT NULL DEFAULT 1`
7. `created_at` `DATETIME NOT NULL`

约束建议：

1. `UNIQUE(step_id, depends_on_step_id, dependency_kind)`

索引建议：

1. `INDEX step_deps_step_idx(step_id)`
2. `INDEX step_deps_depends_on_idx(depends_on_step_id)`

## 6.6 artifacts

证据、计划、报告、输出的统一载体。

建议字段：

1. `id` `INTEGER PK`
2. `requirement_id` `INTEGER NOT NULL FK requirements.id`
3. `workflow_run_id` `INTEGER FK workflow_runs.id`
4. `step_id` `INTEGER FK workflow_steps.id`
5. `producer_step_id` `INTEGER FK workflow_steps.id`
6. `artifact_type` `TEXT NOT NULL`
7. `path` `TEXT`
8. `content_summary` `TEXT`
9. `human_readable_body` `TEXT`
10. `machine_readable_payload` `TEXT`
11. `checksum` `TEXT`
12. `snapshot_version` `INTEGER NOT NULL DEFAULT 1`
13. `schema_version` `TEXT NOT NULL DEFAULT '1.0'`
14. `created_at` `DATETIME NOT NULL`

索引建议：

1. `INDEX artifacts_requirement_idx(requirement_id)`
2. `INDEX artifacts_run_idx(workflow_run_id)`
3. `INDEX artifacts_step_idx(step_id)`
4. `INDEX artifacts_type_idx(artifact_type)`
5. `INDEX artifacts_producer_step_idx(producer_step_id)`

说明：

1. `path` 用于落盘文件索引，例如 `roles/dev_rel/outputs/...`
2. `human_readable_body` 是 Markdown 面向阅读层
3. `machine_readable_payload` 是 JSON 面向控制层

## 6.7 step_input_bindings

描述 step 消费哪些 artifacts。

建议字段：

1. `id` `INTEGER PK`
2. `step_id` `INTEGER NOT NULL FK workflow_steps.id`
3. `artifact_id` `INTEGER NOT NULL FK artifacts.id`
4. `purpose` `TEXT NOT NULL`
5. `is_required` `BOOLEAN NOT NULL DEFAULT 1`
6. `consumed_at` `DATETIME`
7. `created_at` `DATETIME NOT NULL`

约束建议：

1. `UNIQUE(step_id, artifact_id, purpose)`

索引建议：

1. `INDEX step_input_bindings_step_idx(step_id)`
2. `INDEX step_input_bindings_artifact_idx(artifact_id)`

## 6.8 requirement_acceptance_checks

需求级验收项表。

建议字段：

1. `id` `INTEGER PK`
2. `requirement_id` `INTEGER NOT NULL FK requirements.id`
3. `check_key` `TEXT NOT NULL`
4. `description` `TEXT NOT NULL`
5. `check_type` `TEXT NOT NULL`
6. `owner_role` `TEXT NOT NULL`
7. `status` `TEXT NOT NULL DEFAULT 'pending'`
8. `success_criteria_markdown` `TEXT`
9. `verified_by_step_id` `INTEGER FK workflow_steps.id`
10. `evidence_artifact_id` `INTEGER FK artifacts.id`
11. `created_at` `DATETIME NOT NULL`
12. `updated_at` `DATETIME NOT NULL`

约束建议：

1. `UNIQUE(requirement_id, check_key)`

索引建议：

1. `INDEX req_checks_requirement_idx(requirement_id)`
2. `INDEX req_checks_status_idx(status)`
3. `INDEX req_checks_owner_role_idx(owner_role)`

## 6.9 approval_requests

这是对现有 `approvals` 的未来替代，不再把审批限定在 `task_id` 上。

建议字段：

1. `id` `INTEGER PK`
2. `requirement_id` `INTEGER FK requirements.id`
3. `workflow_run_id` `INTEGER FK workflow_runs.id`
4. `step_id` `INTEGER FK workflow_steps.id`
5. `approval_type` `TEXT NOT NULL`
6. `status` `TEXT NOT NULL DEFAULT 'pending'`
7. `reviewer` `TEXT`
8. `comment` `TEXT`
9. `created_at` `DATETIME NOT NULL`
10. `decided_at` `DATETIME`

索引建议：

1. `INDEX approval_requests_requirement_idx(requirement_id)`
2. `INDEX approval_requests_step_idx(step_id)`
3. `INDEX approval_requests_status_idx(status)`

说明：

1. Phase 1 可以继续复用 `approvals`
2. Phase 2 开始应逐步迁移到 `approval_requests`

## 6.10 workflow_step_events

这是对 `task_logs` 的未来替代，用于 step 级事件流。

建议字段：

1. `id` `INTEGER PK`
2. `step_id` `INTEGER NOT NULL FK workflow_steps.id`
3. `event_type` `TEXT NOT NULL`
4. `detail` `TEXT`
5. `created_at` `DATETIME NOT NULL`

索引建议：

1. `INDEX workflow_step_events_step_idx(step_id)`
2. `INDEX workflow_step_events_event_type_idx(event_type)`
3. `INDEX workflow_step_events_created_at_idx(created_at)`

说明：

1. Phase 1 可以仍由 `task_logs` 承担主要日志展示
2. Phase 2 开始将 runtime 事件逐步切到 `workflow_step_events`

---

## 7. 与现有表的兼容策略

### 7.1 tasks 的角色

Phase 1 中，`tasks` 不立即退役，而是作为 step execution adapter。

建议规则：

1. 每个可执行 `workflow_step` 创建一个兼容 `task`
2. `workflow_steps.compatibility_task_id` 指向该 task
3. UI 和 runtime 仍可复用现有任务执行链

### 7.2 approvals 的角色

Phase 1 继续允许：

1. `approvals.task_id -> tasks.id`

但新的审批语义不应继续只绑定 task。

因此：

1. `approval_requests` 是长期设计
2. `approvals` 是过渡设计

### 7.3 task_logs 的角色

Phase 1 继续允许：

1. `task_logs.task_id -> compatibility task`

长期上，step 事件应进入 `workflow_step_events`。

---

## 8. 索引与查询路径

系统最常见的查询路径有四类：

1. Requirement Pool 列表页
2. Requirement Detail 页
3. Workflow Run / Step 执行页
4. Validation / Closeout 查询

因此索引优先保障：

1. `requirements(status, priority, created_at)`
2. `workflow_runs(requirement_id, status)`
3. `workflow_steps(workflow_run_id, status)`
4. `artifacts(requirement_id, artifact_type)`
5. `requirement_acceptance_checks(requirement_id, status)`

不建议在 Phase 1 过度添加联合索引，先围绕已知页面和调度路径设计即可。

---

## 9. 迁移策略

### 9.1 迁移原则

当前仓库数据库层仍使用轻量 `_migrate()` 模式。

Phase 1 建议继续使用轻量迁移，规则如下：

1. 只新增表
2. 尽量不改动现有表语义
3. 如需给现有表补字段，只补兼容字段

### 9.2 迁移顺序

建议顺序：

1. 创建 `requirements`
2. 创建 `requirement_dependencies`
3. 创建 `workflow_runs`
4. 创建 `workflow_steps`
5. 创建 `workflow_step_dependencies`
6. 创建 `artifacts`
7. 创建 `step_input_bindings`
8. 创建 `requirement_acceptance_checks`
9. 创建 `approval_requests`
10. 创建 `workflow_step_events`

### 9.3 数据回填策略

Phase 1 不需要把历史 `tasks` 全量回填成 `requirements`。

建议：

1. 新功能只对新建 requirement 生效
2. 历史 task 继续按旧链路运行
3. 若后续需要迁移历史数据，再单独做离线脚本

---

## 10. Phase 1 实施切片

如果目标是最快进入实现，同时尽量避免返工，建议严格按这个切片做：

1. 新增 `requirements`
2. 新增 `requirement_dependencies`
3. 新增 `workflow_runs`
4. 新增 `workflow_steps`
5. 新增 `artifacts`
6. 新增 `step_input_bindings`
7. 新增 `requirement_acceptance_checks`
8. 在 `workflow_steps` 上加入 `compatibility_task_id`
9. 继续复用 `tasks`、`approvals`、`task_logs`

这一步已经可以支持：

1. Requirement Pool
2. Planner 输出落盘
3. step 顺序执行
4. step 输入绑定
5. 验收项关闭
6. 失败进入 bugfix step

---

## 11. 暂不建议现在就做的事情

为了降低 Phase 1 风险，暂不建议：

1. 立即废弃 `tasks`
2. 立即把 `approvals` 和 `task_logs` 全部重做
3. 一开始就支持任意 DAG 并行调度
4. 一开始就引入复杂的 polymorphic approval / event framework

原因很简单：

1. 当前目标是先跑通 requirement-first 主闭环
2. 现有 runtime 已可复用
3. 数据层应先为主流程服务，而不是先追求终极抽象

---

## 12. 最终建议

数据库层最重要的决定不是字段多少，而是边界是否清晰。

这份设计建议明确三层：

1. `requirements` 负责业务完成语义
2. `workflow_runs` / `workflow_steps` 负责编排和执行语义
3. `artifacts` / `requirement_acceptance_checks` 负责证据和关闭语义

同时保留 `tasks` 作为 Phase 1 的兼容执行桥，避免一上来推翻整个运行时。

因此，推荐的实际落地顺序是：

1. 先建新表
2. 再把 Planner Output 和 Step Context 写入这些表
3. 再通过 `compatibility_task_id` 接入现有执行链
4. 最后逐步去除对旧表的深度依赖