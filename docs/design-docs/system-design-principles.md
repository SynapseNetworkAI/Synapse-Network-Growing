# Synapse Company Ops 系统设计原则

这份文档定义 `Synapse-Network-Growing` 当前的硬约束。

后续新增功能、流程、API、页面和自动化策略，默认都必须遵守这些原则。例外只能通过专门设计文档说明原因、风险和补偿机制。

## 1. 把模型当不稳定部件，不当同事

1. 不允许假设模型会持续正确、持续稳定、持续理解上下文。
2. 可靠性必须来自状态机、权限、验证、恢复、日志和预算。
3. 自动化必须以“失败也能收口”为前提。

## 2. 错误路径按主路径设计

1. 恢复不是补丁，而是主路径的一部分。
2. 每条核心执行链都必须定义失败分支、恢复分支、熔断条件和 operator 接管点。
3. 禁止无限重试、无限 self-repair、无限 resume。

## 3. Verification 必须独立于 Execute

1. execute 不能自证正确。
2. validate 必须独立于 execute，并默认由独立 verification agent 执行。
3. “代码存在”不等于“问题解决”；完成定义必须包含验证证据。
4. deliver 只能发生在 validate 成功之后。

## 4. 默认 workflow 必须最小化

1. 当前正式核心流只有：
   `intake -> execute -> validate -> deliver`
2. simple task 不得被治理框架强制扩成多步流程。
3. 复杂任务才允许展开 execution graph。
4. `research / plan / review / test / closeout` 不再是默认一等 workflow step。

## 5. Agent 主导执行，程序只做治理

1. agent 决定执行内容、研究顺序、实现路径和按需展开的复杂度。
2. 程序不替 agent 生成仪式性计划，不替 agent 规定固定执行阶段数。
3. 程序当前只拥有 5 类职责：
   - 需求治理
   - 运行时治理
   - 稳定性治理
   - 自动化编排
   - 发布治理
4. 任何新能力如果让程序重新变成“执行内容裁判”而不是“治理与守门者”，都应视为架构倒退。
5. requirement submit 是 requirement 进入 execution 的唯一正式桥接点；程序应在 submit 时完成审批判定、确保 acceptance / execution plan 可用、自动创建 execution、并在放行后自动启动。
6. 高信号错误必须自动回流到 requirement 主链，错误发现、审批、自动执行、verification、PR、release 必须保持在同一条治理链上。

## 6. Planner 是执行形状选择器，不是阶段生成器

1. planner 只负责 shape decision：
   - execution mode
   - complexity
   - validation profile
   - delivery intent
   - approval requirement
2. planner 不得强制生成固定 research/plan/closeout 仪式。
3. harness 不负责替 agent 决定执行顺序。

## 6.5 声明式复杂 Workflow 必须由确定性 Runner 治理

1. 复杂 workflow 可以由 Meta-Builder Agent 生成声明式 State Machine YAML，但只能组合受控 atom。
2. workflow 不得退回到隐藏在 Python `if-else` 中的多阶段过程式编排。
3. Agent Atom 负责推理、生成、诊断、修复建议和内容创作，但不允许直接改变 workflow state。
4. State transition 必须由 deterministic runner 基于 schema、evidence、policy、budget 和 guard 判断。
5. 所有 loop 必须有 retry budget、terminal state 和 operator fallback。
6. Agent Atom 输出必须 schema 化；解析失败最多自修一次，原始输出必须落 artifact。
7. 下游 deterministic atom 只能读取 parsed payload，不能把非结构化模型输出当作可信输入。
8. 高风险 atom 必须进入 human gate；资金、结算、合约、auth、生产部署和外部付费动作不得自动放行。
9. Blackboard 只保存 workflow 继续运行需要的最终 KV；禁止把 `state_outputs`、`transition_history`、raw artifact map 或长日志写回 `blackboard_json`。

## 6.6 No Legacy Workflow Compatibility

