---
id: account_registration_plan
title: Account Registration and Distribution Plan
role: growth_lead
status: ready
created_at: 2026-04-03
updated_at: 2026-04-03
author: AI-GrowthLead
---

# 📈 增长分发与账号注册矩阵 (Distribution & Accounts)

作为增长负责人 (Growth Lead)，为了在 30 天内引爆开发者和 Agent 框架社区，我们必须采取“多点触达、精准打击”的策略。

在这里，我们从零开始梳理了**平台分发矩阵**、**账号注册追踪表**以及**接下来的核心工作计划 (To-Do)**。所有已经写好的文案（Launch Copy、Blog）将依托这些平台进行分发。

---

## 1. 账号注册与筹备清单 (Account Registration Tracker)

请按照下表逐一注册并完善资料（Logo、Bio、官网链接）。注册完成后，将状态标记为 `[x]`。

| 状态 | 平台类别 | 目标平台 | 账号注册需求说明 | 对应输出内容 |
|---|---|---|---|---|
| [ ] | **头条曝光** | **Product Hunt (PH)** | 个人的 Maker 账号 + 创建产品页面 (Synapse Network) | `launch_copy_v1.md` 中的产品版 |
| [ ] | **极客讨论** | **Hacker News (HN)** | YCombinator 账号（注意：HN 对新号发带链接的帖有一定权重限制，建议用有历史的老号或立刻注册养号） | `launch_copy_v1.md` 中的 Show HN 版 |
| [ ] | **社交传播** | **X (Twitter)** | 1. 官方企业号 (e.g. @SynapseNetwork)<br>2. 创始号 (CTO/CEO个人号，转化率更高) | `launch_copy_v1.md` 中的极简 Thread |
| [ ] | **技术博客** | **Substack** | 注册官方 Newsletter 主页（最能留存私域流量） | `blog_mcp_budget.md` (作为首篇大作发布) |
| [ ] | **技术博客** | **Hashnode / Dev.to** | 同步分发博客，自带强大的开发者 SEO 和推荐流量 | `blog_mcp_budget.md` (设置 Canonical URL 指向 Substack) |
| [ ] | **垂直社群** | **Reddit** | 包含 r/MachineLearning, r/LocalLLaMA, r/ethdev 等 | 本地化的硬核技术探讨帖子 |

---

## 2. 内容发布与获客策略 (How & Where to Publish)

不要把内容全部堆在同一天无脑发布。为了实现最好的杠杆效应（Leverage），发布节奏如下：

- **第一击：技术心智 (Tech Priming)**
  - **平台**: Hashnode / Dev.to / Substack
  - **内容发布**: 发布底层逻辑博文（*How to let AI agents discover and pay for APIs*）。
  - **打法**: 在社群（Reddit / Discord）做技术探讨，不卖产品，只抛出“API 密钥是 AI 的噩梦”这个痛点，然后链接指向我们的文章。

- **第二击：开发者引爆 (The Hacker Drop)**
  - **平台**: Hacker News (Show HN) / X (Twitter Thread)
  - **内容发布**: 放出 1-Minute Hero Demo 视频与 SDK 的 GitHub 链接。
  - **打法**: 由 CTO 个人号在 X 上发 Thread（配合 Demo 视频），然后在 HN 发布硬核原理解析，承接流量直接进入 GitHub Repo。

- **第三击：商业化发布 (Commercial Launch)**
  - **平台**: Product Hunt
  - **内容发布**: 完整的 Launch Copy（Maker's Comment） + `synapse-agent-demo` 体验入口。
  - **打法**: 利用前两期积累的早期流量，引导他们去 Product Hunt 点赞，冲击 Product of the Day，吸引 Provider (API 卖家) 入驻。

---

## 3. 增长阶段行动计划 (与研发里程碑对齐)

- [ ] **Phase 1: 研发期 · 基建与养号 (当前阶段：开发调试/Staging部署前)**
  - [ ] ⚠️ **立刻注册账号并开始养号**（HN 和 Reddit 对纯新号发链接有严重的防机器惩罚，新号发文几乎零曝光。现在注册，每天花5分钟去别人的帖子里点赞、留几段有深度的评论，养出权重）。
  - [ ] 搭建 Substack / Dev.to 的空间视觉（上传 Logo、写好 Bio、配置好自定义域名，但先别发大新闻）。
  - [ ] 利用你跑通的**本地开发环境**，直接录制那段 **1 分钟 Hero Demo** 的实机操作视频，把宣发物料（视频/GIF）提前剪出来。

- [ ] **Phase 2: 预发内测期 · 私域预热 (Staging / 联调环境上线后)**
  - [ ] 在 Substack 和 Dev.to 上首发架构逻辑这篇 Blog（讲透 MCP + 微支付）。
  - [ ] 将文章投递到 Reddit 等垂类节点，不推销产品，只聊“API Key的危险性”，观察开发者最真实的反馈。

- [ ] **Phase 3: 全网空投 (Day 8-14)**
  - [ ] 在 X (Twitter) 发布爆款 Thread。
  - [ ] 提交 "Show HN: Synapse Network" 冲顶。
  - [ ] 观察 Gateway/Dashboard 上的用户注册量和 API 调用量。

- [ ] **Phase 4: PH 打榜与 B 端招商 (Day 15-30)**
  - [ ] 正式上线 Product Hunt。
  - [ ] 使用 `provider_onboarding.md` 文案单独触达数据服务商，引导他们把 API 挂载到我们的网络。
