#!/usr/bin/env python3
"""Backfill historical task/requirement completions into Agents-Memory.

Usage:
    python scripts/backfill_agents_memory.py [--dry-run]
"""
from __future__ import annotations
import sys, os, time, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.database import SessionLocal, TaskRow, RequirementRow, WorkflowStepRow, WorkflowRunRow
from server.services.agents_memory_sync import (
    push_task_completed,
    push_task_failed,
    push_requirement_completed,
    AGENTS_MEMORY_URL,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Agents-Memory from ops.db history")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be pushed without sending")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["AGENTS_MEMORY_SYNC_ENABLED"] = "false"
        print("[DRY-RUN] AGENTS_MEMORY_SYNC_ENABLED=false – nothing will be sent")

    db = SessionLocal()
    try:
        # ── 1. Completed tasks ────────────────────────────────────────────────
        completed_tasks = db.query(TaskRow).filter(TaskRow.status == "completed").all()
        print(f"Found {len(completed_tasks)} completed tasks to push…")
        for task in completed_tasks:
            step = db.query(WorkflowStepRow).filter(
                WorkflowStepRow.compatibility_task_id == task.id
            ).first()
            requirement = (
                db.query(RequirementRow).filter(RequirementRow.id == step.requirement_id).first()
                if step else None
            )
            if args.dry_run:
                print(f"  [DRY] task {task.id}: {(task.description or '')[:60]}")
            else:
                push_task_completed(task, step, requirement)
            time.sleep(0.05)  # gentle rate-limit

        # ── 2. Failed tasks ────────────────────────────────────────────────────
        failed_tasks = db.query(TaskRow).filter(TaskRow.status.in_(["failed", "rejected"])).all()
        print(f"Found {len(failed_tasks)} failed/rejected tasks to push…")
        for task in failed_tasks:
            step = db.query(WorkflowStepRow).filter(
                WorkflowStepRow.compatibility_task_id == task.id
            ).first()
            requirement = (
                db.query(RequirementRow).filter(RequirementRow.id == step.requirement_id).first()
                if step else None
            )
            if args.dry_run:
                print(f"  [DRY] failed task {task.id}: {(task.description or '')[:60]}")
            else:
                push_task_failed(task, step, requirement)
            time.sleep(0.05)

        # ── 3. Completed requirements ─────────────────────────────────────────
        done_reqs = db.query(RequirementRow).filter(RequirementRow.status == "done").all()
        print(f"Found {len(done_reqs)} completed requirements to push…")
        for req in done_reqs:
            run = db.query(WorkflowRunRow).filter(
                WorkflowRunRow.requirement_id == req.id,
                WorkflowRunRow.status == "completed",
            ).order_by(WorkflowRunRow.id.desc()).first()
            steps_summary: list[dict] = []
            output_summary = ""
            changed_files: list[str] = []
            if run:
                steps = db.query(WorkflowStepRow).filter(
                    WorkflowStepRow.workflow_run_id == run.id
                ).order_by(WorkflowStepRow.sequence_no.asc(), WorkflowStepRow.id.asc()).all()
                steps_summary = [
                    {"title": s.title, "role": s.assigned_workflow_role or "", "status": s.status, "execution_time_ms": None}
                    for s in steps
                ]
            if args.dry_run:
                print(f"  [DRY] req {req.id}: {req.title[:60]}")
            else:
                push_requirement_completed(req, steps_summary, output_summary, changed_files)
            time.sleep(0.1)

    finally:
        db.close()

    if not args.dry_run:
        print(f"\nAll records pushed. Check {AGENTS_MEMORY_URL} for updated ingest count.")
    else:
        print("\n[DRY-RUN] Done – no data was sent to Agents-Memory.")


if __name__ == "__main__":
    main()
