---
id: launch_plan_v1
title: Synapse Network Launch Strategy — Full Playbook
role: launch_strategist
status: draft
created_at: 2026-04-08
updated_at: 2026-04-08
author: AI-LaunchStrategist
---

# Synapse Network 发布策略 (Launch Strategy)

> **Product:** Synapse Network — The Settlement Layer for AI Agents
> **Stage:** MVP Complete → Ready for Public Launch
> **Model:** Two-sided marketplace (API Providers ↔ Agent Developers)
> **Goal:** Maximum Day-1 signups + sustained flywheel momentum

---

## 一、发布阶段总览 (Five-Phase Timeline)

```
Week -2 ~ -1     Week 0          Week 0           Week 1~2         Week 3+
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ Phase 1  │──▶│ Phase 2  │──▶│ Phase 3  │──▶│ Phase 4  │──▶│ Phase 5  │
│ Internal │   │  Alpha   │   │  Beta    │   │  Early   │   │  Full    │
│  Launch  │   │  Launch  │   │  Launch  │   │  Access  │   │  Launch  │
│          │   │          │   │          │   │          │   │          │
│·Dog-food │   │·Landing  │   │·Waitlist │   │·PH / HN  │   │·Self-    │
│ SDK+Gate │   │ page live│   │ open     │   │ /X launch│   │ serve    │
│·Fix criti│   │·Invite   │   │·Sow buzz │   │·Provider │   │·Scale    │
│ cal bugs │   │ 10 devs  │   │·Influencer│   │ cold out │   │·Referral │
│·Tracking │   │·Feedback │   │ seeding  │   │·reach    │   │ program  │
│ infra    │   │ loop     │   │          │   │          │   │          │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
   T-14d          T-7d           T-3d           T+0~14d         T+14d+
```

---

## 二、Phase 1: Internal Launch（T-14 天）

**目标：** 验证核心功能可用、埋点就绪、团队对产品足够自信。

### 2.1 产品就绪检查表

| # | 检查项 | 负责 | 状态 |
|---|--------|------|------|
| 1 | Gateway 结算幂等性验证（重复调用不双扣） | CTO | [ ] |
| 2 | SDK `pip install synapse-sdk` 三行代码跑通 Demo | DevRel | [ ] |
| 3 | Provider 服务注册 → 接收第一笔 Agent 调用 → 收款 全链路 | CTO | [ ] |
| 4 | 钱包创建 → 充值 USDC → 余额显示 → 调用扣款 → 余额更新 | CTO | [ ] |
| 5 | 风控：Agent 死循环时，budget 耗尽后自动阻断 | CTO | [ ] |
| 6 | 全链路 analytics 埋点就绪（注册、钱包创建、首充、首调） | CRO Optimizer | [ ] |
| 7 | 错误页面 & 限流提示 UX 可接受 | CTO | [ ] |

### 2.2 Dog-food 测试

你（CEO）亲自用 SDK 完成一次完整任务：
```python
from synapse_sdk import AgentWallet

wallet = AgentWallet.connect(budget=5.0)
# Agent 使用 wallet.mcp_tool 调用外部 API
# 验证扣款、余额、审计日志全部正确
```

记录所有卡壳点。每个卡壳点 = 上线前必须修复的 DX 问题。

---

## 三、Phase 2: Alpha Launch（T-7 天）

**目标：** 10 个外部开发者验证产品，收集真实反馈。

### 3.1 Landing Page 上线

**URL:** synapse.network（或临时域名）

**页面结构（交由 Content Writer + CRO Optimizer 协作）：**

```
Hero Section:
  Headline: "Give your AI agent a $5 budget. Let it buy any API it needs."
  Sub: "3 lines of code. Zero gas. Zero API key management."
  CTA: [Get Early Access] → Email 捕获

How It Works (3 步):
  1. Install SDK → pip install synapse-sdk
  2. Set Budget → wallet = AgentWallet.connect(budget=5.0)
  3. Let Agent Run → Agent discovers + pays for APIs autonomously

Social Proof (placeholder):
  "Built by engineers who got tired of API key nightmares."

Footer CTA:
  [For API Providers: List your API →] 
```

