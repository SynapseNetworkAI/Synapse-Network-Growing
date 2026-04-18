---
id: openai-unified-runtime-architecture
title: Unified LLM Runtime and OpenAI Session Architecture
role: dev_rel
status: draft
created_at: 2026-04-11
updated_at: 2026-04-11
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing
---

# Unified LLM Runtime and OpenAI Session Architecture

## Problem

当前运行时配置把两个维度混在一起：

- `LLM_PROVIDER` 决定模型 API 来自哪里。
- `ORCHESTRATION_BACKEND` 决定任务怎么执行。

这导致几个明显问题：

1. 想切换到 `OpenAI + GPT-5.4` 时，除了配置 provider/model，还要知道 `ORCHESTRATION_BACKEND=legacy` 这种内部实现细节。
2. `openai` 只支持同步单次 `chat/completions`，没有 session / detached monitor / 轮询恢复能力。
3. session 能力目前只和 `copilot_sdk` 绑定，导致 “不用 Copilot，但要 session” 这个需求没有统一入口。
4. `task_runner.py`、`main.py`、`workflow_orchestrator.py`、`tasks.py` 都写死了 `copilot_sdk` 的特殊分支，无法平滑扩展第二种异步 runtime。

## Goals

1. 让 `.env` 以 LLM 配置为主，不要求用户理解内部后端实现。
2. 支持 `LLM_PROVIDER=openai` + `LLM_MODEL=gpt-5.4` + `LLM_EXECUTION_MODE=session`。
3. OpenAI session 不依赖 CLI，直接走官方 Responses API。
4. 保留旧配置兼容：已有 `ORCHESTRATION_BACKEND=copilot_sdk` 不失效。
5. 异步任务仍然通过现有任务表、日志表、workflow 同步机制工作。

## Non-Goals

- 本期不引入 Realtime API。
- 本期不做跨服务重启后的角色 session 持久恢复。
- 本期不重构整个 `CrewEngine`，只在 runtime 层增加 session 能力。

## Official OpenAI Basis

设计基于 OpenAI 官方文档的两个能力：

- Responses API 的 `previous_response_id` 可把多轮响应串成上下文链。
- Background mode 允许 `background=true` 后异步执行，再通过 retrieve 轮询最终状态。

这意味着我们不需要 `openai cli`，也不需要自建 session 协议。

## Proposed Configuration

### New Primary Config

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-5.4
LLM_EXECUTION_MODE=session
OPENAI_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
```

### Semantics

- `LLM_PROVIDER`
  - `openai | claude | copilot`
- `LLM_MODEL`
  - provider-specific model id
- `LLM_EXECUTION_MODE`
  - `sync`: synchronous single-shot execution
  - `session`: detached session-style execution with monitor polling

### Compatibility Layer

- If `ORCHESTRATION_BACKEND` is explicitly set, it still wins.
- If `ORCHESTRATION_BACKEND` is omitted:
  - `LLM_EXECUTION_MODE=sync` -> `legacy`
  - `LLM_EXECUTION_MODE=session` + `LLM_PROVIDER=openai` -> `openai_responses`
  - `LLM_EXECUTION_MODE=session` + `LLM_PROVIDER=copilot` -> `copilot_sdk`
- `LLM_EXECUTION_MODE=session` + unsupported provider falls back with a clear error.

## Runtime Model

### 1. Sync Runtime

- Backend id: `legacy`
- Behavior:
  - current `CrewEngine.execute()`
  - blocking, single request / single response

### 2. OpenAI Session Runtime

- Backend id: `openai_responses`
- Transport:
  - `POST /responses` with `background=true`
  - `GET /responses/{response_id}` for polling
- Context carry-over:
  - per role via `previous_response_id`

### 3. Copilot Session Runtime

- Backend id: `copilot_sdk`
- Existing behavior retained.

## OpenAI Session Flow

### Dispatch

```text
TaskRunner
  -> OpenAIResponsesTaskRuntime.execute()
     -> build system prompt + user packet
     -> lookup role session cache by agent_id
     -> POST /responses
        - model
        - instructions
        - input
        - background=true
        - previous_response_id? (if role session exists)
     -> save latest response id in role session cache
     -> return deferred TaskExecutionResult
