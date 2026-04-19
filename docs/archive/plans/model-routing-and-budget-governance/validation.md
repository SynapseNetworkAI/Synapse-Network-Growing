# Validation

## 自动化验证

### 后端

1. planner schema 回归
   1. 断言每个 step 都带 `complexity_tier / budget_cap / escalation_rule`
2. runtime selection 回归
   1. 断言 `mini / standard / max` 会映射到预期 backend/model
3. escalation 回归
   1. 连续失败两次后自动升级
   2. 多项目 requirement 自动升级
   3. review/test blocker 自动升级
4. dynamic validation 回归
   1. `project_change_summary` 只验证实际改动项目

### 前端

1. requirement detail 显示 step tier / budget / selected runtime
2. scheduler / company review 显示模型层级占比、预算和升级事件

## 人工验收

1. 新建 requirement，观察 planner 是否生成 tier 注解
2. 执行单项目 requirement，确认走 mini/standard 默认层级
3. 制造失败，确认 orchestrator 自动升级
4. 执行多项目 requirement，确认 validation 只验证实际修改到的项目

## 通过标准

1. requirement 可以完整跑通，不因为 tier 路由造成新的状态分裂
2. 平均 planning / aggregation token 成本下降
3. incident / review / publish 链仍然可追踪、可解释
