# Plan

## P0

### P0-R1 Planner Tier Annotation

状态：已完成

目标：

1. planner 在 full-plan 和 fallback 两条路径都输出 `complexity_tier / budget_cap / escalation_rule / expected_outputs`

实现：

1. 扩展 planner step schema
2. 为 fallback 规则提供 deterministic tier defaults
3. requirement detail 展示每个 step 的模型层级与预算

### P0-R2 Runtime Selection Contract

状态：已完成

目标：

1. scheduler / orchestrator 能根据 step tier 选择 runtime backend 和模型

实现：

1. 新增 `step_runtime_contract`
2. 支持 `mini / standard / max` 对应不同 backend/model
3. 记录 runtime selection artifact，方便回放和调试

### P0-R3 Dynamic Validation Contract

状态：已完成

目标：

1. validation 由 `project_change_summary` 驱动，而不是 requirement intake 时预判

实现：

1. implementation 后稳定生成 `project_change_summary`
2. review/test 在运行前动态收集 affected projects 的 required checks
3. closeout 只认真实执行的 validation evidence

## P1

### P1-R1 Escalation And Downgrade Loop

状态：已完成

目标：

1. orchestrator 按失败信号自动升级模型层级
2. 对低复杂度收尾任务自动回落到便宜模型

实现：

1. 失败 2 次升级
2. 多项目升级
3. changed files 超阈值升级
4. review/test blocker 升级
5. summary/report 类 step 自动降回 mini

### P1-R2 Budget Guardrails

状态：已完成

目标：

1. 在不牺牲完成率的前提下，对 step / requirement / project 三层做预算保护

实现：

1. `budget_cap` 真正生效
2. 项目级预算与 scheduler 联动
3. 超预算时暂停并生成 operator review

### P1-R3 Prompt Caching And Compaction

状态：已完成

目标：

1. 压缩重复上下文和重复证据消耗

实现：

1. policy / repo brief / project profile 走缓存引用
2. 长对话后生成 compact artifact
3. evidence dedupe 和 incident dedupe 统一规则
4. dispatch 前生成 `prompt_cache_profile` artifact，记录 cache key、复用段落和节省字符数

## P2

### P2-R1 Portfolio-Level Cost And Completion Dashboard

状态：已完成

目标：

1. 在 company review 里加入完成率、预算、升级次数、模型占比

实现：

1. company review 汇总 runtime tier metrics
2. recommendation 中纳入“哪些 requirement 应降级、哪些应升级”
3. 首页 review 面板展示 `completion_rate / budget_spent_points / prompt_cache_saved_chars / escalations / downgrades / tier_mix`

### P2-R2 Human Gate On Expensive Branches Only

状态：已完成

目标：

1. 把人工审批收缩到 max-tier、发布前和事故恢复链

实现：

1. 普通 mini/standard 链默认不审批
2. 高成本或高风险步骤自动挂 review gate
3. capability deny 仍然是硬拦截，但 operator confirmation 只保留给 `max-tier / publish / incident recovery`

### P2-R3 Human Gate Hotspots And Automation Candidates

状态：已完成

目标：

1. 在 company review 中回答“哪些 branch 经常触发 human gate”
2. 给出“哪些 gate 值得进一步自动化”的候选集

实现：

1. 聚合 `approval_requests + workflow_steps.approval_scope + delivery_state`，生成 `human_gate_hotspots`
2. 对高频 gate 自动产出 `automation_candidates`
3. 首页 review 面板展示 hotspot 数、热点列表和自动化候选列表