```

### Monitor

```text
OpenAIResponsesTaskMonitor.poll_once()
  -> load tasks where status=running and runtime_backend=openai_responses
  -> GET /responses/{runtime_session_id}
  -> if completed:
       persist output.md
       mark task completed / pending_approval
       sync workflow step
     elif failed|cancelled|incomplete:
       mark task failed
       sync workflow step
     else:
       leave task running
```

## Role Session Reuse

和 Copilot 的角色 session 复用保持一致，但底层标识改成 `response_id` 链：

```python
_role_sessions: dict[str, OpenAIRoleSessionInfo]

@dataclass
class OpenAIRoleSessionInfo:
    response_id: str
    last_used_at: float
```

规则：

- 同一需求生命周期内，同一 role 的后续任务优先使用 `previous_response_id=<last response id>`。
- 需求完成/失败后清空内存 role session cache。
- 本期不做跨重启恢复；跨重启时允许重新开始新的上下文链。

## State and Artifacts

每个 task 仍输出到独立目录：

`roles/<agent_id>/outputs/task-<id>/`

OpenAI session runtime 产物：

- `output.md`
- `metadata.json`

`metadata.json` 至少包含：

- `response_id`
- `previous_response_id`
- `conversation_id`
- `status`
- `model`
- `provider`

## API / DB Impact

Declarative workflow runs should store OpenAI Responses session metadata on atom invocations and artifacts, not on legacy fixed workflow steps:

- `tasks.runtime_backend = "openai_responses"` remains valid for standalone task runtime records.
- `tasks.runtime_session_id = <response_id>` remains valid for standalone task runtime records.
- `atom_invocations.metadata_json.runtime_backend = "openai_responses"` should be used for declarative workflow atoms.
- `atom_invocations.metadata_json.runtime_session_id = <response_id>` should be used for declarative workflow atoms.

## Required Code Changes

| File | Change |
|------|--------|
| `server/config.py` | 新增 `LLM_EXECUTION_MODE`，增加 runtime backend 解析函数与兼容层 |
| `.env.example` | 更新统一配置说明 |
| `server/services/llm_adapter.py` | 为 OpenAI provider 增加 Responses API create/retrieve 能力 |
| `server/services/task_runtime.py` | 新增 `OpenAIResponsesTaskRuntime`，并统一 backend 选择 |
| `server/services/openai_responses_monitor.py` | 新增后台轮询 monitor |
| `server/main.py` | 根据解析后的 backend 启动对应 monitor |
| `server/services/task_runner.py` | 日志使用解析后的 backend，不再依赖旧 raw 配置语义 |
| `server/routers/tasks.py` | 创建/重试任务时记录真实 backend |
| `server/services/workflow_orchestrator.py` | 将 runtime terminate / deferred backend 判断从 `copilot_sdk` 特判改为可扩展逻辑 |
| `tests/` | 补配置解析、OpenAI session runtime、monitor、API 行为测试 |

## Validation Plan

自动化验证至少覆盖：

1. `ORCHESTRATION_BACKEND` 未设置时，`LLM_PROVIDER + LLM_EXECUTION_MODE` 能解析到正确 backend。
2. `openai + session` 返回 deferred 结果，并持久化 `runtime_session_id`。
3. 同 role 第二次执行会带上 `previous_response_id`。
4. monitor 在 response `completed` 时能写回输出并结束任务。
5. monitor 在 response `failed` / `incomplete` 时能把任务标记失败。
6. 显式 `ORCHESTRATION_BACKEND=copilot_sdk` 仍保持旧行为。

## Risks

| Risk | Mitigation |
|------|-----------|
| Responses API 状态字段和输出结构可能随官方演进变化 | 输出解析做宽松兼容：优先 `output_text`，再回退遍历 `output[].content[]` |
| background response 在极短任务上可能立即 completed | runtime 同时支持 immediate-complete 和 deferred |
| 角色 session 只在内存中 | 明确为第一阶段约束；后续如有需要再补 DB 级 role-chain 恢复 |
| 旧代码中存在多处 `copilot_sdk` 硬编码 | 统一抽到 backend 判定和 monitor 启动处，新增自动化覆盖 |