### 3.2 Alpha 邀请名单

**手动邀请 10 人：**
- 3 × Agent 框架开发者（LangChain / CrewAI / AutoGen 生态）
- 3 × 拥有独特 API 的 Provider 候选人
- 2 × Web3 开发者（已有 USDC 钱包经验）
- 2 × Tech Twitter 有影响力的开发者 KOL

**邀请方式：** 私信 / 邮件，1-on-1 onboarding call（15 分钟）附赠 10 USDC 测试额度。

### 3.3 反馈收集模板

每位 Alpha 用户完成体验后填写：
1. 从注册到第一次成功 API 调用用了多久？（目标 < 5 分钟）
2. 哪一步最让你困惑？
3. 你会推荐给同事吗？为什么？
4. 你最希望我们接下来做什么？

---

## 四、Phase 3: Beta Launch（T-3 天）

**目标：** 扩大等候名单、制造发布前的期待感。

### 4.1 Waitlist 开放

在 Landing Page 添加 waitlist 功能。推荐用 Tally / Typeform 极简表单：
- Email
- "你主要是 Agent Developer 还是 API Provider？"（单选）
- "你用什么 Agent 框架？"（可选多选）

### 4.2 Pre-Launch 造势内容（T-5 到 T-1）

| 天数 | 渠道 | 内容 | 负责 Agent |
|------|------|------|-----------|
| T-5 | X/Twitter | "Building something for AI agents that can actually pay for things. Shipping next week." + GIF 预览 | Growth Lead |
| T-4 | X/Twitter | Thread: "The API key nightmare: Why AI agents need their own wallets" (教育性长推) | Growth Lead |
| T-3 | Dev Blog | 技术博客: "How to let AI agents discover and pay for APIs" | DevRel |
| T-2 | X/Twitter | "Sneak peek: Watch an AI agent discover an API, negotiate price, and pay $0.03 — in real-time." + 30s screencast | DevRel |
| T-1 | Email to waitlist | "Tomorrow we launch. Here's what's coming." | Content Writer |

### 4.3 Influencer / KOL 种子

**在 T-5 前完成：**
- 精选 5-10 位 AI/Agent 领域 KOL（Twitter > 5K followers）
- 发送私信提供抢先体验 + 赠送 25 USDC 测试额度
- 不要求强制发帖，只要求"如果你觉得有趣，随意分享"
- 重点目标：LangChain / CrewAI / AutoGen 核心贡献者

---

## 五、Phase 4: Early Access Launch（T+0，发布日）

**目标：** PH + HN + X 三平台联动，单日最大化曝光。

### 5.1 发布日时间表（UTC-7 太平洋时间 / UTC+8 北京时间）

```
┌─────────────────────────────────────────────────────────┐
│ 发布日时间线 (Launch Day Timeline)                        │
├────────────┬────────────────────────────────────────────┤
│ 00:01 PST  │ Product Hunt listing 自动上线              │
│ (16:01 CST)│ → 首条 Maker Comment 立即发布              │
│            │                                            │
│ 06:00 PST  │ Twitter/X Launch Thread 发布               │
│ (22:00 CST)│ → 10 条推文 Thread + Demo GIF              │
│            │ → Pin to profile                           │
│            │                                            │
│ 08:00 PST  │ Hacker News "Show HN" 发布                 │
│ (00:00+1   │ → 使用已准备好的 HN 文案                    │
│  CST)      │ → CEO 亲自回复每一条评论                    │
│            │                                            │
│ 09:00 PST  │ 邮件群发 waitlist 用户                     │
│ (01:00+1   │ → Subject: "We're live. Get your agent     │
│  CST)      │   a wallet."                               │
│            │                                            │
│ 10:00 PST  │ LinkedIn 发布面向 Provider 端的公告         │
│ (02:00+1   │                                            │
│  CST)      │                                            │
│            │                                            │
│ All Day    │ CEO 全天在线回复 PH/HN/X 评论               │
│            │ → 每条评论 < 15 分钟内回复                   │
│            │ → 回复中始终包含产品链接                     │
└────────────┴────────────────────────────────────────────┘
```

