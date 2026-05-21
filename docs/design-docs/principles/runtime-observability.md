# Runtime And Observability Principles

Load this when touching recurring workflows, background loops, `/schedules`, runtime lifecycle, subagents, workspace recovery, telemetry, notifications, alerts, or structured logging.

## Recurring Workflows And Schedules

1. Any periodic, polling, retrying, or auto-advancing mechanism must be visible in Ops Console.
2. Background work cannot exist only in threads, daemons, logs, cron, or implicit request side effects.
3. Every run records triggered_by, dry_run, params, result, error, started_at, completed_at, and duration.
4. High-risk recurring workflows do not auto-start requirements, delivery, deploy, funds, auth, contracts, or external paid actions.
5. `Dry Run` is the default config validation path. `Run Now` requires explicit confirmation and traceable result.
6. `/schedules` groups workflows by business domain and decision priority, not as a bare crontab table.
7. Schedule cards show `Input -> Action -> Output`.
8. Failed, due, locked, or anomalous runs appear in `Attention Required`.
9. Missing presentation metadata falls into `New / Uncategorized Initiates` with `Missing Presentation Metadata` but history and manual run remain available.
10. Run Inspector opens immediately for Dry Run / Run Now with optimistic running entry. If the operator closed it, completion must not steal focus.
11. Run history defaults to recent 50 and handles selected runs falling out of window.
12. `dry_run=true` history is visually downgraded and marked `DRY RUN`.
13. High-frequency operations views are compact monitoring surfaces. Long descriptions and full I-P-O are folded.
14. Overdue tasks show `OVERDUE`, debt time, and likely reason; more than 24 hours overdue is danger state.
15. Items in `Attention Required` are not fully duplicated in their original lane.
16. Schedule configuration can be edited only through allowlisted templates and bounded fields. Do not expose arbitrary execution logic, shell, prompt, raw cron edit, or high-risk auto switches.

## Runtime And Workspace Recovery

1. Runtime lifecycle must support start, running, pause, fail, cleanup, and abort.
2. Transcript, session, artifact, log, and ownership must be traceable.
3. Parent execution end must close or review child resources.
4. Runtime reset uses controlled scripts only; do not preserve old dirty-state compatibility.
5. After Cancel / Kill, workspace is untrusted by default and records `workspace_trust_state=dirty_after_kill`, `requires_workspace_recovery=true`, `killed_at`, and `kill_signal`.
6. Retry / Resume must run Workspace Recovery Preflight before waking Codex: repo root, branch, project policy, stale git locks, active git process, and owned worktree/branch checks.
7. Recovery can hard reset only workflow-owned worktree or matching `ops/` / `codex/` branch.
8. Human-owned workspace, missing trusted checkpoint, untracked human work, wrong branch, or dirty status after recovery must fail closed to Human Review.
9. Recovery success and failure write visible events and UI trust badges.
10. Verification/manual review is not a formal execution stage. Execution completion dispatches verification agent; its verdict is the release precondition.

## CI Runner And Background Sweeps

1. Long final regression must not block workflow worker. Fire-and-suspend to `awaiting_ci`; observable recurring sweep closes it.
2. CI runner streams logs and writes atomic exit marker. Do not buffer complete stdout/stderr in memory.
3. CI status sweep has a single-run time limit; stale-lock recovery threshold is larger than that limit.
4. Local/dev does not automatically consume historical `awaiting_ci` records unless explicitly enabled.
5. Release PR status sweep is read-only. It can absorb MERGED/CLOSED/404 external facts, but must not deploy, merge, rollback, or delete branches.
6. GitHub run removed/unavailable must record root cause; pending/running beyond safety threshold converges to diagnosable failure.

## Telemetry, Notifications, And Logs

1. Requirement, execution, release, incident, publish, rollback, scheduling decision, recovery action, and operator takeover must leave structured evidence.
2. Automation without telemetry should not enter the default path.
3. Requirement, alert, approval, and release notifications use a unified envelope: service, event type, priority, risk, timestamp, what happened, next action, and links.
4. Ordinary state transitions, atom success, artifacts, and blackboard snapshots stay in Ops Console; only P0/P1 alerts and human gates notify external channels.
5. Requirement generation suppression and notification suppression are separate systems.
6. Schedulers that create requirements or trigger side effects need a database lease; lock failure records skipped/locked history.
7. Python services use structured `structlog + logging`; primary output is stdout JSON, optional local backup is JSONL.
8. File logs rotate daily and keep 14 days unless a design doc says otherwise.
9. Logs bind chain fields such as request_id, task_id, requirement_id, execution_id, release_id, and fingerprint_key.
10. Every structured log includes ts, level, event, service, env, logger, and message; result logs include outcome, status, duration_ms, error_type, and error_message.
11. Never log token, secret, webhook URL, authorization header, or sensitive config in error messages.
