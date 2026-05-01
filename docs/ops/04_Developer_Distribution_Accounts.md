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

