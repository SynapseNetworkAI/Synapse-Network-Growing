---
id: postgres-migration-and-e2e-runbook
title: Postgres Migration and E2E Runbook
role: dev_rel
status: ready
created_at: 2026-05-04
updated_at: 2026-05-15
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing
---

# Postgres Migration and E2E Runbook

This runbook moves the Ops Console from `server/ops.db` SQLite into Postgres, then validates API, frontend, release, and scheduled-job flows against Postgres. Local can still use SQLite as a fallback, but staging and production must set an explicit PostgreSQL `OPS_DATABASE_URL`; the app fails closed otherwise.

## Environment Policy

1. Local/dev: Docker Postgres is recommended. SQLite remains a lightweight fallback when `OPS_DATABASE_URL` is unset.
2. Test: fast unit tests keep in-memory SQLite; DB-sensitive integration tests use `OPS_TEST_POSTGRES_URL`.
3. Staging/prod: SQLite is forbidden. `OPS_ENV=staging|prod|production` requires an explicit Postgres URL.
4. Do not dual-write. After cutover, SQLite is an archive/rollback source only, not a hot database.

## Target Database

Recommended local DSN:

```bash
export OPS_DATABASE_URL="postgresql+psycopg://synapse_growing:synapse_growing_dev@127.0.0.1:54329/synapse_growing"
```

Docker service:

```bash
docker-compose -f docker-compose.postgres.yml up -d
docker exec synapse-growing-postgres pg_isready -U synapse_growing -d synapse_growing
```

For CI/local integration tests:

```bash
export OPS_TEST_POSTGRES_URL="$OPS_DATABASE_URL"
PYTHONPATH=. python -m pytest -q tests/test_postgres_migration.py
```

## Full Data Migration

The migration copies every SQLite table, including legacy, social, release, scheduled-job, and SDK package tables.

Before copying, stop write-producing loops and checkpoint SQLite WAL:

```bash
sqlite3 server/ops.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python \
  scripts/db/migrate_sqlite_to_postgres.py \
  --postgres-url "$OPS_DATABASE_URL" \
  --reset-postgres \
  --confirm MIGRATE_SQLITE_TO_POSTGRES
```

Safety behavior:

1. Backs up `server/ops.db` to `runtime/backups/` before copying.
2. Creates ORM-declared tables and reflects extra legacy SQLite tables.
3. Copies rows table-by-table.
4. Resets Postgres sequences after copy.
5. Creates `schema_migrations` for future idempotent SQL.

Cutover rules:

1. Validate row counts and core smoke tests before switching `OPS_DATABASE_URL`.
2. Restart backend workers only after validation passes.
3. If cutover has accepted new Postgres writes, roll back from a Postgres snapshot/backup rather than returning to SQLite and creating split-brain data.

Validate row counts:

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python \
  scripts/db/validate_postgres_migration.py \
  --sqlite server/ops.db \
  --postgres-url "$OPS_DATABASE_URL"
```

## Idempotent SQL Migrations

Put future hand-written SQL files under `server/migrations/` with sortable names, for example:

```text
server/migrations/20260504_001_add_example_index.sql
```

Run:

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python \
  scripts/db/run_sql_migrations.py \
  --database-url "$OPS_DATABASE_URL" \
  --migrations-dir server/migrations
```

Rules:

1. Every SQL file is recorded in `schema_migrations`.
2. Already-applied files are skipped.
3. SQL must be idempotent where possible, using `IF NOT EXISTS` / `ON CONFLICT` patterns.
4. Do not put destructive data rewrites in the shared migrations folder without a dedicated operator runbook.

## Postgres App Smoke

Run backend/API checks with Postgres:

```bash
OPS_DATABASE_URL="$OPS_DATABASE_URL" PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python - <<'PY'
from server.database import SessionLocal
from server.services.planning.mission_workbench import mission_workbench_snapshot
from server.services.releases.task_query import query_release_tasks
from server.services.releases.scheduled_job_tasks import list_scheduled_job_release_tasks

with SessionLocal() as db:
    print(sorted(mission_workbench_snapshot(db).model_dump().keys()))
    print(query_release_tasks(db, limit=5).total)
    print(list_scheduled_job_release_tasks(db, limit=5).total)
PY
```

## Frontend E2E Against Postgres

The Playwright webserver reads `OPS_E2E_DATABASE_URL` and starts the backend against Postgres:

```bash
cd dashboard
OPS_E2E_DATABASE_URL="$OPS_DATABASE_URL" \
  npm run test:e2e -- --grep "Ops Console primary pages|Release management|Social Publishing"
```

Required UI coverage:

1. `/command-center`
2. `/planning`
3. `/publishing`
4. `/publishing/trends`
5. `/releases`
6. `/projects`

Each checked page must render without uncaught browser errors or 5xx API responses, and core modals/tabs must be usable.

## Full Staging Release E2E

This step performs real staging writes through GitHub Actions + WIF. It creates release tasks and immediately deploys them sequentially.

```bash
PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/python \
  scripts/e2e/release_all_staging_targets.py \
  --base-url http://127.0.0.1:9700 \
  --branch main \
  --confirm RELEASE_ALL_STAGING_TARGETS
```

The script publishes:

1. `synapse-network / gateway`
2. `synapse-network / gateway-admin`
3. `synapse-network / admin-front`
4. `synapse-network / user-front`
5. `synapse-network / docs-front`
6. `synapse-network-provider / provider-service`
7. Scheduled job `synapse-staging-deposit-indexer`

Success criteria:

1. Service `ReleaseTask.status=completed`.
2. Linked `DeploymentRecord.status=succeeded`.
3. Health is `passed` / `healthy`.
4. GitHub Actions URL is recorded.
5. Successful deployment appears in `/releases -> 上线记录`.
6. Scheduled job task reaches `completed` with an Actions URL.

If any publish fails, do not mark it manually complete. Open the Actions link, fix the root cause, then rerun from the failed target or create a new proof run.
