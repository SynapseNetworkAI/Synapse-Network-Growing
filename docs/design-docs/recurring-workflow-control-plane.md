---
id: recurring-workflow-control-plane
title: Recurring Workflow Control Plane
role: dev_rel
status: draft
created_at: 2026-04-18
updated_at: 2026-04-18
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing
---

# Recurring Workflow Control Plane

## Summary

Scheduled Jobs / 定时任务管理面把系统里所有“会定期或后台推动 Company Ops”的机制显式化。v1 的边界是 **只读管理 + 手动运行 + 运行历史 + 健康状态**，不开放自定义任务新增或编辑。

这个页面不是新的自动化大脑，而是后台自动化的仪表盘。Operator 可以回答四个问题：

1. 哪些后台任务存在。
2. 哪些任务真正会自动跑。
3. 上次运行做了什么，是否失败。
4. 是否需要人工介入或手动 dry run。

## Current Background Mechanisms

当前平台存在五类后台或准后台机制：

1. **Bug Log Sweep Scheduler**
   - 真实自动运行的后台 scheduler。
   - 周期性扫描日志，将高信号错误进入 bug intake / requirement pipeline。
   - v1 暴露 `enabled / running / interval / last_tick / last_run / last_error`。

2. **Recurring Workflows Registry**
   - 内置 recurring workflow 定义清单。
   - 当前包括 `bug_log_sweep`、`morning_intake_sweep`、`dispatcher_loop`、`closeout_and_compact_sweep`、`weekly_operating_review`、`approval_sweep`、`requirement_family_cleanup_sweep`。
   - v1 支持手动 `Dry Run` 与 `Run Now`，但不自动按 schedule 执行全部 registry。

3. **Notification Dispatcher**
   - 统一消费 `notification_events`，执行 dedupe、cooldown、suppression、delivery retry。
   - v1 从“请求内同步消费一次”升级为后台 loop。
   - 暴露 queued、dead letter、open fingerprints、suppressed fingerprints。

4. **Requirement Asset Generation**
   - Requirement 创建后异步生成 acceptance / plan / workflow assets。
   - 它是后台动作，但 v1 不把它作为可手动新增的 recurring workflow，只在 requirement 面展示状态。

5. **Portfolio / Operating Review Scheduler**
   - 面向 company review、weekly review、portfolio cleanup 的任务定义。
   - v1 先进入 registry 与手动运行，不自动启动周期执行，避免突然扩大系统行为面。

## V1 Product Boundary

v1 明确不做这些事：

1. 不开放自定义定时任务新增、编辑、删除。
2. 不做通用 cron 编排器自动执行所有 recurring workflows。
3. 不让 operator 在 UI 写任意 shell command。
4. 不允许高风险 workflow 因为 schedule 到期而自动启动 requirement 或 delivery。
5. 不把完整 raw JSON 堆到默认视图；raw result 只在 inspector 展开。

v1 必须做这些事：

1. 展示内置 recurring workflow registry。
2. 展示每个任务的 schedule、owner、status、last run、next run、health。
3. 支持 `Dry Run`。
4. 支持受确认保护的 `Run Now`。
5. 保存每次运行历史。
6. 聚合 Bug Scheduler 与 Notification Dispatcher 健康状态。
7. 让 operator 能看见 queue 堆积、dead letter、suppression 状态。

## Data Model

新增运行历史表：

```text
recurring_workflow_runs
  id
  workflow_key
  status: running | succeeded | failed | skipped_locked
  triggered_by: operator | scheduler | system
  dry_run
  params_json
  result_json
  error_excerpt
  started_at
  completed_at
  duration_ms
  created_at
  updated_at
```

既有 `recurring_workflows` 继续保存 registry 与最近一次结果：

```text
recurring_workflows
  workflow_key
  display_name
  owner_role
  cadence_type
  schedule_json
  status
  last_run_at
  last_result_json
```

规则：

1. 每次 `run_recurring_workflow` 都必须创建一条 `recurring_workflow_runs`。
2. 成功时写 `succeeded + result_json + duration_ms`。
3. 失败时写 `failed + error_excerpt + duration_ms`，然后由 API 返回错误。
4. 旧 `last_run_at / last_result_json` 保留，用于列表快速展示。

