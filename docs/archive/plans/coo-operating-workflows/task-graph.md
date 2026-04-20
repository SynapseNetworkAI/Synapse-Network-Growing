# Task Graph

## Dependency Order

1. `P0-R1 Role Operating Contract`
2. `P0-R2 Requirement Source Registry`
3. `P0-R3 Recurring Workflow Registry`
4. `P1-R1 Daily Intake And Triage Loop`
5. `P1-R2 Dispatcher And Follow-Through Loop`
6. `P1-R3 End-Of-Day Closeout Sweep`
7. `P2-R1 Weekly Operating Review Workflow`
8. `P2-R2 Automation Candidate Backlog`
9. `P2-R3 Operator Dashboard And Rituals`
10. `P3-R1 Role KPIs And Work Allocation`
11. `P3-R2 Autonomous COO Mode`

## Critical Path

1. 先定义 role contract，不然后面的 workflow 没有明确 owner
2. 再定义 requirement source registry，不然后面的 intake 没有稳定输入
3. 再定义 recurring workflow registry，不然后面的定时任务会散落实现
4. 完成 daily intake / dispatch / closeout 三件套后，系统才有“每天上班”的基础
5. weekly operating review 和 automation backlog 是公司级经营层
6. role KPI 和 autonomous COO mode 是稳定运行后的增强层

## Parallelizable Work

以下工作可以并行推进：

1. `P0-R1` 和 role 文档编写
2. `P0-R2` 的 source registry 后端与需求池 UI 展示
3. `P0-R3` 的 workflow registry 后端与定时任务 runner
4. `P2-R3` 的 operator dashboard 与 ritual view 设计
