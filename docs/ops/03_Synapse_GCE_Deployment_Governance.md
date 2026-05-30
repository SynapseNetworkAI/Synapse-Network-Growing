---
id: synapse-gce-deployment-governance
title: "Synapse Deployment Governance"
status: ready
created_at: 2026-04-13
updated_at: 2026-05-17
author: engineering-ops
---

# Synapse Deployment Governance

本文件固定 `Synapse-Network` 与 `Synapse-Network-Provider` 的发布控制面规则。两者 staging / production 默认使用 Growing 本地 Deploy Runner + GCP service account impersonation + Cloud Build/Docker build + Cloud Run，由 Growing 统一记录 Release Task、DeploymentRecord、append-only deploy events 和上线记录。Staging GCP project 固定为 `fabled-archive-494108-k5`；production GCP project 固定为 `synapse-network-prod`。

## 1. 固定部署策略

1. 不使用 Jenkins
2. 不使用远端 Actions 执行 CI/CD；GitHub 只保留代码托管和 review
3. `Synapse-Network-Growing` 是 deploy control plane；真实写 GCP 的动作由本机 local runner 子进程执行
4. Staging 支持按 branch 部署，但 runner 必须冻结为 resolved commit SHA
5. Production 不允许直接部署 feature branch，只能 promote verified main staging manifest / immutable digest

## 2. 责任边界

### Growing 负责

1. requirement 是否已经 review-ready
2. deploy trigger 按钮
3. deployment records
4. staging / production 环境状态
5. production promotion gate
6. rollback 审计记录

### 目标仓库负责

1. Dockerfiles and build scripts
2. Cloud Run migration/deploy/smoke scripts
3. rollback manifest and image-digest recovery commands
4. service-owned schema migration scripts

当前目标仓库策略：

| Project | Service key | Staging runner | GCP execution |
|---|---|---|---|
| `Synapse-Network` | `gateway` | `scripts/local/deploy_synapse_staging.sh` | local runner + staging deploy service account |
| `Synapse-Network` | `gateway-admin` | `scripts/local/deploy_synapse_staging.sh` | local runner + staging deploy service account |
| `Synapse-Network` | `admin-front`, `user-front`, `docs-front` | `scripts/local/deploy_synapse_staging.sh` | local runner + staging deploy service account |
| `Synapse-Network-Provider` | `provider-service` | `scripts/local/deploy_synapse_provider_staging.sh` | local runner + staging deploy service account |

Production 使用统一的 local promote runner。所有 production deploy 都必须从同 service / same commit 的 successful staging DeploymentRecord 读取 immutable digest；production 阶段不重新 build。

| Project | Service key | Production runner |
|---|---|---|
| `Synapse-Network` | `gateway` | `scripts/local/promote_synapse_production.sh` |
| `Synapse-Network` | `gateway-admin` | `scripts/local/promote_synapse_production.sh` |
| `Synapse-Network` | `admin-front`, `user-front`, `docs-front` | `scripts/local/promote_synapse_production.sh` |
| `Synapse-Network-Provider` | `provider-service` | `scripts/local/promote_synapse_production.sh` |

| Local runner env | Purpose |
|---|---|
| `LOCAL_DEPLOY_IMPERSONATE_SERVICE_ACCOUNT` | Optional production/staging deploy service account impersonation, applied only to subprocess env / command flags |
| `SYNAPSE_PROD_GCP_PROJECT_ID` | Must be `synapse-network-prod` |
| `SYNAPSE_PROD_GCP_REGION` | Production Cloud Run region |
| `SYNAPSE_PROD_ARTIFACT_REPOSITORY` | Production Artifact Registry repo |

Growing 的 `/releases` 仍然是一个统一发布入口，但后端会按 `service_key`
选择对应 local runner command。不要让 operator 手工维护这张映射，也不要把所有
服务继续塞进一个不可诊断的 mega script。

## 3. Promotion Rule

`production` promotion 前，必须已经存在同一 project / service / commit SHA 的 `staging success` 记录。Production Release Task 必须绑定一个确定的 `target_commit_sha`；如果是旧任务没有该字段，Growing 只能用最近一次同服务 `main` staging success 作为兼容 evidence，并在 dispatch 前把该 commit 写回任务。Production gate 不允许每次刷新时无声追随最新 moving `main`。

这条规则由 Growing 在创建 local production deployment record 前先阻断。

Production 只允许 `main`。Growing 的 Release Task production deploy endpoint 会在创建 local deploy record 前验证：

1. task environment 是 `production`。
2. branch 是 `main`。
3. operator 输入 `YES`。
4. 同一 `project_key + service_key + target_commit_sha` 已有 staging `DeploymentRecord(status=succeeded, health_status=passed|healthy|manual_verified)`。
5. staging DeploymentRecord metadata 中有 `imageDigest` / manifest digest；缺失则 fail closed。

Production DeploymentRecord metadata 必须写入 `gcpProject=synapse-network-prod`、`region=us-central1`、`chain=arbitrum-one`、`requiresSuccessfulStagingDigest=true`、`sourceStagingDeploymentRecordId`、`deployScope`、`environmentIsolationVersion=v1`、`deploy_repo_full_name` 和 `service_key`。

## 4. Branch-Based Staging Deploy

