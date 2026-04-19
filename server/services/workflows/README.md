# `workflows/` 地图

负责 declarative state machine、planner adapter 与 workflow 编排层。

## 公开入口

- `declarative.py`
- `planner_provider.py`
- `verification_agent.py`
- `reset.py`

## 依赖边界

- 可以依赖其他服务面。
- 是服务层里唯一允许跨 requirement/runtime/delivery 多面协同的编排层。

## 常见改动

- LLM / Codex planner adapter：`planner_provider.py`
- 声明式 State Machine / Blackboard workflow：`declarative.py`
- workflow verification interpretation：`verification_agent.py`
- local destructive reset helpers：`reset.py`
- requirement lifecycle、assets、workflow start：`server/services/requirements/service.py`
- release actions：`server/services/releases/service.py`

## 迁移映射

- `server.services.workflow_planner` -> retired; use `server.services.requirements.service` for requirement assets and `server.services.workflows.planner_provider` for model calls.
- `server.services.workflow_orchestrator` -> retired; use `server.services.workflows.declarative`.