### 5.2 发布日资产清单（依赖其他 Agent 预先完成）

| 资产 | 负责 | 交付路径 | 前置状态要求 |
|------|------|----------|-------------|
| PH Listing (tagline + description + images) | Growth Lead | `roles/growth_lead/go_to_market/ph_copy.md` | `status: ready` ✅ 已有 |
| HN Show HN 文案 | Growth Lead | `roles/growth_lead/go_to_market/launch_copy_v1.md` | `status: ready` ✅ 已有 |
| X Launch Thread | Growth Lead | `roles/growth_lead/go_to_market/x_thread.md` | 需要生成 |
| Homepage 文案 | Content Writer | `roles/content_writer/outputs/homepage-copy.md` | 需要生成 |
| Waitlist → Launch 邮件 | Content Writer | `roles/content_writer/outputs/launch-email.md` | 需要生成 |
| Demo GIF / Screencast (30s) | DevRel | `demos/synapse-agent-demo/` | 需要录制 |
| 埋点方案确认 | CRO Optimizer | `roles/cro_optimizer/outputs/tracking-plan.md` | 需要生成 |

### 5.3 Product Hunt 优化要点

- **发布日选择：** 周二或周三（竞争相对适中，避开周末低流量）
- **Tagline:** "Stripe for AI Agents. Let your agents pay for APIs natively."
- **Maker's Comment:** 必须在上线后 5 分钟内发出（见已有文案）
- **视觉资产：** 至少 4 张截图 + 1 个 30s Demo Video
- **全天互动：** 每条评论在 15 分钟内回复（CEO 亲自）
- **引流：** 每条回复结尾附上注册链接 "→ Try it free: synapse.network"

### 5.4 Hacker News 策略

- **不能的：** 不要求人投票、不发"请支持"的私信、不在其他帖子留广告
- **必须的：** CEO 亲自发帖（Show HN:）、以工程师身份深入讨论技术细节
- **关键回复策略：**
  - 被问"为什么用 crypto？" → 回答微支付的经济性，$0.01 交易在 Stripe 上不可能
  - 被问"和 RapidAPI 区别？" → 回答 agent-native vs human-native，MCP 自动发现
  - 被问"安全性？" → 回答 budget isolation + 链上最终结算 + 审计追溯
  - 被挑战"过度设计" → 承认简单场景可以直接 API key，但阐明预算控制和多 API 场景

---

## 六、Phase 5: Full Launch + Post-Launch（T+7 到 T+30）

### 6.1 供给侧引爆：Provider 冷触达（T+3 开始）

**目标：** 上线首月至少 20 个 Provider 注册列出有价值 API。

**冷触达路径（交由 Content Writer 执行 `cold-email` skill）：**

| 批次 | 目标 Provider 类型 | 数量 | 邮件主题方向 |
|------|-------------------|------|-------------|
| 1 | Web3 数据 API（链上分析、实时Gas、Token价格） | 10 | "Your API + AI Agents = passive USDC income" |
| 2 | AI 模型推理 API（RAG、Embedding、特定领域LLM） | 10 | "AI agents want to buy your model inference — here's how" |
| 3 | 自动化 / RPA API（浏览器自动化、数据抓取） | 10 | "Sell your automation API to autonomous agents" |
| 4 | 金融数据 API（情感分析、另类数据） | 10 | "AI hedge fund agents need your data. Set your price." |

### 6.2 需求侧增长：Developer 曝光续航

| 时间 | 动作 | 渠道 |
|------|------|------|
| T+3 | 发布 "Week 1 metrics" 透明度推文(注册数、调用量) | X |
| T+5 | 技术博客: "Building an autonomous stock analyst agent with Synapse" | Dev Blog + HN |
| T+7 | 在 LangChain / CrewAI Discord 发教程 | Community |
| T+10 | 发布 "Top 10 APIs on Synapse this week" 排行榜 | X + Blog |
| T+14 | 第二篇技术博客: "MCP + Micropayments: The missing infrastructure" | Dev Blog + HN |
| T+21 | 在 AI Meetup / Twitter Space 做 15 分钟技术分享 | Borrowed Channel |
| T+30 | 发布月度透明度报告（GMV、Provider 数、Agent 调用量） | Blog + Email |

