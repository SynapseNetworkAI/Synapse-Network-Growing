# 多场景沙盘验证：Blackboard + State Machine + Agent Atom 是否满足一人公司复杂工作流

## Summary

你的 5 个场景推演整体是正确的，而且这套设计确实能覆盖一人公司最核心的复杂工作流：

```text
监控自己
监控目标产品
日常运营
增长战役
客服与技术支持
```

结论：

- **满足 Agent-First**：Agent 负责诊断、生成、修复、创作、分类、总结等高认知任务。
- **满足安全性**：确定性 Atom、Risk Gate、Human Gate、Kill Switch 控制边界。
- **满足复杂流转**：State Machine 支持 retry、loop、observing、awaiting_operator。
- **满足长期演进**：SOP Ledger 和 Workflow YAML 让系统能持续沉淀。
- **比传统 CI/CD 更强**：传统 CI/CD 只能执行固定命令；这套系统能让 Agent 在节点内推理和创造。
- **比自由多 Agent 更稳**：Agent 不再自由开会，而是在状态机允许的工位上解决难题。

关键前提：

```text
必须有共享 Blackboard。
必须有 Agent 输出 parser/schema。
必须有 Risk-Evidence Gate。
必须有 retry budget。
必须有 Human Gate。
必须有 workflow sandbox。
```

只要这 6 个前提成立，这套系统可以支撑多个工作流和复杂场景。

## Scenario Validation

### 1. Agent 系统自我修复

是否满足：满足。

推荐状态机：

```text
detect_ops_failure
-> collect_logs
-> diagnose
-> patch
-> verify
   -> failed && retries < 2: patch
   -> failed && retries >= 2: awaiting_operator
-> open_pr
-> awaiting_operator
```

Agent 能力体现：
- 读懂自身 Python traceback。
- 定位失败模块。
- 生成补丁。
- 补测试。
- 解释风险。

确定性系统负责：
- 抓取固定日志。
- 限制修改范围。
- 跑测试。
- 创建 PR。
- 禁止自动 merge / deploy 自己。

必要门禁：
- 自修改代码必须 human approval。
- 重启 Ops runtime 必须 human approval。
- 不能自动修改自己的权限系统。
- 不能自动修改 kill switch。

结论：
- 这是非常适合第一批落地的工作流。
- 它能证明系统具备“自我维护”能力，但不会让系统自毁。

### 2. Synapse-Network Bug 修复

是否满足：满足，而且是最有价值的首个生产场景。

推荐状态机：

```text
desired_state_drift
-> collect_gateway_logs
-> fingerprint
-> diagnose
-> patch
-> verify
   -> failed && retries < 2: patch
   -> failed && retries >= 2: awaiting_operator
-> risk_gate
-> open_pr
-> awaiting_operator 或 observing
-> done / reopen
```

Agent 能力体现：
- 从日志中提炼 Error Fingerprint。
- 判断是否和 USDC 精度、Provider 超时、预算不足、Auth 失败有关。
- 修改目标仓库代码。
- 增加测试。
- 生成 PR 说明。
- 生成 SOP learning。

确定性系统负责：
- Watcher 检测 5xx drift。
- Dedupe 防止重复建单。
- Harness 跑测试。
- Risk Gate 识别资金/结算/权限高风险。
- Observing 验证业务指标是否恢复。

必要门禁：
- Gateway 普通 bug 可自动 PR。
- 涉及 settlement / USDC / contract / auth 必须 human approval。
- Production deploy 必须 human approval。
- 指标未恢复不能直接 done。

结论：
- 这套设计比传统 CI/CD 强，因为它区分了“测试通过”和“业务恢复”。
- `observing` 是这里的关键状态，必须保留。

### 3. 日常运营：X / Reddit / 内容

是否满足：满足，但不能和工程验证用同一套 gate。

推荐状态机：

```text
content_goal_drift
-> collect_context
-> draft_content
-> brand_review
-> awaiting_operator
-> publish
-> observe_engagement
-> done / record_learning
```

Agent 能力体现：
- 把 commit、产品更新、行业新闻转成内容。
- 根据 X / Reddit / HN 风格调整语气。
- 生成多个版本。
- 自查品牌风险。
- 生成发布建议。

