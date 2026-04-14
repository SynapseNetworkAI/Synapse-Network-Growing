# `workflows/` 地图

负责 planner 与 orchestrator 等 requirement workflow 编排层。

## 公开入口

- `planner.py`
- `orchestrator/`

## 依赖边界

- 可以依赖其他服务面。
- 是服务层里唯一允许跨 requirement/runtime/delivery 多面协同的编排层。

## 禁止依赖

- `routers/` 不得越过本目录 facade 直接依赖更深层子模块。
- 不得把项目策略、requirement 语义、delivery 控制逻辑重新堆回单一巨型文件。

## 常见改动

- 规划输出与 step policy：`planner.py`
- requirement lifecycle、dispatch、validation、closeout：`orchestrator/`

## 迁移映射

- `server.services.workflow_planner` -> `server.services.workflows.planner`
- `server.services.workflow_orchestrator` -> `server.services.workflows.orchestrator`