### 6.3 推荐裂变计划（T+14 开始）

**机制：双向激励 (Double-sided Referral)**

```
┌──────────────────────────────────────────────────────┐
│                 Synapse Referral Loop                 │
├──────────────────────────────────────────────────────┤
│                                                      │
│  推荐人 (Referrer)          被推荐人 (Invitee)       │
│  ┌─────────────┐            ┌─────────────┐         │
│  │ 获得 2 USDC  │            │ 获得 3 USDC  │         │
│  │ 奖励到钱包   │◀──────────▶│ 首充额度    │         │
│  └─────────────┘            └─────────────┘         │
│                                                      │
│  触发条件: 被推荐人完成首次 API 调用                   │
│  每人最多推荐 50 人 (cap: 100 USDC / 推荐人)          │
│                                                      │
│  Provider 推荐加成:                                   │
│  推荐 Provider 注册 → 额外 5 USDC                     │
│  (因为 Provider 供给 > Consumer 供给 的战略重要性)      │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**单位经济学：**
- 获客成本 (CAC): 5 USDC (推荐人 2 + 被推荐人 3)
- 预期 LTV: Agent Developer 月交易额 $50 × 5% take = $2.50/月 → 2 个月回本
- Provider 推荐 CAC: 7 USDC，但 Provider 带来多个 Consumer，回本更快

---

## 七、定价策略确认

### 7.1 发布前锁定，发布后不变

| 角色 | 费用 |
|------|------|
| Agent Developer (Consumer) | 免费注册 + 免费创建钱包。仅按 API 调用付费（Provider 定价）。 |
| API Provider | 免费注册 + 免费列出服务。Synapse 从每笔交易中抽取 ~5% 网络通道费。 |
| 首充优惠 | 新用户首充 10 USDC，赠送 2 USDC（20% bonus），限首月。 |

### 7.2 为什么这个定价有效

1. **Developer 端零门槛** — 没有月费、没有最低消费，和 Stripe "免费开始" 一样的增长引擎。
2. **Provider 端零风险** — 不收上架费，只从成功交易中分成。Provider 不赚钱 = Synapse 不赚钱。
3. **5% 合理性** — 远低于传统支付（Stripe 2.9% + $0.30 在微支付时等效 > 30%），对 Provider 无感。

---

## 八、关键指标追踪 (North Star Metrics)

### 发布日 (Day 1)

| 指标 | 目标 | 追踪方式 |
|------|------|---------|
| 注册用户数 | ≥ 200 | Analytics |
| 钱包创建率 | ≥ 50% of signups | Internal DB |
| PH Upvotes | ≥ 300 | Product Hunt |
| HN Points | ≥ 100 | Hacker News |
| X Thread Impressions | ≥ 50K | Twitter Analytics |

### 第一周 (Week 1)

| 指标 | 目标 | 追踪方式 |
|------|------|---------|
| 累计注册 | ≥ 500 | Analytics |
| 首次 API 调用完成率 | ≥ 20% of wallets | Internal DB |
| Provider 注册 | ≥ 5 | Internal DB |
| SDK GitHub Stars | ≥ 50 | GitHub |

### 首月 (Month 1)

| 指标 | 目标 | 追踪方式 |
|------|------|---------|
| 累计注册 | ≥ 1,500 | Analytics |
| 月活 Agent Wallets | ≥ 200 | Internal DB |
| Provider 列出服务数 | ≥ 20 | Internal DB |
| 月 GMV (Gross Merchandise Volume) | ≥ $5,000 | Internal DB |
| NPS (from alpha/beta users) | ≥ 40 | Survey |

---

## 九、风险与应急预案

| 风险 | 概率 | 影响 | 预案 |
|------|------|------|------|
| Gateway 宕机（发布日流量超预期） | 中 | 高 | T-3 前完成压力测试；准备 "We're experiencing high demand" 公告模板 |
| PH 排名不理想（< Top 5） | 中 | 低 | HN 和 X 是主渠道，PH 是加分项不是生命线 |
| HN 被怀疑"为什么非要用 crypto" | 高 | 中 | 准备好微支付经济性的数据论证（$0.01 × Stripe = 亏本） |
| Provider 供给冷启动困难 | 高 | 高 | CEO 亲自 onboard 前 5 个 Provider；内部先搭 2-3 个有价值的 Demo API |
| SDK 安装 / 配置报错 | 中 | 高 | DevRel 发布日全天在 Discord/GitHub Issues 值班 |

---

## 十、依赖链与 Agent 协作地图

```
                    ┌─────────────────┐
                    │ Launch          │
                    │ Strategist      │
                    │ (本文档 = 总指挥) │
                    └────────┬────────┘
                             │
              需要以下 Agent 预先完成交付：
                             │
        ┌────────────┬───────┴───────┬────────────┐
        ▼            ▼               ▼            ▼
   ┌─────────┐ ┌──────────┐  ┌──────────┐ ┌──────────┐
   │Growth   │ │Content   │  │DevRel    │ │CRO       │
   │Lead     │ │Writer    │  │          │ │Optimizer │
   ├─────────┤ ├──────────┤  ├──────────┤ ├──────────┤
   │□ X      │ │□ Homepage│  │□ Demo    │ │□ Tracking│
   │  Thread │ │  Copy    │  │  GIF/    │ │  Plan    │
   │□ PH 资产 │ │□ Launch  │  │  Screen  │ │□ Signup  │
   │  优化    │ │  Email   │  │  cast    │ │  Flow    │
   │         │ │□ Provider│  │□ Blog    │ │  Design  │
   │         │ │  Cold    │  │  Post    │ │          │
   │         │ │  Emails  │  │          │ │          │
   └─────────┘ └──────────┘  └──────────┘ └──────────┘