## API

v1 API：

```text
GET /api/recurring-workflows
GET /api/recurring-workflows/{workflow_key}
POST /api/recurring-workflows/sync
POST /api/recurring-workflows/{workflow_key}/run
GET /api/recurring-workflows/{workflow_key}/runs?limit=50
GET /api/recurring-workflows/health
```

`RecurringWorkflowOut` 增加计算字段：

```text
next_run_at
is_due
health_status
```

`/health` 聚合：

```text
bug_log_scheduler
notification_dispatcher
recurring_registry
```

`bug_log_scheduler` 额外暴露数据库租约状态：

```text
lock
  lock_key
  owner_id
  status
  held
  stale
  acquired_at
  expires_at
  heartbeat_at
```

## Frontend Layout

新增 `/schedules` 页面，导航名为 `定时任务`。

### Health Overview

展示三张健康卡：

1. Bug Log Scheduler
2. Notification Dispatcher
3. Recurring Registry

每张卡显示运行状态、最近 tick、最近错误、队列数量或 registry 统计。

### Recurring Workflow Registry

表格字段：

1. workflow key / display name / description
2. owner role
3. schedule
4. health status
5. last run / next run
6. actions

操作：

1. `Dry Run`
2. `Run Now`
3. 查看历史

### Run History

每个 workflow 展示最近运行记录：

1. status
2. triggered_by
3. dry_run
4. started_at / completed_at
5. duration_ms
6. params
7. result
8. error_excerpt

`bug_log_sweep` 如果遇到另一个 scheduler 或手动 Run Now 正在运行，会写入：

```text
status = skipped_locked
result.reason = scheduler_lock_held
result.lock = <scheduler lock snapshot>
```

这不是失败，而是防并发保护生效。Operator 可以在历史记录里确认本次没有重复扫描，也没有重复创建 requirement。

### Result Inspector

默认只展示摘要。raw JSON 使用折叠面板，避免页面变成日志垃圾场。

### Dispatcher Queue Health

展示：

1. queued count
2. dead letter count
3. open fingerprint count
4. suppressed fingerprint count
5. last tick / last dispatch count / last error

## Safety Rules

1. 高风险 recurring workflow 默认 `auto_start=false`。
2. `Run Now` 对可能创建 requirement 的任务必须弹确认。
3. `Dry Run` 不产生业务副作用，是验证配置的默认方式。
4. Notification Dispatcher 可以后台 loop，因为它只消费已入队通知，不创建业务 requirement。
5. v1 不提供“新增任务”按钮，避免 operator 通过 UI 创建未经 review 的长期自动化。
6. 资金、结算、合约、auth、生产部署、外部付费动作不得通过 recurring workflow 自动执行。
7. `bug_log_sweep` 必须先获得数据库级 scheduler lease；后台 scheduler 与手动 Run Now 共用同一个 lock。

## Requirement Intake Fingerprint Gate

Bug sweep 的去重不能直接复用 Lark notification queue。原因是两者语义不同：

1. Notification queue 决定“是否发消息到 Lark”。
2. Requirement intake gate 决定“是否创建新的业务 requirement”。

因此系统使用独立的 `requirement_intake_fingerprints` 表治理错误到需求的 materialization：

```text
requirement_intake_fingerprints
  fingerprint_key
  source_kind
  source_key
  project_key
  project_root_path
  status: open | linked_requirement | resolved | suppressed | cooldown | reopened
  linked_requirement_id
  linked_workflow_run_id
  linked_release_id
  first_seen_at
  last_seen_at
  last_materialized_at
  resolved_at
  cooldown_until
  occurrence_count
  suppressed_count
  latest_evidence_json
  resolution_json
```

Materialization 规则：