1. 新复杂执行链的唯一真相是 declarative workflow run：`workflow_definitions`、`workflow_runs`、`workflow_state_events`、`workflow_artifacts`、`blackboard_snapshots`、`atom_invocations`、`human_gate_requests`。
2. 历史 fixed-step orchestrator、旧 agent-first bugfix loop、旧 delivery repair loop、旧 task runner 已从主代码路径删除，不得作为新链路 fallback。
3. 新业务只能读取 declarative state machine 的 `workflow_key/current_state/status/resolution/blackboard` 与 state events / atom invocations / human gates，不得恢复旧 fixed-step execution 表达。
4. `workflow_artifacts.workflow_run_id` 必须直接外键到 declarative run，不得把历史 execution id 塞进 artifact payload 伪关联。
5. Requirement submit 后只应创建 declarative workflow run；planner 只选择 `workflow_key` 与初始化 blackboard，不再生成固定 `research/plan/implementation/validate/closeout` steps。
6. Agent 只能写 structured output 与 artifact；state transition、retry budget、terminal state、human gate 由 deterministic runner 决定。
7. Workflow detail 默认必须展示 chronological timeline；Raw Blackboard / Raw Artifacts 只能通过 Debug details 或 Debug Dump 查看。
8. 不得为了掩盖数据不一致而在 Summary API 或前端条件分支里写脏补丁；必须修复状态机未流转的根本原因。
9. Human Gate decision 是状态机输入，不是普通表单状态；decision 写入后 Runner 必须被唤醒并收敛到下一状态、新 gate 或明确 failed terminal。
10. Human Override 只降低人类手动需求的验收录入摩擦；technical terminal 不等于 business done。缺少结构化验收矩阵的 override workflow 必须在 Evidence 页面显示 Manual Review Panel，并由 operator 显式确认业务结果后才算 truthfully completed。
11. 当前主链视觉流以 `ARCHITECTURE.md#system-architecture-flow` 为准；不要在多个文档复制架构图导致漂移。

## 6.6.1 Fail-Closed Acceptance

1. Planner/Candidate 转正为 Requirement 前必须有合法 `execution_acceptance_steps`，不得由代码生成默认空壳验收。
2. 每个验收步骤必须声明 `required_commands` 或固定枚举内的 `required_evidence_types`；`required_db_lineage` 在 v1 只作为说明信息，不能作为通过条件。
3. 验收标准必须验证业务目标是否达成，不得只验证 Candidate、Requirement 或 WorkflowRun 是否被创建。
4. Agent 生成的 acceptance 缺失、空泛、解析失败或格式不合法时，必须进入 `validation_failed` / `awaiting_operator`，不得自动补 fallback criteria。
5. Planner Agent 输出 JSON 只允许对格式/schema 错误做最多两次 repair；危险命令、未知 workflow、越权风险不得 repair 成放行。
6. Planner Agent 生成的 `required_commands` 必须通过安全命令 allowlist / denylist；生产、资金、部署、删除、外部网络、权限或破坏性命令必须 Fail Closed。
   本地 dashboard E2E 只能通过受控项目脚本放行，例如 `cd dashboard && npm run test:e2e` 或 `npm --prefix dashboard run test:e2e`；不得放开任意 `playwright`、`npx`、外部网络或 shell 执行。
   Planner-generated pytest acceptance commands 必须指向明确测试文件或 selector；`pytest tests -q`、`pytest -q`、`python -m pytest -q` 这类 live workflow 内全量递归命令不得作为 acceptance command，完整回归应走 Final Regression CI runner。Git evidence 只允许读操作，例如 `git diff --check` 和 `git diff --stat`，不得放开 `git push/reset/checkout`。
7. Planner Agent 只能从已注册 workflow definitions 的 enum 中选择 `workflow_key`，不得自由发明 workflow。
8. Verification Agent 的 `inconclusive` 不能被 fallback 提升为 `passed`；不确定就是不放行。
9. Planner Candidate 必须前置声明 `expected_outcome=code_delivery|verification_only`；执行阶段不得为了绕过 no-diff 失败而自行改写。
10. `code_delivery` 没有 repository diff 必须 Fail Closed；`verification_only` 只有在证据矩阵完整时才允许 no-op success。
11. Supersede retry 必须携带一次性 `context_hint` 给 Planner，解释前次 no-change/bootstrap dead end，防止 Planner 失忆后无限重复同一个 code-delivery 任务。
12. Acceptance Matrix Is Executable Contract：Planner 生成的 `execution_acceptance_steps.required_commands` 必须在 workflow verify 阶段执行，`verification.status=passed` 必须依赖 `acceptance_matrix.status=passed`。
13. `required_evidence_types` 是封闭词汇表：`workflow_command_result`、`project_change_summary`、`git_diff_summary`、`frontend_validation_result`、`coverage_report`、`docs_sync_review`、`workflow_agent_raw_output`；未知类型必须在 Candidate validation 阶段 Fail Closed。Planner 不得声明无法由本 step 命令或系统产物支持的 evidence，例如 `coverage_report` 必须绑定 `diff-cover`、`coverage.xml` 或 `pytest --cov` 命令，`frontend_validation_result` 必须绑定 dashboard/npm 验证命令，`project_change_summary` 必须绑定 `code_delivery` 或 git diff evidence，不能只靠 `required_db_lineage`。
14. Evidence v1 至少必须属于同一个 `workflow_run_id`；不得跨 workflow run 复用旧 artifact 来满足新的 acceptance matrix。v2 可升级为校验 artifact 时间戳晚于当前 verify phase。
15. Planner 生成的 acceptance commands 必须使用确定性硬超时执行；`current_command_started_at`、heartbeat 或日志活跃度只能用于诊断展示，不能替代 exit code / artifact evidence。
16. acceptance matrix 失败必须写入 `failure_summary`，并作为下一轮 patch context；Agent 不得在不知道 timeout、non-zero exit、missing evidence 或未知 evidence type 的情况下盲目重试。
17. 默认 smoke tests 不能替代 Planner contract：`scripts/ci/agent_guardrails.sh`、`py_compile` 和 full pytest 只是系统底线，Requirement-specific acceptance steps 未通过时整体仍然 failed。

