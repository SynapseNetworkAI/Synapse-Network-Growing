# Plan

## P0

### P0-R1 Bug Source Registry

状态：已完成

目标：

1. 建立统一的 bug source registry
2. 明确系统支持哪些 bug 来源，以及每类来源如何归一化

实现：

1. 新增 `bug_sources` 内置注册表
2. 首批内置来源：
   1. `manual_bug_report`
   2. `runtime_log_error`
   3. `workflow_incident`
   4. `task_failure`
   5. `delivery_blocker_bug`
3. 暴露 `GET /api/bugs/sources`
4. 在文档中明确 source contract、severity mapping、dedupe scope

### P0-R2 Bug Intake API

状态：已完成

目标：

1. 提供统一 bug 接收入口
2. 支持手工或系统外部推送 bug

实现：

1. 新增 `POST /api/bugs/intake`
2. 新增 `bug_records` 存储层或等价 registry
3. 归一化字段：
   1. `project_key`
   2. `title`
   3. `summary`
   4. `severity`
   5. `fingerprint`
   6. `source_key`
   7. `source_ref`
   8. `environment`
   9. `evidence`
4. 返回 `created / deduped / updated`

### P0-R3 Dedupe And Severity Scoring

状态：已完成

目标：

1. 防止同一 bug 重复占满 token 和 backlog
2. 为后续 auto-intake 建立稳定评分

实现：

1. 引入 fingerprint 生成器
2. 保留 representative evidence 样本
3. 增加 recurrence / freshness / blocker / publish impact scoring
4. 输出：
   1. `priority`
   2. `auto_intake_eligible`
   3. `intake_reason`

## P1

### P1-R1 Bug Log Sweep Workflow

状态：已完成

目标：

1. 把日志监控做成 recurring workflow，而不是 ad-hoc 排查

实现：

1. 新增 `bug_log_sweep` recurring workflow
2. 扫描：
   1. `server/logs/*`
   2. task logs
   3. runtime failure logs
3. 先做 deterministic prefilter，再做必要的模型归一化
4. 将新发现问题写入 bug registry

### P1-R2 Bug Backlog In Requirement Sources

状态：已完成

目标：

1. 让 bug 成为 requirement pool 的正式来源之一

实现：

1. requirement source registry 新增 `bug_intake`
2. `/api/requirements/intake` 支持 `bug_intake`
3. company review 显示 bug pressure 与 recurring fingerprints
4. daily intake loop 自动纳入高价值 bug candidates

### P1-R3 Bug Validation Contract

状态：已完成

目标：

1. bug 修复 requirement 必须带真实修复与回归验证，不允许只交设计文档

实现：

1. bug-derived requirement 默认 acceptance focus：
   1. `root_cause_documented`
   2. `bug_reproduced_or_evidence_bound`
   3. `fix_applied`
   4. `regression_guard_added`
   5. `bug_verification_passed`
2. validation contract 根据实际改动项目动态生成验证项
3. closeout 时检查同 fingerprint 是否仍在高频复现

## P2

### P2-R1 Auto Materialize High-Value Bugs

状态：已完成

目标：

1. 高价值 bug 自动回流成 requirement，不再依赖人工抄日志

实现：

1. 对 `critical / high` 且满足 policy 的 bug 自动 materialize
2. requirement 自动绑定目标项目、source ref、approval contract
3. incident 或 workflow-blocking bug 默认进入高优先级
4. `bug_log_sweep` recurring workflow 在 intake 后自动调用 bug backlog materialization

### P2-R2 Bug COO Dashboard

状态：已完成

目标：

1. 让 operator 在首页看到 bug 经营态，而不是只在日志里发现问题

实现：

1. 首页展示：
   1. open bug pressure
   2. recurring fingerprints
   3. bug-to-requirement conversion
   4. unresolved critical bugs
2. weekly review 输出 bug remediation package

### P2-R3 Cross-Project Bug Recovery Loop

状态：已完成

目标：

1. 当一个 bug 影响多个项目时，让系统能做 portfolio 级修复和验证

实现：

1. 支持 multi-project bug requirement
2. 生成 cross-project validation plan
3. 在 company review 中显示跨项目复发与修复状态
