# `workflows/orchestrator/` 地图

这是 requirement workflow 的编排分面目录。`server.services.workflows.orchestrator` 已经是唯一稳定入口，真实实现按责任分组落在本目录子模块中。

## 责任分面

- `creation.py`: requirement create / revise / dependencies
- `planning.py`: planner 调用、计划 artifact、计划失败
- `dispatch.py`: step dispatch、runtime 对接、pause / sync
- `file_changes.py`: baseline、snapshot、tracked repo change
- `handoff.py`: brief、handoff、compact packet、stale memory packet
- `validation.py`: validation contract、acceptance refresh、bugfix loop
- `artifacts.py`: runtime/incident/budget/project-change artifacts
- `closeout.py`: delivery branch、review PR、closeout gate、terminalization
- `queue.py`: auto advance、queue scheduling、same-project chaining

## 当前实现状态

- `__init__.py` 负责对外稳定导出。
- 真实实现按 `creation / planning / dispatch / handoff / artifacts / validation / closeout / queue` 分面组织。
- 后续新增 orchestrator 逻辑应直接进入对应子模块，而不是回写到旧 flat 文件。
