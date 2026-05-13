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
13. Goal Mission Lanes v1.1 保留三条核心战线：`product_planner` 发现产品缺口并提出 Product Opportunity，`growth_lead` 承接增长和 `/publishing`，`software_engineer` 承接 evidence-bound Requirement / Workflow。`content_writer` 是 Social Publishing 内部能力，不作为独立 lane。
14. `product_planning_sweep` 是轻量 recurring workflow：它只生成 `product_opportunities` / Goal Proposal，不自动创建正式 Goal、Requirement、workflow、X 发布、release、auth 或代码改动。
15. `/planning` 显示 `产品机会 / Goal Proposals` 审核区。Operator 可将 opportunity 转成 Planning Goal、defer 或 reject；转成 Goal 时保留 `metadata.source=product_opportunity` 与 `product_opportunity_id` lineage。
16. `/api/planning/mission-board` 提供嵌套 Mission Board：`active_goal`、`active_goals`、public-preview traction proof、`product_planner / growth_lead / software_engineer` 三列任务、`lane_summary`、`next_actions`、`unassigned` 红灯，不返回 graph `nodes[] / edges[]`。`active_goal` 是公司级主目标，`active_goals` 展示公司目标与产品/工程子目标，`software_engineer` 聚合所有 active goals 的工程候选、Requirement、Workflow 和 Release Task。
17. `/api/planning/mission-workbench` 提供 TreeGrid 投影：Company Goal -> Business/Product Goal -> Mission Lane -> Work Item，并为每行返回 task-specific `process_stages`。工程交付、产品机会、内容草稿和增长摘要各自展示自己的生命周期，不把 Social Ops 草稿强行套进 PR/Release 轨道。它同样是嵌套树，不返回 graph `nodes[] / edges[]`。
18. `/command-center` 是只读 Mission Dashboard：展示 active goal、三条 lane 摘要、每列最多 3 个最高优先级事项和 Unassigned 红灯；不在这里处理 Create / Reject / Defer。
19. `/planning` 是处理态 Queues：默认显示 Requirement-first `Task Board`，按 `requirements.status` 投影为 Backlog / Todo / In Progress / Human Review / Rework / Delivery / Done / Canceled。WorkflowRun、PR、Release 不再作为看板主卡片，只在 Requirement 卡详情里展示运行日志和交付证据。`Mission Workbench` 保留为 `Hierarchy` Tab，用树状层级和流程状态轨道辅助 operator 看清 Goal -> Lane -> Task -> Evidence；Growth Lead 在这里只展示摘要，具体回帖、转发候选和趋势明细在 `/publishing` / `/publishing/trends` 处理。其它 Tabs 包括 `产品机会`、`业务目标`、`工程队列`、`未归属`、`历史/Debug`。工程队列为空时给出 `Run Planner Sweep` 操作入口，用于让 operator 将 active business goals 转成 evidence-bound RequirementCandidate；active 但缺失 goal lineage 的数据进入 `未归属`，不能静默藏进 Debug。

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
13. Push / PR 质量门禁采用 scoped PR CI + full gate 分层：`scripts/ci/pr_checks.sh` 仍是 main/nightly/manual full 的 source of truth，并支持 `PR_CHECKS_PHASE=quality|backend|dashboard|all` 供远端 CI 并行拆分；PR 默认由 `scripts/ci/ci_scope.py` 分类后只运行相关 checks；`.githooks/pre-push` 默认运行 `scripts/ci/local_pr_checks.sh --scope auto`。
14. GitHub PR CI 暴露单一聚合 required check `pr-checks`，内部按 scope 运行 `guardrails`、`backend-checks`、`dashboard-checks`、`docs-checks`、`security-lite`、`scope-self-test`，或在 full gate 中并行运行 `full-quality` / `full-backend` / `full-dashboard`，避免 skipped job 阻塞合并并减少 Actions minutes。
15. PR CI 使用 pip / yarn / uv cache，并通过 `verify_system_tools.sh` 先检查 `rg`；只有 runner image 缺失 ripgrep 时才执行条件式 apt fallback，避免常规 PR 路径无脑 `apt-get update`。classifier-only 和 prompt/content-only 改动有更细 scope，避免误触发完整 backend + dashboard gate。
16. Push Quality Gates v2 已加入 typecheck/lint、复杂度、行数 ratchet、重复代码、secret scan、Bandit、dependency audit 与 branch protection diagnostic；现有 >500 行 legacy 文件通过 `quality/quality_baseline.json` 固定基线，后续变更不得继续膨胀；dependency audit 在 scoped PR 中按风险运行，full gate 必须执行。
17. `scripts/ci/source_quality_checks.py` 是 Push Quality Gates 的 source API shape 门禁：核心 Planning / Social / Releases public service surface 不允许返回裸 `dict` / `Dict[str, Any]` / `Mapping[str, Any]` 或前端 `Promise<Record<string, unknown>>`，必须返回 typed result object；raw maps 仅允许保留在 request/payload/metadata/blackboard 字段和 private helper 中；历史债务进入 `scripts/ci/source_quality_baseline.json`，普通 PR 不新增 baseline。
18. 新增内置 workflow definition `x_official_account_content_ops`：Agent 只生成 X 官方账号内容草稿并运行内容风险检查，随后停在人类审核边界；外部发布不由 workflow 自动触发。

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
8. `/releases` 的 `发布管理` 分面使用独立 Release Task 记录手动和需求流转发布意图；Release Task 不等于 Deployment Record。任务创建不会自动部署，分支选择从目标 GitHub 仓库 branch list 读取；`main` 分支可由 Operator 直接点击 `发布到 staging`，其它分支没有 open/merged PR 时只能提交 PR，PR checks 通过后才允许触发白名单发布 runner，production 仍必须 Human Gate。当前一等发布目标包含 `Synapse-Network` 的 gateway / gateway-admin / admin-front / user-front / docs-front，以及 `Synapse-Network-Provider` 的 provider-service。`Synapse-Network` staging dispatch 按 runtime family 选择 workflow：gateway -> `deploy-staging-gateway.yml`，gateway-admin/admin-front -> `deploy-staging-admin.yml`，user-front/docs-front -> `deploy-staging-frontends.yml`；目标仓库的 `deploy-staging.yml` 只作为 reusable core / compatibility runner。
9. Release Task detail modal 展示 PR gate、DeploymentRecord、GitHub Actions run link、health check、failure summary 和 deployment metadata；Synapse-Network 与 Synapse-Network-Provider staging runner 都使用 GCP Workload Identity Federation + Cloud Build + Cloud Run，不使用长生命周期 GCP service account JSON key 或 SSH deploy secrets；Provider DeploymentRecord 标记 `deploy_strategy=github_actions_wif_cloudrun`。
10. `/releases` 的 `上线记录` 分面只读展示成功的 `DeploymentRecord(status=succeeded)`，不混入 pending / failed / cancelled Release Task。手动标记 Release Task 已完成时，后端会创建或绑定一条 `manual_completion` 成功 DeploymentRecord 后再进入上线记录。上线记录用于确认 GitHub Actions、Cloud Run revision / image / manifest、health check 和 rollback target。
11. 没有 webhook callback 的本地发起 staging 部署，由全局 `release_deployment_status_sweep` 定时拉取 GitHub Actions run 结果，也可通过 `/releases` 的 `同步状态` 人工触发同一幂等同步函数；同步只处理未终态 DeploymentRecord，只读吸收外部事实，不触发 deploy / merge / rollback。点击 `发布到 staging` 后 Release Task 进入 `deploying / 自动检查中`，健康检查事实由 GitHub Actions runner 内的 Cloud Run smoke check 负责，Ops Console 只同步 Actions success/failure 和 smoke metadata。人工 completed / failed / cancelled 终态优先，不会被后台同步回滚。
12. Staging 发布分两类：`main` 分支可直接由 Operator 点击 `发布到 staging`；非 main 分支不要求先合并 `main`，但必须存在 PR 且 PR checks 通过。Production 默认只允许从 `main` / tag / verified staging manifest 推进，并必须 Human Gate。
13. Rollback 不由 Drop Goal、普通 Release Task PATCH 或 staging 快捷按钮触发。Runtime rollback 以历史成功上线记录的 commit / image / manifest 为 target 并进入 Human Gate；代码级 revert 必须走新分支、PR、checks、merge 和正常发布链路。
14. `/releases` 的 `定时任务发布` 分面管理 Synapse-Network 部署在 Google 上的 Cloud Run Jobs：gateway 周期任务 `deposit-indexer`、`provider-withdraw-reaper`、`consumer-withdraw-processor`、`notification-outbox-drain`、`in-app-cleanup`，以及 gateway / gateway-admin migration jobs。Operator 先通过 `创建定时任务发布` 选择 staging 环境、GitHub 分支和具体 job 名称，系统只创建 `scheduled_job_release_tasks(status=requested)`，不会 dispatch；只有在列表中点击 `发布到 staging` 才创建 `DeploymentRecord(trigger_source=scheduled_job_release)` 并 dispatch `deploy-staging-jobs.yml`。
15. 定时任务发布状态以 `scheduled_job_release_tasks` 为 UI source of truth；物理执行结果来自关联 DeploymentRecord、GitHub Actions callback / sync 和 `jobsManifest`。全局 `release_deployment_status_sweep` 与手动 `同步状态` 都会同步普通 Release Task 和定时任务发布任务。Google 写操作、单 job image 更新、可选 smoke / migration execution 全部在 GitHub Actions + WIF 中完成，本机 API 不调用 `gcloud`。Scheduler freshness 是健康信号，不等同发布失败；migration jobs 是发布时手动/受控执行任务，不做 freshness 警报。
16. 本地主库支持 Docker Postgres。`OPS_DATABASE_URL=postgresql+psycopg://synapse_growing:synapse_growing_dev@127.0.0.1:54329/synapse_growing` 可将应用切到 Postgres；`scripts/db/migrate_sqlite_to_postgres.py` 负责从 `server/ops.db` 全量迁移所有现有表和数据，`scripts/db/validate_postgres_migration.py` 校验每表 row count，`scripts/db/run_sql_migrations.py` 通过 `schema_migrations` 幂等执行后续 SQL。完整操作记录见 `docs/ops/05_Postgres_Migration_and_E2E_Runbook.md`。