## 6.6.2 Push / PR Quality Gates

1. 本地 `pre-push` 和 GitHub PR CI 必须复用同一个 `scripts/ci/pr_checks.sh`，不得维护两套不同门禁。
2. Push / PR 门禁必须至少覆盖：repo guardrails、backend full pytest、Python diff coverage、dashboard Vitest、dashboard build、`git diff --check`。
3. Python runtime 必须通过脚本动态探测；不得把单台机器的虚拟环境路径写死成唯一可用路径。
4. diff coverage 必须基于可解析的 merge-base；本地 `origin/main` 过旧时应先尝试 fetch，不能用陈旧 diff 误判覆盖率。
5. `--no-verify` 只能绕过本地 hook，不能被视为合格交付；远端 GitHub CI 仍是最终兜底。

## 6.7 后台任务必须一等可观测

1. 任何会定期运行、后台轮询、延迟重试或自动推进系统状态的机制，都必须在 Ops Console 中可见。
2. 后台任务不能只存在于 thread、daemon、log、cron 或隐式请求副作用中。
3. 每次后台运行必须记录 run history，包括 triggered_by、dry_run、params、result、error、started_at、completed_at 和 duration。
4. 高风险 recurring workflow 默认不得 auto-start requirement、delivery、deploy、funds、auth、contract 或外部付费动作。
5. `Dry Run` 是验证 recurring workflow 配置的默认方式；`Run Now` 必须有明确确认与可追踪结果。
6. Notification Dispatcher 这类可靠性后台 loop 必须暴露 queue、dead letter、suppression、last tick 和 last error。
7. `/schedules` 必须按业务领域和 operator 决策优先级展示 recurring workflows，不得退回只有 workflow key、owner、schedule、last/next timestamp 的 crontab 表格。
8. 定时任务卡片必须展示 `Input -> Action -> Output`，让 operator 知道它监听什么、执行什么、产出什么。
9. 失败、due、锁冲突或最近运行异常的任务必须置顶到 `Attention Required`，不能被常规业务分组或页面滚动淹没。
10. 新 recurring workflow 缺少 presentation metadata 时必须进入 `New / Uncategorized Initiates` 兜底分组，并显示 `Missing Presentation Metadata`，但不得阻断查看历史或手动运行。
11. `Run Now` 后必须有局部运行锁定和状态反馈；完成后应刷新 run history 并提供本次运行的 inspector。
12. Last Run 必须可下钻为人话战报；raw params/result JSON 只能放在 Debug details。
13. `Dry Run` / `Run Now` 点击后 Run Inspector 必须立即打开并显示 optimistic running entry；异步完成后如果 operator 已关闭抽屉，不得重新抢焦点。
14. Recurring workflow 历史默认只展示最近 50 条；刷新时必须处理选中 run 掉出窗口的情况，不能白屏或崩溃。
15. `dry_run=true` 的历史记录必须视觉降级并标记为 `DRY RUN`，不得和真实执行记录使用同等完成语义。
16. 高频运维主视图必须是 compact monitoring surface：静态 description 和完整 I-P-O 必须折叠，不能把三个大按钮和三块大黑框铺满每张任务卡。
17. 逾期定时任务必须显示 `OVERDUE`、欠账时间和可推断原因；超过 24 小时的 due 必须用危险态。
18. 出现在 `Attention Required` 的任务不得在原业务泳道重复完整展示；原泳道最多保留极简归属 ghost row。
19. 定时任务 Configuration v1 只能做只读配置检查和安全运行控制；不得开放任意 execution logic、shell、prompt、cron 编辑或高风险自动化开关。
20. `Dry Run` 是调试动作，默认归入 inspector / configuration surface，不应压过监控主视图。
21. 耗时 final regression 不得阻塞 workflow worker；必须 fire-and-suspend 到 `awaiting_ci`，由可观测 recurring sweep 收口。
22. CI runner 必须流式写日志并原子写 exit marker；不得用内存缓冲完整 stdout/stderr。
23. CI status sweep 必须有单次运行时长上限，且 stale-lock recovery 阈值必须显著大于该上限。
24. CI status sweep 的后台自动 tick 必须显式开启；local/dev 默认不自动消费历史 `awaiting_ci` 记录，避免无意发射 full regression。
25. `release_pr_status_sweep` 只能只读同步 GitHub PR 外部状态；`MERGED` 可更新本地 release 为 merged，`CLOSED` 或 `404 / Not Found` 必须收敛为 abandoned/review 状态，不能永久保留 `pr_opened` 僵尸记录。

