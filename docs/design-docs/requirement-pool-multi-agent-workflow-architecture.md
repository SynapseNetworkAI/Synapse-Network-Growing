---
id: requirement_pool_multi_agent_workflow_architecture
title: Synapse Ops 需求池与多 Agent 协作工作流架构设计
status: proposed
created_at: 2026-04-09
updated_at: 2026-04-09
author: github-copilot
target_repo: cliff-personal/Synapse-Network-Growing
---

# Synapse Ops 需求池与多 Agent 协作工作流架构设计

## 1. 背景与结论

当前 Synapse Ops 已经具备三项关键基础能力：

1. `roles/*` 自动发现业务 Agent。
2. 任务创建、执行、审批、日志、重试与 TaskBoard 展示。
3. `copilot_sdk` 长任务后台执行、状态持久化与恢复。

但当前系统的核心抽象仍然是“单条任务交给单个 Agent 执行”。

这意味着系统还不理解：

1. 一个需求需要先规划、再拆解、再执行、再验证。
2. 多个步骤之间存在依赖关系。
3. 不同角色需要串行协作直到任务完成。
4. 测试失败后进入 bugfix 分支。
5. 需求本身有问题时，需要先修订需求再继续执行。

因此，结论很明确：

1. **这个目标可以实现。**
2. **但必须把当前系统从 Task Executor 升级成 Requirement Orchestrator。**
3. **核心新增层不是更多 Agent，而是“需求池 + 工作流编排器 + 验证闭环”。**

---

## 2. 目标定义

本设计要实现的目标是：

1. 支持需求进入统一需求池。
2. 支持需求排序、依赖判定、阻塞管理。
3. 支持 Planner 先读取需求，输出实现计划、所需角色、执行步骤。
4. 支持多个 Agent 按步骤依次执行，直至测试验证通过。
5. 支持测试失败进入 bugfix 循环。
6. 支持需求本身有问题时进入 requirement revision。
7. 支持组织架构页只显示 `roles/*` 下真实存在的 Agent 角色。

本设计**不**在第一阶段解决：

1. 任意 DAG 的大规模并行调度。
2. 多租户隔离与跨团队权限模型。
3. 外部 issue tracker 双向同步。
4. 完整的 artifact 对象存储平台化。

---

## 3. 设计原则

### 3.1 需求优先于任务

系统的顶层抽象不再是 `Task`，而是 `Requirement`。

`Task` 或后续的 `Workflow Step` 只是需求实现过程中的执行单元，不应直接承担“业务完成”语义。

### 3.2 验证驱动关闭

需求不能因为某个 Agent 宣称“完成”就关闭。

需求关闭的唯一标准应是：

1. 计划中的验收项全部被验证通过。
2. 所有关联步骤都进入完成态。
3. 没有未关闭的 bugfix 子步骤。

### 3.3 业务角色与运行时角色分离

系统必须区分两类 Agent：

1. **业务角色 Agent**：来自 `roles/*`，是用户可见的组织成员。
2. **工作流角色 Agent**：Planner、Reviewer、Tester、Bugfixer 这类流程角色。

业务角色解决“谁负责”，工作流角色解决“这一步要干什么”。

### 3.4 数据驱动工作流，避免硬编码分支地狱

工作流顺序不应写死在代码的 if/else 里，而应由：

1. 标准化 `step_type`
2. 需求计划产出的 step graph
3. Orchestrator 的状态机

共同决定。

### 3.5 最小必要上下文原则

默认情况下，执行 Agent 不应看到整个需求的全部历史上下文。

系统应只向当前 step 暴露完成该 step 所必需的信息，包括：

1. 需求摘要与验收标准
2. 当前 step 的目标与完成条件
3. 明确指定的输入工件
4. 明确允许访问的文件范围
5. 必要的上游结论与风险提示

只有 Planner、Reviewer、Tester、Requirement Editor 这类流程角色，才应被授予更宽的全局上下文。

### 3.6 交接必须结构化，不依赖自然语言猜测

一个 step 的输出不能只是一段“请继续处理”的 prose。

系统必须要求每个 step 产出结构化 handoff，至少可回答：

1. 下游应该读取哪些内容
2. 下游应该验证哪些结果
3. 哪些文件允许继续修改
4. 哪些问题仍未解决

否则工作流虽然表面串起来了，但实现阶段仍会回到人工解释和重复沟通。

### 3.7 快照优先，避免运行时漂移

Requirement、Plan、Step Input、Artifact 引用都应基于运行开始时的快照，而不是依赖再次读取最新内容。

原因是：

1. 需求可能在执行中被修改
2. 上游步骤产物可能被覆盖
3. 工作树可能继续发生变化

因此系统需要区分：

1. `snapshot`：当前 run 应使用的冻结上下文
2. `live reference`：仅用于查看最新状态，不作为执行依据

### 3.8 组织架构只反映真实角色

组织架构页应只显示 `roles/*` 中真实存在的业务 Agent，不再展示静态 CTO 根节点和硬编码 team/domain 结构。

---

## 4. 当前系统边界

截至当前实现，系统数据模型主要包含：

1. `agents`
2. `tasks`
3. `approvals`
4. `task_logs`

这套模型适合：

1. 单任务创建与执行
2. 失败重试
3. 运行时日志与最终产出展示
4. 批量审批与运维操作

但不适合：

1. 表达需求依赖图
2. 表达一条需求的多个执行阶段
3. 记录 plan version
4. 记录 requirement revision
5. 记录验证闭环

因此，现有 `TaskRow` 不应被继续无限扩展成“万能对象”。

---

## 5. 目标架构

目标系统建议拆为五层。

### Layer 1: Requirement Pool

负责需求的收集、排序、依赖判定与状态管理。

职责：

1. 存储需求主记录。
2. 维护需求优先级和排序分数。
3. 表达需求依赖关系。
4. 只允许 `ready` 状态的需求进入调度队列。

