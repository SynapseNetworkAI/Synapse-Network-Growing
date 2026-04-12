from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from server.database import ApprovalRequestRow, ArtifactRow, RecurringWorkflowRow, RequirementRow, utcnow


def test_recurring_workflows_registry_lists_builtin_workflows(synced_client, db_session):
    response = synced_client.get("/api/recurring-workflows")
    assert response.status_code == 200
    items = response.json()
    workflow_keys = {item["workflow_key"] for item in items}
    assert {
        "morning_intake_sweep",
        "dispatcher_loop",
        "closeout_and_compact_sweep",
        "weekly_operating_review",
    } <= workflow_keys

    rows = db_session.query(RecurringWorkflowRow).all()
    assert len(rows) >= 4
    morning = next(item for item in items if item["workflow_key"] == "morning_intake_sweep")
    assert morning["owner_role"] == "ops_intake_manager"
    assert morning["trigger_type"] == "scheduled"


def test_run_morning_intake_workflow_uses_unified_intake(synced_client):
    with patch(
        "server.services.recurring_workflows.intake_requirement_sources",
        return_value={
            "executed_sources": ["optimization_signal", "company_review_bundle"],
            "created_requirement_ids": [11, 12],
            "reused_requirement_ids": [],
            "skipped": [],
            "items": [],
        },
    ) as mock_intake, patch(
        "server.services.recurring_workflows.list_optimization_signals",
        return_value=[
            MagicMock(
                id=7,
                title="High-value bug signal",
                severity="high",
                confidence=0.91,
                project_key="synapse-network",
                occurrence_count=9,
                latest_evidence_at=None,
            )
        ],
    ), patch(
        "server.services.recurring_workflows.list_open_incidents",
        return_value=[
            {
                "incident_key": "incident-1",
                "title": "Runtime incident",
                "severity": "high",
                "recovery_status": "operator_review_required",
            }
        ],
    ), patch(
        "server.services.recurring_workflows.latest_company_operating_review",
        return_value=MagicMock(id=18),
    ), patch(
        "server.services.recurring_workflows.company_review_to_dict",
        return_value={
            "next_cycle_requirement_bundle": [
                {
                    "bundle_item_key": "bundle-1",
                    "title": "High priority bundle item",
                    "priority": "high",
                    "project_key": "synapse-network-sdk",
                }
            ]
        },
    ):
        response = synced_client.post(
            "/api/recurring-workflows/morning_intake_sweep/run",
            json={"auto_start": False, "intake_min_score": 70, "intake_max_created": 3},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_key"] == "morning_intake_sweep"
    assert payload["result"]["created_requirement_ids"] == [11, 12]
    assert payload["result"]["company_review_id"] == 18
    assert payload["result"]["requires_operator_review"] is True
    assert len(payload["result"]["operator_attention_items"]) >= 2
    assert "Daily Intake Summary" in payload["result"]["daily_summary_markdown"]
    assert mock_intake.call_count == 1
    assert mock_intake.call_args.kwargs["source_key"] == "all"
    assert mock_intake.call_args.kwargs["min_score"] == 70
    assert mock_intake.call_args.kwargs["max_created"] == 3


def test_run_dispatcher_loop_workflow_advances_requirement_queue(synced_client):
    with patch(
        "server.services.recurring_workflows.advance_requirement_queue",
        return_value={"started_ids": [31], "created_requirement_ids": [], "rebalanced_ids": [], "preempted_ids": []},
    ) as mock_advance:
        response = synced_client.post("/api/recurring-workflows/dispatcher_loop/run", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_key"] == "dispatcher_loop"
    assert payload["result"]["started_ids"] == [31]
    assert mock_advance.call_count == 1


def test_run_dispatcher_loop_workflow_generates_follow_through_actions(synced_client, db_session):
    stale_running = RequirementRow(
        title="Stuck requirement",
        description_markdown="Investigate stalled execution",
        status="in_progress",
        priority="high",
        source="manual",
        updated_at=utcnow() - timedelta(hours=6),
    )
    paused_requirement = RequirementRow(
        title="Paused requirement",
        description_markdown="Retry after runtime pause",
        status="paused",
        priority="normal",
        source="manual",
    )
    blocked_requirement = RequirementRow(
        title="Blocked requirement",
        description_markdown="Waiting for approval",
        status="blocked",
        priority="normal",
        source="manual",
    )
    revision_requirement = RequirementRow(
        title="Needs revision requirement",
        description_markdown="Needs replanning",
        status="needs_revision",
        priority="normal",
        source="manual",
    )
    db_session.add_all([stale_running, paused_requirement, blocked_requirement, revision_requirement])
    db_session.flush()
    db_session.add(
        ApprovalRequestRow(
            requirement_id=blocked_requirement.id,
            approval_type="publish_gate",
            status="pending",
            reviewer="portfolio_operator",
            created_at=utcnow() - timedelta(hours=7),
        )
    )
    db_session.commit()

    with patch(
        "server.services.recurring_workflows.advance_requirement_queue",
        return_value={"started_ids": [31], "created_requirement_ids": [], "rebalanced_ids": [], "preempted_ids": []},
    ), patch(
        "server.services.recurring_workflows.list_open_incidents",
        return_value=[
            {
                "requirement_id": paused_requirement.id,
                "title": "Paused runtime recovery",
                "severity": "high",
                "recovery_status": "operator_review_required",
            }
        ],
    ):
        response = synced_client.post("/api/recurring-workflows/dispatcher_loop/run", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["started_ids"] == [31]
    assert payload["result"]["stuck_requirement_ids"] == [stale_running.id]
    assert payload["result"]["paused_requirement_ids"] == [paused_requirement.id]
    assert payload["result"]["blocked_requirement_ids"] == [blocked_requirement.id]
    assert payload["result"]["needs_revision_ids"] == [revision_requirement.id]
    assert len(payload["result"]["approval_reminders"]) == 1
    actions = {
        (item["action"], item["requirement_id"]): item["reason"]
        for item in payload["result"]["follow_up_actions"]
    }
    assert ("investigate_stuck", stale_running.id) in actions
    assert ("incident_recovery", paused_requirement.id) in actions
    assert ("approval_reminder", blocked_requirement.id) in actions
    assert ("replan", revision_requirement.id) in actions


def test_run_weekly_operating_review_refreshes_company_review(synced_client):
    fake_review = MagicMock(id=7, cycle_label="2026-W15")
    with patch(
        "server.services.recurring_workflows.refresh_company_operating_review",
        return_value=fake_review,
    ) as mock_refresh, patch(
        "server.services.recurring_workflows.company_review_to_dict",
        return_value={
            "next_cycle_requirement_bundle": [{"bundle_item_key": "bundle-1"}],
            "next_cycle_recommendations": [{"recommendation_key": "rec-1"}],
            "incidents": [{"item_key": "incident-1"}],
            "human_gate_hotspots": [{"gate_key": "gate-1"}],
            "automation_candidates": [{"candidate_key": "auto-1"}],
            "source_snapshot": {
                "workflow_rituals": {
                    "dispatcher_loop": {"stuck_requirement_count": 2},
                }
            },
            "operator_review_package": {
                "title": "Operator Review Package",
                "summary_markdown": "Weekly COO review summary",
                "decisions": [{"decision_key": "d-1"}],
                "recommended_bundle_item_keys": ["bundle-1"],
            },
        },
    ):
        response = synced_client.post("/api/recurring-workflows/weekly_operating_review/run", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_key"] == "weekly_operating_review"
    assert payload["result"]["review_id"] == 7
    assert payload["result"]["bundle_item_count"] == 1
    assert payload["result"]["recommendation_count"] == 1
    assert payload["result"]["incident_count"] == 1
    assert payload["result"]["human_gate_hotspot_count"] == 1
    assert payload["result"]["automation_candidate_count"] == 1
    assert payload["result"]["workflow_rituals"]["dispatcher_loop"]["stuck_requirement_count"] == 2
    assert payload["result"]["weekly_coo_review_package"]["decision_count"] == 1
    assert payload["result"]["weekly_coo_review_package"]["recommended_bundle_item_keys"] == ["bundle-1"]
    assert mock_refresh.call_count == 1


def test_run_closeout_and_compact_workflow_records_review_snapshot_and_compaction(synced_client, db_session):
    stale_requirement = RequirementRow(
        title="Long running requirement",
        description_markdown="Needs end-of-day compaction",
        status="paused",
        priority="high",
        source="manual",
        updated_at=utcnow() - timedelta(hours=10),
    )
    done_requirement = RequirementRow(
        title="Completed requirement",
        description_markdown="Needs review snapshot",
        status="done",
        priority="normal",
        source="manual",
        updated_at=utcnow() - timedelta(hours=1),
    )
    db_session.add_all([stale_requirement, done_requirement])
    db_session.flush()
    db_session.add(
        ArtifactRow(
            requirement_id=done_requirement.id,
            artifact_type="delivery_state",
            content_summary="Ready for review",
            machine_readable_payload='{"publish_status":"review_ready"}',
        )
    )
    db_session.commit()

    fake_review = MagicMock(id=22, cycle_label="2026-04-12")
    with patch(
        "server.services.recurring_workflows.dispatch_acceptance_sweep",
        return_value={"scanned": 2, "dispatched_requirement_ids": [], "candidates": [{"requirement_id": done_requirement.id}]},
    ), patch(
        "server.services.recurring_workflows.refresh_company_operating_review",
        return_value=fake_review,
    ):
        response = synced_client.post(
            "/api/recurring-workflows/closeout_and_compact_sweep/run",
            json={"acceptance_limit": 5, "auto_dispatch_acceptance": False},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_key"] == "closeout_and_compact_sweep"
    assert payload["result"]["acceptance_candidates"] == 1
    assert payload["result"]["company_review_id"] == 22
    assert stale_requirement.id in payload["result"]["stale_requirement_ids"]
    assert stale_requirement.id in payload["result"]["compacted_requirement_ids"]
    assert done_requirement.id in payload["result"]["review_snapshot_requirement_ids"]
    assert "End Of Day Summary" in payload["result"]["daily_summary_markdown"]

    compaction = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == stale_requirement.id,
        ArtifactRow.artifact_type == "end_of_day_compaction",
    ).order_by(ArtifactRow.id.desc()).first()
    assert compaction is not None
    snapshot = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == done_requirement.id,
        ArtifactRow.artifact_type == "review_snapshot",
    ).order_by(ArtifactRow.id.desc()).first()
    assert snapshot is not None