## 6.8 Planning Lifecycle 必须数据穿透且 Drop Goal 不自动回滚

1. 系统只能有一个 active Operating Manifest，用 `active_slot="global"` 表达当前公司策略。
2. Operating Manifest 是控制面，只承载预算、权重、全局约束和短 steering 字段；不得重新把 `payload.goals` 或长 Markdown 塞回 Manifest JSON。
3. Goal 是 `planning_goals` 一等业务实体，`intent_markdown` 是目标长文本真源。
4. `GET /api/planning/mission-control` 只能返回 goal map 与 200 字 `intent_excerpt`，不得返回全文 `intent_markdown`；全文只能通过 `GET /api/planning/goals/{id}` 按需读取。
5. `goal_key` 必须稳定，并穿透 `requirement_candidates`、`requirements`、`workflow_runs` 和 `release_records`。
6. Planner Sweep 是无状态评估器，只能基于 active manifest、compact goal map 与聚合进度生成候选需求，不得扮演长生命周期 PM。
7. Planner Sweep 为单个 goal 生成 candidate 时，只能注入该 goal 的 full Markdown context，不得把所有 goals 的 PRD 一次性塞进 prompt/snapshot。
8. Planner Sweep 不得为 `dropped` goal 生成新 candidate。
9. Candidate 是自动规划与正式 requirement pool 之间的缓冲区；未经过 operator approval 的 candidate 不得直接污染需求池。
10. Drop Goal 的语义是停止未来投入并安全阻断未交付链路，不是撤销已经发布的物理世界状态。
11. Drop Goal 必须 suppress pending candidates、cancel 未开始 requirements、pause / human-gate running workflows、block 未发布 release-ready artifacts。
12. Drop Goal 绝不能自动 rollback、revert commit、删除数据库变更、撤回外部发布或修改 delivered release。
13. 已上线功能如需下线，必须创建新的 decommission requirement，并按正常 workflow、verification、human gate、release 流程执行。
14. Rollback 只能由 observing failed、deployment failed、kill switch 或 operator manual rollback 触发，并必须记录在 release / deployment 面。
15. Operating Manifest 只表达商业目标、预算、权重和全局约束，不承载自动执行策略。
16. Candidate 是否可自动 materialize / start 必须由 deterministic risk router 根据 workflow allowlist、risk level、project policy 和 atom risk profile 决定。

## 6.9 Ops Console 必须按决策路径设计，不按数据库对象平铺