### Layer 2: Planner

负责在执行前读取需求并输出计划。

职责：

1. 解析需求目标与验收标准。
2. 输出 step graph。
3. 给出所需角色与推荐 Agent。
4. 标记可能的风险、阻塞与前置条件。

#### 2.1 智能拆分策略

当需求关联了 `target_project_path` 时，Planner 根据需求描述中的关键词自动识别并拆分实现步骤：

| 关键词 | 拆分为 | 说明 |
|--------|--------|------|
| 方案设计、架构 | `design` step | 产出设计文档到 `roles/*/outputs/` |
| 前端、frontend、UI | `frontend_impl` step | 允许写入目标项目前端目录 |
| 后端、backend、API、服务端 | `backend_impl` step | 允许写入目标项目后端目录 |
| 测试、test、验证 | `test_impl` step | 允许读写测试目录 |

如果需求不包含上述关键词，退化为默认的单步 `implementation`。

多步实现之间为串行依赖关系：design → frontend_impl → backend_impl，最后统一进入 review → test → closeout。

#### 2.2 动态 file_scope

`file_scope` 不再固定为 `roles/**` + `docs/**`，而是根据 `target_project_path` 动态生成：

1. **实现步骤**：`allowed_read_globs` 和 `allowed_write_globs` 包含目标项目路径下的所有文件。
2. **Review/Test 步骤**：`allowed_read_globs` 包含目标项目路径，`allowed_write_globs` 限制为 `roles/**`（只产出报告，不修改代码）。
3. 始终保留 `roles/**`, `docs/**` 的读写权限用于产出文档和报告。

### Layer 3: Workflow Orchestrator

负责把需求计划变成可执行工作流。

职责：

1. 创建 workflow run。
2. 调度 step 执行顺序。
3. 处理依赖关系与重试策略。
4. 管理 bugfix loop 与 requirement revision。

### Layer 4: Step Executor Runtime

负责执行单个 workflow step。

职责：

1. 根据 `assigned_agent_id` 或流程角色生成 prompt/context。
2. 调用当前 `legacy` 或 `copilot_sdk` runtime。
3. 回写 step 产物、日志、产出与状态。

### Layer 5: Verification & Closure

负责验收和关闭。

职责：

1. 收集测试与验证结果。
2. 判断 acceptance criteria 是否全部满足。
3. 未满足时创建 bugfix step。
4. 全部通过后关闭 requirement。

---

## 6. 两类 Agent 模型

### 6.1 业务角色 Agent

来源：`roles/*/prompts/persona.md`

当前仓库已有角色：

1. `content_writer`
2. `cro_optimizer`
3. `dev_rel`
4. `growth_lead`
5. `launch_strategist`
6. `seo_strategist`

这些 Agent 应继续作为：

1. 组织架构页的唯一展示对象。
2. 实际业务执行步骤的负责人。

### 6.2 工作流角色 Agent

这是新增的流程语义层，不一定直接显示在组织架构页。

第一阶段建议支持：

1. `planner`
2. `implementer`
3. `reviewer`
4. `tester`
5. `bugfixer`
6. `requirement_editor`

映射策略：

1. `planner` 初期可由 `dev_rel` 或通用 runtime planner prompt 承担。
2. `implementer` 由 Planner 推荐业务角色。
3. `reviewer` 与 `tester` 尽量独立于 `implementer`。
4. `bugfixer` 可复用 `implementer`，但必须单独作为 step type 记录。
5. `requirement_editor` 负责在需求有歧义时修订需求描述和验收标准。

---

## 7. 核心实体设计

数据库物理建模、索引、迁移和与现有 `tasks`/`approvals`/`task_logs` 的兼容策略，单独见 [docs/design-docs/requirement-pool-workflow-database-design.md](docs/design-docs/requirement-pool-workflow-database-design.md)。

### 7.1 requirements

建议新增 `requirements` 表，作为需求池主表。

核心字段：

1. `id`
2. `title`
3. `description`
4. `status`
5. `priority`
6. `source`
7. `acceptance_criteria`
8. `current_plan_version`
9. `planned_roles`
10. `blocked_by_count`
11. `created_at`
12. `started_at`
13. `completed_at`

推荐状态机：

1. `draft`
2. `triaged`
3. `blocked`
4. `ready`
5. `planning`
6. `in_progress`
7. `validating`
8. `needs_revision`
9. `done`
10. `cancelled`

### 7.2 requirement_dependencies

用于表达“先做被依赖项”。

核心字段：

1. `requirement_id`
2. `depends_on_requirement_id`
3. `dependency_type`

第一阶段只需要 `hard_block` 即可。

### 7.3 workflow_runs

一条需求可以多次被规划或重跑，因此需要独立的 workflow run。

核心字段：

1. `id`
2. `requirement_id`
3. `plan_version`
4. `status`
5. `triggered_by`
6. `started_at`
7. `completed_at`

### 7.4 workflow_steps

这是系统真正执行的单元。

核心字段：

1. `id`
2. `workflow_run_id`
3. `requirement_id`
4. `step_key`
5. `step_type`
6. `title`
7. `assigned_agent_id`
8. `assigned_workflow_role`
9. `depends_on_step_id`
10. `status`
11. `input_artifact_id`
12. `output_artifact_id`
13. `retry_count`
14. `runtime_backend`
15. `runtime_session_id`
16. `started_at`
17. `completed_at`

仅靠上述字段仍不足以支撑稳定交接。

为了避免后期返工，建议在逻辑模型中补充以下能力，哪怕第一阶段先以 JSON 字段承载：

18. `context_scope`
19. `handoff_summary`
20. `done_when`
21. `file_scope`
22. `validation_targets`
23. `failure_policy`
24. `approval_policy`

其中：

