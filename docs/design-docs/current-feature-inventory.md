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
17. `/api/planning/mission-workbench` 提供 TreeGrid 投影：Company Goal -> Business/Product Goal -> Mission Lane -> Work Item，并为每行返回固定 stage rail：`opportunity / candidate / requirement / workflow / pr / release / online_record`。它同样是嵌套树，不返回 graph `nodes[] / edges[]`。
18. `/command-center` 是只读 Mission Dashboard：展示 active goal、三条 lane 摘要、每列最多 3 个最高优先级事项和 Unassigned 红灯；不在这里处理 Create / Reject / Defer。
19. `/planning` 是处理态 Queues：默认显示 `Mission Workbench` 树状层级和流程状态轨道，辅助 operator 看清 Goal -> Lane -> Task -> Evidence；其它 Tabs 包括 `产品机会`、`业务目标`、`工程队列`、`未归属`、`历史/Debug`。工程队列为空时给出 `Run Planner Sweep` 操作入口，用于让 operator 将 active business goals 转成 evidence-bound RequirementCandidate；active 但缺失 goal lineage 的数据进入 `未归属`，不能静默藏进 Debug。

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
13. Push / PR 质量门禁通过 `.githooks/pre-push` 与 GitHub PR CI 复用 `scripts/ci/pr_checks.sh`，覆盖 repo guardrails、`scripts/ci/code_quality_gates.sh`、backend pytest、Python diff coverage、dashboard tests/build 与 whitespace。
14. Push Quality Gates v2 已加入 typecheck/lint、复杂度、行数 ratchet、重复代码、secret scan、Bandit、dependency audit 与 branch protection diagnostic；现有 >500 行 legacy 文件通过 `quality/quality_baseline.json` 固定基线，后续变更不得继续膨胀。
15. `scripts/ci/source_quality_checks.py` 是 Push Quality Gates 的 source API shape 门禁：核心 Planning / Social / Releases public service surface 不允许返回裸 `dict` / `Dict[str, Any]` / `Mapping[str, Any]` 或前端 `Promise<Record<string, unknown>>`，必须返回 typed result object；raw maps 仅允许保留在 request/payload/metadata/blackboard 字段和 private helper 中；历史债务进入 `scripts/ci/source_quality_baseline.json`，普通 PR 不新增 baseline。
16. 新增内置 workflow definition `x_official_account_content_ops`：Agent 只生成 X 官方账号内容草稿并运行内容风险检查，随后停在人类审核边界；外部发布不由 workflow 自动触发。

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
8. `/releases` 的 `发布管理` 分面使用独立 Release Task 记录手动和需求流转发布意图；Release Task 不等于 Deployment Record。任务创建不会自动部署，分支选择从目标 GitHub 仓库 branch list 读取；`main` 分支可由 Operator 直接点击 `发布到 staging`，其它分支没有 open/merged PR 时只能提交 PR，PR checks 通过后才允许触发白名单发布 runner，production 仍必须 Human Gate。当前一等发布目标包含 `Synapse-Network` 的 gateway / gateway-admin / admin-front / user-front，以及 `Synapse-Network-Provider` 的 provider-service。
9. Release Task detail drawer 展示 PR gate、DeploymentRecord、GitHub Actions run link、health check、failure summary 和 deployment metadata；Synapse-Network 与 Synapse-Network-Provider staging runner 都使用 GCP Workload Identity Federation + Cloud Build + Cloud Run，不使用长生命周期 GCP service account JSON key 或 SSH deploy secrets；Provider DeploymentRecord 标记 `deploy_strategy=github_actions_wif_cloudrun`。
10. `/releases` 的 `上线记录` 分面只读展示成功的 `DeploymentRecord(status=succeeded)`，不混入 pending / failed / cancelled Release Task。手动标记 Release Task 已完成时，后端会创建或绑定一条 `manual_completion` 成功 DeploymentRecord 后再进入上线记录。上线记录用于确认 GitHub Actions、Cloud Run revision / image / manifest、health check 和 rollback target。
11. 没有 webhook callback 的本地发起 staging 部署，由全局 `release_deployment_status_sweep` 定时拉取 GitHub Actions run 结果，也可通过 `/releases` 的 `同步状态` 人工触发同一幂等同步函数；同步只处理未终态 DeploymentRecord，只读吸收外部事实，不触发 deploy / merge / rollback。人工 completed / failed / cancelled 终态优先，不会被后台同步回滚。
12. Staging 发布分两类：`main` 分支可直接由 Operator 点击 `发布到 staging`；非 main 分支不要求先合并 `main`，但必须存在 PR 且 PR checks 通过。Production 默认只允许从 `main` / tag / verified staging manifest 推进，并必须 Human Gate。
13. Rollback 不由 Drop Goal、普通 Release Task PATCH 或 staging 快捷按钮触发。Runtime rollback 以历史成功上线记录的 commit / image / manifest 为 target 并进入 Human Gate；代码级 revert 必须走新分支、PR、checks、merge 和正常发布链路。