1. Operator 页面必须优先展示“状态、原因、下一步动作”，而不是把 JSON、表、日志和对象列表平铺在同一个主视图。
2. Planning Console 必须体现 `goal_key` 数据穿透：goal、candidate、requirement、workflow、release 的信息要在 goal lane 中汇聚。
3. Candidate 不得在 Planning 主视图中作为孤立全局队列展示；审批动作必须发生在所属 goal 上下文里。
4. Raw payload、raw JSON、raw artifact 只能通过 Debug tab、drawer 或 details 展开，不得成为默认主操作面板。
5. Raw Manifest JSON 不得作为 Goal PRD/Markdown 主入口；目标长文必须通过 Goal Markdown editor 编辑。
6. History、archive、debug 信息必须和当前操作面分离，避免遮挡 operator 当下要做的判断。
7. Planning 主视图必须按 operator decision priority 排序：需要处理的 candidate 优先，其次已 materialized 的工作，再次是 Fail-Closed 拦截记录，最后才是 rejected / suppressed 历史。
8. 长 PRD、Candidate Markdown、Planner raw output 和 metadata dump 不得压过当前动作；主视图只展示摘要、状态、原因和跳转入口。
9. `validation_failed` 是规划层诊断草稿，不是执行阻塞。它应默认折叠，展开后先显示 Fail-Closed 原因，再允许查看 Agent 原始输出。
10. Planning 主视图必须按 `Active / Achieved / Dropped` 组织目标：Active 目标永远优先展开，Achieved / Dropped 历史目标默认折叠。
11. 历史目标数量变大时必须使用 local filtering 和 virtualized history，避免把几百个历史 Goal 同时渲染进 DOM 或要求 operator 传统分页翻找。
12. 重复的 Planner Fail-Closed 错误必须聚合为 deduped planner intercepts，按 reason signature 显示次数和最新时间，不能把重复废稿当作同等重要的主线工作。
13. Ops Console 时间显示必须使用浏览器 local time，并保留 UTC 原始值用于排查日志；不得硬编码特定地理时区作为唯一显示口径。
14. Workflow Human Gate 默认视图必须是高管决策看板：展示发生了什么、根因摘要、推荐动作和决策按钮；`state`、`resolution`、fingerprint、Lark payload、blackboard JSON 只能出现在 Technical details 或 Debug。
15. Human Gate 决策按钮必须有本地防抖和 loading/disabled 状态；`approve` 在失败场景中必须使用中性语义，例如 `确认并放行`，不得被渲染成“全绿通过”。
16. Human Gate 决策可能异步唤醒 Runner；没有 WebSocket 时，前端必须在决策后短轮询 workflow detail，确认是否推进、完成或重新阻断，不能只凭 POST 成功显示“已解决”。
17. Workflow Delivery Summary 必须先验证 `delivery_status` / `release_status` 是可信交付状态，再渲染 PR、branch 或 compare 字段；孤立的历史 branch / PR URL 不得让主视图展示脏交付。

## 6.10 Ops Console 页面必须可测试、可截图、可追溯

1. 每个主页面必须有文档说明页面职责、输入、输出、下一步动作和证据位置。
2. 页面测试不得只断言 render 成功；必须覆盖主按钮、Tab、Drawer、详情跳转或空状态解释。
3. 产品级 E2E 必须保留 dogfood 证据，包括截图、复现步骤、浏览器 console/network 结果和 DB lineage summary。
4. 证明新架构可跑通时，必须沿 `Operating Manifest -> RequirementCandidate -> Requirement -> WorkflowRun -> Evidence` 验证数据穿透。
5. 测试和 dogfood 默认禁止真实 Lark、生产发布、资金、auth、合约和外部付费副作用。

## 7. Requirement / Execution / Release 必须分面治理

### 6.1 Requirement

Requirement 只负责：

1. 为什么做
2. 要达到什么结果
3. 在什么约束下做

Requirement 不得直接承载：

1. 运行时 telemetry 明细
2. deploy / rollback 控制
3. 环境状态面板

### 6.2 Execution

Execution 负责：

1. agent 工作过程
2. execution graph 或 direct execute
3. validate 结果
4. incidents / pause / resume / retry

### 6.3 Release

Release 负责：

1. branch / commit / PR
2. delivery readiness
3. deployment promotion
4. rollback

凡是环境视角或发布视角能力，默认进入 release surface，不得回灌到 requirement 页面。

### 6.4 Errors（辅助治理页）

`/errors` 是稳定性治理辅助面，不是第四个主业务面。

它只负责：

1. 高信号错误事件与 fingerprint 聚合
2. linked requirement / execution / release 的追踪
3. 告警发送历史

它不得承担：

1. requirement 意图编辑
2. execution 主控制入口
3. release 主决策入口

## 7.5 Project 是正式主对象

1. Requirement 必须挂到正式 `Project`，不再把 `target_project_path` 当作用户侧主输入。
2. `Project` 是 GitHub、默认分支、部署策略、环境标签和仓库根路径的主入口。
3. `project policy` 是挂在 `Project` 上的治理子配置，不再代表项目本身。
4. Requirement 创建默认先选项目，只在高级场景允许填写 `target_project_path_override`。
5. Release / Deployment 必须以 Project 为边界执行，不得再从 requirement 零散字段拼接仓库与环境配置。

## 8. Execution 必须只有一条当前主链

1. 同一 requirement 任何时刻只允许一条当前 execution 主链。
2. `queued / running / paused / validating` 是唯一活跃 execution 状态。
3. 已完成、已失败、已验证的 run 不能再次 `start`。
4. `retry` 必须创建新的 execution run，不得复活旧 run。
5. requirement、execution、release 三面的读模型必须指向同一条当前 execution 主链。
6. 旧 execution / release 脏数据不做兼容；需要时直接重置运行态数据。

## 9. Artifact 必须面向消费方

当前默认只保留最小证据集：

