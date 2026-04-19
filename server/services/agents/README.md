# `agents/` 地图

负责 agent、skill、上下文和 LLM 相关能力。

## 公开入口

- `loader.py`: agent 元数据加载。
- `matcher.py`: agent 匹配。
- `skills.py`: skill 加载与枚举。
- `context.py`: context 文件加载。
- `llm_adapter.py`: provider 适配。
- `crew_engine.py`: persona + skill + context 组装与执行。

## 依赖边界

- 可以依赖 `server.database`、`server.config`。
- 不应依赖 retired fixed-step orchestrator 或 legacy task runner。

## 常见改动

- 增加 skill 加载逻辑：改 `skills.py`
- 调整 provider 适配：改 `llm_adapter.py`
- 调整 agent / skill 匹配：改 `matcher.py`

## 迁移映射

- `server.services.agent_loader` -> `server.services.agents.loader`
- `server.services.agent_matcher` -> `server.services.agents.matcher`
- `server.services.skill_loader` -> `server.services.agents.skills`
- `server.services.context_loader` -> `server.services.agents.context`
- `server.services.execution_resolver` -> retired with the legacy task runner.
- `server.services.llm_adapter` -> `server.services.agents.llm_adapter`
- `server.services.crew_engine` -> `server.services.agents.crew_engine`
