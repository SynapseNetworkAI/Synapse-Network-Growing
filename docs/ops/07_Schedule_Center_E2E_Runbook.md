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
  tests/test_secret_manager_cleanup_recurring_workflow.py
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
4. schedule runs are persisted in `recurring_workflow_runs`;
5. high-risk cleanup handlers return visible result JSON.

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

## Controlled Secret Manager Apply

Only run this against the test secret fixture. It creates
`schedule-e2e-cleanup-test`, writes dummy versions, runs a scoped custom schedule
with `secret_ids=["schedule-e2e-cleanup-test"]`, then verifies only the newest 3
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

## Database Evidence

Use these queries to inspect the durable schedule facts:

```sql
select workflow_key, status, is_builtin, schedule_json, output_action_json
from recurring_workflows
where workflow_key in (
  'secret_manager_version_cleanup_sweep',
  'artifact_registry_cleanup_sweep'
);
```

```sql
select workflow_key, status, dry_run, result_json, error_excerpt, started_at, completed_at
from recurring_workflow_runs
where workflow_key in (
  'secret_manager_version_cleanup_sweep',
  'artifact_registry_cleanup_sweep'
)
order by id desc
limit 20;
```

## Acceptance

1. `/schedules` shows Overview, Tasks, Run History, and Templates.
2. Every manual run writes one row to `recurring_workflow_runs`.
3. Dry-run never changes remote GCP metadata.
4. Apply is scoped to explicit test resources unless an operator deliberately
   uses a production runbook.
5. Result JSON and failure excerpts are visible from the Schedule Center detail
   modal after page refresh.
