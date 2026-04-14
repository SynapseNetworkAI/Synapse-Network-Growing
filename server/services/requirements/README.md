# `requirements/` 地图

负责 requirement 语义、来源、附件、审批和 family 去重。

## 公开入口

- `acceptance.py`
- `approval.py`
- `attachments.py`
- `family.py`
- `sources.py`

## 依赖边界

- 负责 requirement 本身的语义层，不负责 workflow 调度。
- 可以为 `workflows/` 提供 contract 和 metadata。

## 禁止依赖

- 不得依赖 `scheduling/`。
- 不得直接承担环境发布、promotion 或 rollback 控制面。

## 常见改动

- acceptance contract：`acceptance.py`
- execution approval：`approval.py`
- intake attachment：`attachments.py`
- family dedupe：`family.py`
- source registry / backlog materialization：`sources.py`

## 迁移映射

- `server.services.acceptance` -> `server.services.requirements.acceptance`
- `server.services.requirement_approval` -> `server.services.requirements.approval`
- `server.services.requirement_attachments` -> `server.services.requirements.attachments`
- `server.services.requirement_family` -> `server.services.requirements.family`
- `server.services.requirement_sources` -> `server.services.requirements.sources`
