# Release Governance Principles

Load this when touching release tasks, delivery, PR handoff, deploy, staging, production, rollback, online records, Cloud Run, local deploy runner, or release status sweeps.

## Release Surface Boundary

1. Release Candidate only comes from validated requirements.
2. Publish, deploy, promotion, and rollback live in Release / Deployment surfaces, not Requirement pages.
3. Requirement execution approval controls whether agent work may start; it does not replace release/deployment gates.
4. Agent may create or update Draft PRs but never auto-merge.
5. GitHub PR merge is external fact absorption, not a deploy action.
6. Merged PR can update Release state only. It must not auto-trigger deploy, rollback, branch deletion, or production change.

## PR And Delivery Handoff

1. Delivery atom smart-syncs remote branch before push: preserve human commits, clean rebase if possible, otherwise await operator.
2. PR body is reviewer-first: business summary, safety review reason, and human merge checklist at top.
3. Evidence, logs, and retry history should be folded or linked to artifacts.
4. After execution approval, system prepares requirement branch from latest target repository `main` before starting execution; do not defer all branch/PR work to the end.
5. GitHub PR bodies and comments must be written with real newlines via `--body-file`, heredoc, or an equivalent multiline file. Do not pass escaped `\n` sequences in shell arguments; GitHub renders them as garbled literal text.

## Release Tasks And Deployment Records

1. Release Task is business release intent and human closure record.
2. Deployment Record is physical deployment trace.
3. `/releases` can show both manual and requirement-derived release tasks, but must not fake Release Tasks by flattening Deployment Records.
4. Creating a Release Task does not deploy.
5. Release Task branch selection comes from target GitHub repository branch list, not free text.
6. Release Task detail exposes PR gate, DeploymentRecord, local runner status, health check, failure summary, metadata drilldown, and append-only deployment logs.
7. Main list shows status summary and next action, not long logs or raw payload.

## Staging, Production, And WIF

1. Staging from `main` can be manually published because it is trunk fact.
2. Staging from non-main branch requires open or merged PR and passing PR checks.
3. Staging deploys use whitelisted release runner and write `deployment_record_id`.
4. Synapse-Network and Synapse-Network-Provider staging use the local deploy runner with subprocess-scoped GCP service account impersonation, Cloud Build/Docker build, and Cloud Run.
5. Do not store GCP JSON keys or SSH deploy secrets in source control.
6. Production deploy and rollback require Human Gate.
7. Production cannot reuse staging API or ordinary PATCH to bypass release governance.
8. Staging and production conditions differ: production normally requires a task-pinned main/tag/verified staging manifest plus Human Gate. Production tasks must promote the staged commit they selected; they must not silently drift to a newer moving branch head.
9. Successful staging does not auto-promote production.

## Online Records And Reconciliation

1. Online Record is the successful release ledger and only comes from successful DeploymentRecord.
2. Manual completion must first create or bind a successful `manual_completion` DeploymentRecord, then enter Online Records.
3. Online Records retain local runner evidence, commit, branch, service, environment, health, revision/image/manifest metadata, and release task anchor.
4. Local deployments or runs without webhook callback use pull-based reconciliation.
5. `release_deployment_status_sweep` and manual "sync status" reuse the same idempotent sync function.
6. Sync only reads local runner state from Postgres and updates unfinished DeploymentRecords and Release Tasks.
7. Sync must not deploy, merge, rollback, publish production, or mutate terminal manual completed/failed/cancelled records.
8. Health checks run inside the local deploy runner with per-service retry smoke checks; Ops Console should not create a second health fact source.

## Rollback And Cloud Run Jobs

1. Rollback requires structured Release / Deployment evidence.
2. Runtime rollback targets a historical successful Online Record commit/image/manifest and enters Human Gate.
3. Code revert uses new revert branch -> PR -> checks -> merge -> normal release.
4. Drop Goal, ordinary PATCH, or staging deploy API must not trigger rollback.
5. Synapse-Network Cloud Run Jobs are target-repo release objects, not Growing recurring workflows.
6. Scheduled job release is two-step: create requested task, then operator clicks staging deploy.
7. Ops Console request handlers must not directly call local `gcloud` to write Google resources; they create durable records for the local runner.
8. Job image update, optional smoke execution, optional migration execution, and status writeback happen in the local runner.
9. Cloud Run Jobs publish success uses local runner manifest / `jobsManifest` as source of truth.
10. Scheduler freshness and Cloud Run Job execution status are health signals, not release failure facts unless deployment evidence says so.
