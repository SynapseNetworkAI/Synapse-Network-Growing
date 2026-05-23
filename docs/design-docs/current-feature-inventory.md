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
13. Push / PR 质量门禁已切换为 CLI-first 本地 CI：`scripts/local/ci.sh` 读取当前 repo / branch / commit，调用 `POST /api/ci/runs` 创建 `local_ci_runs(status=requested)`，随后立即运行 `scripts/local/run_ci_worker.py --once --run-id <id>`。Worker 复用 chunked log writer，将 stdout / stderr 写入 `local_ci_events`，终端保留实时输出，Ops Console 保留审计记录。`scripts/ci/local_pr_checks.sh --scope auto|full` 仍是本地 checks source of truth；Backend scoped check 默认进入 `backend-targeted`，通过 `scripts/ci/backend_targeted_tests.py` 按 changed files 选择映射测试；例如 `server/services/scheduling/**` 只跑 `tests/test_weekly_repo_hygiene_review.py` 加基础 CI/quality/py_compile。`backend-full` 只保留给 main、manual full、migration/schema、release/runtime/security/finance、CI gate 等高风险改动。
14. GitHub 仓库只承担代码托管和 PR review，不再运行 required GitHub workflow checks。Branch protection 必须移除已删除 workflow check 要求；v1 的合并保护由 operator 在本地执行 `scripts/local/ci.sh` 并在 PR 描述/评论中记录结果。
15. 本地 CI 使用本机 pip / yarn / uv cache 和 repo 内工具脚本，不再消耗 GitHub-hosted runner minutes。Ops Console 通过 `local_ci_runs/local_ci_events` 展示历史、状态和完整日志。
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
8. `/releases` 的 `发布管理` 分面使用独立 Release Task 记录手动和需求流转发布意图；Release Task 不等于 Deployment Record。任务创建不会自动部署，分支选择从目标 GitHub 仓库 branch list 读取；`main` 分支可由 Operator 直接点击 `发布到 staging`，其它分支没有 open/merged PR 时只能提交 PR，并以本地 CI run 结果作为人工门禁证据。Production 发布已接入 Human-Gated Release Task：只允许 `main`，要求 operator 输入 `YES`。后端 / 资金 / migration 相关服务仍必须同一 project / service / commit 已有 staging success；前端也默认从 staging 成功 digest promote，保持统一状态机。当前一等发布目标包含 `Synapse-Network` 的 gateway / gateway-admin / admin-front / user-front / docs-front，以及 `Synapse-Network-Provider` 的 provider-service。点击发布只创建 `DeploymentRecord(trigger_source=local_deploy_runner)`，真实构建、digest promotion、Cloud Run deploy、smoke 和 manifest 写入全部由 `scripts/local/run_deploy_worker.py` 执行；production impersonation 只能通过子进程环境变量 `CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT`，禁止修改全局 `gcloud config`。
9. Release Task detail modal 展示 PR gate、DeploymentRecord、本地 runner、health check、failure summary、deployment metadata 和 append-only deployment event log。`deployment_events` 按 `deployment_record_id + sequence` 保存完整 stdout / stderr / step / runner status；Local Deploy Runner 使用 `server/services/local_runner/log_stream.py` 以 2 秒或 64KB 时间窗口块状写入，避免日志风暴一行一条 DB event，同时不做 tail-only 或业务级截断。详情 Modal 通过 `/api/releases/deployments/{id}/events?after_sequence=` 增量轮询。Force Reset local deploy 只把任务重置为 `requested`，将旧 DeploymentRecord 标记 failed，并追加 `local_deploy_force_reset` event，不删除旧日志。
10. `/releases` 的 `上线记录` 分面只读展示成功的 `DeploymentRecord(status=succeeded)`，不混入 pending / failed / cancelled Release Task。手动标记 Release Task 已完成时，后端会创建或绑定一条 `manual_completion` 成功 DeploymentRecord 后再进入上线记录。上线记录用于确认本地 runner、Cloud Run revision / image / manifest、health check 和 rollback target，并可按 `staging` / `production` 过滤。
11. 本地发起 staging / production 部署由 `release_deployment_status_sweep` 只读汇总本地 DeploymentRecord 状态，也可通过 `/releases` 的 `刷新本地状态` 人工触发同一幂等函数；同步只处理本地记录，不触发 deploy / merge / rollback。点击 `发布到 staging` 后 Release Task 进入 `deploying / 自动检查中`，健康检查事实由本地 runner 的 Cloud Run smoke check 负责。人工 completed / failed / cancelled 终态优先，不会被后台同步回滚。
12. Staging 发布分两类：`main` 分支可直接由 Operator 点击 `发布到 staging`；非 main 分支不要求先合并 `main`，但必须存在 PR 且 PR checks 通过。Production v1 只允许从 `main` 的 verified staging commit 推进，并必须经过 Growing Human Gate 与 GitHub Environment `production` 双门禁。
13. Rollback 不由 Drop Goal、普通 Release Task PATCH 或 staging 快捷按钮触发。Runtime rollback 以历史成功上线记录的 commit / image / manifest 为 target 并进入 Human Gate；代码级 revert 必须走新分支、PR、checks、merge 和正常发布链路。
14. `/releases` 的 `定时任务发布` 分面管理 Synapse-Network 部署在 Google 上的 Cloud Run Jobs：gateway 周期任务 `deposit-indexer`、`provider-withdraw-reaper`、`consumer-withdraw-processor`、`notification-outbox-drain`、`in-app-cleanup`，以及 gateway / gateway-admin migration jobs。Operator 先通过 `创建定时任务发布` 选择 staging 环境、GitHub 分支和具体 job 名称，系统只创建 `scheduled_job_release_tasks(status=requested)`；只有在列表中点击 `发布到 staging` 才创建本地 `DeploymentRecord(trigger_source=local_deploy_runner)`，等待 scheduled-job local runner 执行。
15. 定时任务发布状态以 `scheduled_job_release_tasks` 为 UI source of truth；物理执行结果来自关联 DeploymentRecord、本地 runner events 和 `jobsManifest`。全局 `release_deployment_status_sweep` 与手动 `同步状态` 都会同步普通 Release Task 和定时任务发布任务。Google 写操作、单 job image 更新、可选 smoke / migration execution 全部在本地 scheduled-job runner 中完成。Scheduler freshness 是健康信号，不等同发布失败；migration jobs 是发布时手动/受控执行任务，不做 freshness 警报。
16. 本地主库已切换为 PostgreSQL-only。`OPS_DATABASE_URL` 必须是 PostgreSQL URL，例如 `postgresql+psycopg://synapse_growing:synapse_growing_dev@127.0.0.1:54329/synapse_growing_local`；缺失或 SQLite URL 会 fail closed。`scripts/db/migrate_sqlite_to_postgres.py` 只负责从历史 `server/ops.db` 一次性导入现有表和数据，`scripts/db/validate_postgres_migration.py` 校验每表 row count/hash，`scripts/db/run_sql_migrations.py` 通过 `schema_migrations` 幂等执行后续 SQL。完整操作记录见 `docs/ops/05_Postgres_Migration_and_E2E_Runbook.md`。
17. `/releases` 的 `SDK Packages` 分面管理公共 SDK registry 发布，而不是 Cloud Run 环境部署。主视图是分页 `Release History`，每个平台、每个版本是一条发布记录，并在发布成功后展示 PyPI / npm / Go / Maven / NuGet registry URL；release train 详情页展示 `Public SDK links` 汇总区与 GitHub SDK source repo。当前 `1.0.0` 已发布到 Python `synapse-network-ai-sdk`、TypeScript `@synapse-network-ai/sdk`、Go module、Java `ai.synapse-network:synapse-network-sdk` 和 .NET `SynapseNetwork.Sdk`。Operator 可新增单个平台记录或完整 release train，例如 `1.0.0`，为 Python / TypeScript / Go / Java / .NET 创建 package release records；平台配置通过 `SDK Platform Settings` 启用 allowlisted registry template，凭据只来自本地 runner env 或等价 secret storage，不写入普通 metadata。Dry-run 进入 `dry_running` 并由 `scripts/local/run_sdk_publish_worker.py` 执行真实构建 / pack / registry metadata 检查；通过后进入 `ready_to_publish`。Publish 需要 Human Gate 确认短语 `PUBLISH_SDK_<version>`，本地 runner 执行真实 registry publish、写入 artifact manifest、package URL、verify result 和 append-only events；同一已发布版本不可覆盖，修复必须提升 patch version。SDK 发布完成后必须回写 registry URL、安装命令和 verify metadata，并用公共 registry 下载命令确认可下载。
18. SDK package release detail 将 `sdk_package_releases` 作为发布结果账本：详情页在 Links 后展示同一 `sdk_language + registry + package_name` 的分页搜索结果历史，默认按 `updated_at desc, id desc` 排序，并提供 Registry、GitHub tag 和 Workflow 跳转；`sdk_package_release_events` 只作为单条结果的操作时间线。