1. `context_scope` 定义当前 step 可以看到哪些层级的上下文
2. `handoff_summary` 供下游快速理解上游结论
3. `done_when` 是结构化完成条件，而不是自由文本备注
4. `file_scope` 限定允许读取或修改的仓库范围
5. `validation_targets` 定义测试、审查、断言对象
6. `failure_policy` 定义失败后是重试、转 bugfix 还是转 revision
7. `approval_policy` 定义是否需要人工确认后再进入下一步

另外，`depends_on_step_id` 建议不要长期停留在单依赖模型。

真实流程里一个 step 往往会同时依赖：

1. 实现输出
2. 代码评审结论
3. 测试报告

因此推荐在物理实现上改为 `workflow_step_dependencies` 关联表，当前文档中的单字段可仅作为 MVP 兼容表示。

### 7.5 workflow_step_dependencies

用于表达 step 级别依赖，而不仅是 requirement 级别依赖。

核心字段：

1. `step_id`
2. `depends_on_step_id`
3. `dependency_kind`
4. `required_artifact_types`
5. `is_blocking`

建议支持的 `dependency_kind`：

1. `output_required`
2. `review_required`
3. `test_required`
4. `approval_required`

这样下游 step 才能明确知道自己不是“依赖上一个 agent”，而是“依赖上一个步骤的哪类产物”。

### 7.6 artifacts

用于存储计划、实现说明、测试结果、修订内容等。

核心字段：

1. `id`
2. `requirement_id`
3. `workflow_run_id`
4. `step_id`
5. `artifact_type`
6. `path`
7. `content_summary`
8. `checksum`
9. `created_at`
10. `producer_step_id`
11. `snapshot_version`
12. `schema_version`

建议 artifact type 包括：

1. `requirement_snapshot`
2. `implementation_plan`
3. `step_output`
4. `review_report`
5. `test_report`
6. `bug_report`
7. `requirement_revision`
8. `review_checklist_result`
9. `validation_manifest`
10. `execution_log_bundle`

artifact 需要满足两个要求：

1. 可被人阅读
2. 可被系统验证和路由

因此建议每类 artifact 都有：

1. `human_readable_body`
2. `machine_readable_payload`

前者用于 TaskBoard / Requirement Detail 页面展示，后者用于 Orchestrator 和 Verifier 自动判断下一步动作。

### 7.6.1 JSON 与 Markdown 的职责划分

在这个系统里，不建议在 JSON 和 Markdown 之间二选一，而应明确分层。

建议规则：

1. **JSON 是控制面真相源**
2. **Markdown 是阅读面和协作面投影**

也就是说：

1. Orchestrator、Verifier、依赖调度、状态推进、幂等恢复，应依赖 JSON
2. Agent 阅读、人工审批、TaskBoard 展示、Requirement Detail 展示，可以依赖 Markdown

原因很直接：

1. JSON 适合字段约束、状态判断、依赖路由和自动校验
2. Markdown 适合长文本说明、方案解释、审查意见和人类阅读

因此推荐每个关键 artifact 都以“双表示”存在：

1. canonical JSON payload
2. 从同一 payload 派生的 Markdown summary

不能反过来让 Markdown 成为唯一真相源，否则后续实现中会遇到：

1. 字段解析不稳定
2. prompt 中靠自然语言猜测路由
3. 验证阶段难以自动判断通过条件
4. 恢复和幂等逻辑难以建立

### 7.6.2 对 Agent 更友好的实际做法

“对 Agent 友好”不等于“全部给 Markdown”或“全部给 JSON”。

更合理的做法是：

1. 用 JSON 存结构化事实
2. 用 Markdown 呈现需要阅读和推理的摘要
3. 执行器在构造上下文时，把 JSON 中的关键字段渲染成短 Markdown 或项目符号，再连同必要 artifact 一起注入

换句话说：

1. 持久化层优先 JSON
2. 上下文注入层优先精选后的 Markdown 片段
3. 原始 JSON 仅在需要精确字段时附带给 Agent

这能同时兼顾系统稳定性和 Agent 可读性。

### 7.7 step_input_bindings

为了避免 `input_artifact_id` 单值字段在后期被推翻，建议设计显式输入绑定表。

核心字段：

1. `step_id`
2. `artifact_id`
3. `purpose`
4. `is_required`
5. `consumed_at`

建议 `purpose` 包括：

1. `primary_spec`
2. `implementation_context`
3. `review_context`
4. `test_context`
5. `bugfix_context`

这样执行器在构造 prompt/context 时，不是把所有 artifact 都塞给 Agent，而是按用途精确注入。

### 7.8 file_scopes

为了避免 Agent 在执行中无边界扫描整个仓库，建议把文件范围显式建模。

核心字段：

1. `id`
2. `requirement_id`
3. `workflow_run_id`
4. `step_id`
5. `allowed_read_globs`
6. `allowed_write_globs`
7. `blocked_globs`
8. `reason`

这解决三个问题：

1. 实现 Agent 明确知道应该看哪些文件
2. Reviewer / Tester 明确知道应该验证哪些范围
3. 工具层可以据此限制搜索与修改权限

### 7.9 requirement_acceptance_checks

仅有 `acceptance_criteria` 文本仍然过于宽泛，建议把验收项细化成可追踪对象。

核心字段：

1. `id`
2. `requirement_id`
3. `check_key`
4. `description`
5. `check_type`
6. `owner_role`
7. `status`
8. `verified_by_step_id`
9. `evidence_artifact_id`

建议 `check_type` 包括：

1. `manual_review`
2. `automated_test`
3. `artifact_presence`
4. `content_assertion`
5. `file_diff_assertion`

这样“需求是否完成”就不再是模糊判断，而是有一组明确的 checks 被逐项关闭。

---

## 8. 需求池排序与可执行判定

### 8.1 可执行判定

需求是否能进入调度队列，不由优先级决定，而是先由依赖决定。

规则：

