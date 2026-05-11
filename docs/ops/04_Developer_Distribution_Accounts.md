---
id: developer-distribution-accounts
title: Developer Distribution Account Registry
role: growth_lead
status: ready
created_at: 2026-05-01
updated_at: 2026-05-01
author: operator
target_repo: Synapse-Network-Growing
---

# Developer Distribution Account Registry

本文记录 Synapse Network 用于精准分发硬核技术文章、上线复盘和 demo 的开发者社区账号清单。它是账号注册与渠道治理文档，不代表系统可以自动发帖。

所有对外代表 Synapse Network 的发布、评论、转发、提交 Product Hunt 或社区互动，都必须由 operator 人工确认。Agent 可以生成草稿、标题、摘要和评论建议，但不能绕过 Human Gate。

## 1. Account Governance

1. 优先使用 `growth@synapse-network.ai` 或等价官方邮箱注册官方账号。
2. Hacker News、Reddit、V2EX 这类社区优先使用 founder / operator 个人账号建立信任；官方账号用于公告和品牌一致性。
3. 所有账号启用 2FA。恢复码进入 password manager，不写入 repo、日志、artifact、截图或 Lark 消息。
4. 账号状态、profile URL、2FA 状态和备注可以回填到本文的渠道记录表；后续如需要系统化管理，再新增 `social_distribution_accounts` 数据表。
5. P0 平台立即注册并开始养号；P1 平台注册并准备内容；P2 平台作为后续 editorial / launch 渠道。

## 2. Channel Registry

