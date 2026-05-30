---
id: schedule-center-e2e-runbook
title: Schedule Center E2E Runbook
role: dev_rel
status: ready
created_at: 2026-05-21
updated_at: 2026-05-21
author: codex
target_repo: Synapse-Network-Growing
---

# Schedule Center E2E Runbook

This runbook verifies that `/schedules` is an executable control plane, not just
a registry page. The proof chain is:

```text
Schedule Center UI/API
-> recurring_workflows
-> recurring_workflow_runs
-> cleanup handler dry-run/apply
-> GCP metadata state
-> visible run history/result JSON
```

## Safe Default Verification

Run the non-destructive suite first:

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python -m pytest -q \
  tests/test_schedule_center_api.py \
  tests/test_schedule_center_e2e.py \
  tests/test_artifact_registry_cleanup.py \
  tests/test_artifact_registry_cleanup_recurring_workflow.py \
  tests/test_secret_manager_cleanup.py \
  tests/test_secret_manager_cleanup_recurring_workflow.py \
  tests/test_staging_environment_shutdown.py \
  tests/test_staging_environment_shutdown_recurring_workflow.py \
  tests/test_cost_control_scheduler.py
```

```bash
cd dashboard && npm test -- --run SchedulesPage App
```

```bash
cd dashboard && npm run build
```

The mocked E2E tests prove:

1. built-in schedules exist and are visible through `/api/schedules`;
2. custom schedules can be created, patched, run, observed, and deleted;
3. built-in schedules cannot be deleted;
4. cost-control schedules are visible for Artifact Registry, Secret Manager,
   and staging shutdown;
5. schedule runs are persisted in `recurring_workflow_runs`;
6. high-risk cleanup handlers return visible result JSON.

## Real GCP Dry-run

With the backend running locally and `OPS_DATABASE_URL` pointed at Postgres:

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python \
  scripts/e2e/schedule_center_e2e.py \
  --base-url http://127.0.0.1:9700 \
  --real-gcp-dry-run \
  --artifact-region us-central1
```

Dry-run must not mutate remote state. Confirm with:

```bash
gcloud secrets versions list <secret-name> \
  --project fabled-archive-494108-k5
```

```bash
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/fabled-archive-494108-k5/<repository> \
  --include-tags \
  --format=json
```

For full before/after evidence across staging and production, prefer the
dedicated cost-control verifier. Default mode is non-destructive and writes
snapshots under `docs/archive/evidence/`:

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python \
  scripts/e2e/schedule_cost_control_real_e2e.py \
  --base-url http://127.0.0.1:9700 \
  --database-url "$OPS_DATABASE_URL"
```

The verifier captures:

1. Artifact Registry before / after-dry-run snapshots for all configured
   staging and production targets.
2. Secret Manager before / after-dry-run snapshots for staging and production.
3. Staging shutdown target snapshots plus production control snapshots proving
   production was not touched.
4. Schedule Center dry-run results and DB run history.

Destructive applies require explicit flags and confirmation:

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python \
  scripts/e2e/schedule_cost_control_real_e2e.py \
  --base-url http://127.0.0.1:9700 \
  --database-url "$OPS_DATABASE_URL" \
  --apply-artifacts \
  --apply-secrets \
  --confirm APPLY_COST_CONTROL_E2E
```

Staging shutdown is intentionally separate because it stops staging Cloud SQL
and pauses staging jobs:

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python \
  scripts/e2e/schedule_cost_control_real_e2e.py \
  --base-url http://127.0.0.1:9700 \
  --database-url "$OPS_DATABASE_URL" \
  --apply-staging-shutdown \
  --confirm APPLY_COST_CONTROL_E2E
```

Acceptance for the real verifier:

1. Dry-run snapshots are byte-for-byte unchanged before and after dry-run.
2. Artifact apply `deleted_count` equals remote digest count reduction.
3. Secret apply `destroyed_count` equals active-version count reduction, and no
   secret has more than two active versions.
4. Staging shutdown commands reference only `fabled-archive-494108-k5`, and the
   production control snapshot remains unchanged.

## Controlled Secret Manager Apply

Only run this against the test secret fixture. It creates
`schedule-e2e-cleanup-test`, writes dummy versions, runs a scoped custom schedule
with `secret_ids=["schedule-e2e-cleanup-test"]`, then verifies only the newest 2
active versions remain.

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python \
  scripts/e2e/schedule_center_e2e.py \
  --base-url http://127.0.0.1:9700 \
  --apply-secret-test \
  --cleanup-test-secret \
  --confirm APPLY_SCHEDULE_E2E
```

The implementation must never run destructive apply across all production
secrets during E2E.

## Controlled Artifact Registry Apply

Only run this on a safe staging test repository prepared with disposable image
digests:

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python \
  scripts/e2e/schedule_center_e2e.py \
  --base-url http://127.0.0.1:9700 \
  --artifact-apply-repository <safe-test-repository> \
  --artifact-region us-central1 \
  --artifact-keep 3 \
  --confirm APPLY_SCHEDULE_E2E
```

The verifier checks DB `deleted_count` against the before/after remote digest
count. Promoted, production, and release tags must be preserved by the cleanup
policy.

## Staging Shutdown Dry-run

Run the staging shutdown workflow in dry-run before allowing the nightly
scheduler to apply it:

```bash
curl -X POST http://127.0.0.1:9700/api/schedules/staging_environment_shutdown_sweep/run \
  -H 'Content-Type: application/json' \
  -d '{"dry_run": true}'
```

The result must list only staging targets:

1. Cloud Run services with `--min-instances 0`.
2. Cloud Scheduler jobs with `pause`.
3. The configured staging Cloud SQL instance with `--activation-policy NEVER`.

Production project ids must never appear in this workflow output.

## Database Evidence

Use these queries to inspect the durable schedule facts:

```sql
select workflow_key, status, is_builtin, schedule_json, output_action_json
from recurring_workflows
where workflow_key in (
  'artifact_registry_cleanup_sweep',
  'secret_manager_version_cleanup_sweep',
  'staging_environment_shutdown_sweep'
);
```

```sql
select workflow_key, status, dry_run, result_json, error_excerpt, started_at, completed_at
from recurring_workflow_runs
where workflow_key in (
  'artifact_registry_cleanup_sweep',
  'secret_manager_version_cleanup_sweep',
  'staging_environment_shutdown_sweep'
)
order by id desc
limit 20;
```

`secret_manager_version_cleanup_sweep` is intentionally destructive: it destroys
old active versions and keeps the newest two versions per secret. Disabled
versions are treated as active cleanup candidates because they still retain
secret contents.

## Acceptance

1. `/schedules` shows Overview, Tasks, Run History, and Templates.
2. Every manual run writes one row to `recurring_workflow_runs`.
3. Dry-run never changes remote GCP metadata.
4. Apply is scoped to explicit test resources unless an operator deliberately
   uses a production runbook.
5. Result JSON and failure excerpts are visible from the Schedule Center detail
   modal after page refresh.
