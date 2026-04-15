# 错误发现与自修复 v1

## Summary

本设计把错误发现正式收敛成一条统一主链：

1. error intake
2. fingerprint / bug record
3. discovery recommendation
4. requirement materialization
5. approval
6. execution
7. verification
8. PR

本版本只覆盖 defect self-healing，不覆盖新增功能自动发现。

## Discovery Pipeline

统一入口：

1. `/api/errors/intake`
2. `/api/bugs/intake/log-center`
3. `bug_log_sweep`

统一流程：

1. 先写入 `error_fingerprint` 或 `bug_record`
2. 聚合 occurrence、evidence 与最新摘要
3. 生成 discovery recommendation
4. 由系统硬规则决定：
   - `auto_materialize`
   - `queue_for_operator`
   - `ignore_as_noise`
5. 被 materialize 的错误继续进入 requirement agent-first 主链

## Discovery Recommendation

discovery recommendation 的正式字段：

1. `discovery_action`
2. `confidence`
3. `reason`
4. `target_project_key`
5. `suggested_title`
6. `suggested_priority`
7. `auto_start_allowed`

## Hard Rules

system rules 只负责硬边界：

1. 同一 fingerprint 若已有 active requirement，则复用，不重复 materialize
2. 高风险项目可自动建 requirement，但不能跳过 approval gate
3. retry budget 继续沿用 `retry_execution = 1`
4. verification failure 默认优先 `retry_execution`
5. 只有明显超出原 requirement scope 时，才允许 follow-up requirement 或 route to human

## Approval Agent

approval 采用：

1. approval agent 先给出 recommendation
2. policy 决定是否自动放行
3. 高风险或低置信度时转人工

这保证 agent-first，但不取消高风险人工 execution approval。

## v1 Boundary

纳入：

1. runtime error
2. external log center error
3. task failure
4. workflow incident
5. verification 暴露的系统性缺陷

不纳入：

1. feature opportunity
2. 用户行为信号
3. PR 评论
4. 市场/运营机会
5. 自动产品路线发现
