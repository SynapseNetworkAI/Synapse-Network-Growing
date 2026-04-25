# Synapse Ops 当前功能清单

本文记录 `Synapse-Network-Growing` 当前正式能力。它描述已经实现并应被维护的系统行为，不记录历史计划、旧 TaskBoard/CrewAI 路线或临时验证证据。

使用规则：

1. 新增、删除或重构正式功能时，同步更新本文件。
2. 新执行真相是 Declarative Workflow Run，不是 legacy task / fixed workflow step。
3. 历史证据、旧设计和旧计划已归档到 `docs/archive/`，不能覆盖本文。

## 1. Planning Control Plane

当前已具备：

1. `/planning` 经营规划控制台。
2. 唯一 active Operating Manifest，通过 `active_slot="global"` 表达当前公司策略。
3. Manifest payload 只支持 focus weights、global budget、constraints 等短 steering 配置；Goal 不再嵌入 payload。
4. `planning_goals` 是一等 Goal 数据面，支持 title、intent Markdown、success metric、workflow/project binding 与 acceptance steps。
5. Mission Control 只投射 200 字 `intent_excerpt`，完整 `intent_markdown` 通过 `GET /api/planning/goals/{id}` 按需读取。
6. Minor revision 保存，用于非断代微调。
7. Manifest History 全量分页与搜索，支持按 cycle label、version name、goal key、status 查询。
8. Planner Sweep 读取 active manifest、compact goal map 与聚合状态，只生成 `RequirementCandidate`。
9. Candidate 支持 approve、reject、materialize。
10. Materialized requirement 继承 `operating_manifest_id`、`goal_key`、`requirement_candidate_id`。
11. Drop Goal safe halt：
   - pending / approved candidates 会 suppressed。
   - 未开始 requirements 会 cancelled。
   - running workflows 进入 `awaiting_operator` 并生成 human gate。
   - release-ready but not delivered 记录会 blocked。
   - delivered / released 记录保持不变。
12. Drop Goal 不触发 rollback、revert、删除、unpublish 或已交付产物变更。

## 2. Requirement Pool

当前已具备：

1. Requirement 列表、搜索、状态筛选。
2. 新建、编辑、提交、修订、取消、逻辑删除。
3. Requirement 必须挂到正式 Project。
4. Requirement 创建后可生成轻量 acceptance / workflow assets。
5. `assets_status = pending | ready | failed` 用于表达资产生成状态。
6. Workflow readiness API 能说明是否已有 active workflow run，以及阻塞原因。
7. Submit / workflow start 后创建 declarative workflow run。
8. Requirement detail 展示 acceptance、workflow readiness、active workflow summary 与跳转入口。
9. Error / bug materialization 可进入 requirement pool，但会经过 intake fingerprint gate 去重和抑制。
10. `bug_intake` 默认 acceptance contract 声明 `expected_outcome=code_delivery`；错误指纹 linkage / `required_db_lineage` 只作为诊断线索，代码变更证据必须由 `project_change_summary`、`git_diff_summary`、guardrails 和 regression command evidence 支撑。
11. Requirement 不再有 pre-execution approval；人工决策统一进入 workflow human gate。

## 3. Declarative Workflow Factory

当前已具备：

1. `/workflows` workflow run 列表。
2. `/workflows/:id` Explainable Step Workbench。
3. Workflow definitions API。
4. Workflow run detail 展示：
   - overview
   - state timeline
   - step explorer
   - step inspector
   - blackboard summary
   - atom invocations
   - artifacts / evidence
   - human gates
   - delivery / PR metadata
   - debug raw payload
