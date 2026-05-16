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
4. The current `main` commit has a successful staging DeploymentRecord for the same project and service.
5. Target repository has production WIF secrets configured.
6. GitHub Environment `production` reviewer approval is granted.

Growing records the source staging deployment in `DeploymentRecord.metadata_json.sourceStagingDeploymentRecordId`.

## Pilot E2E

Use `docs-front` as the low-risk first production pilot.

1. Deploy `docs-front` from `main` to staging and wait for `DeploymentRecord.status=succeeded` plus `health_status=passed`.
2. Create a `/releases` production Release Task for `Synapse-Network · Docs Front`, branch `main`.
3. Confirm the Production Gate shows the same main commit and source staging DeploymentRecord.
4. Click `发布到 production`, type `YES`, and submit.
5. Approve the target repository GitHub Environment `production` review.
6. Wait for GitHub Actions `deploy-production-frontends.yml` to pass. The wrapper calls reusable `deploy-production.yml` but the visible Actions run should identify the module.
7. Click `/releases` `同步状态` or wait for the deployment sweep.
8. Verify `/releases -> 上线记录` includes an `environment=production` row with GitHub Actions URL and health passed.
9. Smoke `https://docs.synapse-network.ai/`.

## Full Service Order

After the pilot succeeds, promote services in this order to reduce blast radius:

1. `docs-front`
2. `user-front`
3. `admin-front`
4. `gateway-admin`
5. `gateway`
6. `provider-service`

If any deployment fails, keep the Release Task failed with the GitHub Actions URL and failure excerpt. Do not manually mark success. Fix the root cause and retry from the failed service.

## Modular Production Workflow Map

Production deploy observability mirrors staging:

| Service | Workflow |
|---|---|
| `gateway` | `deploy-production-gateway.yml` |
| `gateway-admin` | `deploy-production-admin.yml` |
| `admin-front` | `deploy-production-frontends.yml` |
| `user-front` | `deploy-production-frontends.yml` |
| `docs-front` | `deploy-production-frontends.yml` |
| `provider-service` | `deploy-production-provider.yml` in `Synapse-Network-Provider` |

Growing records the concrete workflow file on each `DeploymentRecord.workflow_file` so failed production deploys can be traced to the exact module runner.

## Rollback

Production rollback is not automatic in v1. Runtime rollback must use a previous successful production Online Record as the target and pass a separate Human Gate. Code rollback must use a revert branch, PR checks, merge to `main`, staging verification, then production promotion.