## 4.5 Social Publishing

当前已具备：

1. `/publishing` 已升级为 **Social Ops + Developer Distribution Center**，主流程只使用 `social_content_assets`、`social_distribution_tasks`、`social_distribution_documents`、`social_distribution_events` 和 `social_distribution_accounts`。旧 X 主流程表 `social_post_drafts`、`social_post_media_assets`、`social_publish_events`、`social_reply_items`、`social_repost_candidates` 只允许通过一次性迁移脚本读取并落到新表；新 UI / 新 API 不做双写同步。
2. `/publishing` 顶层只保留 3 个 Tabs：`Tasks`、`Signals & Metrics`、`Settings`。旧 `Assets`、`今日队列`、`回帖处理`、`转发候选`、`分发任务`、`分发渠道`、`已发布效果`、`品牌规则` 不再作为顶层入口，相关能力按职责归入三个新分区。
3. `Tasks` 默认是简化的 Symphony / Linear 风格内容任务看板，列为 `待计划 / 待审核 / 待发布 / 已发布 / 异常`。一张卡代表一个 Content Asset，卡内聚合平台 task、document、event 和发布证据；列位置由后端 `/api/social/distribution/board` 投影，不允许拖拽直接改状态，内部细状态只在详情 Modal 展示。
4. `Tasks` 支持 `创建内容任务`：operator 输入主题、来源材料、目标受众、目标平台、source doc path 和 canonical URL 后，系统创建 `social_content_assets(source_type=manual_task)` 并同步写入 `social_distribution_documents(document_kind=source_plan)`。正式平台任务必须先经过 `source_plan -> canonical_article 母稿扩写 -> 人工审核母稿`，缺少已审核母稿时生成任务会 fail closed 为 `canonical_article_required`。
5. 源内容资产由 `social_content_assets` 承载，但不再作为顶层 `Assets` Tab 暴露给 operator。文章、demo、X post、reply、quote、launch asset 都通过 `Tasks` 看板卡片和详情 Modal 进入操作流；Operator 创建内容资产后先点击 `扩写母稿`，后端调用 Asset Expansion Agent 生成 `social_distribution_documents(document_kind=canonical_article,status=needs_review,generated_by=asset_expansion_agent_v1)`；母稿审核通过后，后端才按固定平台顺序串行生成 task draft：`x -> hacker_news -> reddit -> v2ex -> devto -> hashnode -> product_hunt`。平台间加入小 jitter，单个平台失败只标记该 task `failed` 并记录 event，不回滚已成功平台。
6. `Tasks` 新增 Campaign Template：`X Brand Week - Technical Builders` 可一键创建 12 张 X 品牌周任务卡，包含 7 个原创内容任务和 5 个 reply-block 互动任务，统一写入 `goal_key=campaign_key=x_brand_awareness_week_1`，并在 metadata 中记录 `post_intent` 与计划发布时间。互动任务只生成 value-add reply drafts，不自动评论、不自动点赞、不自动关注。
7. 平台草稿是一等文档：每次成功生成 `social_distribution_tasks` 时，同步写入 / 更新 `social_distribution_documents(document_kind=platform_draft)`；`platform_title/platform_body` 继续作为最新文档投影，保证列表和旧调用方兼容。历史 task 若已有 `platform_title/platform_body` 但缺少 `platform_draft`，board/detail 读取会幂等 backfill。
8. `social_asset_planner_sweep` 自动生成候选 Assets，但每次只采样一种核心信号类型，最多传 5 条 public-safe signals，每天 active Asset 库存达到 3 个就不再生成。它只创建 `social_content_assets(status=proposed)`，不自动生成 task、不自动发布。
9. 平台适配使用信息密度驱动 prompt：X Official Account 默认生成 `x_long_post`，Premium 长帖软上限 4000 字符且无下限；简单更新或显式要求 thread 时才使用 `single/thread`。Reddit / V2EX 软上限 2000 字符且只提取 1-2 个最适合讨论的技术决策，DEV / Hashnode 基于完整母稿做 Markdown/canonical URL 适配，不额外拉长，HN 保持克制的提交标题 / URL / 首评提示。所有平台禁止为了凑字数重复观点、写空话或编造细节。
10. `Settings` 管理 `social_distribution_accounts`：平台、channel、注册入口、profile URL、账号状态、2FA 状态、备注、read automation mode、human publish required，并可实时调用 `auth-status` 展示 `official_api / browser_assisted / manual_only / blocked`、blockers、next action 和登录/打开平台入口。登录状态是 computed preflight，不落库为永久事实。
11. `Signals & Metrics` 只读展示本地信号与效果：`social_trend_items`、`social_watchlist_accounts`、`social_post_metrics` / 后续 `social_distribution_metrics`。页面切换、分页、详情查看不得触发额外外部平台 read。发布后的 X views、profile visits、replies、bookmarks、followers delta、posted time 与 format kind 允许 operator 手动录入，用于品牌周复盘；这些指标是人工证据，不是自动抓取。
12. 非 X 平台 v1 采用 API-first / browser-assisted 闭环：系统生成平台适配标题、正文、checklist、打开平台链接和复制按钮；`/api/social/distribution/accounts/auth-status` 实时计算每个账号的 `official_api | browser_assisted | manual_only | blocked` 发布路径。DEV / Reddit / Hashnode 只有在 credential 和平台权限明确配置后才允许官方 API；HN / V2EX / Product Hunt 默认浏览器辅助或人工发布，不逆向私有页面接口。operator 在外部平台发布后回填 `published_url` 并 `标记为已发布`，live 任务显示 `查看帖子`；`removed | skipped` 仍由 operator 手动记录。X API publish 成功会直接写 `status=live`、`external_post_id`、`published_url` 和 `task_published_*` event；失败会 fail-closed 并保留人工复制到 X Web 发布和回填 URL 的路径。不要求人工维护 votes/comments/views 等 metrics，避免把 operator 变成爬虫。
13. X 仍可以保留 OAuth/API 发布能力，但在新模型中表现为 `social_distribution_tasks(platform=x, action=post|reply|quote|repost_link)`。公开 X 发布、回复、引用转发仍必须 Human Gate，不允许自动点赞、关注、删除、私信或绕过平台限制。
14. X Official Account 的 OAuth2 `access_token` 不落库；`x-official-oauth2-client-id` / `x-official-oauth2-client-secret` 暂留 Secret Manager，`x-official-oauth2-refresh-token` 改由本地 Postgres `local_secret_versions` 加密版本表保存。refresh token 轮换只新增本地加密版本，并自动保留最近 3 个 active versions，避免 Secret Manager version storage 暴涨。
14. DEV / Hashnode task 必须在 `operator_checklist` 中提示填写 Canonical URL；缺少 `canonical_url` 时 task metadata 写入 `canonical_url_missing` warning，UI 明确提示不建议发布。
15. Agent Content Pack 的结构化输出使用 `parse_agent_json_output`：只剥离 Markdown fence / `json` 外包装并提取第一段完整 JSON object，解析失败以 `agent_json_parse_failed` fail closed，不保存假 Asset。
16. 高可信教程依赖 `@synapse-context:*` 标签契约：`synapse-network-sdk:quickstart`、`synapse-network-mcp-server:spring_boot_mcp`、`synapse-network-provider:onboarding` 必须由白名单文件解析；缺失时返回 `insufficient_source_context`，不得靠模型猜 API 或代码。
17. Social Content / Distribution Agent 当前支持矩阵：
   - `codex + gpt-5.4`：当前本机已验证，可作为默认 Social Content / Distribution 生成模型。
   - `codex + gpt-5-codex`：当前 ChatGPT Codex account 不支持，不作为默认。
   - `openai + gpt-4o`：代码路径支持，但本机当前 quota 不足时必须 fail closed。
   - `claude + claude-3-7-sonnet-latest`：代码路径支持，但本机 key 无效时必须 fail closed。
   - `copilot + gpt-4o`：代码支持 direct API；不能使用 GitHub PAT，必须使用 Copilot OAuth token。
