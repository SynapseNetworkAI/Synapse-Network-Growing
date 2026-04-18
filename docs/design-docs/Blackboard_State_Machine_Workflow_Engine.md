# Blackboard + State Machine Workflow Engine：保留 Agent 自修复能力的声明式工作流

## Summary

你的判断正确：单向 YAML DAG 会限制 Agent 的核心能力。真实 Agent 工作流必须支持：

- verify 失败后回到 patch
- patch 多次仍失败后 route_to_human
- 所有节点共享上下文
- Agent 输出先被 parser / schema / evidence gate 消化
- 高风险任务无论测试多绿都进入人工门禁

因此推荐从 **YAML DAG** 升级为 **YAML State Machine + Blackboard**。

关键设计：

```text
YAML 定义状态与流转规则
Blackboard 保存共享上下文
Agent 在 state 内推理/写作/修复
Harness 执行验证和证据采集
Policy Engine 决定自动流转还是人工门禁
```

实现选择：**先不要引入 `transitions` 这类外部状态机库，v1 手搓一个轻量状态路由字典。**

原因：
- 当前流程需要和 DB、Artifact、ExecutionRun、Task、ValidationRecord 深度结合。
- 状态数量少，核心是安全与可观察性，不是复杂状态机语法。
- 少一个依赖，调试更透明。
- 后续如果状态机复杂到难维护，再迁移到库也不迟。

## Key Changes

### 1. 从 DAG 改成 State Machine

旧模式：

```text
collect -> diagnose -> patch -> verify -> open_pr
```

新模式：

```text
diagnose
-> patch
-> verify
   -> tests_passed: risk_gate
   -> tests_failed && retries < 2: patch
   -> tests_failed && retries >= 2: awaiting_operator
-> risk_gate
   -> low_risk && evidence_high: open_pr / done
   -> high_risk: awaiting_operator
```

Workflow YAML 示例：

```yaml
workflow_key: gateway_reliability_repair
initial_state: diagnose
capability_profile: reliability

limits:
  max_patch_retries: 2
  max_cost_per_run_usd: 2
  max_runtime_minutes: 30

blackboard:
  persist_keys:
    - trigger
    - logs
    - diagnosis
    - suspected_files
    - patch_summary
    - verification_result
    - risk_score
    - evidence_score
    - sop_learning

states:
  diagnose:
    kind: agent
    atom: agent_diagnose_error
    writes:
      - diagnosis
      - suspected_files
      - confidence
    transitions:
      - if: diagnosis.confidence >= 0.6
        goto: patch
      - if: diagnosis.confidence < 0.6
        goto: awaiting_operator

  patch:
    kind: agent
    atom: agent_implement_patch
    session: preserve
    reads:
      - diagnosis
      - suspected_files
      - verification_result
    writes:
      - patch_summary
      - changed_files
      - commands_run
    transitions:
      - goto: verify

  verify:
    kind: deterministic
    atom: run_harness_verification
    writes:
      - verification_result
      - evidence_score
    transitions:
      - if: verification_result.status == "passed"
        goto: risk_gate
      - if: verification_result.status == "failed" and counters.patch_retries < limits.max_patch_retries
        goto: patch
        increment: patch_retries
      - if: verification_result.status == "failed" and counters.patch_retries >= limits.max_patch_retries
        goto: awaiting_operator

  risk_gate:
    kind: deterministic
    atom: risk_evidence_gate
    writes:
      - risk_score
      - gate_decision
    transitions:
      - if: gate_decision == "auto_continue"
        goto: open_pr
      - if: gate_decision == "human_required"
        goto: awaiting_operator

  open_pr:
    kind: deterministic
    atom: create_github_pr
    transitions:
      - goto: observing

  observing:
    kind: deterministic
    atom: observe_desired_state
    transitions:
      - if: observation.status == "recovered"
        goto: done
      - if: observation.status == "not_recovered" and counters.observation_retries < 1
        goto: diagnose
        increment: observation_retries
      - if: observation.status == "not_recovered"
        goto: awaiting_operator

  awaiting_operator:
    kind: terminal
    terminal_reason: human_gate

  done:
    kind: terminal
```

### 2. Blackboard 解决上下文撕裂

每个 workflow run 创建一个 Blackboard。

Blackboard 不是聊天记录堆积，而是结构化上下文：

```json
{
  "workflow_key": "gateway_reliability_repair",
  "requirement_id": 123,
  "current_state": "patch",
  "counters": {
    "patch_retries": 1,
    "observation_retries": 0
  },
  "data": {
    "trigger": {},
    "logs": {},
    "diagnosis": {},
    "suspected_files": [],
    "patch_summary": "",
    "verification_result": {},
    "risk_score": 0,
    "evidence_score": 0
  },
  "artifacts": {
    "diagnosis_markdown": "...",
    "verification_evidence": "...",
    "latest_diff": "..."
  }
}
```

落地方式：
- 新执行链使用独立 declarative workflow 表：`workflow_runs.blackboard_json`、`blackboard_snapshots`、`workflow_state_events`、`workflow_artifacts`、`atom_invocations`、`human_gate_requests`。
- 大文本和证据写 `workflow_artifacts` 或 runtime artifact 文件，`workflow_artifacts.workflow_run_id` 直接关联 declarative run。
- Blackboard 只存摘要、路径、结构化字段、计数器。
- `patch` state 复用同一个 `runtime_session_id`，避免每轮重新理解上下文。
- 每次 state transition 都写一条 event artifact，方便回放。

### 3. Agent 输出必须经过 Parser Layer

Agent atom 不允许把自由文本直接传给 deterministic atom。

每个 Agent atom 必须声明输出 schema：