Growing 可以让操作者选择 branch 并点击 `Deploy Branch to Staging`。Local runner 必须在执行开始时将 branch HEAD 解析成不可变 commit SHA，并在 deployment record metadata 中保存：

- `sourceRefType`
- `sourceRef`
- `resolvedCommitSha`
- `imageDigest`
- `cloudRunRevision`
- `manifest`

`Synapse-Network` staging 的服务到 local runner 映射固定为：

| Service key | Runner script |
|---|---|
| `gateway` | `scripts/local/deploy_synapse_staging.sh` |
| `gateway-admin` | `scripts/local/deploy_synapse_staging.sh` |
| `admin-front` | `scripts/local/deploy_synapse_staging.sh` |
| `user-front` | `scripts/local/deploy_synapse_staging.sh` |
| `docs-front` | `scripts/local/deploy_synapse_staging.sh` |

部署记录不能只保存分支名。分支后续继续 push 时，必须形成新的 deployment record。

Staging local deploy metadata 也必须写死环境隔离字段，不允许依赖操作者当前 shell 猜环境：

- `gcpProject=fabled-archive-494108-k5`
- `region=us-central1`
- `chain=arbitrum-sepolia`
- `gatewayCallbackUrl=https://api-staging.synapse-network.ai/internal/webhooks/alchemy/deposits`
- `environmentIsolationVersion=v1`

Local runner command 必须显式带 `--project` 和 `--region`。脚本启动后还要再做一次 fail-closed preflight：

1. 打印 active gcloud account、target project、target region、target service、target repo。
2. 校验 target project 与当前环境是否一致。
3. 校验 active account 能访问 target project。
4. 允许执行 `gcloud config set project <target-project>` 作为显式对齐，但真正信任根仍然是每条 `gcloud` 命令上的 `--project`。

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
2. 选择目标项目 / 服务和分支。
3. 如果选择 `main` 分支，可以直接由 Operator 点击 `发布到 staging`；`main` 已经是主干事实。
4. 如果选择非 `main` 分支且没有 PR，点击 `提交 PR`。
5. 等待 PR Checks 通过。非 `main` 分支 Checks pending / failed 时不得发布 staging。
6. Checks 通过后，由 Operator 点击 `发布到 staging`。
7. Local deploy runner 从 Postgres 抢占 `DeploymentRecord(trigger_source=local_deploy_runner)` 并执行真实 GCP 部署。
8. 查看 `/releases` 的 `上线记录`，确认 target runner、revision / image digest / manifest，以及 health check 成功。
9. 如果 staging 发布的是 `gateway`，operator 还必须按 `Synapse-Network` 仓库 runbook 收口 staging Alchemy webhook：
   - app=`synapse-network-staging`
   - chain=`Arbitrum Sepolia`
   - callback=`https://api-staging.synapse-network.ai/internal/webhooks/alchemy/deposits`
   - contract=`0x0bA1dcE1Cc8d877052ab1C3CE2362830459D8FF4`
   - signing key -> `synapse-staging-alchemy-deposit-webhook-signing-key`
10. Production 不使用 staging 快捷按钮。Production 默认从 `main` 的 verified staging commit/digest promote，并必须经过 Growing Human Gate。

Staging 对 `main` 与非 `main` 分支采用不同 gate：`main` 可以直接发布 staging；非 `main` 分支不要求先合并到 `main`，但必须先提交 PR 且 checks 通过，用于验证分支在真实 staging 环境的行为。Production v1 的来源必须收敛到 `main` 且同 commit 已经在 staging 成功。

## 7. 上线记录

`上线记录` 是只读账本，只来自 `deployment_records.status=succeeded`。
如果 Operator 手动把 Release Task 标记为已完成，后端必须先创建或绑定一条 `manual_completion` 成功 DeploymentRecord，再让它进入上线记录；UI 不得直接把 Release Task 当作上线事实。

上线记录必须能回答：

1. 哪个 project / service 上线了。
2. 发布到哪个 environment。
3. 使用哪个 branch 和 commit SHA。
4. 由哪个 local runner / command 执行。
5. Cloud Run revision、image tag / digest、manifest / evidence URI 是什么。
6. health check 是否通过。
7. 该记录是否来自某个 Release Task。

上线记录不得混入 `requested`、`failed`、`cancelled` Release Task，也不得把人工备注直接伪造成真实上线结果。Local runner 必须把 stdout/stderr 写入 append-only deployment events，并在成功时写回 manifest / revision / image digest。同步只读取 Postgres 中的 local runner 状态，不调用外部 CI/CD 系统。

## 8. 回滚说明

回滚分两类：

1. Runtime rollback：选择 `上线记录` 中的历史成功 DeploymentRecord，把其中的 commit / image / manifest 作为 rollback target，创建 rollback deployment request，并进入 Human Gate。v1 不提供直接 rollback 快捷按钮。
2. Code revert：当需要撤回代码变更时，新建 revert 分支，提交 PR，等待 PR checks 通过并合并到 `main`，再按正常发布流程上线。

不要默认“新建一个回滚分支再发布”来处理运行时回滚。运行时回滚优先复用历史成功上线记录的不可变产物；代码级回滚才走新分支 / PR / merge / release。

Drop Goal、普通 Release Task PATCH、staging deploy API 都不得触发 production rollback。Production deploy / rollback 始终必须通过 Human Gate。
