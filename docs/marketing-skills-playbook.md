---
id: marketing_skills_playbook
title: MarketingSkills 集成运营手册 — 一人公司 × 多 Agent 员工
role: cross-functional
status: published
created_at: 2026-04-08
updated_at: 2026-04-08
author: CTO
---

# MarketingSkills 集成运营手册

> 用 [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) 武装你的 Agent 员工团队，以一人公司模式运营 Synapse Network 的上线推广。

---

## 一、核心理念：一人公司 + Agent 员工矩阵

你不需要雇人。你需要的是一支 **Agent 员工团队**，每位 Agent 拥有独立身份（Persona）、专属技能（Skills）、明确的 KPI 和隔离的工作目录。你作为 CEO/CTO，只负责三件事：

1. **定战略** — 决定做什么、不做什么
2. **审产出** — Review Agent 的交付物，决定是否 publish
3. **调资源** — 根据数据反馈，决定哪个 Agent 加班、哪个暂停

```
                            ┌─────────────┐
                            │   你 (CEO)   │
                            │  战略 / 审批  │
                            └──────┬──────┘
                                   │
        ┌──────────┬───────────┬───┴───┬───────────┬──────────┐
        ▼          ▼           ▼       ▼           ▼          ▼
   ┌─────────┐┌─────────┐┌────────┐┌────────┐┌─────────┐┌─────────┐
   │Growth   ││Content  ││SEO     ││DevRel  ││CRO      ││Launch   │
   │Lead     ││Writer   ││Expert  ││Engineer││Optimizer││Strategist│
   │Agent    ││Agent    ││Agent   ││Agent   ││Agent    ││Agent    │
   └─────────┘└─────────┘└────────┘└────────┘└─────────┘└─────────┘
```

---

## 二、安装 MarketingSkills

在 `Synapse-Network-Growing` 项目根目录执行：

```bash
# 方式 1：Clone 到本地（推荐，便于定制）
git clone https://github.com/coreyhaines31/marketingskills.git .marketingskills
cp -r .marketingskills/skills/* .agents/skills/

# 方式 2：Git Submodule（便于跟踪上游更新）
git submodule add https://github.com/coreyhaines31/marketingskills.git .agents/marketingskills
```

### 创建产品营销上下文（所有 Skill 的基础）

MarketingSkills 的所有 Skill 都会先读取 `product-marketing-context`。这是你必须首先创建的文件：

```bash
mkdir -p .agents
```

将以下内容写入 `.agents/product-marketing-context.md`：

```markdown
# Product Marketing Context: Synapse Network

## Product
- Name: Synapse Network
- Tagline: The Settlement Layer for AI Agents — "Stripe for AI Agents"
- URL: [TBD - 上线后填写]
- Category: Infrastructure / Fintech / AI

## What It Does
AI Agent 时代的去中心化结算层。允许 Agent 自主发现、调用并支付 API 服务，
支持低至 $0.01 的零 Gas 微支付，原生适配 MCP 协议。

## Target Audience
1. **Primary**: AI Agent 开发者 / Agent 框架开发者（LangChain, CrewAI, AutoGen 用户）
2. **Secondary**: API / 数据服务提供商（想把 API 卖给 Agent 的人）
3. **Tertiary**: Web3 开发者、DeFi 用户

## Core Value Props
1. 预算隔离 — 每任务固定加密预算，杜绝 Agent 超支
2. 零 Gas 微支付 — 链下结算，链上最终确认
3. MCP 原生 — Agent 自主发现服务，无需人类干预
4. 统一身份 — 钱包私钥即身份，不需要 20 个 SaaS 账号

## Competitors / Alternatives
- 传统支付：Stripe（不支持微支付，$0.30 最低手续费）
- Crypto 支付：直接链上转账（Gas 费太贵，确认太慢）
- API 市场：RapidAPI（面向人类，没有 Agent 计费）

## Pricing Model
双边平台抽成。Provider 自行定价，Synapse 收取 ~5% 网络通道费。

## Current Stage
MVP 开发完成，准备上线推广。
```

---

## 三、Agent 员工花名册与技能分配

### Agent 1: Growth Lead（增长负责人）— 已有

