# Spec

## 目标

把当前 requirement-first orchestration 升级成：

1. planner 输出 step graph + `complexity_tier / budget_cap / escalation_rule / expected_outputs`
2. scheduler 基于复杂度、项目风险、预算余量和历史失败率决定实际模型层级
3. orchestrator 执行时按失败信号自动升级或降级
4. validation 根据 `project_change_summary` 动态生成，而不是在 intake 时写死

## 不变原则

1. harness 不替模型决定“改文档还是改代码”
2. harness 仍然控制 project scope、capability matrix、interrupt policy、approval gate、delivery gate
3. review/test/closeout 仍然是必经流程，不允许跳过治理闭环

## 目标状态

### planner 输出

每个 step 至少包含：

1. `step_type`
2. `title`
3. `complexity_tier`
4. `budget_cap`
5. `allow_escalation`
6. `escalation_rule`
7. `expected_outputs`

### complexity tier

1. `mini`
   1. 搜索、分类、摘要、日志归因、报告整理
2. `standard`
   1. synthesis、常规实现、review、测试修复
3. `max`
   1. 跨仓改动、疑难 bug、架构迁移、反复失败恢复

### runtime 路由

建议默认：

1. `openai_responses`
   1. planning、signal summarization、incident clustering、company review aggregation
2. `codex_cli`
   1. implementation、review、test、需要读仓和跑命令的 research

### 动态验证

1. implementation 结束后统一生成 `project_change_summary`
2. review/test 根据实际修改到的项目加载 project policy 和 required checks
3. closeout/publish 只认真实跑过的验证证据

## 非目标

本阶段不做：

1. 全局自动成本优化 UI 看板
2. 细粒度 token 计费对账
3. 多供应商实时竞价调度
