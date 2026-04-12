---
id: developer_onboarding_emails_v1
title: Developer Welcome & Onboarding Emails
role: content_writer
status: draft
created_at: 2026-04-12
updated_at: 2026-04-12
author: Content Writer Agent
target_repo: Synapse-Network
---

Sequence Name: Developer Welcome & Onboarding
Trigger: New developer signs up via Synapse dashboard
Goal: Drive SDK quickstart completion, wallet creation, and first deposit
Length: 3 emails
Timing: Day 0, +24h (no wallet), +72h (no deposit)
Exit Conditions: Exit once wallet creation + first deposit both occur

### Email 1 – 注册即时 Welcome + Quickstart
- Trigger: Registration event
- Send: 立即 (Day 0)
- Subject: 注册成功：3 步让代理立即调用 API
- Preview: 预算隔离 + MCP 自动发现，5 分钟跑通 quickstart。
- Body (≤150字): 欢迎加入 Synapse。照这3步跑通 quickstart：①pip install synapse-client ②export SYNAPSE_API_KEY=agt_xxx ③python synapse_client_quickstart.py，5分钟看到$0.01扣费日志。
- CTA Label: 打开 Quickstart 指南
- CTA Link: https://console.synapse.network/quickstart
- CTA Metric: Quickstart 点击率 ≥45%，SDK 安装率 ≥35%

### Email 2 – +24h 未建钱包提醒
- Trigger: 24h 内未创建 Agent Wallet
- Send: +24h
- Subject: 你的 $2 测试额度还没激活
- Preview: 创建 Agent Wallet 即刻注入 2 USDC sandbox，零 gas 费用。
- Body (≤150字): 你的$2 sandbox额度还未绑定代理。登录控制台 Wallet→Create Agent Wallet，系统自动铸造预算并在 MCP 中可见。现在完成钱包创建即可让测试代理消费。
- CTA Label: 立即创建钱包
- CTA Link: https://console.synapse.network/wallet
- CTA Metric: Wallet 创建点击率 ≥40%，钱包完成率 ≥35%

### Email 3 – +72h 未首充提醒 + Demo
- Trigger: 72h 内无首笔充值
- Send: +72h
- Subject: 亲眼看代理扣费 → 一键充值
- Preview: 60 秒 Demo 展示 $0.01 结算，充值按钮同屏可用。
- Body (≤150字): 还没充值的话，新的API调用仍会被拦截。观看60秒demo，现场展示AgentWallet.connect(budget=5)触发三次$0.01扣费，再点同屏Deposit USDC按钮即可一键充值5 USDC。
- CTA Label: 观看 Demo 并充值
- CTA Link: https://console.synapse.network/topup-demo
- CTA Metric: Demo 播放到充值点击 ≥30%，首充完成率 ≥25%

### Measurement & Automation Notes
- [Placeholder for instrumentation events]
- [Placeholder for suppression / exit logic]
- [Placeholder for weekly review + experiment trigger]