确定性系统负责：
- 抓 GitHub commits。
- 抓 RSS / 手动输入热点。
- 保存草稿。
- 调用发布 API。
- 记录发布时间和链接。
- 观察基础数据。

必要门禁：
- 默认 public content 必须 human approval。
- 低风险内部 digest 可以自动发。
- 不能根据小样本自动改品牌策略。
- 不能自动进行外部 paid spend。

结论：
- 满足日常运营需求。
- 但“文案好不好”不能靠 Verification Agent 最终裁决，只能靠 human approval 或后续数据观察。

### 4. 增长战役

是否满足：满足，但应该把它定义为 Campaign Workflow，不是单个工程 Ticket。

推荐状态机：

```text
operator_intent
-> decompose_campaign
-> generate_assets
-> assemble_launch_package
-> awaiting_operator
-> publish_assets
-> observing
-> campaign_review
-> done / followup_requirement
```

Agent 能力体现：
- 把“做一次免费额度推广活动”拆成落地页、邮件、推文、教程、FAQ。
- 生成 campaign copy。
- 生成 landing page patch。
- 生成邮件序列。
- 生成发布 checklist。
- 分析结果并提出下一轮建议。

确定性系统负责：
- 保存所有资产。
- 跑页面构建检查。
- 调用 SendGrid / Vercel / social API。
- 记录发布证据。
- 观察 GA / signup / activation 数据。

必要门禁：
- 对外 campaign launch 必须 human approval。
- 付费投放必须 human approval。
- 低样本阶段不做自动 A/B 结论。
- 早期只判断 artifact/publish evidence，不判断统计显著性。

结论：
- 满足增长战役。
- 但 v1 不要自动优化投放，先做“生成资产 + 人审发布 + 数据观察”。

### 5. 客服与技术支持

是否满足：满足，但这是最复杂场景，应该后置实现。

推荐状态机：

```text
support_webhook
-> classify_intent
-> branch:
   technical_question -> retrieve_docs -> draft_reply -> confidence_gate -> send_or_approval
   funds_or_refund -> readonly_lookup -> draft_response -> awaiting_operator
   bug_report -> create_requirement -> acknowledge_user
-> record_interaction
-> done
```

Agent 能力体现：
- 多意图识别。
- 把一句话拆成技术问题、资金问题、bug report。
- RAG 检索 docs。
- 生成自然语言回复。
- 总结成 bug requirement。
- 草拟退款说明。

确定性系统负责：
- 接收 Discord/X webhook。
- 只读查询 TxHash / ledger / user state。
- confidence gate。
- 调用 Discord API。
- 创建 Requirement。
- 阻止资金动作自动执行。

必要门禁：
- 技术问题高置信度可自动回复。
- 资金、退款、账户、安全、权限问题必须 human approval。
- Agent 可以草拟 refund payload，但不能执行。
- 所有公开回复要记录证据和引用来源。

结论：
- 架构可以满足。
- 但因为涉及外部用户和资金，应在 Reliability 工作流稳定后再做。

## Comparison

### 对比 1：自由多 Agent 开会

缺陷：
- 容易无限讨论。
- 状态不可控。
- 成本不可控。
- 结果不可验证。
- 多 Agent 互相甩锅。

当前方案优势：
- Agent 只在 state 内工作。
- State Machine 决定下一步。
- Blackboard 保存共享上下文。
- Harness 提供证据。
- Human Gate 控制高风险。

结论：
- 当前方案显著更适合生产。

### 对比 2：传统 CI/CD

缺陷：
- 只能跑固定命令。
- 不能读懂日志。
- 不能生成修复。
- 不能写文案。
- 不能做客服。
- 不能总结 SOP。

当前方案优势：
- CI/CD 能力被保留为 deterministic atom。
- Agent atom 增加诊断、修复、生成、分类能力。
- Observing 增加业务恢复验证。

结论：
- 当前方案不是退化为 CI/CD，而是 CI/CD + Agent 推理层。

### 对比 3：单向 YAML DAG

缺陷：
- verify 失败后难以回到 patch。
- 没有自然 retry loop。
- 不适合观察期。
- 不适合 human pause/resume。
- 上下文容易断裂。

当前方案优势：
- State Machine 支持循环。
- Blackboard 解决上下文共享。
- Counters 防止无限重试。
- Terminal states 保证收口。

结论：
- State Machine YAML 明显优于 DAG YAML。

