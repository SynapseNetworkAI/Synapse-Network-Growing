from __future__ import annotations

import json

from server.database import ApprovalRow, ArtifactRow, RequirementRow, TaskRow


def test_refresh_optimization_signals_deduplicates_bug_reports_and_collects_sources(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    req1 = RequirementRow(
        title="Req one",
        description_markdown="First requirement",
        status="done",
        priority="high",
        source="manual",
        target_project_path=target_path,
        current_plan_version=1,
    )
    req2 = RequirementRow(
        title="Req two",
        description_markdown="Second requirement",
        status="done",
        priority="normal",
        source="manual",
        target_project_path=target_path,
        current_plan_version=1,
    )
    db_session.add_all([req1, req2])
    db_session.flush()

    db_session.add_all([
        ArtifactRow(
            requirement_id=req1.id,
            artifact_type="bug_report",
            content_summary="Validation failed",
            machine_readable_payload=json.dumps({
                "step_type": "test",
                "failed_checks": [{"check_key": "validation_passed"}],
            }),
        ),
        ArtifactRow(
            requirement_id=req2.id,
            artifact_type="bug_report",
            content_summary="Validation failed again",
            machine_readable_payload=json.dumps({
                "step_type": "test",
                "failed_checks": [{"check_key": "validation_passed"}],
            }),
        ),
        ArtifactRow(
            requirement_id=req1.id,
            artifact_type="delivery_state",
            content_summary="Review ready but blocked",
            machine_readable_payload=json.dumps({
                "publish_status": "review_ready",
                "publish_blockers": ["required check pending: npm run build"],
            }),
        ),
    ])
    task = TaskRow(
        description="Need manual approval",
        agent_id="growth_lead",
        status="pending_approval",
        requires_approval=True,
        priority="normal",
        project_id=target_path,
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(ApprovalRow(task_id=task.id, status="pending"))
    db_session.commit()

    resp = synced_client.post("/api/optimization-signals/refresh")

    assert resp.status_code == 200
    payload = resp.json()
    by_type = {item["signal_type"]: item for item in payload}
    assert by_type["bug_report"]["occurrence_count"] == 2
    assert by_type["bug_report"]["project_key"] == "synapse-network"
    assert by_type["delivery_blocker"]["occurrence_count"] == 1
    assert by_type["manual_override"]["occurrence_count"] == 1


def test_create_requirement_from_optimization_signal_marks_signal_converted(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network-Sdk"
    requirement = RequirementRow(
        title="SDK blocker",
        description_markdown="Manual delivery blocker",
        status="done",
        priority="high",
        source="manual",
        target_project_path=target_path,
        current_plan_version=1,
    )
    db_session.add(requirement)
    db_session.flush()
    db_session.add(
        ArtifactRow(
            requirement_id=requirement.id,
            artifact_type="delivery_state",
            content_summary="Blocked publish",
            machine_readable_payload=json.dumps({
                "publish_status": "blocked",
                "publish_blockers": ["publish disabled by project policy"],
            }),
        )
    )
    db_session.commit()

    refresh_resp = synced_client.post("/api/optimization-signals/refresh")
    signal = next(item for item in refresh_resp.json() if item["signal_type"] == "delivery_blocker")

    create_resp = synced_client.post(
        f"/api/optimization-signals/{signal['id']}/create-requirement",
        json={},
    )

    assert create_resp.status_code == 200
    detail = create_resp.json()
    assert detail["requirement"]["source"] == "optimization_signal"
    assert detail["requirement"]["source_ref"] == f"optimization-signal:{signal['id']}"
    assert detail["requirement"]["target_project_path"] == target_path

    list_resp = synced_client.get("/api/optimization-signals?status=converted")
    assert list_resp.status_code == 200
    converted = next(item for item in list_resp.json() if item["id"] == signal["id"])
    assert converted["status"] == "converted"
    assert converted["converted_requirement_id"] == detail["requirement"]["id"]