```

### 交付优先级排序（阻塞关系）

```
Priority 1 (阻塞 Phase 2):
  → CRO Optimizer: 埋点方案
  → Content Writer: Homepage 文案

Priority 2 (阻塞 Phase 4 发布日):
  → Growth Lead: X Thread
  → Content Writer: Launch Email
  → DevRel: Demo Screencast

Priority 3 (Post-launch, 不阻塞发布):
  → Content Writer: Provider Cold Emails
  → SEO Strategist: SEO Audit
```

---

## 十一、立即可执行的下一步

你（CEO）现在应该按以下顺序调度 Agent 员工：

```
Step 1: [阻塞] CRO Optimizer → 生成埋点方案
  Prompt: "使用 analytics-tracking skill，为 Synapse Network 设计全链路埋点方案。
          覆盖：注册、钱包创建、首充、首次 API 调用、Provider 注册、Provider 首次被调用。
          产出到 roles/cro_optimizer/outputs/tracking-plan.md"

Step 2: [阻塞] Content Writer → 生成 Homepage 文案
  Prompt: "使用 copywriting skill，为 Synapse Network 编写首页文案。
          结构：Hero + How It Works + Value Props + Social Proof + CTA。
          产出到 roles/content_writer/outputs/homepage-copy.md"

Step 3: [并行] Growth Lead → 生成 X Launch Thread
  Prompt: "使用 social-content skill，为 Synapse Network 发布日编写 10 条推文 Thread。
          产出到 roles/growth_lead/go_to_market/x_thread.md"

Step 4: [并行] Content Writer → 生成 Launch Email
  Prompt: "使用 email-sequence skill，编写 waitlist → launch day 的发布邮件。
          产出到 roles/content_writer/outputs/launch-email.md"

Step 5: [并行] DevRel → 录制 Demo Screencast
  Prompt: "基于 demos/synapse-agent-demo/，录制 30s Demo GIF/视频。
          展示 pip install → set budget → agent auto-discovers API → pays → gets result"

Step 6: [Post-launch] Content Writer → Provider 冷触达邮件
Step 7: [Post-launch] SEO Strategist → 全站 SEO 审计
```
