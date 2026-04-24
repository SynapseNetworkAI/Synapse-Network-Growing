---
id: synapse-gce-deployment-governance
title: "Synapse Deployment Governance"
status: draft
created_at: 2026-04-13
updated_at: 2026-04-13
author: engineering-ops
---

# Synapse Deployment Governance

本文件固定 `Synapse-Network` 与 `Synapse-Network-Provider` 的发布控制面规则。旧版 GCE/SSH 部署已降级为历史 fallback；Synapse-Network staging 默认使用 GitHub Actions + Cloud Build + Cloud Run。

## 1. 固定部署策略

1. 不使用 Jenkins
2. 使用 GitHub Actions 执行部署
3. `Synapse-Network-Growing` 只做 deploy control plane，不直接持有 GCP 部署权限
4. Staging 支持按 branch 部署，但 workflow 必须冻结为 resolved commit SHA
5. Production 不允许直接部署 feature branch，只能 promote verified main/tag/staging manifest

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
4. Cloud Build image build scripts
5. Cloud Run migration/deploy/smoke scripts
6. rollback manifest and image-digest recovery commands

## 3. Promotion Rule

`production` promotion 前，必须已经存在同一 commit SHA 的 `staging success` 记录。

这条规则由 Growing 在 dispatch GitHub Actions 前先阻断。

## 4. Branch-Based Staging Deploy

Growing 可以让操作者选择 PR/feature branch 并点击 `Deploy Branch to Staging`。提交给 GitHub Actions 的关键输入是：

```json
{
  "source_ref_type": "branch",
  "source_ref": "codex/example-feature",
  "deploy_scope": "auto"
}
```

GitHub Actions 必须在执行开始时将 branch HEAD 解析成不可变 commit SHA，并在 deployment record metadata 中保存：

- `sourceRefType`
- `sourceRef`
- `resolvedCommitSha`
- `deployScope`
- `imageDigest`
- `cloudRunRevision`
- `evidenceUri`

部署记录不能只保存分支名。分支后续继续 push 时，必须形成新的 deployment record。

## 5. 当前控制面展示

Growing 当前会展示：

1. `Staging Status`
2. `Production Status`
3. `Last deployed SHA`
4. `Deploy History`
5. `Deploy To Staging`
6. `Promote To Production`
7. `Rollback`
8. `Deploy Scope`
9. `Release Manifest / Evidence URI`
