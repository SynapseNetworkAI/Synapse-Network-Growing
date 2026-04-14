# `signals/` 地图

负责 incident taxonomy、optimization signal 与 template。

## 公开入口

- `incidents.py`
- `optimization_signals.py`
- `optimization_templates.py`

## 依赖边界

- 可以依赖 project intelligence 与 requirement source metadata。
- 不负责执行 workflow。

## 禁止依赖

- 不得直接 dispatch workflow step。
- 不得把 signal 聚合逻辑和 requirement/release 控制面混写。

## 迁移映射

- `server.services.incidents` -> `server.services.signals.incidents`
- `server.services.optimization_signals` -> `server.services.signals.optimization_signals`
- `server.services.optimization_templates` -> `server.services.signals.optimization_templates`