| 维度 | 配置 |
|------|------|
| **Persona** | `roles/growth_lead/prompts/persona.md` |
| **MarketingSkills** | `marketing-ideas`, `marketing-psychology`, `launch-strategy`, `social-content` |
| **职责** | 制定 GTM 策略、撰写发布文案、监控增长指标 |
| **KPI** | PH upvotes、HN points、X impressions、signup 转化率 |
| **工作目录** | `roles/growth_lead/` |

### Agent 2: DevRel（技术布道师）— 已有

| 维度 | 配置 |
|------|------|
| **Persona** | `roles/dev_rel/prompts/persona.md` |
| **MarketingSkills** | `content-strategy`, `community-marketing` |
| **职责** | 编写技术博客、维护 Demo、优化 DX |
| **KPI** | SDK star 数、Demo clone 数、首次集成时间 < 5 分钟 |
| **工作目录** | `roles/dev_rel/` |

### Agent 3: Content Writer（内容写手）— 新增

| 维度 | 配置 |
|------|------|
| **Persona** | `roles/content_writer/prompts/persona.md` |
| **MarketingSkills** | `copywriting`, `copy-editing`, `cold-email`, `email-sequence` |
| **职责** | 官网文案、邮件序列、冷触达邮件、所有对外文字 |
| **KPI** | 邮件打开率、回复率、落地页跳出率 |
| **工作目录** | `roles/content_writer/` |

### Agent 4: SEO Strategist（SEO 专家）— 新增

| 维度 | 配置 |
|------|------|
| **Persona** | `roles/seo_strategist/prompts/persona.md` |
| **MarketingSkills** | `seo-audit`, `ai-seo`, `site-architecture`, `schema-markup`, `programmatic-seo`, `competitor-alternatives` |
| **职责** | 网站 SEO 审计、AI 搜索引擎优化、竞品对比页、结构化数据 |
| **KPI** | 有机流量、AI 引用次数、关键词排名 |
| **工作目录** | `roles/seo_strategist/` |

### Agent 5: CRO Optimizer（转化优化师）— 新增

| 维度 | 配置 |
|------|------|
| **Persona** | `roles/cro_optimizer/prompts/persona.md` |
| **MarketingSkills** | `page-cro`, `signup-flow-cro`, `onboarding-cro`, `form-cro`, `ab-test-setup`, `analytics-tracking` |
| **职责** | 落地页转化优化、注册流程优化、A/B 测试设计、埋点方案 |
| **KPI** | 注册转化率、激活率、首次付费率 |
| **工作目录** | `roles/cro_optimizer/` |

### Agent 6: Launch Strategist（发布策划师）— 新增

| 维度 | 配置 |
|------|------|
| **Persona** | `roles/launch_strategist/prompts/persona.md` |
| **MarketingSkills** | `launch-strategy`, `pricing-strategy`, `referral-program`, `sales-enablement`, `lead-magnets` |
| **职责** | 产品发布节奏编排、定价策略、推荐计划设计、销售物料 |
| **KPI** | 发布日注册数、WoM 裂变系数、付费转化 |
| **工作目录** | `roles/launch_strategist/` |

---

## 四、MVP 上线推广：分阶段执行计划

### Phase 0: 基建期（第 1 周）

| # | 任务 | 负责 Agent | 使用的 Skill | 产出物 |
|---|------|-----------|-------------|--------|
| 0.1 | 创建 `product-marketing-context.md` | CEO（你） | `product-marketing-context` | `.agents/product-marketing-context.md` |
| 0.2 | 官网/落地页文案 | Content Writer | `copywriting` | `roles/content_writer/outputs/homepage-copy.md` |
| 0.3 | 注册流程设计 | CRO Optimizer | `signup-flow-cro` | `roles/cro_optimizer/outputs/signup-flow.md` |
| 0.4 | 埋点方案 | CRO Optimizer | `analytics-tracking` | `roles/cro_optimizer/outputs/tracking-plan.md` |
| 0.5 | 定价方案确认 | Launch Strategist | `pricing-strategy` | `roles/launch_strategist/outputs/pricing.md` |

### Phase 1: 发布期（第 2 周）

