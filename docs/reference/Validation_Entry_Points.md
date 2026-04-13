---
id: validation-entry-points
title: "Validation Entry Points"
status: draft
created_at: 2026-04-13
updated_at: 2026-04-13
author: engineering-ops
---

# Validation Entry Points

## 1. Repository-level shortcuts

| Command | Purpose |
|---------|---------|
| `scripts/ci/approval_automation.sh` | 在昂贵分支触发 `Synapse-Network/services/gateway-admin/tests/test_execution_worker.py`，验证审批自动化 worker。|
| `scripts/ci/allow_expensive_branch.sh <branch>` | 单独检测某分支是否触发昂贵 gate，返回码 0/1 可直接用于 CI `if` 条件。|

> **Note:** `approval_automation.sh` 会自动跳转到 `../Synapse-Network`。若仓库布局不同，设置 `TARGET_SYNAPSE_REPO=/alt/path` 覆盖默认路径。将 `CI_FORCE_EXPENSIVE_BRANCH=1` 传给脚本可在任意分支强制运行。

## 2. Branch policy

- 默认昂贵分支模式：`main`、`release/*`、`hotfix/*`。
- 自定义：向 `CI_EXPENSIVE_BRANCH_PATTERNS` 写入以空格分隔的 glob pattern。
- 跳过：普通 feature 分支直接得到 `skip` 提示，脚本仍返回 0 以免干扰 PR CI。

## 3. Local smoke

当需要手动验证审批自动化或复现 stale-memory refresh hook，可执行：

```bash
CI_FORCE_EXPENSIVE_BRANCH=1 scripts/ci/approval_automation.sh
```

脚本会自动创建/复用 `Synapse-Network/services/gateway-admin/.venv`，并运行 `pytest tests/test_execution_worker.py -q` 以保证执行工人可以消费 pending approvals。
