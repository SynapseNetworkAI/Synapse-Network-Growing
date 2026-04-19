---
id: logging-strategy-ops-dashboard
title: Ops Dashboard Logging Strategy
role: software_engineer
status: ready
created_at: 2026-04-14
updated_at: 2026-04-14
author: software_engineer
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing
---

# Purpose

Synapse Ops Dashboard needs structured logs that are durable, reviewable, and easy to correlate with agent workflows.
This strategy documents how logs are emitted, where they land, and how to reason about the data when debugging or running
postmortems.

## Objectives
- Emit JSON logs that keep request / workflow context without leaking secrets.
- Persist every log line to disk using daily file rotation and bounded retention.
- Capture key workflow transitions (HTTP middleware + agent task runner) so we can replay execution trails.
- Keep the setup configurable through environment variables so staging and prod can tighten retention independently.

## Architecture

| Layer | Responsibility |
| --- | --- |
| `server/logging_utils.py` | Configures StructLog + stdlib logging, sanitizes sensitive keys, and creates handlers. |
| Console handler | Streams JSON logs to stderr for local visibility and CI. |
| File handler | `TimedRotatingFileHandler` writing to `<LOG_DIR>/<LOG_FILE>` using UTC midnight boundaries. |
| Context helpers | `bind_context`, `clear_context`, and `log_event` expose a consistent API for services and tests. |

Handlers are configured during FastAPI boot (`server/main.py`) via `setup_ops_logging`, which takes
`log_level`, `log_dir`, `log_file`, `backup_days`, `service_name`, and `env`. The helper performs the following:

1. Builds a shared processor chain (adds timestamps, service/env tags, sanitizes sensitive keys, serializes JSON).
2. Resets the root logger and installs both console and file handlers.
3. Ensures the log directory exists and configures the file handler for midnight rotation with UTF-8 encoding.
4. Marks the root logger with `_ops_dashboard_configured` so repeated imports do not duplicate handlers.

## Daily Rotation & Retention

- `TimedRotatingFileHandler` is created with `when="midnight"`, `interval=1`, `utc=True`, and `backupCount=LOG_BACKUP_DAYS`.
- `OPS_LOG_DIR`, `OPS_LOG_FILE`, and `OPS_LOG_BACKUP_DAYS` can be overridden per environment (defaults live in `server/config.py`).
- Each midnight, the active `ops-dashboard.jsonl` file is rotated to `ops-dashboard.jsonl.YYYY-MM-DD`. Older files beyond the
  configured retention window are pruned automatically by the handler.
- Tests under `tests/test_logging_utils.py` assert both the handler wiring and rotation behavior to guard against regressions.

## Key Workflow Emission Points

| Event | Emitted From | Fields |
| --- | --- | --- |
| `service_starting`, `http_request_completed`, `http_request_failed` | FastAPI middleware (`server/main.py`) | request id, method, path, duration, outcome |
| `task_dispatch_inline`, `task_dispatch_enqueued` | `server/services/runtime/task_runner.dispatch` | task id, skill, mode, thread |
| `task_execution_started`, `task_execution_completed`, `task_runtime_crashed` | `server/services/runtime/task_runner._run_task_sync` | runtime backend/provider/model, selection reason, execution time, status |
| `task_runtime_guard_paused` | Same module when OpenAI guard pauses a run | runtime backend, guard reason |
| `requirement_assets_generated`, `workflow_run_started`, etc. | Requirement and workflow services (`server/services/requirements/service.py`, `server/services/workflows/declarative.py`) | requirement + workflow run ids |

These structured events allow dashboards and alerting rules to filter on `event`, `service`, and `env` without parsing free-form text.
Each event consistently includes numeric identifiers (`task_id`, `requirement_id`, `execution_id`), making it possible to join
against database rows during investigations.

## Operations & Validation

- Local debugging: tail `server/logs/ops-dashboard.jsonl` (or the directory configured via `OPS_LOG_DIR`).
- Log rotation health: ensure dated files (`*.jsonl.YYYY-MM-DD`) appear daily; older slices should stay within
  `OPS_LOG_BACKUP_DAYS` count.
- Automated verification: `pytest tests/test_logging_utils.py -k rotation` exercises the handler wiring and rollover path.
- Release validation: run the repository-wide checks listed in the requirement (pytest, dashboard `npm test`, `npm run build`).