18. `/publishing` 交互继续遵守 **Modal-only** 与 **NEVER USE DRAWERS** 约束：所有新建、编辑、详情、发布/标记确认都必须使用居中 Modal / Dialog，禁止 Drawer、Slide-out、Offcanvas、Side Panel 或右侧滑出面板。UI 继续遵守 `ui-ux-pro-max` SaaS / Ops Console 设计约束。
19. 一次性迁移脚本 `scripts/dev/migrate_social_distribution_v2.py` 会把旧草稿、回帖、转发候选转换为 `asset + task + event`，并在显式确认后删除旧主流程表。迁移不是长期兼容层，迁移完成后旧表不再是 Source of Truth。

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
7. Release Deployment Status Sweep，用于吸收本地 runner 写入的 DeploymentRecord success / failure / running / requested 事实；它是全局固定 sweep，不是每个发布任务动态 cron。
8. Weekly Repo Hygiene Review：每周日扫描 repo/docs/CI review hygiene 与 Ops stale state；低风险 mechanical cleanup 通过 `agent_self_repair` 自动开 PR，但不自动 merge，不清理 Docker、本机缓存、外部平台或生产资源。
9. Notification Dispatcher 后台 loop。
10. Notification queue / fingerprint / delivery 记录。
11. Lark channel routing：
   - alert
   - approval
   - workflow notification
   - release