1. `requirement_brief`
2. `execution_record`
3. `validation_record`
4. `delivery_record`

规则：

1. 没有消费方的 artifact 不生成。
2. artifact 必须明确服务于 Requirement、Execution、Release 其中一面。
3. 禁止制造“为了阶段完整性而存在”的仪式性 artifact。
4. 普通 state transition 只写 `workflow_state_events`，不得额外创建 transition artifact。

## 10. Release Candidate 只接受 Validate 成功的 Requirement

1. release candidate 不得来自未验证 requirement。
2. publish、deploy、rollback 必须在 release surface 处理。
3. requirement 面只能展示 release 摘要与跳转入口。
4. requirement execution approval 只负责执行许可，不替代 release / deployment gate。
5. 高风险 requirement 的人工 execution approval 必须保留；它控制的是“是否允许 agent 开始高风险动作”，不能被 PR merge 替代。
6. Agent 可以自动创建或更新 Draft PR，但不得自动 merge；人类保留最终 Review/Merge 边界。
7. Delivery atom 在 push PR 分支前必须 smart-sync 远端分支：保留人类提交，能 clean rebase 则更新同一个 PR，发生 rebase conflict 则进入 `awaiting_operator`，不得静默覆盖。
8. PR body 默认必须 reviewer-first：顶部只放业务摘要、安全 review 理由和人工 merge checklist，长 evidence / logs / retry history 必须折叠或链接 artifact。
9. execution approval 放行后，系统必须先在目标项目上基于最新 `main` 准备 requirement branch，再启动 execution；不得把 branch / PR 完全拖到流程末端。
10. GitHub PR merge 是外部事实吸收，不是部署动作；已合并 PR 只允许更新 Release 面状态，不得自动触发 deploy、rollback、删分支或生产变更。
11. Release Task 是业务发布意图与人工闭环记录；Deployment Record 是物理部署流水。`/releases` 可以统一展示手动与需求流转发布任务，但不得通过临时合并 `deployment_records` 来伪造发布任务列表。
12. Release Task 创建动作不得自动 deploy。Release Task 的分支必须从目标 GitHub 仓库分支列表选择，不能依赖手写自由文本。Staging 允许两类显式 operator 动作：`main` 分支可直接点击 `发布到 staging`，因为它已经是主干事实；非 `main` 分支必须存在 open 或 merged PR 且 PR checks 通过后才能点击 `发布到 staging`。所有 staging deploy 都必须通过白名单发布 runner、写入 `deployment_record_id` 留痕，并使用 GCP Workload Identity Federation；不允许 GitHub 保存 GCP JSON key。production deploy / rollback 必须走 Human Gate，不能复用 staging API 或普通 PATCH 绕过。
13. Release Task 详情必须提供部署排障入口：PR gate、DeploymentRecord、GitHub Actions run URL、health check、failure summary 和 metadata 可下钻查看；主列表只显示状态摘要和下一步动作，不平铺长日志或 raw payload。
14. Online Record 是成功上线账本，只能来自 `DeploymentRecord(status=succeeded)`，不得直接从 Release Task、失败 DeploymentRecord 或普通备注投影。Operator 手动把 Release Task 标记为已完成时，后端必须先创建或绑定一条 `manual_completion` 成功 DeploymentRecord，再进入上线记录。上线记录需要保留 GitHub Actions、commit、branch、service、environment、health、revision / image / manifest metadata 和 release task anchor。
15. 本地发起或没有 webhook callback 的 staging 部署必须支持 pull-based reconciliation：Ops Console 可只读拉取 GitHub Actions run 状态，把 success / failure 同步回 DeploymentRecord 和 Release Task。同步动作不得触发 deploy、merge、rollback 或生产发布。
16. Staging 与 production 发布条件必须不同：staging 可以从 `main` 直接手动发布，也可以从 PR checks 通过的 release branch 手动发布；production 默认必须基于 `main` / tag / verified staging manifest，并经 Human Gate。已合并 PR 不自动 deploy，成功 staging 也不自动 promote production。
17. Rollback 必须使用 Release / Deployment 面的结构化证据。Runtime rollback 选择历史成功 Online Record 的 commit / image / manifest 作为 target，并进入 Human Gate；Code revert 使用新 revert branch -> PR -> checks -> merge -> normal release。Drop Goal、普通 PATCH、staging deploy API 不得触发 rollback。
17. acceptance contract 只负责定义完成标准、范围约束和期望证据；最终 verification plan 必须在 execution 完成后由 verification agent 基于真实执行证据生成，harness 不得提前写死完整测试方案。
18. verification agent 负责决定怎么验，Harness 负责权威执行 required commands 并记录 cwd、exit code、日志路径、耗时和 stdout/stderr excerpt；execution agent 自述测试结果不能单独作为最终 gate。
19. 错误发现 v1 必须优先于机会发现。
   - 本阶段只自动化 defect self-healing，不自动化新增功能发现。
   - 错误信号必须先进入统一 discovery pipeline，再决定是否 materialize requirement。