1. 存在未完成硬依赖的需求，状态必须是 `blocked`。
2. 只有没有未完成依赖的需求，才能进入 `ready`。
3. `ready` 需求才可被 Planner 转成 workflow run。

### 8.2 排序模型

在所有 `ready` 需求中，建议按综合分数排序：

$$
score = priority + aging + business\_value - risk\_penalty
$$

第一阶段可以先简化为：

1. `high` 优先于 `normal` 优先于 `low`
2. 同优先级按创建时间先后排序
3. 若某需求被更多其他需求依赖，则提高排序权重

---

## 9. 标准工作流模板

建议先把系统能力收敛到一条标准模板，而不是一开始支持任意工作流。

标准主链：

1. `plan`
2. `implementation`
3. `review`
4. `test`
5. `closeout`

异常支线：

1. `bugfix`
2. `requirement_revision`

标准状态流：

```text
requirement_received
-> requirement_triaged
-> plan_generated
-> roles_selected
-> steps_scheduled
-> implementation
-> review
-> test_validation
-> bugfix_loop? 
-> requirement_done
```

如果测试失败：

```text
test_validation_failed
-> bugfix_step_created
-> bugfix_execution
-> re_review
-> re_test
```

如果需求有问题：

```text
plan_or_review_detects_requirement_issue
-> requirement_revision
-> new_plan_version
-> re_schedule
```

---

## 10. Planner 输出契约

Planner 不应只输出一段 prose，而应输出结构化计划。

最小输出契约建议包括：

1. `goal_summary`
2. `acceptance_criteria`
3. `required_roles`
4. `workflow_steps`
5. `known_risks`
6. `open_questions`
7. `required_inputs`
8. `global_constraints`
9. `validation_plan`

其中 `workflow_steps` 至少包含：

1. `step_key`
2. `step_type`
3. `title`
4. `assigned_role`
5. `depends_on`
6. `done_when`
7. `required_artifacts`
8. `file_scope`
9. `expected_outputs`
10. `validation_targets`
11. `failure_policy`

这样 Orchestrator 才能真正把计划转成可执行图，而不是继续依赖人工理解。

进一步说，Planner 输出应该满足三层契约。

### 10.1 计划层契约

必须回答：

1. 这条需求要做到什么
2. 为什么按这个顺序执行
3. 哪些验收项必须被单独验证

### 10.2 步骤层契约

每个 step 都必须回答：

1. 我读取哪些输入
2. 我允许读取或修改哪些文件
3. 我完成后必须交付什么
4. 谁会消费我的输出
5. 我失败后进入哪条支线

### 10.3 验证层契约

必须回答：

1. 验证谁负责
2. 验证使用什么方法
3. 验证证据保存在哪里
4. 哪些 check 通过后 requirement 才能关闭

### 10.4 应该定死什么，应该保留什么弹性

把结构定死，并不等于把整体工作流程写死。

真正应该定死的是**协议边界**，而不是每个 Agent 的具体表达方式。

建议按下面原则处理：

#### 必须定死的部分

这些内容一旦不定死，后面大概率返工：

1. 顶层对象模型：requirement、workflow run、workflow step、artifact、acceptance check
2. 状态机名称与状态转换约束
3. Planner 输出中的关键字段名和必填字段
4. step context 的三层结构
5. artifact 的 JSON 真相源格式
6. 验证结果的结构化输出格式
7. 幂等、恢复、审批 gate 的控制字段

这些内容属于系统的“控制面协议”，应该尽早稳定。

#### 应该保留弹性的部分

这些内容不应该过早写死，否则会抑制 Agent 能力：

1. `goal_summary`、`known_risks`、`open_questions` 的表述方式
2. review report、bug report、plan explanation 的正文写法
3. 每个角色的提示词组织方式
4. Markdown summary 的模板细节
5. 某些非关键扩展字段

这些内容属于“内容层”和“协作层”，可以允许 Agent 自由发挥。

#### 更合适的设计方式

因此下一步最合适的方案不是“只写 JSON Schema”或“只保留 Markdown 灵活性”，而是：

1. **先定义一个最小且稳定的 Planner Output JSON Schema**
2. **再允许 schema 中若干字段承载自由文本 Markdown 内容**

推荐模式如下：

1. schema 定义字段存在性、字段类型、依赖关系、最小必填约束
2. 字段内容中的长文本说明允许 Agent 用 Markdown 生成
3. 下游运行时只依赖结构化字段做调度和验证
4. 人和 Agent 阅读时优先看渲染后的 Markdown 摘要

也就是说：

1. **用 schema 锁定骨架**
2. **用 Markdown 保留肌肉和表达弹性**

这不会伤害整体工作流，反而会让流程更稳定，因为编排层不再依赖“猜 Planner 想表达什么”。

### 10.5 Planner Output JSON Schema

下面给出建议的最小稳定 schema。目标不是一次性穷举所有字段，而是先锁定 Phase 1 真正需要的控制面协议。