## 4.5 Social Publishing

当前已具备：

1. `/publishing` 已升级为 **Social Ops + Developer Distribution Center**，主流程只使用 `social_content_assets`、`social_distribution_tasks`、`social_distribution_documents`、`social_distribution_events` 和 `social_distribution_accounts`。旧 X 主流程表 `social_post_drafts`、`social_post_media_assets`、`social_publish_events`、`social_reply_items`、`social_repost_candidates` 只允许通过一次性迁移脚本读取并落到新表；新 UI / 新 API 不做双写同步。
2. `/publishing` 顶层只保留 3 个 Tabs：`Tasks`、`Signals & Metrics`、`Settings`。旧 `Assets`、`今日队列`、`回帖处理`、`转发候选`、`分发任务`、`分发渠道`、`已发布效果`、`品牌规则` 不再作为顶层入口，相关能力按职责归入三个新分区。
3. `Tasks` 默认是简化的 Symphony / Linear 风格内容任务看板，列为 `待计划 / 待审核 / 待发布 / 已发布 / 异常`。一张卡代表一个 Content Asset，卡内聚合平台 task、document、event 和发布证据；列位置由后端 `/api/social/distribution/board` 投影，不允许拖拽直接改状态，内部细状态只在详情 Modal 展示。
4. `Tasks` 支持 `创建内容任务`：operator 输入主题、来源材料、目标受众、目标平台、source doc path 和 canonical URL 后，系统创建 `social_content_assets(source_type=manual_task)` 并同步写入 `social_distribution_documents(document_kind=source_plan)`。正式平台任务必须先经过 `source_plan -> canonical_article 母稿扩写 -> 人工审核母稿`，缺少已审核母稿时生成任务会 fail closed 为 `canonical_article_required`。
5. 源内容资产由 `social_content_assets` 承载，但不再作为顶层 `Assets` Tab 暴露给 operator。文章、demo、X post、reply、quote、launch asset 都通过 `Tasks` 看板卡片和详情 Modal 进入操作流；Operator 创建内容资产后先点击 `扩写母稿`，后端调用 Asset Expansion Agent 生成 `social_distribution_documents(document_kind=canonical_article,status=needs_review,generated_by=asset_expansion_agent_v1)`；母稿审核通过后，后端才按固定平台顺序串行生成 task draft：`x -> hacker_news -> reddit -> v2ex -> devto -> hashnode -> product_hunt`。平台间加入小 jitter，单个平台失败只标记该 task `failed` 并记录 event，不回滚已成功平台。
6. 平台草稿是一等文档：每次成功生成 `social_distribution_tasks` 时，同步写入 / 更新 `social_distribution_documents(document_kind=platform_draft)`；`platform_title/platform_body` 继续作为最新文档投影，保证列表和旧调用方兼容。历史 task 若已有 `platform_title/platform_body` 但缺少 `platform_draft`，board/detail 读取会幂等 backfill。
7. `social_asset_planner_sweep` 自动生成候选 Assets，但每次只采样一种核心信号类型，最多传 5 条 public-safe signals，每天 active Asset 库存达到 3 个就不再生成。它只创建 `social_content_assets(status=proposed)`，不自动生成 task、不自动发布。
8. 平台适配使用信息密度驱动 prompt：X 为 Premium 长帖软上限 4000 字符且无下限，Reddit / V2EX 软上限 2000 字符且只提取 1-2 个最适合讨论的技术决策，DEV / Hashnode 基于完整母稿做 Markdown/canonical URL 适配，不额外拉长，HN 保持克制的提交标题 / URL / 首评提示。所有平台禁止为了凑字数重复观点、写空话或编造细节。
9. `Settings` 管理 `social_distribution_accounts`：平台、channel、注册入口、profile URL、账号状态、2FA 状态、备注、read automation mode、human publish required。`docs/ops/04_Developer_Distribution_Accounts.md` 是账号注册和治理 source of truth。
10. `Signals & Metrics` 只读展示本地信号与效果：`social_trend_items`、`social_watchlist_accounts`、`social_post_metrics` / 后续 `social_distribution_metrics`。页面切换、分页、详情查看不得触发额外外部平台 read。
11. 非 X 平台 v1 只支持人工发布闭环：系统生成平台适配标题、正文、checklist、打开平台链接和复制按钮；operator 在外部平台手动发布后回填 `published_url` 和 `status=live | removed | skipped`。不要求人工维护 votes/comments/views 等 metrics，避免把 operator 变成爬虫。
12. X 仍可以保留 OAuth/API 发布能力，但在新模型中表现为 `social_distribution_tasks(platform=x, action=post|reply|quote|repost_link)`。公开 X 发布、回复、引用转发仍必须 Human Gate，不允许自动点赞、关注、删除、私信或绕过平台限制。
13. DEV / Hashnode task 必须在 `operator_checklist` 中提示填写 Canonical URL；缺少 `canonical_url` 时 task metadata 写入 `canonical_url_missing` warning，UI 明确提示不建议发布。
14. Agent Content Pack 的结构化输出使用 `parse_agent_json_output`：只剥离 Markdown fence / `json` 外包装并提取第一段完整 JSON object，解析失败以 `agent_json_parse_failed` fail closed，不保存假 Asset。
15. 高可信教程依赖 `@synapse-context:*` 标签契约：`synapse-network-sdk:quickstart`、`synapse-network-mcp-server:spring_boot_mcp`、`synapse-network-provider:onboarding` 必须由白名单文件解析；缺失时返回 `insufficient_source_context`，不得靠模型猜 API 或代码。
16. Social Content / Distribution Agent 当前支持矩阵：
   - `codex + gpt-5.4`：当前本机已验证，可作为默认 Social Content / Distribution 生成模型。
   - `codex + gpt-5-codex`：当前 ChatGPT Codex account 不支持，不作为默认。
   - `openai + gpt-4o`：代码路径支持，但本机当前 quota 不足时必须 fail closed。
   - `claude + claude-3-7-sonnet-latest`：代码路径支持，但本机 key 无效时必须 fail closed。
   - `copilot + gpt-4o`：代码支持 direct API；不能使用 GitHub PAT，必须使用 Copilot OAuth token。
