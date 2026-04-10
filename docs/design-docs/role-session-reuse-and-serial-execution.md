# Role-Based Session Reuse & Serial Requirement Execution

> Design Doc — April 2026

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

## Implementation Changes

| File | Change |
|------|--------|
| `server/services/task_runtime.py` | `CopilotSDKTaskRuntime` 维护 `_role_sessions` 映射，`execute()` 判断复用/新建，新增 `clear_role_sessions()` |
| `copilot-sdk-runner/run_session.mjs` | resume 模式支持发送新 prompt（`sendPrompt` 参数支持 resume 时传入） |
| `server/services/workflow_orchestrator.py` | `start_requirement()` 加串行守卫；需求完成时调 `clear_role_sessions()` |
| `server/services/copilot_sdk_monitor.py` | `_complete_task` / `_fail_task` 不变，stale recovery 兼容 role session |
| `tests/` | 新增 session 复用 + 串行执行测试 |

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| 上下文窗口溢出 | 当前需求步骤 < 10，单需求内累积不会超限；后续 Phase 3 可加 summarize |
| Session idle timeout | 已有 `resumeSession()` + stale recovery 机制 |
| resume 失败 | fallback 回 createSession()：清除 role 映射，重新建立 |
