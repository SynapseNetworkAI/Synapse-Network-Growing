---
id: taskboard-automation-test-plan
title: 任务看板自动化测试方案
status: verified
created_at: 2026-04-09
updated_at: 2026-04-09
author: CTO
target_repo: Synapse-Network-Growing
---

# 任务看板自动化测试方案

## 1. 目标

本方案用于验证任务看板改造后的三类核心能力：

1. 分类与筛选是否正确
2. 失败任务恢复链路是否可用
3. 前后端数据结构是否一致
4. 历史任务归属快照与重试时间线是否正确
5. 第三阶段批量重试、批量审批与右侧抽屉交互是否稳定

## 2. 测试目录与功能关联

当前仓库测试目录与功能职责的关系如下：

### `tests/`

面向 FastAPI 后端接口、数据库迁移、任务执行状态机。

与任务看板功能直接相关的文件：

1. `tests/test_tasks_api.py`
   负责任务创建、查询、运行、重试、分类字段、筛选参数。
2. `tests/test_crew_integration.py`
   负责真实执行链路、失败写回、日志、异步执行和 LLM 调用适配。
3. `tests/test_approvals_api.py`
   负责待审批任务进入审批流后的接口行为。
4. `tests/conftest.py`
   提供共享测试数据库和任务执行 patch，保证看板功能测试可重复执行。

### `dashboard/tests/`

面向 React 页面交互和前端状态切换。

与任务看板功能直接相关的文件：

1. `dashboard/tests/TaskBoard.test.tsx`
   负责筛选器、分组展示、失败摘要、重试按钮、批量重试、右侧抽屉、创建表单预填、轮询等 UI 行为。
2. `dashboard/tests/Approvals.test.tsx`
   负责审批中心待审批渲染、批量批准/拒绝的选择态与提交行为。

### `docs/test/`

面向测试方案、缺陷记录、验证结论，不承载可执行测试。

与当前功能相关的文件：

1. `docs/test/taskboard-automation-test-plan.md`
   记录任务看板自动化测试范围、策略、覆盖矩阵。
2. `docs/test/bugfix.md`
   记录在实现和验证过程中发现并修复的问题。

结论：当前测试目录规划与功能是有关联的，职责分层也基本清晰。

1. `tests/` 管后端能力
2. `dashboard/tests/` 管前端交互
3. `docs/test/` 管方案与缺陷追踪

这是合理结构，不建议为了这次任务再重构测试目录。

## 3. 覆盖范围

### 3.1 后端接口

任务看板改造需要新增或验证的后端能力：

1. 任务返回持久化字段：`project_id`、`project_label`、`agent_group`
2. 任务返回失败摘要字段：`last_error_message`
3. 任务返回重试链路字段：`retry_of_task_id`、`attempt_no`
4. 支持按 `agent_group`、`project_id`、`only_anomalies` 过滤
5. 支持 `POST /api/tasks/{id}/retry`
6. 支持 `GET /api/tasks/{id}/history`
7. 历史任务在 Agent 分组变化后仍保留原始 `project_id/agent_group` 快照
8. 支持 `POST /api/tasks/bulk-retry`
9. 支持 `POST /api/approvals/bulk-decide`

### 3.2 前端页面

任务看板改造需要新增或验证的前端能力：

1. 顶部 `状态` + `项目` 筛选
2. 高级筛选中的 `Agent组`、`Agent`、`搜索`、`仅看异常`
3. 按项目分组展示任务
4. 失败任务直接显示错误摘要
5. 失败任务支持 `重试`
6. 失败任务支持 `编辑后重试`
7. 创建表单支持显示 Agent 提示信息
8. 运行中任务继续轮询
9. 详情区展示重试历史时间线
10. 失败/拒绝任务支持多选并批量重试
11. 审批中心支持多选并批量批准/拒绝
12. 任务详情使用右侧抽屉而非卡片内联展开
13. 创建任务时支持自动推荐 Agent / Skill
14. 低置信度推荐时阻止直接提交并要求人工确认

## 4. 用例矩阵

### 后端用例

1. 创建任务后，列表接口返回派生分类字段
2. `agent_group` 过滤返回正确任务
3. `project_id` 过滤返回正确任务
4. `only_anomalies=true` 仅返回异常任务
5. `retry?mode=run_now` 生成新任务并立即置为 `running`
6. `retry?mode=edit_first` 生成新任务但保持 `pending`
7. 对非失败任务调用 retry 返回 400
8. `history` 接口返回按 attempt 排序的重试链
9. 任务创建后，如果 Agent 分组后续变化，任务接口仍返回原始快照
10. `bulk-retry` 能按请求顺序批量创建重试任务
11. `bulk-retry` 对非失败/拒绝任务返回 400
12. `bulk-decide` 能批量更新审批与对应任务状态
13. `suggest-execution` 能根据任务描述返回推荐 Agent / Skill
14. 自动创建任务在高置信度时补齐 `agent_id` / `skill_name`
15. 自动创建任务在低置信度时返回 409 并附带推荐结果

### 前端用例

1. 渲染项目分组标题
2. 渲染失败摘要
3. 点击 `重试` 调用 retry API
4. 点击 `编辑后重试` 打开表单并预填原任务
5. 变更 `Agent组` 筛选时重新请求任务列表
6. 运行中任务持续轮询
7. 展开详情时请求并渲染重试历史时间线
8. 多选失败任务后显示批量重试工具条并调用批量接口
9. 点击任务卡片后以右侧抽屉展示详情
10. 审批中心多选后显示批量审批工具条并调用批量接口
11. 仅输入任务描述时，表单展示自动推荐的 Agent / Skill
12. 低置信度推荐时，表单展示候选项并在确认前阻止提交

## 5. 执行命令

后端：

```bash
/Users/cliff/workspace/agent/.venv/bin/python -m pytest tests/test_tasks_api.py tests/test_approvals_api.py tests/test_crew_integration.py -q
python -m pytest tests/ -v
```

前端：

```bash
cd dashboard
yarn test
```

UI 验证：

1. 启动后端与前端
2. 打开任务看板页面
3. 创建失败任务或查看已有失败任务
4. 验证失败摘要、重试按钮、批量重试工具条、筛选器和项目分组
5. 打开失败任务右侧抽屉，验证重试历史时间线
6. 切换到审批中心，验证批量审批工具条与批量批准动作
7. 截图作为最终结果凭证

## 6. 通过标准

本次任务通过需要同时满足：

1. 后端 pytest 全通过
2. 前端 vitest 全通过
3. UI 截图能看到批量重试工具条或右侧抽屉，以及批量审批工具条
4. 若实现过程中发现 bug，必须登记到 `docs/test/bugfix.md` 并修复后重新验证

## 7. 最新验证结果

验证时间：2026-04-09

后端：

```bash
/Users/cliff/workspace/agent/.venv/bin/python -m pytest tests/test_tasks_api.py tests/test_approvals_api.py tests/test_crew_integration.py -q
```

结果：`69 passed`

前端：

```bash
cd dashboard
yarn test
```

结果：`43 passed`

UI 结果：

1. 页面已展示持久化后的 `project_id` / `agent_group` 标签
2. TaskBoard 已展示批量重试工具条与右侧详情抽屉，抽屉内可见三段重试历史时间线（Attempt #1 / #2 / #3）
3. Approvals 页面已展示批量审批工具条，并验证批量批准交互
4. 验证截图将更新到 `docs/test/taskboard-phase3-validation.png` 与 `docs/test/approvals-phase3-validation.png`