# Role-Based Session Reuse, Serial Execution & Prompt Optimization

> Design Doc — April 2026 (updated)

## Problem

### 1. Token 浪费

当前每个 task 创建全新 Copilot SDK session：
- `session_id = f"task-{timestamp_ms}"` — 每次新 ID
- `Popen(node run_session.mjs)` — 每次新进程
- `CopilotClient.createSession()` — 每次新 SDK session
- system prompt（persona + skill + project context）每次完整重发

以需求 #3 为例，6 个 step 中 3 个由 `cro_optimizer` 执行，但每个都重建 session，system prompt 重复发送 3 次。

### 2. 缺乏串行保证

当前 `start_requirement()` 只检查当前需求的 `blocked_by_count`，不检查是否有其他需求正在 `in_progress`。多个需求可以并发执行，导致：
- 同 role 的 session 混乱
- 资源竞争

## Solution

### Phase 1: Role-Based Session Reuse

**核心**：同一个 agent_id（role）在同一个需求生命周期内复用同一个 Copilot SDK session。后续 task 使用 `resumeSession()` + `session.send()` 追加 prompt，共享上下文。

#### 数据结构

```python
# CopilotSDKTaskRuntime 新增内存映射
_role_sessions: dict[str, RoleSessionInfo]  # agent_id -> session info

@dataclass
class RoleSessionInfo:
    session_id: str
    output_dir: Path
    last_used_at: float
```

#### 执行流程

```
CopilotSDKTaskRuntime.execute(persona, skill, description)
  agent_id = persona["role"]
  if agent_id in _role_sessions:
    info = _role_sessions[agent_id]
    → action="resume", session_id=info.session_id
    → 新 output_dir（每 task 独立产出）
    → resumeSession() + send new prompt
  else:
    → action="start", session_id=f"role-{agent_id}-{timestamp}"
    → createSession() + send prompt
    → _role_sessions[agent_id] = RoleSessionInfo(...)
```

#### 产出目录

每个 task 仍有独立的 `roles/{agent_id}/outputs/task-{id}/` 目录。Session 复用不影响产出隔离。

#### Session 清理

- `clear_role_sessions()` 方法：需求完成/失败时由 orchestrator 调用，清空映射。
- 确保需求结束时 session 断开，避免累积。

### Phase 2: Serial Requirement Execution

**核心**：同一时间只能有一个需求在 `in_progress` 状态。

#### 实现

1. `start_requirement()` 加全局守卫：
```python
running = db.query(RequirementRow).filter(
    RequirementRow.status == "in_progress",
    RequirementRow.id != requirement_id,
).count()
if running > 0:
    raise ValueError("另一个需求正在执行中，请等待完成后再启动。")
```

2. `create_requirement(auto_start=True)` 同样检查。

3. 需求完成/失败时的 `_refresh_run_status()` 调用 `clear_role_sessions()` 清理。

## Phase 3: Prompt Quality Optimization

### Problem

发给执行 agent 的 prompt 有两个问题：

1. **Plan artifact 以原始 JSON 注入**：`implementation_plan` artifact 包含大量 schema 元数据（file_scope、failure_policy、validation_targets），对执行 agent 完全无用，浪费 token。
2. **Step 边界不清晰**：`done_when_markdown` 只说"Write actual source code"，不限制 scope，导致 frontend_impl step 同时输出了后端代码。

### Solution

#### A) Plan Artifact → 精简 Markdown 转换

`_step_task_description()` 遇到 `implementation_plan` 类型的 artifact 时，调用 `_plan_artifact_to_markdown()` 将 JSON 转为精简 Markdown：

- 只保留 goal_summary、target_project、detected_phases、workflow_steps 列表、risks
- 删除 file_scope、failure_policy、acceptance_checks 等系统级字段
- 从 ~3000 字符 JSON 压缩到 ~500 字符 Markdown

#### B) Step 边界约束

在 `done_when_markdown` 中添加 `SCOPE:` 约束：

| Step | 约束 |
|------|------|
| frontend_impl | `SCOPE: Only implement frontend/client-side code. Do NOT implement backend/API code.` |
| backend_impl | `SCOPE: Only implement backend/API/server-side code. Do NOT implement frontend code.` |
| design | `SCOPE: Only produce design documents — do NOT write implementation code.` |
| test_impl | `Focus on integration tests and e2e tests. Unit tests should already exist from prior steps.` |

#### C) Predecessor Handoff Summary

执行 agent 的 prompt 现在包含前置 step 的 `handoff_summary_markdown`，而不是完整的 artifact body。这让下游 step 能快速理解上游结论。

## Implementation Changes

| File | Change |
|------|--------|
| `server/services/task_runtime.py` | `CopilotSDKTaskRuntime` 维护 `_role_sessions` 映射，`execute()` 判断复用/新建，新增 `clear_role_sessions()` |
| `copilot-sdk-runner/run_session.mjs` | resume 模式支持发送新 prompt |
| `server/services/workflow_orchestrator.py` | 串行守卫；`clear_role_sessions()`；`_step_task_description()` plan→MD 转换 + handoff summary |
| `server/services/workflow_planner.py` | `done_when_markdown` 加 SCOPE 边界约束 |
| `tests/` | 新增 session 复用 + 串行执行 + prompt 质量测试 |

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| 上下文窗口溢出 | 当前需求步骤 < 10，单需求内累积不会超限；后续可加 summarize |
| Session idle timeout | 已有 `resumeSession()` + stale recovery 机制 |
| resume 失败 | fallback 回 createSession()：清除 role 映射，重新建立 |
| Agent 仍然越界 | SCOPE 约束 + review step 兜底；后续可加 file_scope enforcement |
