from __future__ import annotations

import json
from unittest.mock import patch

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
        ArtifactRow(
            requirement_id=req1.id,
            artifact_type="stale_memory_verification",
            content_summary="stale context verification for step implementation",
            machine_readable_payload=json.dumps({
                "verification_status": "stale",
                "stale_findings": ["implementation_plan comes from workflow run #2"],
                "step_key": "implementation",
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
    assert by_type["workflow_incident"]["incident_family"] == "context_integrity"
    assert by_type["workflow_incident"]["incident_code"] == "stale_memory_blocked"
    assert by_type["workflow_incident"]["recovery_status"] == "replan_required"


def test_refresh_optimization_signals_keeps_raw_occurrences_but_deduplicates_repeated_evidence(synced_client, db_session):
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
    duplicate_payload = json.dumps({
        "step_type": "research",
        "failed_checks": [{"check_key": "runtime_session_available"}],
    })
    db_session.add_all([
        ArtifactRow(
            requirement_id=req1.id,
            artifact_type="bug_report",
            content_summary="Request session.resume failed with message: Session not found",
            machine_readable_payload=duplicate_payload,
        ),
        ArtifactRow(
            requirement_id=req2.id,
            artifact_type="bug_report",
            content_summary="Request session.resume failed with message: Session not found",
            machine_readable_payload=duplicate_payload,
        ),
    ])
    db_session.commit()

    resp = synced_client.post("/api/optimization-signals/refresh")

    assert resp.status_code == 200
    bug_signal = next(item for item in resp.json() if item["signal_type"] == "bug_report")
    assert bug_signal["occurrence_count"] == 2
    assert len(bug_signal["evidence"]) == 1
    assert bug_signal["evidence"][0]["content_summary"] == "Request session.resume failed with message: Session not found"


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
    assert detail["requirement"]["title"].startswith("Release Bottleneck:")

    list_resp = synced_client.get("/api/optimization-signals?status=converted")
    assert list_resp.status_code == 200
    converted = next(item for item in list_resp.json() if item["id"] == signal["id"])
    assert converted["status"] == "converted"
    assert converted["converted_requirement_id"] == detail["requirement"]["id"]

    plan_resp = synced_client.post(f"/api/requirements/{detail['requirement']['id']}/plan")
    assert plan_resp.status_code == 200
    acceptance_keys = [item["check_key"] for item in plan_resp.json()["acceptance_checks"]]
    assert "release_blocker_removed" in acceptance_keys
    assert "rollback_path_documented" in acceptance_keys


def test_auto_intake_picks_highest_scored_signal(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    blocker_requirement = RequirementRow(
        title="Gateway publish blocker",
        description_markdown="Blocked by release policy.",
        status="done",
        priority="high",
        source="manual",
        target_project_path=target_path,
        current_plan_version=1,
    )
    manual_requirement = RequirementRow(
        title="Need manual approvals",
        description_markdown="Manual override pressure exists.",
        status="done",
        priority="normal",
        source="manual",
        target_project_path=target_path,
        current_plan_version=1,
    )
    db_session.add_all([blocker_requirement, manual_requirement])
    db_session.flush()
    db_session.add(
        ArtifactRow(
            requirement_id=blocker_requirement.id,
            artifact_type="delivery_state",
            content_summary="Blocked publish",
            machine_readable_payload=json.dumps({
                "publish_status": "blocked",
                "publish_blockers": ["publish disabled by project policy"],
            }),
        )
    )
    task = TaskRow(
        description="Needs manual approval",
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

    refresh_resp = synced_client.post("/api/optimization-signals/refresh")
    assert refresh_resp.status_code == 200
    signals = refresh_resp.json()
    delivery_signal = next(item for item in signals if item["signal_type"] == "delivery_blocker")
    manual_signal = next(item for item in signals if item["signal_type"] == "manual_override")
    assert delivery_signal["score_breakdown"]["total"] > manual_signal["score_breakdown"]["total"]
    assert delivery_signal["auto_intake_eligible"] is True

    intake_resp = synced_client.post("/api/optimization-signals/auto-intake", json={"max_created": 1})
    assert intake_resp.status_code == 200
    payload = intake_resp.json()
    assert len(payload["created"]) == 1
    assert payload["created"][0]["signal_id"] == delivery_signal["id"]

    requirements_resp = synced_client.get("/api/requirements?sort=score")
    created_requirement = next(
        item for item in requirements_resp.json()
        if item["source_ref"] == f"optimization-signal:{delivery_signal['id']}"
    )
    assert requirements_resp.json()[0]["id"] == created_requirement["id"]
    assert created_requirement["priority"] == "high"
    assert created_requirement["score_breakdown"]["signal_impact"] > 0
    assert created_requirement["score_breakdown"]["signal_risk"] > 0


def test_queue_advance_auto_intakes_best_signal_when_no_ready_requirements(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network-Sdk"
    requirement = RequirementRow(
        title="SDK delivery blocker",
        description_markdown="Blocked publish",
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
                "publish_blockers": ["required check pending: npm run build"],
            }),
        )
    )
    db_session.commit()

    with patch("server.services.workflow_orchestrator.plan_requirement") as mock_plan, patch(
        "server.services.workflow_orchestrator.start_requirement"
    ) as mock_start:
        resp = synced_client.post("/api/requirements/queue/advance")

    assert resp.status_code == 200
    payload = resp.json()
    assert "started" in payload
    started_requirement_id = payload["started"]
    created_requirement = db_session.query(RequirementRow).filter(RequirementRow.id == started_requirement_id).first()
    assert created_requirement is not None
    assert created_requirement.source == "optimization_signal"
    assert created_requirement.source_ref is not None
    assert mock_plan.call_count == 1
    assert mock_plan.call_args[0][1] == started_requirement_id
    assert mock_start.call_count == 1
    assert mock_start.call_args[0][1] == started_requirement_id


def test_lists_templates_and_operator_can_create_template_backed_requirements(synced_client):
    templates_resp = synced_client.get("/api/optimization-signals/templates")
    assert templates_resp.status_code == 200
    templates = templates_resp.json()
    template_keys = {item["template_key"] for item in templates}
    assert {"defect_reduction", "release_bottleneck", "approval_automation", "incident_recovery", "onboarding_friction", "docs_drift"} <= template_keys


def test_operator_template_requirements_generate_structured_acceptance_checks(synced_client):
    cases = [
        ("defect_reduction", "Defect signal", "/Users/cliff/workspace/agent/Synapse-Network"),
        ("release_bottleneck", "Release blocker", "/Users/cliff/workspace/agent/Synapse-Network-Provider"),
        ("approval_automation", "Approval friction", "/Users/cliff/workspace/agent/Synapse-Network-Sdk"),
        ("onboarding_friction", "Onboarding gap", "/Users/cliff/workspace/agent/Agents-Memory"),
        ("docs_drift", "Docs drift", "/Users/cliff/workspace/agent/Synapse-Network-Growing"),
    ]
    expected = {
        "defect_reduction": {"root_cause_documented", "regression_guard_added"},
        "release_bottleneck": {"release_blocker_removed", "rollback_path_documented"},
        "approval_automation": {"manual_override_reduced", "escalation_policy_preserved"},
        "onboarding_friction": {"readiness_gap_closed", "onboarding_contract_documented"},
        "docs_drift": {"docs_alignment_verified", "docs_examples_refreshed"},
    }

    for template_key, title, target_path in cases:
        create_resp = synced_client.post(
            f"/api/optimization-signals/templates/{template_key}/create-requirement",
            json={
                "title": title,
                "context_summary": f"Apply template {template_key}",
                "target_project_path": target_path,
            },
        )
        assert create_resp.status_code == 200
        detail = create_resp.json()
        plan_resp = synced_client.post(f"/api/requirements/{detail['requirement']['id']}/plan")
        assert plan_resp.status_code == 200
        acceptance_keys = {item["check_key"] for item in plan_resp.json()["acceptance_checks"]}
        assert expected[template_key] <= acceptance_keys