## 4.5 Social Publishing

当前已具备：

1. `/publishing` 官方账号内容发布控制面。
2. 第一版只支持 X 平台、`@SynapseNetworkA`、单条 Post，并最多附带一张 Agent 生成的图片。
3. `social_accounts` 保存账号投影和 Secret Manager 引用；不保存账号密码，不把 secret 返回前端。
4. `social_post_drafts` 保存 Agent / operator 草稿、审核状态、标题、最终正文、风险检查、X post id 和失败摘要；`让 Agent 写草稿` 入口只要求 operator 输入目标 / prompt，系统生成 policy-checked 标题、正文和可选图片决策。policy 通过且 media ready 时可由人类点击发布；policy 阻断或图片失败时必须改写、重新生成图片或移除图片，系统不会直接发布。
5. `social_post_media_assets` 保存单张图片资产：`media_type=image`、生成 prompt、alt text、预览 URL、本地 runtime 路径、X media id 和失败摘要。
6. `social_publish_events` 保存草稿生成、图片生成、图片上传、编辑、拒绝、发布请求、发布成功/失败事件；`/publishing` 草稿列表必须显示草稿 ID，详情居中 Modal 通过 `GET /api/social/posts/{id}` 展示草稿内容、媒体资产、事件 timeline、外部发布结果和 bounded debug metadata。
7. 未批准草稿不能调用 `publish-x`；发布成功后写入 `external_post_id` 和 `published_at`。
8. X 发布失败会进入 `failed` 并展示 bounded root cause；不会自动重试刷屏。
9. 有图片时 `publish-x` 必须先上传 X media，拿到 `media_id` 后再创建 Post；media upload 失败不得降级成纯文字发布。
10. GCP Secret Manager 只保存 X OAuth2 长期凭据：client id、client secret、refresh token；`access_token` 通过 refresh flow 在发布请求内存中短暂生成，不入库、不写日志、不进入事件 payload。token、Authorization header 和 raw API payload 不进入默认 UI、日志或事件 payload。
11. 社媒文案生成使用专用 `SOCIAL_CONTENT_LLM_PROVIDER` / `SOCIAL_CONTENT_LLM_MODEL` 配置，默认 `codex / gpt-5-codex`，并提供 `SOCIAL_CONTENT_LLM_FALLBACK_MODEL` 处理本地 Codex CLI/账号兼容性；生成时只给 Codex bounded X brand/operator prompt，避免复用 Planner/workflow runtime 产生验收矩阵或工程计划 JSON。
12. 图片生成使用 `SOCIAL_IMAGE_PROVIDER=openai_images` / `SOCIAL_IMAGE_MODEL=gpt-image-1.5`，由后端 OpenAI Images provider 生成 runtime 预览资产；Codex 内置 image_gen 只适合人工预览，不作为生产后端能力。
13. 生成上下文默认注入 `.agents/product-marketing-context.md` 和 `.agents/skills/social-content/SKILL.md`；staging / launch / product update 类 prompt 额外注入 bounded `launch-strategy` guidance。`ad-creative`、`paid-ads`、`community-marketing`、视频、GIF、多图和 thread 不进入 v1 默认链路。
14. Social Publishing 不做应用层 280 字符硬限制；policy 和 UI 只展示字符数，真实平台限制由 X API 在发布时返回 root cause。
15. 默认生成 X Premium 风格完整运营内容，不再主动优化为旧 280 字符短帖；短帖只在 operator 明确要求或材料不足时生成。
16. Playwright E2E 包含真实 Codex 生成路径：不 mock `/api/social/posts/generate-draft`，验证标题/正文非空、正文不复制 prompt、不泄露 `/Users/` 或内部指令、policy passed，并且不点击真实 `publish-x`；图片生成 E2E 默认 mock，避免 CI 外部配额不稳定。
17. `/publishing` 使用 Modal-only 交互：让 Agent 写草稿、编辑草稿和发布确认都必须是居中 Modal / Dialog，禁止 Drawer、Slide-out、Offcanvas、Side Panel 或右侧滑出面板。
18. Social Publishing UI 必须参考 vendored `ui-ux-pro-max` SaaS / Ops Console 设计约束，保持深色 cockpit、清晰状态 badge、低噪声操作和可读表单。
19. `/publishing` 已升级为 Social Ops Center：默认按 `Campaign Goal -> Content Ideas -> Draft Queue -> Risk Gate -> Human Review -> Publish/Reply/Repost -> Observe Metrics` 展示运营链路。
20. 新增运营对象投影：`social_campaign_goals`、`social_trend_items`、`social_watchlist_accounts`、`social_reply_items`、`social_repost_candidates`、`social_post_metrics`。这些对象默认只读或 draft-only，不会自动对 X 产生公开动作。
21. `/publishing` 分面包括 `今日队列`、`趋势雷达`、`回帖处理`、`转发候选`、`已发布效果`、`品牌规则`。趋势采集、watchlist、回复草稿、引用转发候选和 metrics 只辅助 operator 决策；发布、回复、引用转发、删除仍必须 Human Gate。
22. X 专属 recurring workflows 使用平台前缀命名：`x_social_daily_content_planner`、`x_social_trend_radar_sweep`、`x_social_repost_candidate_sweep`、`x_social_reply_candidate_sweep`。公共数据表仍保持 `social_*`，为后续 LinkedIn / Discord / site content 扩展保留平台字段。
23. X Social Sweep Scheduler 真实自动触发 `x_social_*` workflows；`x_social_daily_content_planner` 每小时 tick，但按 `OPS_OPERATOR_TIMEZONE` 的自然日幂等：同一 X 账号每天最多生成 1 条 `source_type=daily_planner` 草稿；已生成则返回 `already_created=true`，不会制造重复草稿。生成结果必须进入 `needs_review`，不得自动发布。
24. `x_social_trend_radar_sweep`、`x_social_repost_candidate_sweep` 和 `x_social_reply_candidate_sweep` 只读/草稿化运行：趋势雷达只保留高相关度素材，转发候选只生成 quote 文案和 candidate row，回帖 sweep 每 30 分钟最多调用真实 `social_reply_agent_v1` 生成 1 条 `needs_review` 回复草稿，不调用 X repost / quote / reply / publish API；Agent 失败时 fail closed，不使用模板 fallback。
25. X 趋势雷达 v1 的真实数据入口是 Watchlist timeline，而不是全网搜索：`social_watchlist_accounts -> GET /2/users/by/username/:username -> GET /2/users/:id/tweets -> social_trend_items`。每个 watchlist account 通过 `last_checked_at` 做 1 小时级节流；X rate limit / auth failure 只能写 diagnostic，不得强制重试或伪造真实趋势。
26. `social_trend_items.source_url` 是 X 来源真相边界。带 `https://x.com/.../status/...` 的趋势可以进入 `x_social_repost_candidate_sweep`；本地趋势种子或缺少 source URL 的素材只能作为内容灵感，UI 必须禁用转发/引用发布。
27. `/publishing/trends` 是 `x_social_trend_radar_sweep` 结果检索页。它只读展示 `social_trend_items`，支持 operator-local 日期范围、关键字、来源类型和作者筛选，列表分页，点击行后用居中 Modal 查看完整来源、摘要、采集时间和 `source_kind`。
28. 趋势详情页继续遵守 Modal-only + `ui-ux-pro-max` SaaS/Ops 约束：真实 X 来源展示 `打开 X 原帖`，本地趋势种子明确标注“仅作内容灵感，不能引用转发”，不提供任何自动互动动作。
29. `x_social_repost_candidate_sweep` 生成的 `suggested_quote` 必须增加 Synapse 视角或额外观点，不得只是 `Great point` / `Interesting` 这类无价值附和。
30. `social_reply_items` 是回帖增长的人审队列：来源必须是带 `source_url` 的真实 X 候选，`social_reply_agent_v1` 必须逐条生成正向、相关、有额外观点的 `suggested_reply`；`回复到 X` 必须由 operator 在居中 Modal 确认后才调用 X API。

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
2. 深色 cockpit AppShell 使用 Top Header Navigation，不再使用桌面左侧 sidebar。主导航只保留 `Command Center`、`Planning`、`Publishing`、`Releases` 四个高频业务入口。
3. 顶栏右侧保留 `Needs Human` badge、`Cmd+K / Search` 低频入口和 `Alerts` 通知入口；`/gates`、`/requirements`、`/workflows`、`/schedules`、`/projects`、`/errors` 等路由继续存在，但不占用主导航。
4. `/gates` 集中展示 pending human gates、failed / blocked workflow。
5. `/factory/workflows` 只读展示 workflow definitions、states、transitions、limits、risk policy。
6. `/factory/atoms` 从 workflow definitions 反推 agent / deterministic / terminal atom registry。
7. `/intake` 作为需求发现入口，连接 errors、planner、forum feedback 和 watcher events。
8. `/knowledge` 作为 artifacts / SOP Ledger 的一等入口。
9. `/system/notifications` 展示 notification dispatcher、queue、dead letter、open fingerprint 概览。
10. Figma / Stitch 原型视觉方向已记录在 `frontend-control-plane-figma-implementation.md`。
11. Factory pages v1 只读，不开放在线 YAML 编辑。