| # | 任务 | 负责 Agent | 使用的 Skill | 产出物 |
|---|------|-----------|-------------|--------|
| 1.1 | 发布策略编排 | Launch Strategist | `launch-strategy` | `roles/launch_strategist/outputs/launch-plan.md` |
| 1.2 | Product Hunt 文案 | Growth Lead | `social-content`, `copywriting` | `roles/growth_lead/go_to_market/ph_copy.md` |
| 1.3 | Hacker News Show HN | Growth Lead | `social-content` | `roles/growth_lead/go_to_market/hn_copy.md` |
| 1.4 | Twitter/X Launch Thread | Growth Lead | `social-content` | `roles/growth_lead/go_to_market/x_thread.md` |
| 1.5 | 技术博客发布 | DevRel | `content-strategy` | `roles/dev_rel/contents/launch-blog.md` |
| 1.6 | Demo 仓库上线 | DevRel | — | `demos/synapse-agent-demo/` |

### Phase 2: 增长期（第 3-4 周）

| # | 任务 | 负责 Agent | 使用的 Skill | 产出物 |
|---|------|-----------|-------------|--------|
| 2.1 | SEO 审计 & 优化 | SEO Strategist | `seo-audit`, `ai-seo` | `roles/seo_strategist/outputs/seo-audit.md` |
| 2.2 | 竞品对比页 | SEO Strategist | `competitor-alternatives` | `roles/seo_strategist/outputs/vs-stripe.md` |
| 2.3 | 冷触达 Provider | Content Writer | `cold-email` | `roles/content_writer/outputs/provider-outreach.md` |
| 2.4 | 5 封欢迎邮件序列 | Content Writer | `email-sequence` | `roles/content_writer/outputs/welcome-sequence.md` |
| 2.5 | 落地页 A/B 测试 | CRO Optimizer | `page-cro`, `ab-test-setup` | `roles/cro_optimizer/outputs/ab-test-v1.md` |
| 2.6 | 推荐计划设计 | Launch Strategist | `referral-program` | `roles/launch_strategist/outputs/referral.md` |
| 2.7 | Onboarding 优化 | CRO Optimizer | `onboarding-cro` | `roles/cro_optimizer/outputs/onboarding.md` |

### Phase 3: 规模化（第 5-8 周）

| # | 任务 | 负责 Agent | 使用的 Skill | 产出物 |
|---|------|-----------|-------------|--------|
| 3.1 | 程序化 SEO 页面 | SEO Strategist | `programmatic-seo` | `roles/seo_strategist/outputs/programmatic-pages.md` |
| 3.2 | Schema 结构化数据 | SEO Strategist | `schema-markup` | `roles/seo_strategist/outputs/schema.md` |
| 3.3 | 免费工具引流 | Growth Lead | `free-tool-strategy` | 独立工具仓库 |
| 3.4 | 社区运营计划 | DevRel | `community-marketing` | `roles/dev_rel/contents/community-plan.md` |
| 3.5 | 流失预防 | CRO Optimizer | `churn-prevention` | `roles/cro_optimizer/outputs/churn-prevention.md` |
| 3.6 | Sales 物料包 | Launch Strategist | `sales-enablement` | `roles/launch_strategist/outputs/sales-kit/` |

---

## 五、Agent 调用实操指南

### 1. 如何调度一个 Agent 执行任务

每次任务调度遵循三步协议：

```
Step 1: 加载 Persona（角色身份）
  → 读取 roles/<agent>/prompts/persona.md

Step 2: 加载 Skill（专业技能）
  → Agent 读取 .agents/skills/<skill-name>.md
  → Skill 自动先读取 .agents/product-marketing-context.md

Step 3: 下达任务指令
  → 明确产出物路径、格式要求、KPI 标准
```

**示例 — 让 Content Writer 写冷触达邮件：**

```
你是 Content Writer Agent。
先读取 roles/content_writer/prompts/persona.md 获取你的身份。
使用 cold-email skill 的方法论。
为 Synapse Network 编写一组 3 封冷触达邮件序列，
目标受众是拥有独特数据 API 的开发者（Provider 端）。
产出写入 roles/content_writer/outputs/provider-outreach.md。
邮件必须有明确的 CTA，且长度控制在 150 字以内。
```

### 2. Skill 之间如何协作

MarketingSkills 的设计允许跨 Skill 引用。实际运营中常见的协作链路：

```
customer-research → copywriting → page-cro → ab-test-setup
                                            ↓
seo-audit → ai-seo → schema-markup     analytics-tracking
                                            ↓
launch-strategy → social-content → email-sequence
```