```json
{
	"$schema": "https://json-schema.org/draft/2020-12/schema",
	"$id": "synapse://schemas/planner-output.schema.json",
	"title": "PlannerOutput",
	"type": "object",
	"additionalProperties": false,
	"required": [
		"schema_version",
		"goal_summary",
		"acceptance_checks",
		"required_roles",
		"workflow_steps",
		"validation_plan"
	],
	"properties": {
		"schema_version": {
			"type": "string",
			"const": "1.0"
		},
		"goal_summary": {
			"type": "string",
			"minLength": 1
		},
		"goal_summary_markdown": {
			"type": "string"
		},
		"acceptance_checks": {
			"type": "array",
			"minItems": 1,
			"items": {
				"type": "object",
				"additionalProperties": false,
				"required": ["check_key", "description", "check_type", "owner_role"],
				"properties": {
					"check_key": { "type": "string", "minLength": 1 },
					"description": { "type": "string", "minLength": 1 },
					"check_type": {
						"type": "string",
						"enum": [
							"manual_review",
							"automated_test",
							"artifact_presence",
							"content_assertion",
							"file_diff_assertion"
						]
					},
					"owner_role": { "type": "string", "minLength": 1 },
					"success_criteria_markdown": { "type": "string" }
				}
			}
		},
		"required_roles": {
			"type": "array",
			"minItems": 1,
			"items": { "type": "string", "minLength": 1 },
			"uniqueItems": true
		},
		"known_risks_markdown": {
			"type": "string"
		},
		"open_questions_markdown": {
			"type": "string"
		},
		"global_constraints_markdown": {
			"type": "string"
		},
		"workflow_steps": {
			"type": "array",
			"minItems": 1,
			"items": {
				"type": "object",
				"additionalProperties": false,
				"required": [
					"step_key",
					"step_type",
					"title",
					"assigned_role",
					"depends_on",
					"required_artifacts",
					"file_scope",
					"expected_outputs",
					"validation_targets",
					"done_when_markdown",
					"failure_policy"
				],
				"properties": {
					"step_key": { "type": "string", "minLength": 1 },
					"step_type": {
						"type": "string",
						"enum": [
							"plan",
							"implementation",
							"review",
							"test",
							"closeout",
							"bugfix",
							"requirement_revision"
						]
					},
					"title": { "type": "string", "minLength": 1 },
					"assigned_role": { "type": "string", "minLength": 1 },
					"depends_on": {
						"type": "array",
						"items": { "type": "string", "minLength": 1 },
						"uniqueItems": true
					},
					"required_artifacts": {
						"type": "array",
						"items": {
							"type": "object",
							"additionalProperties": false,
							"required": ["artifact_type", "purpose", "required"],
							"properties": {
								"artifact_type": { "type": "string", "minLength": 1 },
								"purpose": { "type": "string", "minLength": 1 },
								"required": { "type": "boolean" }
							}
						}
					},
					"file_scope": {
						"type": "object",
						"additionalProperties": false,
						"required": ["allowed_read_globs", "allowed_write_globs", "blocked_globs"],
						"properties": {
							"allowed_read_globs": {
								"type": "array",
								"items": { "type": "string", "minLength": 1 }
							},
							"allowed_write_globs": {
								"type": "array",
								"items": { "type": "string", "minLength": 1 }
							},
							"blocked_globs": {
								"type": "array",
								"items": { "type": "string", "minLength": 1 }
							}
						}
					},
					"expected_outputs": {
						"type": "array",
						"minItems": 1,
						"items": {
							"type": "object",
							"additionalProperties": false,
							"required": ["artifact_type", "description"],
							"properties": {
								"artifact_type": { "type": "string", "minLength": 1 },
								"description": { "type": "string", "minLength": 1 }
							}
						}
					},
					"validation_targets": {
						"type": "array",
						"items": {
							"type": "object",
							"additionalProperties": false,
							"required": ["check_key", "method"],
							"properties": {
								"check_key": { "type": "string", "minLength": 1 },
								"method": { "type": "string", "minLength": 1 },
								"command": { "type": "string" }
							}
						}
					},
					"done_when_markdown": {
						"type": "string",
						"minLength": 1
					},
					"failure_policy": {
						"type": "object",
						"additionalProperties": false,
						"required": ["on_failure"],
						"properties": {
							"on_failure": {
								"type": "string",
								"enum": ["retry", "bugfix", "requirement_revision", "block"]
							},
							"max_retries": {
								"type": "integer",
								"minimum": 0
							}
						}
					},
					"extensions": {
						"type": "object",
						"additionalProperties": true
					}
				}
			}
		},
		"validation_plan": {
			"type": "object",
			"additionalProperties": false,
			"required": ["owner_role", "checks"],
			"properties": {
				"owner_role": { "type": "string", "minLength": 1 },
				"checks": {
					"type": "array",
					"minItems": 1,
					"items": { "type": "string", "minLength": 1 }
				},
				"summary_markdown": { "type": "string" }
			}
		},
		"extensions": {
			"type": "object",
			"additionalProperties": true
		}
	}
}
```

### 10.6 Step Context JSON Schema

这个 schema 不是给 Planner 输出计划用的，而是给 Step Executor 真正构造当前 step 执行上下文用的。