5. State Machine Runner 推进 workflow state。
6. Agent atom 只能产出结构化输出；state transition 由 deterministic runner 判断。
7. Blackboard 保存跨状态共享上下文。
8. Atom invocation 和 workflow artifact 保存证据链。
9. Loop 必须有 retry budget，预算耗尽进入 `awaiting_operator` 或失败终态。
10. 首批 workflow 包含 `agent_self_repair` 与 `gateway_reliability_repair`。
11. `agent_self_repair` verify 阶段会执行 Planner-generated acceptance commands，并用硬超时、command artifacts 与 `acceptance_matrix` blackboard 状态暴露运行进度和失败原因。
12. Acceptance matrix evidence 当前按同一 `workflow_run_id` 归属校验；timestamp-level evidence scoping 是 v2，不属于当前实现。
13. Push / PR 质量门禁通过 `.githooks/pre-push` 与 GitHub PR CI 复用 `scripts/ci/pr_checks.sh`，覆盖 repo guardrails、backend pytest、Python diff coverage、dashboard tests/build 与 whitespace。

## 4. Human Gate And Release

当前已具备：

1. Human gate request 创建、展示与决策。
   - Workflow detail 的 `Gates & Delivery` 默认展示 `operator_decision_summary`：发生了什么、根因摘要、推荐动作和去抖决策按钮。
   - Raw state / resolution / fingerprint / Lark payload 只在 Technical details 或 Debug 展开。
2. High-risk action 必须 human gate：
   - production deploy
   - funds / settlement / ledger / vault / USDC transfer
   - contract interaction
   - auth / permission / secret change
   - external paid spend
   - self-modifying deployment
3. Release candidate、release detail、PR delivery、deploy / rollback governance。
4. Workflow passed 后进入 delivery / release 面。
5. PR / release 只信任 workflow evidence、verification verdict 和 human gate decision。
6. Drop Goal 不会自动 rollback；下线已发布功能必须创建 decommission requirement。
7. `release_pr_status_sweep` 会只读同步 GitHub PR 状态：merged PR 更新为 `merged`，closed / missing PR 收敛为 `pr_closed / abandoned`，但不会自动 deploy 或 rollback。
8. `/releases` 的 `发布管理` 分面使用独立 Release Task 记录手动和需求流转发布意图；Release Task 不等于 Deployment Record。任务创建不会自动部署，分支选择从目标 GitHub 仓库 branch list 读取；没有 open/merged PR 时只能提交 PR，PR checks 通过后才允许 Operator 点击 `发布到 staging` 触发白名单发布 runner，production 仍必须 Human Gate。
9. Release Task detail drawer 展示 PR gate、DeploymentRecord、GitHub Actions run link、health check、failure summary 和 deployment metadata；staging runner 使用 GCP Workload Identity Federation，不使用长生命周期 GCP service account JSON key。
10. `/releases` 的 `上线记录` 分面只读展示成功的 `DeploymentRecord(status=succeeded)`，不混入 pending / failed / cancelled Release Task。手动标记 Release Task 已完成时，后端会创建或绑定一条 `manual_completion` 成功 DeploymentRecord 后再进入上线记录。上线记录用于确认 GitHub Actions、Cloud Run revision / image / manifest、health check 和 rollback target。
11. 没有 webhook callback 的本地发起 staging 部署，可通过 `/releases` 的 `同步状态` 拉取 GitHub Actions run 结果，并把 success / failure 同步回 DeploymentRecord 与 Release Task；该同步只读吸收外部事实，不触发 deploy / merge / rollback。
12. Staging 发布不要求先合并 `main`，但必须存在 PR 且 PR checks 通过，并由 Operator 点击 `发布到 staging`。Production 默认只允许从 `main` / tag / verified staging manifest 推进，并必须 Human Gate。
13. Rollback 不由 Drop Goal、普通 Release Task PATCH 或 staging 快捷按钮触发。Runtime rollback 以历史成功上线记录的 commit / image / manifest 为 target 并进入 Human Gate；代码级 revert 必须走新分支、PR、checks、merge 和正常发布链路。

## 5. Error Discovery And Intake Gate

当前已具备：