17. discovery / approval 都采用 `agent recommendation + system rules + human fallback`。
   - agent 负责理解与推荐。
   - system rules 只负责稳定硬边界。
   - 人只处理高风险、低置信度或系统无法稳定收口的 case。
18. 新状态机不再允许一个对象同时存在多个真假难辨的主状态字段。
   - `Requirement`、`ExecutionAttempt`、`Delivery`、`ApprovalDecision` 都必须只有一个 canonical `state`
   - 旧 `status / phase / resolution_path / latest_release_status` 只允许作为过渡读字段，不能继续作为写入真相
19. Declarative workflow 的目标与黑板必须可审计。
   - 原始 intent / acceptance brief 不允许被 repair 覆盖。
   - repair turn 必须从最新 verification result、command evidence 和 blackboard 派生。
   - 第二次 repair 必须读取上一次失败结果，而不是简单重跑旧 prompt。
20. 自主修复必须有严格预算。
   - 所有 workflow loop 必须有 counter guard。
   - verification failure 默认由同一个 workflow run 自循环修复，自动 self-repair 最多 2 次。
   - self-repair 达到预算仍失败时必须 `route_to_human`；人工继续 retry 也复用同一个 run / session，并单独计入 manual retry。

## 11. 服务层必须按功能面治理

1. `server/services` 不允许继续回到平铺式万能目录。
2. requirement、release、runtime、review、project policy、signal、bug intake 必须分面拆分。
3. 新服务文件 `> 500 行` 进入预警，`> 900 行` 必须拆分。
4. 每个服务分包都必须有 `README.md`，说明职责、入口、依赖边界和禁止依赖。
5. router 只能依赖 facade 或稳定公开入口，不得直接抓私有 helper。

## 12. 防膨胀工程约束

### 12.1 单一职责

1. 一个模块只能服务一个业务面。
2. requirement、release、runtime、review、signal、project policy 不得混写进同一个主文件。

### 12.2 接口隔离

1. 每个分包必须有最小公开入口。
2. `routers/` 只能依赖 facade，不得跨目录点对点抓内部函数。

### 12.3 迪米特法则

1. 禁止跨两层以上目录直接取内部实现。
2. 出现这种需要时，应补 facade 或提取公共 helper。

### 12.4 合成复用优先

1. 新能力优先通过 helper / service / policy 组合实现。
2. 默认不通过复杂继承树做扩展。

### 12.5 依赖倒转

1. 上层编排只依赖稳定 facade 和 schema。
2. 不得依赖底层实现拆分文件。

## 13. 前端必须是 Enterprise Workbench，而不是平铺卡片后台

1. 默认禁止整页卡片化；卡片只能用于独立对象，而不是整页每个区块的万能容器。
2. 页面必须先有工作台骨架，再有组件。标准骨架包括：
   - shell
   - page header
   - primary workspace
   - secondary inspector
   - activity/feed rail
   - command bar / filters
3. 一个页面只能有一个主焦点，不得把表单、列表、摘要、状态、日志做成同权重平铺块。
4. Requirement、Execution、Release 三面必须使用各自独立的页面模板，不得继续复用万能卡片页模板。
5. 颜色只承担状态和强调，不承担大面积装饰；工作台不是营销页。
6. 新 UI 必须优先复用统一的 workbench shell、section、inspector、activity feed 和 state badge 结构。
7. 列表页默认不承载常驻 create/edit 大表单；新增与编辑应优先采用 `Toolbar + Drawer` 模式。
8. Requirement create 只采集最小 intent；acceptance 默认由 agent 在创建后生成，并允许在详情页修订。
9. 禁止继续使用浏览器原生 `alert / confirm`；危险操作必须使用统一确认弹窗，成功/失败反馈优先使用统一 toast。

## 14. 前端防回潮约束

1. UI 变更 PR 必须说明页面属于 Requirement、Execution、Release 哪一面。
2. UI 变更 PR 必须说明是否复用了 workbench 模板与 token。
3. 如果继续引入 dashboard-card mosaic、同权重白卡拼盘、装饰性 chips/pills，应直接视为 review 拒绝项。
4. 前端 token 必须同时支持 surface hierarchy、text hierarchy、stroke hierarchy、state colors 和 layout tokens。
5. 如果在列表页重新引入长驻内联 create/edit 表单，而没有明确的 quick-edit 例外说明，应直接视为 review 拒绝项。