```json
{
  "summary": "string",
  "confidence": "number",
  "artifacts": "array",
  "changed_files": "array",
  "next_action": "continue|human_gate|failed",
  "risk_flags": "array"
}
```

Parser 规则：

- 优先要求 JSON。
- JSON 解析失败时，进入 `repair_parse`，要求同一 Agent 只修输出格式。
- parse repair 最多 1 次。
- 仍失败则 `awaiting_operator`。
- 原始文本必须保存为 artifact，不能丢。
- 下游只读取 parsed payload，不读取自由文本。

这解决“Agent 输出非结构化导致工作流崩”的问题。

### 4. Risk-Evidence Matrix 决定自动流转还是人工门禁

每个 state 结束后计算两个值：

```text
risk_score: 0-100
evidence_score: 0-100
```

默认决策矩阵：

| 场景 | Risk | Evidence | 决策 |
|---|---:|---:|---|
| 文档修复 + link check 通过 | 低 | 高 | 自动流转 |
| 普通非核心代码 bug + tests 通过 | 中 | 高 | 可自动 PR，merge 可人工 |
| Gateway 结算 / USDC / auth | 极高 | 高 | 必须人工 |
| 推文/营销文案 | 中 | 低 | 必须人工 |
| 客服技术问答，高置信度 docs 命中 | 低 | 中 | 可自动回复或半自动 |
| 退款/资金动作 | 极高 | 中/高 | 必须人工 |
| 纯读报表 | 低 | 低 | 可自动生成，不自动作为事实决策 |

Gate 规则：

```text
if risk_score >= 70:
  human_required
elif evidence_score >= 80 and risk_score <= 40:
  auto_continue
elif evidence_score < 50:
  human_required_or_observe
else:
  review_needed
```

高风险硬规则永远覆盖 Evidence：

- funds movement
- settlement logic
- contract change
- production deploy
- auth / permission change
- external paid spend
- self-modifying ops runtime merge

### 5. State Machine Runner v1

实现一个轻量 runner，不上复杂库。

核心伪代码：

```python
while not terminal:
    state = spec.states[current_state]
    result = run_atom(state, blackboard)
    parsed = parse_and_validate(result, state.output_schema)
    blackboard = merge_writes(blackboard, parsed)
    decision = evaluate_transitions(state.transitions, blackboard)
    persist_transition(current_state, decision.goto, blackboard)
    current_state = decision.goto
```

必要限制：
- `max_transitions_per_run`
- `max_retries_per_state`
- `max_runtime_minutes`
- `max_cost_per_run`
- `terminal_states` 必须显式定义
- 每个 loop 必须有 counter guard

### 6. 和当前系统对齐

复用现有模型：

- `RequirementRow`：Operating Ticket
- `ExecutionRunRow`：一次 workflow run
- `ExecutionNodeRow`：每个 state 的执行记录
- `TaskRow`：Agent atom 的 runtime task
- `ValidationRecordRow`：verify/risk gate 结果
- `ArtifactRow`：Blackboard 大文本、原始输出、验证证据、SOP learning
- `plan_snapshot_json`：workflow spec snapshot + blackboard summary

不新增核心状态对象。先把 State Machine Engine 做成 ExecutionRun 的一种 `execution_mode`：

```text
execution_mode = "state_machine"
```

## Test Plan

### State Machine

- initial_state 不存在时报错。
- terminal state 缺失时报错。
- transition 指向不存在 state 报错。
- loop 没有 counter guard 报错。
- max transitions 超限进入 awaiting_operator。
- verify failed 且 retries < 2 时回到 patch。
- verify failed 且 retries >= 2 时进入 awaiting_operator。
- tests passed 后进入 risk_gate。

### Blackboard

- diagnose 写入 diagnosis，patch 能读取。
- verify 写入 verification_result，patch retry 能读取失败原因。
- 大文本只存 artifact path，blackboard 不膨胀。
- 每次 transition 都持久化 current_state、counters、summary。
- 同一 workflow run 恢复后能从 current_state 继续。

### Agent Output Parser

- 合法 JSON 输出通过 schema。
- 非 JSON 输出触发 parse repair。
- parse repair 成功后继续。
- parse repair 失败后 awaiting_operator。
- 原始输出保存为 artifact。
- 下游 deterministic atom 只读取 parsed payload。

### Risk-Evidence Gate

- 低风险高证据自动继续。
- 高风险高证据仍然 human_required。
- 推文草稿进入 review_needed。
- refund payload 进入 awaiting_operator。
- Gateway settlement patch 进入 awaiting_operator。
- 普通 docs patch 可自动进入 PR/done。

### Session Reuse

- patch retry 复用同一 Execution Agent session。
- diagnose 和 patch 可以共享 blackboard，但不强制共享同一个 agent session。
- verification 不复用 execution session，保持独立。
- manual retry 继续复用 patch session，并追加 human note。

### Observation

- goal-driven workflow passed 后进入 observing。
- 指标恢复后 done。
- 指标未恢复后可回到 diagnose 或 awaiting_operator。
- observing 期间 Watcher 不重复建单。

## Implementation Defaults

- v1 手写轻量状态路由，不引入 `transitions`。
- v1 支持 state machine，不支持任意复杂 DAG + 并行。
- v1 所有 loop 必须有 counter。
- v1 Blackboard 存在 `workflow_runs.blackboard_json`，并通过 `blackboard_snapshots` 保留每次 state transition 的可审计快照。
- v1 大 artifact 使用 `workflow_artifacts` 或文件路径，不再复用旧 `ArtifactRow.workflow_run_id` 语义。
- v1 Agent atom 必须有 parser/schema。
- v1 高风险全部人工门禁。
- v1 首个工作流实现 `gateway_reliability_repair`。
- 第二个工作流实现 `agent_self_repair`，但只能提 PR，不能自动 merge/deploy 自己。