1. `/api/errors/intake`。
2. `/api/bugs/intake/log-center`。
3. `bug_log_sweep`。
4. Error fingerprint 与 bug record 聚合 occurrence、evidence 和 discovery status。
5. Requirement Intake Fingerprint Gate：
   - 同 fingerprint 已有 active requirement / workflow 时复用，不重复建单。
   - 未 release / observing resolved 前重复错误会 suppressed 或 cooldown。
   - resolved 后再次出现会创建 `Regression:` requirement。
6. Scheduler lock 防止 bug sweep 并发重复执行。
7. 需求去重与 Lark 通知抑制分表，不混用语义。

## 6. Recurring Jobs And Notifications

当前已具备：

1. `/schedules` 定时任务管理面。
2. Recurring workflow registry。
3. Run Now / Dry Run。
4. Run history。
5. Bug Log Sweep Scheduler 状态快照。
6. Release PR Status Sweep，用于吸收 GitHub PR merged / closed / missing 外部事实。
7. Notification Dispatcher 后台 loop。
8. Notification queue / fingerprint / delivery 记录。
9. Lark channel routing：
   - alert
   - approval
   - workflow notification
   - release
10. Cooldown、suppression、rollup、retry、dead letter。
11. Dispatcher queue health 展示 queued、dead letter、open fingerprints、suppressed count。

## 7. Project And Policy

当前已具备：

1. Project 列表与详情。
2. 新建、编辑、逻辑删除项目。
3. Project 配置：
   - `project_key`
   - `display_name`
   - `root_path`
   - `repo_full_name`
   - default branch
   - deploy repo / strategy
   - environment labels
4. Project 绑定 policy。
5. Requirement、workflow、release 按 Project 解析目标仓库与交付策略。

## 8. Runtime And Planner Adapter

当前已具备：

1. `PLANNER_BACKEND` 独立选择 planner adapter。
2. 支持 `openai | claude | copilot | codex_cli | codex_sdk`。
3. Codex CLI / SDK planner adapter 支持项目级 planner session 复用。
4. 普通 LLM adapter 不写 Codex session registry。
5. Codex CLI / SDK 与 OpenAI Responses 保留为 planner/runtime provider 能力，通过 adapter 或 declarative atom 使用。
6. 旧 `/api/tasks`、`/api/approvals`、fixed-step orchestrator 包和 legacy task runner 已退役；新增功能不得重新引入旧 TaskBoard / workflow step 主链。

## 9. Documentation And Evidence

当前已具备：

1. `ARCHITECTURE.md` 作为 coding agent 短宪法。
2. `AGENTS.md` 作为 repo agent protocol。
3. `.github/instructions/architecture-constraints.instructions.md` 作为 GitHub instruction-aware 工具入口。
4. `docs/design-docs/` 保存当前 canonical design。
5. `docs/archive/` 保存历史证据、旧计划、旧设计和测试截图。
6. Browser automation / dogfood 技能保留，用于页面验收与缺陷取证。

## 10. Ops Console Frontend

当前已具备：

1. `/command-center` 作为 Human-Agent Control Plane 首页。
2. 深色 cockpit AppShell 和分组导航：
   - Strategy
   - Intervention
   - Execution
   - Factory
   - System Ops
3. `/gates` 集中展示 pending human gates、failed / blocked workflow。
4. `/factory/workflows` 只读展示 workflow definitions、states、transitions、limits、risk policy。
5. `/factory/atoms` 从 workflow definitions 反推 agent / deterministic / terminal atom registry。
6. `/intake` 作为需求发现入口，连接 errors、planner、forum feedback 和 watcher events。
7. `/knowledge` 作为 artifacts / SOP Ledger 的一等入口。
8. `/system/notifications` 展示 notification dispatcher、queue、dead letter、open fingerprint 概览。
9. Figma / Stitch 原型视觉方向已记录在 `frontend-control-plane-figma-implementation.md`。
10. Factory pages v1 只读，不开放在线 YAML 编辑。
