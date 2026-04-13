---
id: synapse-gce-deployment-governance
title: "Synapse GCE Deployment Governance"
status: draft
created_at: 2026-04-13
updated_at: 2026-04-13
author: engineering-ops
---

# Synapse GCE Deployment Governance

本文件固定 `Synapse-Network` 与 `Synapse-Network-Provider` 的最低机器费用上线方案。

## 1. 固定部署策略

1. 只使用 `2` 台 GCE
2. `staging-vm` 承载两个仓库的 staging 服务
3. `prod-vm` 承载两个仓库的 production 服务
4. 不使用 Jenkins
5. 使用 GitHub Actions 执行部署
6. `Synapse-Network-Growing` 只做 deploy control plane，不直接 SSH

## 2. 责任边界

### Growing 负责

1. requirement 是否已经 review-ready
2. deploy trigger 按钮
3. deployment records
4. staging / production 环境状态
5. production promotion gate
6. rollback 审计记录

### 目标仓库负责

1. `pr-ci.yml`
2. `deploy-staging.yml`
3. `deploy-production.yml`
4. `scripts/deploy/staging.sh`
5. `scripts/deploy/production.sh`
6. `scripts/deploy/rollback.sh`

## 3. Promotion Rule

`production` promotion 前，必须已经存在同一 commit SHA 的 `staging success` 记录。

这条规则由 Growing 在 dispatch GitHub Actions 前先阻断。

## 4. 当前控制面展示

Growing 当前会展示：

1. `Staging Status`
2. `Production Status`
3. `Last deployed SHA`
4. `Deploy History`
5. `Deploy To Staging`
6. `Promote To Production`
7. `Rollback`