### 对比 4：全部写死 Python Workflow

缺陷：
- 每次流程变化都要改代码。
- 工作流容易变成 if-else 面条。
- Agent 无法生成新流程。
- 扩展慢。

当前方案优势：
- Atom 写死，Workflow 配置化。
- Meta-Builder 后续可生成 YAML。
- 核心引擎稳定，业务流程可变。

结论：
- 当前方案更适合长期演进。

### 对比 5：完全动态生成 Raw Code

缺陷：
- 安全不可控。
- 代码风格混乱。
- secret 风险高。
- 常驻脚本难维护。
- 容易生成黑盒自动化。

当前方案优势：
- 默认只生成 YAML workflow。
- 缺 atom 时才生成 connector requirement。
- connector 必须 sandbox + test + PR + human approval。

结论：
- 当前方案在灵活性和安全性之间更平衡。

## Required Core Contracts

### 1. Blackboard Contract

每个 workflow run 必须有共享上下文：

```json
{
  "workflow_key": "...",
  "current_state": "...",
  "counters": {},
  "trigger": {},
  "inputs": {},
  "state_outputs": {},
  "artifacts": {},
  "risk_flags": [],
  "evidence": []
}
```

规则：
- Agent 节点读 blackboard。
- Agent 节点写 structured output。
- 大文本写 artifact path。
- 每次 transition 记录事件。
- retry 节点必须能读上一次失败原因。

### 2. Agent Atom Contract

Agent 输出必须结构化：

```json
{
  "status": "completed|needs_more_context|failed|human_gate",
  "summary": "...",
  "confidence": 0.0,
  "writes": {},
  "artifacts": [],
  "risk_flags": [],
  "suggested_next_action": "continue|retry|human_gate"
}
```

规则：
- JSON/schema 解析失败最多修一次。
- 原始输出必须保存。
- 下游只消费 parsed output。
- confidence 不能直接决定高风险动作。

### 3. Transition Contract

每个 transition 必须是确定性规则：

```yaml
transitions:
  - if: verification.status == "passed"
    goto: risk_gate
  - if: verification.status == "failed" and counters.patch_retries < 2
    goto: patch
    increment: patch_retries
  - if: verification.status == "failed"
    goto: awaiting_operator
```

规则：
- 不允许无限循环。
- 每个 loop 必须有 counter。
- 每个 workflow 必须有 terminal state。
- transition 由程序判断，不由 Agent 自己跳转。

### 4. Risk-Evidence Gate

自动流转只在低风险 + 高证据时发生。

默认规则：

```text
high risk -> human gate
low risk + high evidence -> auto continue
low evidence -> review_needed or observing
funds/auth/settlement/production -> always human
```

### 5. Observation Contract

Goal-driven 任务必须区分：

```text
delivery verification passed
business metric recovered
```

状态：

```text
verified -> observing -> done
verified -> observing -> not_recovered -> diagnose / awaiting_operator
```

## Final Verdict

这套设计可以满足多个工作流和复杂场景。

适配能力：

| 场景 | 是否满足 | 关键能力 |
|---|---|---|
| Agent 自我修复 | 满足 | self-repair + PR-only + human merge |
| Synapse Bug 修复 | 满足 | desired drift + repair loop + observing |
| 社交运营 | 满足 | content generation + human publish |
| 增长战役 | 满足 | campaign decomposition + launch approval + observation |
| 客服支持 | 满足 | intent split + RAG + confidence gate + funds human gate |

当前最值得先实现的顺序：

1. `gateway_reliability_repair`
2. `agent_self_repair`
3. `daily_digest / soft_signal_summary`
4. `social_ops_draft`
5. `customer_support_triage`
6. `growth_campaign_builder`

第一阶段只做前两个，能最直接证明系统对真实产品和自身都有维护能力。

## Assumptions

- Workflow 使用 State Machine YAML，而不是单向 DAG YAML。
- v1 手写轻量状态路由，不引入重型状态机库。
- Blackboard 存在 `ExecutionRun.plan_snapshot_json.blackboard`。
- 大文本和证据存在 Artifact / 文件。
- Agent atom 必须 schema 化输出。
- 所有高风险副作用都必须 human gate。
- 每个 loop 必须有 retry budget。
- Meta-Builder 后续只能生成 workflow YAML，不能直接部署 raw Python 常驻脚本。