```json
{
	"$schema": "https://json-schema.org/draft/2020-12/schema",
	"$id": "synapse://schemas/step-context.schema.json",
	"title": "StepContext",
	"type": "object",
	"additionalProperties": false,
	"required": [
		"schema_version",
		"global_context",
		"step_context",
		"validation_context"
	],
	"properties": {
		"schema_version": {
			"type": "string",
			"const": "1.0"
		},
		"global_context": {
			"type": "object",
			"additionalProperties": false,
			"required": [
				"requirement_id",
				"workflow_run_id",
				"plan_version",
				"requirement_snapshot",
				"acceptance_checks",
				"artifact_index"
			],
			"properties": {
				"requirement_id": { "type": "string", "minLength": 1 },
				"workflow_run_id": { "type": "string", "minLength": 1 },
				"plan_version": { "type": "integer", "minimum": 1 },
				"requirement_snapshot": {
					"type": "object",
					"additionalProperties": false,
					"required": ["title", "description_markdown"],
					"properties": {
						"title": { "type": "string", "minLength": 1 },
						"description_markdown": { "type": "string", "minLength": 1 }
					}
				},
				"acceptance_checks": {
					"type": "array",
					"items": {
						"type": "object",
						"additionalProperties": false,
						"required": ["check_key", "description", "status"],
						"properties": {
							"check_key": { "type": "string", "minLength": 1 },
							"description": { "type": "string", "minLength": 1 },
							"status": {
								"type": "string",
								"enum": ["pending", "passed", "failed", "blocked"]
							}
						}
					}
				},
				"artifact_index": {
					"type": "array",
					"items": {
						"type": "object",
						"additionalProperties": false,
						"required": ["artifact_id", "artifact_type"],
						"properties": {
							"artifact_id": { "type": "string", "minLength": 1 },
							"artifact_type": { "type": "string", "minLength": 1 },
							"summary_markdown": { "type": "string" }
						}
					}
				}
			}
		},
		"step_context": {
			"type": "object",
			"additionalProperties": false,
			"required": [
				"step_id",
				"step_key",
				"step_type",
				"assigned_role",
				"objective_markdown",
				"done_when_markdown",
				"bound_inputs",
				"file_scope",
				"expected_outputs"
			],
			"properties": {
				"step_id": { "type": "string", "minLength": 1 },
				"step_key": { "type": "string", "minLength": 1 },
				"step_type": { "type": "string", "minLength": 1 },
				"assigned_role": { "type": "string", "minLength": 1 },
				"objective_markdown": { "type": "string", "minLength": 1 },
				"done_when_markdown": { "type": "string", "minLength": 1 },
				"handoff_summary_markdown": { "type": "string" },
				"bound_inputs": {
					"type": "array",
					"items": {
						"type": "object",
						"additionalProperties": false,
						"required": ["artifact_id", "artifact_type", "purpose", "required"],
						"properties": {
							"artifact_id": { "type": "string", "minLength": 1 },
							"artifact_type": { "type": "string", "minLength": 1 },
							"purpose": { "type": "string", "minLength": 1 },
							"required": { "type": "boolean" },
							"summary_markdown": { "type": "string" }
						}
					}
				},
				"file_scope": {
					"type": "object",
					"additionalProperties": false,
					"required": ["allowed_read_globs", "allowed_write_globs", "blocked_globs"],
					"properties": {
						"allowed_read_globs": {
							"type": "array",
							"items": { "type": "string", "minLength": 1 }
						},
						"allowed_write_globs": {
							"type": "array",
							"items": { "type": "string", "minLength": 1 }
						},
						"blocked_globs": {
							"type": "array",
							"items": { "type": "string", "minLength": 1 }
						}
					}
				},
				"expected_outputs": {
					"type": "array",
					"items": {
						"type": "object",
						"additionalProperties": false,
						"required": ["artifact_type", "description"],
						"properties": {
							"artifact_type": { "type": "string", "minLength": 1 },
							"description": { "type": "string", "minLength": 1 }
						}
					}
				}
			}
		},
		"validation_context": {
			"type": "object",
			"additionalProperties": false,
			"required": ["changed_files", "validation_targets"],
			"properties": {
				"changed_files": {
					"type": "array",
					"items": { "type": "string", "minLength": 1 }
				},
				"validation_targets": {
					"type": "array",
					"items": {
						"type": "object",
						"additionalProperties": false,
						"required": ["check_key", "method"],
						"properties": {
							"check_key": { "type": "string", "minLength": 1 },
							"method": { "type": "string", "minLength": 1 },
							"command": { "type": "string" }
						}
					}
				},
				"review_report_markdown": { "type": "string" },
				"bug_report_markdown": { "type": "string" }
			}
		},
		"extensions": {
			"type": "object",
			"additionalProperties": true
		}
	}
}
```

这两个 schema 的设计原则是：

1. 用必填字段锁定编排协议
2. 用 `*_markdown` 字段保留 Agent 可读性和表达弹性
3. 用 `extensions` 保留未来扩展位，避免早期 schema 过度僵化

---

## 11. Agent Context Contract

这是本方案避免后期返工的关键约束之一。

### 11.1 为什么不能让所有 Agent 看同样的上下文

如果所有 Agent 都看到同样的上下文，会立刻出现四类问题：

1. prompt 膨胀，运行成本失控
2. 实现 Agent 被无关历史干扰
3. 责任边界模糊，无法判断谁该验证什么
4. 评审与测试无法证明自己是独立步骤

因此默认策略必须是：

**共享 requirement，隔离 step execution context。**

### 11.2 所有 step 默认共享的信息

1. requirement snapshot
2. 当前 plan version
3. acceptance checks 摘要
4. workflow run 元数据

这部分可视为**全局共享上下文**。

建议固定包括：

1. requirement snapshot
2. acceptance criteria 或 acceptance checks 摘要
3. 当前 plan version
4. artifact 索引

### 11.3 Implementer 可见信息

1. 当前 step 目标
2. required input artifacts
3. file scope
4. done_when
5. 上游 review / test 风险摘要（如适用）

这部分可视为**step 私有上下文**。

建议固定包括：

1. 当前 step 的目标
2. 依赖步骤输出
3. 必读文件
4. 允许修改的文件范围
5. 预期产出

默认不应直接注入：

1. 全量历史日志
2. 与当前 step 无关的其他分支产物
3. 整个仓库任意文件

### 11.4 Reviewer 可见信息

1. implementer 输出
2. changed files
3. review checklist
4. acceptance checks 中与评审相关的项

### 11.5 Tester / Verifier 可见信息

1. acceptance checks
2. validation targets
3. changed files
4. implementation / review artifacts
5. 需要执行的测试命令或验证方法

这部分可视为**验证上下文**。

建议固定包括：

1. changed files
2. acceptance criteria 或 acceptance checks
3. test commands 或 validation methods
4. review report
5. bug report

如果某类需求没有自动化测试命令，也必须至少有结构化 validation method，而不是留空。

### 11.6 Requirement Editor 可见信息

1. 原始 requirement snapshot
2. Planner open questions
3. review / test 中暴露出的需求问题
4. 当前 plan version 与拟议修订内容

### 11.7 Context 生成顺序

建议执行器按以下顺序构造上下文：

1. requirement snapshot
2. current plan summary
3. bound input artifacts
4. file scope
5. role persona
6. current step instructions
7. validation targets / done_when

这样每个 Agent 看到的内容是可解释、可追踪、可最小化的。