## 15. 上下文是预算，不是垃圾桶

1. 长期规则、项目 policy、会话上下文和临时证据必须分层治理。
2. 需要为 context budget、compaction 和 stale-memory verification 预留机制。
3. 不允许把未经验证的旧记忆直接继续传播为当前事实。

## 16. Runtime / Subagent 必须有生命周期

1. 所有 runtime 都必须可 start、running、pause、fail、cleanup、abort。
2. transcript、session、artifact、log 和 ownership 必须可追踪。
3. 父执行结束时，子资源必须可收口、可复盘。
4. 当 workflow runtime 失真时，使用 `/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_execution_runtime.py --yes` 直接重置 declarative runtime，不保留旧脏数据兼容逻辑。
5. 当需要丢弃本地 requirement / workflow 状态重新开始时，使用 `/Users/cliff/workspace/agent/.venv/bin/python /Users/cliff/workspace/agent/Synapse-Network-Growing/scripts/reset_workflow_state.py --yes`。
6. verification/manual review 不再是正式主链的一部分；execution 完成后应自动派发 verification agent，并以其 verdict 作为 release 前唯一正式验证信号。
6. verification passed 后应默认自动推进 commit / push / open PR；PR merge 视为最终人工把关。

## 17. 所有关键自动化都必须可观测

1. requirement、execution、release、incident、publish、rollback 都必须留下结构化证据。
2. 调度决策、熔断原因、恢复动作、operator 接管都应有日志。
3. 没有 telemetry 的自动化，不应进入默认主路径。
4. requirement、alert、approval、release 四类对外通知必须使用统一 envelope，至少包含服务、事件类型、优先级、风险等级、发生时间、发生了什么、下一步动作和关联链接。
5. 普通 state transition、atom success、artifact created、blackboard snapshot 不得发送 Lark，只能进入 Ops Console 可观测面；P0/P1 才能进入 alert 群，human gate 才能进入 approval 群。
6. 需求生成抑制和通知投递抑制必须分离。Notification queue 只决定“是否通知人”，Requirement Intake Gate 才决定“是否创建业务 requirement”。
7. 会创建 requirement 或触发后台副作用的 scheduler 必须有数据库级 lease；无法获得 lease 时记录 skipped/locked 运行历史，而不是并发执行。

## 18. Python 日志必须结构化

1. workspace 内的 Python 服务默认使用 `structlog + logging`，不继续把自由文本日志作为主输出。
2. 主输出必须是 `stdout` JSON；本地文件日志只作为备份，采用 `JSONL` 并按天切分。
3. 文件轮转默认按天执行并保留 14 天，除非专门设计文档说明不同保留策略。
4. 新增日志时必须优先绑定链路字段：`request_id`、`task_id`、`requirement_id`、`execution_id`、`release_id`、`fingerprint_key`。
5. 每条结构化日志至少包含基础字段：`ts`、`level`、`event`、`service`、`env`、`logger`、`message`。
6. 运行结果类日志应优先补充：`outcome`、`status`、`duration_ms`、`error_type`、`error_message`。
7. 不允许记录 token、secret、webhook url、authorization header 等敏感信息；traceback 可以保留，但必须避免把敏感配置直接拼进错误消息。
8. 当前阶段先按“各服务内实现、同一规范”落地，不假设已经存在可复用的共享 Python logging 包。

## 19. 正式功能列表必须同步维护

1. 系统当前正式具备的功能，必须维护在 `docs/design-docs/current-feature-inventory.md`。
2. 每次新增、删除、重构正式功能时，必须同步更新功能清单。
3. 功能清单描述的是“当前真实能力”，不是候选想法、计划或 bugfix 草稿。
4. 如果代码已经变更，但功能清单没有同步更新，应视为设计文档未完成。

## 20. 治理优先于更强自主性

1. 自主性提升必须建立在 policy、validation、delivery、incident、observability 已经收口的前提上。
2. 如果治理能力不足，优先补治理，不优先补更复杂的 agent 自主决策。

## 21. 当前正式实现顺序

后续默认优先顺序为：

1. Requirement 面的意图与治理收口
2. Execution 面的最小执行闭环
3. Release 面的交付与发布闭环
4. incident / recovery 的可观察性
5. 更复杂的 execution graph 与 deterministic runtime 能力

任何新设计如果会把系统重新拉回“大而全的单页面控制台”或“固定多阶段仪式流程”，都应视为违反当前正式架构。
