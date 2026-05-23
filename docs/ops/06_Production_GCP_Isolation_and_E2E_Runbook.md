---
id: production-gcp-isolation-and-e2e-runbook
title: "Production GCP Isolation And E2E Runbook"
role: dev_rel
status: ready
created_at: 2026-05-15
updated_at: 2026-05-15
author: codex
target_repo: Synapse-Network-Growing
---

# Production GCP Isolation And E2E Runbook

This runbook defines the environment split used by `/releases` for Synapse Network Cloud Run deploys.

## Isolation Matrix

| Surface | Staging | Production |
|---|---|---|
| GCP project | `fabled-archive-494108-k5` | `synapse-network-prod` |
| Release source | branch or main, with PR gate for non-main | `main` only |
| Ops Console action | `发布到 staging` | `发布到 production` with `YES` Human Gate |
| GitHub environment | optional staging runner policy | required `production` reviewers |
| WIF provider | staging provider secret | `PROD_GCP_WORKLOAD_IDENTITY_PROVIDER` |
| Deploy service account | staging deploy SA | `PROD_GCP_DEPLOY_SERVICE_ACCOUNT` |
| Artifact Registry | staging repo secret or `synapse-staging` | `PROD_ARTIFACT_REGISTRY_REPOSITORY` |
| Evidence bucket | staging evidence bucket | `PROD_EVIDENCE_BUCKET` |
| Secret Manager | staging secrets only | production secrets only |
| Cloud SQL | staging instance | production instance |
| Cloud Run services | `synapse-staging-*` | `synapse-prod-*` |
| Domains | staging subdomains | production domains such as `docs.synapse-network.ai` |

Staging and production must not share deploy service accounts, evidence buckets, Secret Manager values, Cloud SQL instances, or Cloud Run services.

## Production Gate

Production deploy is allowed only when all conditions are true:

1. Release Task environment is `production`.
2. Branch is `main`.
3. Operator enters `YES`.
4. Backend / migration / settlement services require the current `main` commit to have a successful staging DeploymentRecord for the same project and service. Frontend services `docs-front`, `user-front`, and `admin-front` may use direct production deploy from `main` after Human Gate and GitHub Environment review.
5. Target repository has production WIF secrets configured.
6. GitHub Environment `production` reviewer approval is granted.

Growing records the source staging deployment in `DeploymentRecord.metadata_json.sourceStagingDeploymentRecordId` when staging evidence is required. Frontend direct production deploy records `directProductionFrontendDeploy=true`; if a prebuilt image is attached, it also records `prebuiltImageDigest`.

Frontend production digest deploys should be built from a clean detached worktree and pushed to the production Artifact Registry:

```bash
cd /Users/cliff/workspace/agent/Synapse-Network

bash scripts/deploy/local_build_frontend_image.sh \
  --service docs-front \
  --environment production \
  --ref main \
  --release-task-id <release-task-id>
```

Without a prebuilt digest, the local production frontend runner falls back to a local build/push path. That path is valid but slower; prefer prebuilt digest promotion when possible.

## Pilot E2E

Use `docs-front` as the low-risk first production pilot.

1. Create a `/releases` production Release Task for `Synapse-Network · Docs Front`, branch `main`.
2. Prefer attaching a production prebuilt digest with `scripts/deploy/local_build_frontend_image.sh --service docs-front --environment production --ref main --release-task-id <id>`.
3. Confirm the Production Gate shows the current main commit and, if staging evidence is absent, explicitly displays `Direct frontend deploy`.
4. Click `发布到 production`, type `YES`, and submit.
5. Start `scripts/local/run_deploy_worker.py --once` or keep the local deploy runner loop running.
6. Wait for the local runner to finish. With `prebuilt_image_digest`, it should skip build and only validate digest, deploy, smoke, manifest, and write events.
7. Click `/releases` `刷新本地状态` if the page is already open.
8. Verify `/releases -> 上线记录` includes an `environment=production` row with local runner evidence and health passed.
9. Smoke `https://docs.synapse-network.ai/`.

## Full Service Order

After the pilot succeeds, promote services in this order to reduce blast radius:

1. `docs-front`
2. `user-front`
3. `admin-front`
4. `gateway-admin`
5. `gateway`
6. `provider-service`

If any deployment fails, keep the Release Task failed with the local runner event log and failure excerpt. Do not manually mark success. Fix the root cause and retry from the failed service.

## Modular Production Runner Map

Production deploy observability mirrors staging:

| Service | Local runner recipe |
|---|---|
| `gateway` | `local_deploy_runner:production:gateway` |
| `gateway-admin` | `local_deploy_runner:production:gateway-admin` |
| `admin-front` | `local_deploy_runner:production:frontends` |
| `user-front` | `local_deploy_runner:production:frontends` |
| `docs-front` | `local_deploy_runner:production:frontends` |
| `provider-service` | `local_deploy_runner:production:provider-service` |

Growing records the concrete runner recipe on each `DeploymentRecord.workflow_file` so failed production deploys can be traced to the exact local module runner.

## Rollback

Production rollback is not automatic in v1. Runtime rollback must use a previous successful production Online Record as the target and pass a separate Human Gate. Code rollback must use a revert branch, PR checks, merge to `main`, staging verification, then production promotion.