1. 同一 fingerprint 首次出现且 discovery recommendation 允许时，创建 requirement。
2. 如果已有 active requirement 或 active workflow，重复错误只更新 occurrence/evidence，并复用原 requirement。
3. 如果 linked requirement 已终态但 release/observing 尚未写入 `resolved`，重复错误进入 `suppressed`，不创建新 requirement。
4. 如果 release/observing 已写入 `resolved`，同 fingerprint 再次出现会创建 `Regression:` requirement，并链接上一次 requirement/release。
5. severity 升级到 critical 可以突破 cooldown，但仍优先复用 active requirement，不重复建单。

上线后不要删除 fingerprint 标记。正确做法是由 release/observing 写入：

```text
status = resolved
resolved_at = <time>
linked_release_id = <release>
resolution_json = { pr_url, commit_sha, deployed_at, observing_window, recovery_signal }
```

这样系统才能区分“同一个未解决噪声还在刷屏”和“已修复后真实回归”。

## Scheduler Lock

`bug_log_sweep` 运行前必须获取：

```text
lock_key = scheduler:bug_log_sweep
```

锁记录保存在 `scheduler_locks`：

```text
scheduler_locks
  lock_key
  owner_id
  status: held | released | expired
  acquired_at
  expires_at
  heartbeat_at
  metadata_json
```

规则：

1. 后台 scheduler 和手动 Run Now 使用同一个 lock。
2. TTL 默认不少于 300 秒。
3. 运行成功或失败都释放 lock。
4. 进程崩溃后，过 `expires_at` 其他 worker 可以抢占。
5. 未获得 lock 时记录 `skipped_locked`，不报错、不重复执行。

## Notification Dispatcher Loop

Dispatcher 作为后台 daemon thread 随服务启动：

```text
OPS_NOTIFICATION_DISPATCHER_ENABLED=true
OPS_NOTIFICATION_DISPATCH_INTERVAL_SECONDS=5
```

行为：

1. 每个 tick 读取 queued notification events。
2. 更新 notification fingerprints。
3. 按 cooldown、severity upgrade、storm mode 判断发送或抑制。
4. 写入 notification deliveries。
5. 失败按 retry policy 推进，超过次数进入 dead letter。
6. `status_snapshot` 暴露到 `/api/recurring-workflows/health`。

它保留请求内 enqueue 后立即 dispatch 的兼容行为，但不再依赖新的 HTTP 请求来推进 retry / dead letter。

## Implementation Notes

v1 只把 **已有内置任务** 管理起来。后续如果要开放自定义 schedule，需要先实现：

1. workflow spec validator。
2. atom permission model。
3. schedule sandbox check。
4. human approval for activation。
5. kill switch / budget guard。

否则“自定义定时任务”会变成比 agent 自由执行更危险的黑盒自动化。

## Test Plan

后端：

1. `sync_recurring_workflows` 创建/更新内置 registry。
2. dry run 创建 `RecurringWorkflowRunRow` 且不改变业务数据。
3. 成功运行写 run history 并更新 `last_run_at / last_result_json`。
4. 失败运行写 `failed + error_excerpt`。
5. `/runs` 返回最近运行历史。
6. `/health` 返回 bug scheduler、notification dispatcher、registry 状态。
7. Notification Dispatcher 后台 loop 可以消费 queued retry event。
8. 同一 bug/error fingerprint 进入 requirement 后，重复出现只更新 `requirement_intake_fingerprints`，不重复创建 requirement。
9. resolved 后同 fingerprint 再出现，会创建 regression requirement。
10. 两个并发 `bug_log_sweep` 只有一个获得 scheduler lock，另一个记录 `skipped_locked`。

前端：

1. `/schedules` 展示内置 recurring workflows。
2. Health Overview 展示 Bug Scheduler 与 Notification Dispatcher。
3. Dry Run 后刷新 run history。
4. Run Now 前出现确认。
5. Run History 展示 status、dry_run、duration、result。
6. raw result 默认折叠。

## Assumptions

1. v1 只读管理内置任务，不支持新增/编辑自定义定时任务。
2. v1 不实现通用 schedule 自动运行所有 registry。
3. 当前真实自动定时运行的任务仍是 Bug Log Sweep Scheduler。
4. Notification Dispatcher 是告警可靠性的一部分，因此必须后台 loop。
5. 所有高风险 recurring workflow 的手动运行默认不 auto-start requirement。