21. `/publishing` 交互继续遵守 **Modal-only** 与 **NEVER USE DRAWERS** 约束：所有新建、编辑、详情、发布/标记确认都必须使用居中 Modal / Dialog，禁止 Drawer、Slide-out、Offcanvas、Side Panel 或右侧滑出面板。UI 继续遵守 `ui-ux-pro-max` SaaS / Ops Console 设计约束。
22. 一次性迁移脚本 `scripts/dev/migrate_social_distribution_v2.py` 会把旧草稿、回帖、转发候选转换为 `asset + task + event`，并在显式确认后删除旧主流程表。迁移不是长期兼容层，迁移完成后旧表不再是 Source of Truth。

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
7. Release Deployment Status Sweep，用于吸收 GitHub Actions staging deploy success / failure / running / missing-run 外部事实；它是全局固定 sweep，不是每个发布任务动态 cron。
8. Notification Dispatcher 后台 loop。
9. Notification queue / fingerprint / delivery 记录。
10. Lark channel routing：
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
6. 内置项目包含 `Synapse-Network-Growing`、`Synapse-Network`、`Synapse-Network-Provider`、`Synapse-Network-Sdk`、`Synapse-Network-MCP-Server` 和 `Agents-Memory`；`Synapse-Network-MCP-Server` v1 进入项目治理和工程任务体系，但 deploy strategy 为 `disabled`，不接 `/releases` staging 快捷发布。
7. Project 的 `repo_full_name` 是 source repository truth，UI 的 `GitHub 仓库` 字段可输入 `owner/repo`、HTTPS git URL 或 SSH git URL，后端统一归一化为 `owner/repo`；`deploy_repo_full_name` 是独立部署仓库字段，只有部署仓库不同或 deploy-enabled 项目需要填写，不能覆盖 source repo。