| Priority | Platform | Official / Signup URL | Suggested account shape | Best content | Notes |
|---|---|---|---|---|---|
| P0 | Hacker News | [login](https://news.ycombinator.com/login), [submit](https://news.ycombinator.com/submit) | Founder/operator personal account first | Show HN, hard technical articles, demos, open-source tools | Avoid marketing tone. Use restrained titles and proof-first posts. |
| P0 | Reddit | [register](https://www.reddit.com/register/) | Official account plus founder/operator personal account | Long-form discussion, technical explanations, demos | Warm up the account with useful comments before posting links. |
| P0 | Reddit r/LocalLLaMA | [r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/) | Same Reddit account | Local agents, agent tooling, MCP, cost control | Post only when the article is clearly relevant to local/open-source agent builders. |
| P0 | Reddit r/OpenAI | [r/OpenAI](https://www.reddit.com/r/OpenAI/) | Same Reddit account | OpenAI Agents, tool calling, agent payment / permission boundaries | Prefer experience reports and architecture writeups over direct promotion. |
| P0 | Reddit r/java | [r/java](https://www.reddit.com/r/java/) | Same Reddit account | Java SDK, MCP server, provider runtime | Publish only when there is a real Java artifact or technical proof. |
| P0 | V2EX | [signup](https://www.v2ex.com/signup) | Founder/operator personal account first | Chinese technical discussion, launch retrospectives, architecture notes | New accounts may require invitation or activation conditions. |
| P0 | V2EX 程序员 | [programmer](https://www.v2ex.com/go/programmer) | Same V2EX account | Engineering retrospectives, agent development, toolchain articles | Do not paste obvious AI-generated replies; contribute like a real builder. |
| P0 | V2EX OpenAI | [openai](https://www.v2ex.com/go/openai) | Same V2EX account | OpenAI / Codex / Agent content | High relevance for Chinese AI tooling discussions. |
| P0 | V2EX Java | [java](https://www.v2ex.com/go/java) | Same V2EX account | Java SDK / MCP server articles | Wait until Java-facing artifacts are stable. |
| P1 | DEV Community | [dev.to](https://dev.to/), [enter](https://dev.to/enter) | Official author or organization account | Technical blogs, tutorials, SDK quickstarts | Useful as an English long-form distribution surface. |
| P1 | Hashnode | [hashnode.com](https://hashnode.com/), [docs](https://docs.hashnode.com/) | Official blog / team blog | Developer blog, tutorials, architecture articles | Good for SEO-friendly owned-community publishing and custom domains. |
| P1 | HackerNoon | [publish](https://hackernoon.com/p/publish), [writing guide](https://help.hackernoon.com/your-complete-guide-to-writing-for-hacker-noon) | Official author account | Deep technical articles, AI infrastructure, agent economy essays | Editorial process makes it better for polished long-form content. |
| P1 | Medium | [medium.com](https://medium.com/), [new story](https://medium.com/new-story) | Official author account | Thought pieces, launch retrospectives | Do not make Medium the only source of truth for content. |
| P1 | Product Hunt | [producthunt.com](https://www.producthunt.com/), [posting guide](https://help.producthunt.com/en/articles/479557-how-to-post-a-product) | Founder plus official product account | Public preview / launch day | Launch channel, not a daily article distribution platform. |
| P2 | DZone | [dzone.com](https://dzone.com/), [contribute](https://dzone.com/pages/contribute) | Author account | Java, API, developer tooling deep dives | Editorial review; useful when articles are mature. |
| P2 | InfoQ | [contribute](https://www.infoq.com/contribute/) | Author account | Architecture, engineering practice, innovation | High bar; use for later credibility and brand proof. |
| P2 | freeCodeCamp News | [news](https://www.freecodecamp.org/news/) | Author application | Tutorial articles, SDK quickstarts | Good fit for 5-minute quickstart and developer education. |
| P2 | Lobsters | [lobste.rs](https://lobste.rs/) | Invite-only personal account | High-quality technical discussion | Invite-only; pursue through real community relationships. |

## 3. Distribution Rules

1. **HN / Reddit / V2EX:** contribute first, link later. Post only when the article has standalone technical value.
2. **DEV / Hashnode / HackerNoon:** publish canonical or near-canonical long-form articles, then cross-link to docs, GitHub, and staging.
3. **Product Hunt:** reserve for public preview or major launch moments; prepare assets and community support before launch day.
4. **DZone / InfoQ / freeCodeCamp:** use for polished tutorials and architecture stories after the implementation is stable.
5. **Lobsters:** do not treat as a growth hack. Only submit genuinely technical, non-marketing content if an invite is available.

## 4. Content Fit Matrix

| Content type | Primary channels | Secondary channels | Notes |
|---|---|---|---|
| Show HN / demo launch | Hacker News, Product Hunt | Reddit, X | Must include working demo, source, or clear technical proof. |
| SDK quickstart | DEV, Hashnode, freeCodeCamp | Reddit r/OpenAI, V2EX 程序员 | Best as a step-by-step tutorial with runnable code. |
| MCP server / Java article | Reddit r/java, V2EX Java, DZone | DEV, Hashnode | Only post when Java/MCP details are real and tested. |
| Agent payment rails explainer | HackerNoon, Hashnode, DEV | HN, Reddit r/OpenAI | Lead with the problem, not the product. |
| Build-in-public / launch retrospective | V2EX, Medium, Hashnode | Reddit, X | Keep it honest: what worked, what failed, what changed. |

## 5. Publishing Safety Boundary

1. Agent may draft titles, summaries, article variants, comments, and distribution checklists.
2. Agent may recommend where to post based on content fit and community rules.
3. Agent may not create accounts, bypass CAPTCHA, scrape private pages, post publicly, comment, vote, upvote, or submit Product Hunt without explicit operator action.
4. All external posting actions are representational communication and require Human Gate.
5. If a platform blocks a post, rate limits an account, or flags content as spam, record the root cause and pause that channel instead of retrying automatically.

## 6. Channel Account Tracking

| Platform | Account status | Email | 2FA | Profile URL | Read automation | Human publish | Notes |
|---|---|---|---|---|---|---|---|
| Hacker News | not_registered | growth@synapse-network.ai | pending | - | manual_only | required | Founder/operator account preferred. |
| Reddit | not_registered | growth@synapse-network.ai | pending | - | allowed_public_only | required | Warm up before posting links. |
| V2EX | not_registered | growth@synapse-network.ai | pending | - | allowed_public_only | required | May require invite/activation. |
| DEV Community | not_registered | growth@synapse-network.ai | pending | - | allowed_public_only | required | Consider organization profile. |
| Hashnode | not_registered | growth@synapse-network.ai | pending | - | allowed_public_only | required | Candidate for official blog mirror. |
| HackerNoon | not_registered | growth@synapse-network.ai | pending | - | manual_only | required | Editorial workflow. |
| Medium | not_registered | growth@synapse-network.ai | pending | - | allowed_public_only | required | Use as secondary syndication. |
| Product Hunt | not_registered | growth@synapse-network.ai | pending | - | manual_only | required | Launch-only. |
| DZone | not_registered | growth@synapse-network.ai | pending | - | manual_only | required | Mature technical articles. |
| InfoQ | not_registered | growth@synapse-network.ai | pending | - | manual_only | required | High-bar architecture pieces. |
| freeCodeCamp News | not_registered | growth@synapse-network.ai | pending | - | manual_only | required | Author application may be required. |
| Lobsters | invite_needed | personal/operator | pending | - | manual_only | required | Invite-only. |

## 7. `/publishing` Distribution Center Workflow

`/publishing` 现在把 X 官方账号运营和开发者社区分发放在同一个 Social Ops 工作台里，但只有新的 asset/task 表是主流程 Source of Truth。

1. `Tasks` Tab 默认展示简化的 Symphony / Linear 风格内容任务看板：一张卡代表一篇 `social_content_assets` 源内容，列为 `待计划 / 待审核 / 待发布 / 已发布 / 异常`，列位置由 `/api/social/distribution/board` 后端投影决定，不支持拖拽改状态。
2. `Assets` Tab 管理 `social_content_assets`：一篇文章、demo、Show HN、launch asset、X post、reply 或 quote 的源标题、正文、摘要、canonical URL 和 goal lineage。
3. `Settings` Tab 管理 `social_distribution_accounts`：平台、频道、注册入口、profile URL、账号状态、2FA 状态、备注、是否允许 read-only 自动化、是否必须人工发布。
4. `Signals & Metrics` Tab 只读展示趋势、watchlist 和已发布效果；页面浏览不触发外部平台 read。
5. `创建内容任务` 会创建 `social_content_assets(source_type=manual_task)`，并写入 `social_distribution_documents(document_kind=source_plan)`，让“源任务 -> 实现计划 -> 平台文档”成为一等流程。v1 默认采用计划审核优先：创建后自动生成方案，operator 审核后点击 `审核通过，生成平台文档`。
6. `运行 Asset Planner` 会执行 `social_asset_planner_sweep`：每次只选择一种核心信号类型（`shipping_proof`、`developer_education`、`market_commentary`、`launch_asset`），最多采样 5 条 public-safe signals，并且每天最多保持 3 个 active Assets。没有足够信号时返回 `no_asset_created=true`，不生成空洞内容。
7. Asset Planner 只创建 `status=proposed` 的源资产，不自动生成平台 task，也不自动公开发布。
8. Operator 审核 Asset / 内容任务方案后点击生成按钮。后端先把 Asset 标记为 `approved`，再按固定平台顺序串行生成 `social_distribution_tasks` 和对应 `social_distribution_documents(document_kind=platform_draft)`。某个平台生成失败只标记该 task failed，不回滚已经成功的平台。
9. 生成完成后，前端会在当前 Asset 卡片 / 详情 Modal 中展开已生成 Platform Tasks，operator 不需要跳转到 `Tasks` Tab 刷新才能看到结果。
10. Operator 在外部平台人工登录、粘贴、发布；完成后回到系统手动 `标记已发布` 并填写 `published_url`。系统会同步把对应 platform document 标为 `published`。
11. 如果帖子被管理员删除、shadowban、不可见或链接失效，operator 手动 `标记 removed` 并填写原因；v1 不自动探活，避免误判和额外平台请求。`removed` 在简化看板中进入 `异常`，但不会自动重发。
12. 旧 X 主流程表只允许通过一次性迁移脚本转换为 `social_content_assets + social_distribution_tasks + social_distribution_events`；迁移后不做双写同步。

这不是自动发布器。它是一个减少复制粘贴疲劳、统一记录发布状态的 Human-Gated Distribution Center。

## 7.1 Agent Content Pack Contracts

高质量教程和工作流文章不能由通用模板生成。Agent Content Pack 有两条硬约束：

1. Agent structured output 只接受严格 JSON。后端允许剥离外层 Markdown code fence 和 `json` 标识，也允许从少量解释文字中提取第一段完整 JSON object；如果仍无法解析，事件记录 `agent_json_parse_failed`，不创建假 Asset。
2. P0 source context 必须来自带标签的白名单文件，不做全库 RAG。标签是跨仓库内容生成契约，不是普通注释。

当前 P0 tags：

| Ref key | Required tag | Purpose |
|---|---|---|
| `synapse-network-sdk:quickstart` | `@synapse-context:quickstart` | SDK quickstart / tutorial factual source. |
| `synapse-network-mcp-server:spring_boot_mcp` | `@synapse-context:spring_boot_mcp` | Spring Boot MCP tutorial source. |
| `synapse-network-provider:onboarding` | `@synapse-context:onboarding` | Provider onboarding article source. |

目标仓库应在 CI 或 pre-commit 中保护这些标签，例如：

```bash
rg "@synapse-context:quickstart" README.md docs python typescript java
rg "@synapse-context:spring_boot_mcp" README.md docs src examples
rg "@synapse-context:onboarding" README.md docs scripts server
```

Growing 侧可运行：

```bash
PYTHONPATH=. python scripts/ci/check_synapse_context_tags.py
```

## 8. Canonical URL Rules

DEV 和 Hashnode 对镜像文章提供 Canonical URL 设置。为了避免重复内容影响 SEO：

1. `canonical_url` 应优先指向 Synapse 官方站、官方 docs、官方 blog 或 GitHub canonical article。
2. 生成 DEV / Hashnode target 时，operator checklist 必须包含：

```text
粘贴提示：请务必在平台设置的 Canonical URL 字段填写 {canonical_url}，避免重复内容影响 SEO。
```

3. 如果 asset 缺少 `canonical_url`，系统会给 DEV / Hashnode task metadata 写入 `canonical_url_missing`，UI 必须明确提示“不建议发布到 DEV/Hashnode”。
4. HN、Reddit、V2EX 可以链接 canonical article，但不要求平台级 canonical 设置。

## 9. Distribution Task Statuses

| Status | Meaning | Who sets it |
|---|---|---|
| `planned` | Task 已计划但未生成平台草稿 | System / operator |
| `draft_ready` | 平台标题、正文和 checklist 已生成 | System |
| `needs_review` | X 或敏感平台草稿等待 Human Gate | System |
| `approved` | Operator 已审核平台草稿，等待提交 | Operator |
| `submitted` | Operator 已提交但还没有确认公开链接 | Operator |
| `live` | Operator 已回填公开 `published_url` | Operator |
| `removed` | 帖子被删、不可见、shadowban 或链接失效 | Operator |
| `rejected` | Operator 判断不适合该平台 | Operator |
| `skipped` | 本轮跳过该 target | Operator |
| `failed` | 生成或记录流程失败 | System / operator |

`removed` 是手动事实记录，不触发自动重发。社区平台信任比数量更重要。
