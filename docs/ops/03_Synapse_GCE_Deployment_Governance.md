---
id: synapse-gce-deployment-governance
title: "Synapse Deployment Governance"
status: draft
created_at: 2026-04-13
updated_at: 2026-04-25
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
10. `/releases` 的 `上线记录`，只展示成功的 DeploymentRecord

## 6. 当前上线步骤

Staging 发布链路保持“任务意图”和“真实上线”分离：

1. 在 `/releases` 创建 Release Task。
2. 选择目标项目 / 服务和 GitHub 远端分支。
3. 如果分支没有 PR，点击 `提交 PR`。
4. 等待 PR Checks 通过。Checks pending / failed 时不得发布 staging。
5. Checks 通过后，由 Operator 点击 `发布到 staging`。
6. 查看 `/releases` 的 `上线记录`，确认 GitHub Actions、Cloud Run deploy、revision / image / manifest 和 health check 成功。
7. Production 不使用 staging 快捷按钮。Production 默认从 `main` / tag / verified staging manifest promote，并必须经过 Human Gate。

Staging 不要求先合并到 `main`。它允许从已提交 PR 且 checks 通过的 release branch 发布，用于验证分支在真实 staging 环境的行为。Production 的默认来源必须收敛到 `main`、tag 或已经验证的 staging manifest。

## 7. 上线记录

`上线记录` 是只读账本，只来自 `deployment_records.status=succeeded`。

上线记录必须能回答：

1. 哪个 project / service 上线了。
2. 发布到哪个 environment。
3. 使用哪个 branch 和 commit SHA。
4. 触发了哪个 GitHub Actions run。
5. Cloud Run revision、image tag / digest、manifest / evidence URI 是什么。
6. health check 是否通过。
7. 该记录是否来自某个 Release Task。

上线记录不得混入 `requested`、`failed`、`cancelled` Release Task，也不得把人工备注伪造成真实上线结果。

## 8. 回滚说明

回滚分两类：

1. Runtime rollback：选择 `上线记录` 中的历史成功 DeploymentRecord，把其中的 commit / image / manifest 作为 rollback target，创建 rollback deployment request，并进入 Human Gate。v1 不提供直接 rollback 快捷按钮。
2. Code revert：当需要撤回代码变更时，新建 revert 分支，提交 PR，等待 PR checks 通过并合并到 `main`，再按正常发布流程上线。

不要默认“新建一个回滚分支再发布”来处理运行时回滚。运行时回滚优先复用历史成功上线记录的不可变产物；代码级回滚才走新分支 / PR / merge / release。

Drop Goal、普通 Release Task PATCH、staging deploy API 都不得触发 production rollback。Production deploy / rollback 始终必须通过 Human Gate。
