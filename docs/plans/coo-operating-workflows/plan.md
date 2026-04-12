# Plan

## P0

### P0-R1 Role Operating Contract

状态：进行中

目标：

1. 把 `roles/*` 从 persona 文档升级成岗位契约
2. 把 requirement 的验收责任做成正式 acceptance contract
3. 把 requirement 的执行前放行做成正式 approval contract
4. 给 acceptance sweep 预留可定时触发的 dispatcher 骨架

实现：

1. 定义统一 role schema：`mission / input_channels / outputs / decision_rights / handoffs / metrics`
2. 为核心流程角色补齐首批岗位文档：
   1. `ops_intake_manager`
   2. `signal_analyst`
   3. `planner`
   4. `researcher`
   5. `executor`
   6. `reviewer`
   7. `tester`
   8. `portfolio_operator`
3. 组织架构页增加 role contract 摘要
4. requirement 新增 `acceptance_contract`
5. requirement 新增 `approval_status / approval_contract`
6. planner 后按 complexity tier / project count / incident 属性自动判定 auto-approve 还是 pending approval
7. scheduler 与 start 只允许 `approved / waived` requirement 自动执行
8. 新增 `acceptance dispatcher` 骨架接口，供定时任务后续接入

### P0-R2 Requirement Source Registry

状态：已完成

目标：

1. 明确 requirement 现在来自哪里，以及每种来源如何自动进入需求池

实现：

1. 建立 `requirement_source_registry`
2. 统一记录 `source / source_ref / intake_reason / confidence`
3. 提供统一的 `intake` 入口，把 `optimization signals` 与 `company review bundle` 接到同一条契约
4. 在需求池中展示来源分布和近期开启趋势

### P0-R3 Recurring Workflow Registry

状态：已完成

目标：

1. 让日常自动工作流成为一等对象，而不是散落在 cron 和脚本里

实现：

1. 定义 workflow registry：
   1. schedule
   2. trigger type
   3. owner role
   4. input query
   5. output action
2. 首批内置 workflow：
   1. morning intake sweep
   2. dispatcher loop
   3. closeout and compact sweep
   4. weekly operating review
3. 暴露统一 API：
   1. list / sync recurring workflows
   2. run workflow skeleton manually

## P1

### P1-R1 Daily Intake And Triage Loop

状态：已完成

目标：

1. 每天自动刷新 signal、incident、bundle 候选，并生成 requirement drafts

实现：

1. 早间刷新 `optimization_signals`
2. 汇总高价值 signals 和 incidents
3. 自动生成 requirement drafts 或 ready requirements
4. 对需要 operator 判断的项生成 daily intake summary

### P1-R2 Dispatcher And Follow-Through Loop

状态：已完成

目标：

1. 让 scheduler 像值班 COO 一样持续推进 ready work，而不是只做一次性启动

实现：

1. 固定频率运行 scheduler dispatch
2. 检查 stuck / paused / blocked requirements
3. 自动生成 follow-up actions：
   1. retry
   2. replan
   3. incident recovery
   4. approval reminder
4. 将 follow-through 结果固化到 recurring workflow `last_result`，供 operator 日常值班查看

### P1-R3 End-Of-Day Closeout Sweep

状态：已完成

目标：

1. 每天收敛运行链路，减少上下文膨胀和第二天的脏状态

实现：

1. 对长 requirement 做 compact
2. 对完成或失败的 requirement 写回 review snapshot
3. 刷新 company review runtime metrics
4. 生成 end-of-day summary artifact
5. 将 sweep 结果固化到 recurring workflow `last_result`，供第二天 operator 快速接手

## P2

### P2-R1 Weekly Operating Review Workflow

状态：已完成

目标：

1. 每周自动完成一次 company review 生成、bundle 生成和 operator package 准备

实现：

1. 定时刷新 company review
2. 生成 next-cycle requirement bundle
3. 生成 human gate / automation opportunity summary
4. 输出 weekly COO review package
5. 汇总 `morning_intake / dispatcher_loop / closeout_and_compact_sweep` 的 ritual 结果，进入 operator package 和 weekly review source snapshot

### P2-R2 Automation Candidate Backlog

状态：已完成

目标：

1. 把“值得自动化的点”稳定回流成 requirement backlog

实现：

1. human gate hotspots 自动生成 automation candidate requirements
2. incident recurrence 自动生成 recovery hardening requirements
3. budget pressure 自动生成 routing / budget tuning requirements
4. 将 `automation_candidate` 接入 requirement source registry、unified intake 和 daily intake loop，稳定回流到 backlog

### P2-R3 Operator Dashboard And Rituals

状态：已完成

目标：

1. 让 operator 真正像在管理一家公司，而不是逐条盯 task

实现：

1. 首页展示今日经营摘要
2. 增加 daily / weekly ritual views
3. 展示：
   1. today priorities
   2. blocked items needing judgment
   3. publish queue
   4. budget posture
   5. automation opportunities
4. 支持从首页直接运行 recurring rituals，并查看最新结果

## P3

### P3-R1 Role KPIs And Work Allocation

状态：待实现

目标：

1. 让 role 不只是“能做什么”，还要衡量“做得怎么样”

实现：

1. 角色级 KPI：
   1. completion rate
   2. reopen rate
   3. approval dependency
   4. average token cost
2. role workload / backlog 分配面板

### P3-R2 Autonomous COO Mode

状态：待实现

目标：

1. 在 operator 只看经营摘要和高风险审批的前提下，让 COO 流程稳定自主运行

实现：

1. 支持只对高风险事项发起 operator review
2. 低风险日常 workflow 自主运行
3. 失败时自动进入 incident / replan / follow-up requirement 链