**你如何编排**：先让一个 Agent 完成上游 Skill 的产出，再把该产出作为下游 Agent 的输入上下文。

### 3. 产出物质量门禁

所有 Agent 产出必须满足：

- [ ] 包含标准 YAML Frontmatter（id, title, role, status, created_at, author）
- [ ] Growth 文案通过平台格式检查（HN 无 emoji、X 有 Thread 结构、PH 有 tagline + description）
- [ ] DevRel 代码示例通过实际运行验证（Exit 0）
- [ ] `status` 必须从 `draft` → `review` → `ready` → `published` 逐级推进
- [ ] 只有 `status: ready` 的交付物才可回到 campaign manifest 标记 `[x]`

---

## 六、目录结构扩展方案

在现有 `Synapse-Network-Growing` 基础上扩展：

```
Synapse-Network-Growing/
├── .agents/                        # MarketingSkills 安装目录
│   ├── product-marketing-context.md  # 产品营销上下文（所有 Skill 的基座）
│   └── skills/                       # 从 marketingskills repo 安装的 Skill 文件
│       ├── copywriting.md
│       ├── cold-email.md
│       ├── launch-strategy.md
│       ├── page-cro.md
│       └── ...
├── roles/
│   ├── growth_lead/          # ✅ 已有
│   ├── dev_rel/              # ✅ 已有
│   ├── content_writer/       # 🆕 新增
│   │   ├── prompts/persona.md
│   │   └── outputs/
│   ├── seo_strategist/       # 🆕 新增
│   │   ├── prompts/persona.md
│   │   └── outputs/
│   ├── cro_optimizer/        # 🆕 新增
│   │   ├── prompts/persona.md
│   │   └── outputs/
│   └── launch_strategist/    # 🆕 新增
│       ├── prompts/persona.md
│       └── outputs/
└── ... (其余结构不变)
```

---

## 七、回答核心问题

### "我需要做一个一人公司吗？"

**是的，这正是最优解。** 理由：

1. **成本结构碾压**：6 个 Agent 员工的运行成本 ≈ 每月几十美元的 LLM API 费用，而 6 个人类员工 ≈ 每月数万美元薪资。
2. **速度优势**：Agent 可以 24/7 并发执行，一个下午完成传统团队一周的文案产出。
3. **一致性**：每个 Agent 严格遵循 Persona + Skill，不会偏离品牌调性。
4. **可扩展**：需要新能力？新建一个角色目录 + 分配 Skill 即可，无需招聘周期。

### "如何管理这些 Agent 员工？"

你的管理方式是 **Campaign-Driven（战役驱动）**：

```
1. 在 campaigns/active/ 创建战役 manifest（计划清单）
2. 按 manifest 依次调度对应 Agent 执行任务
3. Review 产出，推进 status: draft → review → ready
4. 产出达标后在 manifest 中标记 [x]
5. 战役完成后归档到 campaigns/archived/
```

### "不同 Agent 使用不同身份和 Skills 怎么实现？"

已在本文档第三节定义。核心机制：

- **身份隔离**：每个 Agent 有独立的 `persona.md`，定义其思维方式和行为准则
- **技能装载**：通过 MarketingSkills 的 `.md` 文件注入专业方法论
- **目录隔离**：每个 Agent 只在自己的 `roles/<agent>/` 下工作，互不干扰
- **统一上下文**：所有 Agent 共享 `product-marketing-context.md` 保证品牌一致性

---

## 八、立即行动清单

```
Week 1 — 开干：
□ 安装 marketingskills 到 .agents/skills/
□ 创建 product-marketing-context.md
□ 创建 4 个新 Agent 角色目录和 persona.md
□ 让 Launch Strategist 生成发布策略
□ 让 Content Writer 生成官网文案初稿

Week 2 — 发布：
□ Growth Lead 生成 PH / HN / X 三套发布文案
□ DevRel 润色 Demo 仓库 README
□ CRO Optimizer 设计注册流程和埋点
□ 执行发布 — Product Hunt → Hacker News → Twitter/X

Week 3-4 — 增长：
□ SEO Strategist 执行全站 SEO 审计
□ Content Writer 发起 Provider 冷触达
□ CRO Optimizer 跑首轮 A/B 测试
□ 根据数据反馈迭代
```