---

## 12. Step Executor 与现有 runtime 的衔接

这部分是本设计最有利的地方：现有 runtime 不需要推翻重写，只需要从“执行 Task”扩展成“执行 Workflow Step”。

建议策略：

1. 保留当前 `legacy` 与 `copilot_sdk` runtime 抽象。
2. 让 `workflow_steps` 调用同一套 runtime execute 接口。
3. 把当前 `TaskExecutionResult` 视为 step execution result 的底层实现。
4. 现有 `task_logs` 演进为 step logs，或新增 `workflow_step_logs`。

第一阶段可以采用兼容模式：

1. Requirement 生成 workflow step 时，同时为每个 step 创建兼容 `task`。
2. TaskBoard 继续作为 step execution viewer。
3. Requirement Pool 页面单独负责顶层编排。

这样可以减少一次性重构范围。

但要注意，为了避免以后再拆库迁移，Step Executor 从第一阶段起就应抽象出以下接口：

1. `build_step_context(step_id)`
2. `resolve_step_artifacts(step_id)`
3. `resolve_file_scope(step_id)`
4. `execute_step(step_id)`
5. `finalize_step(step_id, result)`

---

## 13. 测试验证与关闭机制

### 13.1 Verifier 的职责

测试与验收必须独立建模，不应和实现步骤混在一起。

Verifier / Tester 负责：

1. 读取 acceptance criteria
2. 运行对应测试或验证命令
3. 生成 `test_report` artifact
4. 输出是否满足关闭条件

建议进一步要求 Verifier 输出结构化结果：

1. `checked_items`
2. `passed_items`
3. `failed_items`
4. `blocked_items`
5. `evidence_artifacts`

### 13.2 Requirement 关闭条件

需求关闭需要同时满足：

1. 所有必需 step 处于 `completed`
2. 所有 acceptance criteria 标记为通过
3. 没有 `failed` 或 `blocked` 的验证步骤
4. 没有未处理的 requirement revision 请求

另外建议增加：

5. 所有关联 artifact 已落盘并可追溯
6. 当前 run 没有悬挂中的 approval gate

### 13.3 Bugfix Loop

测试失败时，系统不应该简单把需求置为失败，而应：

1. 创建 bugfix step
2. 将状态从 `validating` 回退到 `in_progress`
3. 指派给 bugfixer / implementer
4. 修复后重新进入 `review -> test`

这就是“直到任务完成”的真正含义。

### 13.4 Verification 不应只依赖测试命令

很多增长、内容、运营类需求并不存在单一自动化测试命令。

因此 Verifier 必须支持多种验证来源：

1. 自动化测试
2. 结构化内容检查
3. 目标文件存在性与差异检查
4. 人工审批结果
5. 外部链接或发布产物检查

否则该架构会在非代码型需求上失效。

---

## 14. 运行时状态机、恢复与幂等

为了避免实现阶段再补灾难恢复逻辑，建议现在就明确运行时约束。

### 14.1 workflow step 状态机

建议 step 至少支持：

1. `pending`
2. `ready`
3. `running`
4. `waiting_approval`
5. `waiting_dependency`
6. `blocked`
7. `failed`
8. `completed`
9. `cancelled`

### 14.2 幂等要求

以下操作必须设计成幂等：

1. `plan requirement`
2. `start workflow run`
3. `execute step`
4. `finalize step`
5. `create bugfix step`
6. `close requirement`

否则后台 monitor、重试机制、人工重复点击都会制造重复步骤或重复关闭。

### 14.3 恢复要求

系统应支持在以下情况下恢复：

1. 服务重启
2. Copilot session 中断
3. step 已完成但完成事件未及时回写
4. approval 已提交但状态未推进

恢复时必须以 durable state 和 artifact 状态为准，而不是以内存状态为准。

### 14.4 并发保护

建议至少保证：

1. 同一 requirement 同时只有一个 active workflow run
2. 同一 step 同时只有一个 active executor
3. close / validate / retry 之间有乐观锁或版本检查

否则编排层很容易出现竞态。

---

## 15. 审批、人工介入与治理边界

纯自动化并不适用于所有需求，因此治理边界也应先建模。

建议系统支持以下 gate：

1. `pre_execution_approval`
2. `pre_publish_approval`
3. `requirement_revision_approval`
4. `manual_close_approval`

同时需要记录：

1. 谁批准
2. 批准依据是什么
3. 批准影响了哪个 step / requirement 状态

这样可以避免后期把审批逻辑散落到各页面和各 runtime 分支里。

---

## 16. 可观测性与审计要求

需求编排一旦进入真实执行，没有审计链会非常难排查问题。

建议从设计阶段就要求以下可观测性：

1. requirement timeline
2. workflow run timeline
3. step event timeline
4. artifact lineage graph
5. validation evidence view

至少要能回答：

1. 为什么这一步会执行
2. 它读了哪些输入
3. 它改了哪些文件
4. 它产出了什么
5. 为什么系统判定通过或失败

---

## 17. 前端改造建议

### 17.1 新增 Requirement Pool 页面

建议新增独立页面，而不是把所有概念继续堆进现有 TaskBoard。

需求池页面应展示：

1. 需求标题
2. 需求优先级
3. 当前状态
4. 依赖与阻塞状态
5. 当前 plan version
6. 推荐角色
7. 当前 workflow 进度

支持操作：

1. 新建需求
2. 编辑需求
3. 查看依赖图
4. 触发规划
5. 继续执行
6. 标记关闭

### 17.2 TaskBoard 角色调整

TaskBoard 不再承担“顶层需求管理”，而是聚焦：

1. 当前运行中的 workflow steps
2. 单步执行日志
3. Copilot 输出
4. 审批 / 重试 / Bugfix 执行细节

### 17.3 Requirement Detail 页面

需要新增 Requirement Detail 页面，显示：