## 8. Runtime And Planner Adapter

当前已具备：

1. `PLANNER_BACKEND` 独立选择 planner adapter。
2. 支持 `openai | claude | copilot | codex_cli | codex_sdk`。
3. Codex CLI / SDK planner adapter 支持项目级 planner session 复用。
4. 普通 LLM adapter 不写 Codex session registry。
5. Codex CLI / SDK 与 OpenAI Responses 保留为 planner/runtime provider 能力，通过 adapter 或 declarative atom 使用。
6. Workflow runtime session 现在记录 workspace trust：Kill 后写入 `dirty_after_kill` / `requires_workspace_recovery`，`continue_retry` 之前会运行 Workspace Recovery Preflight；只有 workflow-owned worktree 或匹配的 `ops/` / `codex/` branch 才允许自动 `git reset --hard HEAD && git clean -fd`，用户主工作区会进入 Human Review。
7. Workflow detail 的 Gates & Delivery 会展示 Workspace Recovery badge、repo / branch 和 preflight 日志摘要；需要恢复时按钮文案为 `Recover Workspace & Retry`，并使用居中确认 Modal。
8. 旧 `/api/tasks`、`/api/approvals`、fixed-step orchestrator 包和 legacy task runner 已退役；新增功能不得重新引入旧 TaskBoard / workflow step 主链。

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
2. 深色 cockpit AppShell 使用 Top Header Navigation，不再使用桌面持久次级导航。主导航只保留 `Command Center`、`Planning`、`Publishing`、`Releases` 四个高频业务入口。
3. 顶栏右侧保留 `Needs Human` badge、`Cmd+K / Search` 低频入口和 `Alerts` 通知入口；`/gates`、`/requirements`、`/workflows`、`/schedules`、`/projects`、`/errors` 等路由继续存在，但不占用主导航。
4. `/gates` 集中展示 pending human gates、failed / blocked workflow。
5. `/factory/workflows` 只读展示 workflow definitions、states、transitions、limits、risk policy。
6. `/factory/atoms` 从 workflow definitions 反推 agent / deterministic / terminal atom registry。
7. `/intake` 作为需求发现入口，连接 errors、planner、forum feedback 和 watcher events。
8. `/knowledge` 作为 artifacts / SOP Ledger 的一等入口。
9. `/system/notifications` 展示 notification dispatcher、queue、dead letter、open fingerprint 概览。
10. Figma / Stitch 原型视觉方向已记录在 `frontend-control-plane-figma-implementation.md`。
11. Factory pages v1 只读，不开放在线 YAML 编辑。
