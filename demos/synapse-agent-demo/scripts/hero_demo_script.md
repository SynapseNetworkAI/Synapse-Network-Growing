---
id: hero_demo_script_v1
title: 1-Minute Hero Demo Script
role: dev_rel
status: ready
created_at: 2026-04-03
updated_at: 2026-04-03
author: AI-DevRel
target_repo: Synapse-Network-Sdk
---

# 1-Minute Hero Demo: M2M AI Payment via Synapse Network

**Objective**: Visceral demonstration of an Agent finding a tool, paying for it using USDC via Synapse, and instantly getting a result in under 1 minute.

## 🎬 画面分镜与控制台切换 (Camera & Terminal Workflow)

### 0:00 - 0:15 | The Setup (Terminal Only)
- **Voiceover/Text**: "AI Agents need external APIs, but they don't have credit cards. Here is how Synapse Network fixes this."
- **Visual**: Developer terminal typing:
  ```bash
  pip install synapse-network-sdk
  synapse-cli init --budget 5.00
  ```
- **Action**: SDK instantly provisions a local wallet and connects to Synapse Gateway, approving a $5.00 budget for MCP tool usage.

### 0:15 - 0:35 | The Run (Split Screen: Agent code / Terminal)
- **Voiceover**: "Let's ask an AI Agent to fetch real-time private market data—a paid service."
- **Visual**: Run the script:
  ```python
  from synapse_client import AgentWallet
  from smolagents import CodeAgent

  wallet = AgentWallet.connect()
  agent = CodeAgent(tools=[wallet.mcp_tool("market_data_api")])
  agent.run("Get me the precise sentiment data for AAPL today.")
  ```

### 0:35 - 0:50 | The Invisible Payment (Gateway Dashboard / Terminal)
- **Visual Switch**: Rapidly cut to Gateway Admin Console.
  - See the instant transaction: `-$0.05 USDC | Service: Market Sentiment | Status: SETTLED`
- **Voiceover**: "Behind the scenes, Synapse automatically signs a micropayment lock, deducting $0.05 with Zero Gas fees using state channels."

### 0:50 - 1:00 | The Result (Terminal Final Output)
- **Terminal Output**:
  ```text
  [Agent]: Calling tool 'market_data_api' (Cost: $0.05 USDC)...
  [Agent]: Payment approved.
  [Agent]: Insight -> AAPL sentiment is highly bullish (+0.82) based on recent volume. 
  [Agent]: Task Complete. Remaining Budget: $4.95 USDC.
  ```
- **Outro Text**: "Machine-to-Machine Payments. Unlocked. Synapse Network."
