# `workflows/` 地图

负责 planner 与 orchestrator 等 requirement workflow 编排层。

## 公开入口

- `planner.py`
- `declarative.py`
- `orchestrator/`

## 依赖边界

- 可以依赖其他服务面。
- 是服务层里唯一允许跨 requirement/runtime/delivery 多面协同的编排层。

## 常见改动

- 规划输出与 step policy：`planner.py`
- 声明式 State Machine / Blackboard workflow：`declarative.py`
- requirement lifecycle、dispatch、validation、closeout：`orchestrator/`

## 迁移映射

- `server.services.workflow_planner` -> `server.services.workflows.planner`
- `server.services.workflow_orchestrator` -> `server.services.workflows.orchestrator`