1. 需求描述
2. 计划版本历史
3. 依赖关系
4. workflow timeline
5. artifacts
6. 测试结果
7. 关闭状态

### 17.4 OrgChart 重构

当前组织架构页仍然带有静态 `CTO` 根节点与 team/domain 假设。

应改为：

1. 仅显示 `roles/*` 自动发现的真实角色
2. 可按 `group` 分组展示
3. 可显示技能、目标、最近任务数
4. 不展示 runtime workflow agents

换句话说：

1. OrgChart 展示“业务组织”
2. Workflow 页面展示“执行流程”

两者必须分离。

---

## 18. 后端 API 改造建议

建议新增 API 族：

### Requirements

1. `GET /api/requirements`
2. `POST /api/requirements`
3. `GET /api/requirements/{id}`
4. `PATCH /api/requirements/{id}`
5. `POST /api/requirements/{id}/plan`
6. `POST /api/requirements/{id}/start`
7. `POST /api/requirements/{id}/close`

### Dependencies

1. `POST /api/requirements/{id}/dependencies`
2. `DELETE /api/requirements/{id}/dependencies/{dependency_id}`

### Workflow

1. `GET /api/workflows/{id}`
2. `GET /api/requirements/{id}/workflows`
3. `POST /api/workflow-steps/{id}/run`
4. `POST /api/workflow-steps/{id}/retry`
5. `GET /api/workflow-steps/{id}/logs`
6. `GET /api/workflow-steps/{id}/context`
7. `GET /api/workflow-steps/{id}/artifacts`
8. `GET /api/workflow-steps/{id}/dependencies`

### Verification

1. `POST /api/requirements/{id}/validate`
2. `GET /api/requirements/{id}/artifacts`
3. `GET /api/requirements/{id}/acceptance-checks`
4. `POST /api/workflow-steps/{id}/approve`

### Governance

1. `GET /api/requirements/{id}/timeline`
2. `GET /api/workflows/{id}/lineage`
3. `POST /api/requirements/{id}/replan`
4. `POST /api/requirements/{id}/revision`

---

## 19. 分阶段实施计划

### Phase 1: Requirement Pool MVP

目标：让系统从 task-first 升级到 requirement-first。

范围：

1. 新增 `requirements`
2. 新增 `requirement_dependencies`
3. 新增 Requirement Pool 页面
4. 新增 Planner 输出结构化计划
5. 需求可生成顺序执行的 steps
6. 引入最小版 `file_scope` 与 `step_input_bindings`
7. 引入最小版 acceptance checks

这一阶段仍可复用现有 `tasks` 作为执行单元。

### Phase 2: Workflow Orchestrator

目标：支持真正的多 step 编排。

范围：

1. 新增 `workflow_runs`
2. 新增 `workflow_steps`
3. 新增 step 状态机与依赖调度
4. 支持 `plan -> implementation -> review -> test` 标准链
5. 支持 step context 构建与 artifact 绑定

### Phase 3: Bugfix Loop + Requirement Revision

目标：支持异常闭环。

范围：

1. 支持测试失败自动创建 bugfix step
2. 支持需求问题进入 revision
3. 支持 plan version 递增与重规划
4. 支持审批 gate 与人工介入

### Phase 4: OrgChart 与可视化收敛

目标：让 UI 语义与系统模型一致。

范围：

1. OrgChart 改为纯 `roles/*` 驱动
2. Workflow 页面展示执行层
3. TaskBoard 收敛为 step execution board
4. 增加 timeline、lineage、validation evidence 视图

---

## 20. 第一阶段的最小实现建议

如果目标是尽快落地，我建议第一阶段只做以下最小集合：

1. 新建需求池表与依赖表
2. 新建 Requirement Pool 列表页
3. 新建 Planner API
4. Planner 输出计划、步骤、角色和验收项
5. 系统按依赖生成顺序 steps
6. 复用现有 Task runtime 执行 step
7. 增加独立 Tester step
8. 测试通过则关闭需求；失败则创建 bugfix step
9. OrgChart 改为只显示 `roles/*`
10. 每个 step 必须声明 file scope 与 required inputs
11. 每个 requirement 至少有一组 acceptance checks

这一步完成后，系统就已经从“多任务看板”升级为“需求驱动的多 Agent 协作系统”。

---

## 21. 验收标准

本设计进入实现阶段后，第一阶段至少应满足：

1. 用户可以把新需求放入需求池。
2. 系统可以识别需求依赖，并优先执行被依赖项。
3. Planner 可以先读取需求并输出结构化实现计划。
4. 系统能明确给出推荐角色 / Agent。
5. 系统能按步骤顺序驱动多个 Agent 协作。
6. 至少存在一个独立验证步骤，而不是实现 Agent 自己宣布完成。
7. 测试失败会进入 bugfix step，而不是直接把需求宣告失败。
8. 组织架构页只显示 `roles/*` 中真实存在的 Agent 角色。
9. 下游 step 能明确知道自己依赖哪些 artifacts、哪些文件范围、哪些验证目标。
10. 不同角色 Agent 默认只看到完成当前 step 所需的最小上下文，而不是全量共享上下文。
11. 服务重启或 runtime 恢复后，不会重复创建步骤或丢失验证状态。

---

## 22. 最终判断

这个目标不是概念验证，而是现有 Synapse Ops 的自然下一步。

理由：

1. 当前项目已经具备 Agent 元数据、任务执行、runtime 持久化、日志和前端操作台。
2. 缺失的不是底层执行能力，而是“需求编排与验证闭环”的控制面。
3. 一旦补上 Requirement Pool、Planner、Workflow Orchestrator 和 Verifier，现有系统就可以从单任务执行器演进成真正的多 Agent 协作平台。

因此，本方案建议将下一阶段建设重点定义为：

**从 Task-Centric Ops 升级为 Requirement-Centric Multi-Agent Workflow System。**