12. Cooldown、suppression、rollup、retry、dead letter。
13. Dispatcher queue health 展示 queued、dead letter、open fingerprints、suppressed count。
14. `secret_manager_version_cleanup_sweep` 是可观测 recurring workflow：每天 12:00（`OPS_OPERATOR_TIMEZONE`，默认 `Asia/Kuala_Lumpur`）扫描 staging `fabled-archive-494108-k5` 与 production `synapse-network-prod` 的 Secret Manager metadata，只保留每个 secret 最新 3 个 `ENABLED` / `DISABLED` active versions，其余 destroy；它不读取 secret payload，并在 `/schedules` 记录 dry-run / apply 结果。
15. `artifact_registry_cleanup_sweep` 是可观测 recurring workflow：默认每天 12:20 扫描 staging / production Artifact Registry Docker image metadata，保留最新版本和 promoted / production / release tags，dry-run 展示候选，apply 只删除候选镜像并记录 kept / deleted / skipped / error 明细。
16. `/api/schedules` 是 Schedule Center v1 统一 API，保留 `/api/recurring-workflows` 兼容路径；自定义 schedule 只能从 allowlisted template 创建，不支持任意 shell cron。

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
2. 深色 cockpit AppShell 使用 Top Header Navigation，不再使用桌面持久次级导航。主导航保留 `Command Center`、`Planning`、`Publishing`、`Releases`、`Schedule` 五个高频控制面入口。
3. 顶栏右侧保留 `Needs Human` badge、`Cmd+K / Search` 低频入口和 `Alerts` 通知入口；`/gates`、`/requirements`、`/workflows`、`/projects`、`/errors` 等路由继续存在，但不占用主导航。
4. `/gates` 集中展示 pending human gates、failed / blocked workflow。
5. `/factory/workflows` 只读展示 workflow definitions、states、transitions、limits、risk policy。
6. `/factory/atoms` 从 workflow definitions 反推 agent / deterministic / terminal atom registry。
7. `/intake` 作为需求发现入口，连接 errors、planner、forum feedback 和 watcher events。
8. `/knowledge` 作为 artifacts / SOP Ledger 的一等入口。
9. `/system/notifications` 展示 notification dispatcher、queue、dead letter、open fingerprint 概览。
10. Figma / Stitch 原型视觉方向已记录在 `frontend-control-plane-figma-implementation.md`。
11. Factory pages v1 只读，不开放在线 YAML 编辑。
