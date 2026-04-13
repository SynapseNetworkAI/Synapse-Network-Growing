---
id: ops-ci-release-gates
title: "CI/CD and Release Gates"
status: draft
created_at: 2026-04-13
updated_at: 2026-04-13
author: engineering-ops
---

# CI/CD and Release Gates

本文件记录 Synapse Network 工作区在自动化流水线中的 gate 约束，以及如何通过本仓库新增的 shell 工具跨仓触发昂贵检查。

正式的 Synapse `staging/prod` 部署治理拓扑见：

- [`03_Synapse_GCE_Deployment_Governance.md`](./03_Synapse_GCE_Deployment_Governance.md)

## 1. Pull Request CI

正常 PR gate 仍依赖各产品仓库自带的入口（例如 `Synapse-Network/scripts/ci/pr_checks.sh`）。本仓库提供的脚本用于 orchestration：

1. `scripts/ci/allow_expensive_branch.sh` —— 根据 `CI_BRANCH` / `GITHUB_REF_NAME` 判断当前分支是否属于「昂贵」类别，默认 pattern 为 `main`、`release/*`、`hotfix/*`。设置 `CI_FORCE_EXPENSIVE_BRANCH=1` 可强制通过 gate，`CI_EXPENSIVE_BRANCH_PATTERNS` 可自定义额外模式。
2. `scripts/ci/approval_automation.sh` —— 在 branch 通过 gate 时，进入 `../Synapse-Network` 并调用 `scripts/ci/run_pytest_checks.sh` 运行 `services/gateway-admin/tests/test_execution_worker.py`，从而验证审批自动化执行链路。

## 2. Expensive Branch Gate

该 gate 旨在让「审批自动化 / stale-memory refresh hook」只在真正要发布的分支自动运行，避免在日常迭代中频繁拉起 gateway-admin 的执行工人：

1. feature 分支：`allow_expensive_branch.sh` 返回非零，`approval_automation.sh` 打印 skip 日志后立即退出（仍然以 0 结束以免失败 PR）。
2. main / release / hotfix：gate 返回 0，`approval_automation.sh` 会跨仓运行 `gateway-admin` worker 回归，保证执行工人仍能消费 pending jobs。
3. 手动重放：在任何分支设置 `CI_FORCE_EXPENSIVE_BRANCH=1` 即可强制运行，支持分析或事故复盘。

命令示例：

```bash
# 跳过（feature 分支）
CI_BRANCH=feature/foo scripts/ci/approval_automation.sh

# 强制运行（例如在本地或 release pipeline）
CI_FORCE_EXPENSIVE_BRANCH=1 scripts/ci/approval_automation.sh
```

## 3. 验证与故障切换

运行 gate 时会自动调用目标仓库的虚拟环境安装脚本（`Synapse-Network/scripts/ci/run_pytest_checks.sh`）。若目标仓库路径不同，可设置 `TARGET_SYNAPSE_REPO=/path/to/Synapse-Network`。任何失败都会直接体现在脚本退出码中，供上层 CI 捕获。
