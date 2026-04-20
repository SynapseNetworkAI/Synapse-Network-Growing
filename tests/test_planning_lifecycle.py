import json

from server.database import (
    HumanGateRequestRow,
    OperatingManifestRow,
    ProjectRow,
    ReleaseRecordRow,
    RequirementCandidateRow,
    RequirementRow,
    WorkflowRunRow,
    WorkflowStateEventRow,
)
from server.services.planning.lifecycle import (
    approve_and_run_candidate,
    approve_candidate,
    drop_goal,
    ensure_active_manifest,
    list_manifest_history,
    materialize_candidate,
    run_planner_sweep,
)


def _project(db):
    row = ProjectRow(project_key="synapse", display_name="Synapse", root_path="/tmp/synapse")
    db.add(row)
    db.commit()
    return row


def _candidate_metadata():
    return json.dumps(
        {
            "acceptance_contract": {
                "execution_acceptance_steps": [
                    {
                        "step_key": "business_result",
                        "title": "Business result is verified",
                        "expected_result": "The candidate outcome is proven by workflow evidence.",
                        "required_evidence_types": ["workflow_command_result"],
                    }
                ]
            }
        }
    )


def test_manifest_history_paginates_and_searches_all_archived_manifests(db_session):
    for idx in range(15):
        db_session.add(
            OperatingManifestRow(
                manifest_key=f"archive-{idx}",
                version_name=f"Archived Cycle {idx}",
                cycle_label=f"2026-W{idx:02d}",
                status="archived",
                payload_json=json.dumps({"goals": [{"goal_key": f"goal_{idx}", "status": "active"}]}),
            )
        )
    db_session.commit()

    page = list_manifest_history(db_session, page=2, page_size=5, status="archived")
    assert page["total"] == 15
    assert page["page"] == 2
    assert len(page["items"]) == 5

    searched = list_manifest_history(db_session, search="goal_14")
    assert searched["total"] == 1
    assert searched["items"][0]["manifest_key"] == "archive-14"


def test_planner_sweep_ignores_dropped_goals_and_creates_candidate_for_active_goal(db_session):
    _project(db_session)
    manifest = ensure_active_manifest(db_session)
    payload = json.loads(manifest.payload_json)
    payload["goals"][0]["status"] = "dropped"
    manifest.payload_json = json.dumps(payload)
    db_session.commit()

    sweep = run_planner_sweep(db_session, dry_run=False)
    created = json.loads(sweep.created_candidate_ids_json)
    suppressed = json.loads(sweep.suppressed_items_json)

    assert created
    assert any(item["reason"] == "goal_dropped" for item in suppressed)
    created_rows = db_session.query(RequirementCandidateRow).filter(RequirementCandidateRow.id.in_(created)).all()
    assert {row.goal_key for row in created_rows} == {"operator_growth"}


def test_candidate_materialize_carries_goal_lineage_to_requirement(db_session):
    project = _project(db_session)
    manifest = ensure_active_manifest(db_session)
    candidate = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key="gateway_reliability",
        candidate_fingerprint="fp-materialize",
        title="Fix reliability",
        description_markdown="Need a concrete requirement.",
        project_id=int(project.id),
        project_key=project.project_key,
        workflow_key="gateway_reliability_repair",
        status="pending",
        metadata_json=_candidate_metadata(),
    )
    db_session.add(candidate)
    db_session.commit()

    approve_candidate(db_session, int(candidate.id))
    result = materialize_candidate(db_session, int(candidate.id))
    requirement = db_session.get(RequirementRow, int(result["requirement_id"]))

    assert requirement is not None
    assert requirement.operating_manifest_id == manifest.id
    assert requirement.goal_key == "gateway_reliability"
    assert requirement.requirement_candidate_id == candidate.id


def test_candidate_materialize_fail_closed_without_acceptance_steps(db_session):
    project = _project(db_session)
    manifest = ensure_active_manifest(db_session)
    candidate = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key="gateway_reliability",
        candidate_fingerprint="fp-materialize-invalid",
        title="Invalid acceptance",
        description_markdown="Planner did not provide evidence-bound acceptance.",
        project_id=int(project.id),
        project_key=project.project_key,
        workflow_key="gateway_reliability_repair",
        status="pending",
    )
    db_session.add(candidate)
    db_session.commit()

    approve_candidate(db_session, int(candidate.id))

    try:
        materialize_candidate(db_session, int(candidate.id))
    except ValueError as exc:
        assert "acceptance validation" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("invalid candidate materialized without acceptance steps")

    db_session.refresh(candidate)
    assert candidate.status == "validation_failed"
    assert candidate.suppression_reason == "acceptance_validation_failed"
    assert candidate.materialized_requirement_id is None
    assert db_session.query(RequirementRow).filter(RequirementRow.requirement_candidate_id == int(candidate.id)).count() == 0


def test_candidate_approve_and_run_creates_requirement_and_workflow(db_session):
    project = _project(db_session)
    manifest = ensure_active_manifest(db_session)
    candidate = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key="gateway_reliability",
        candidate_fingerprint="fp-approve-run",
        title="Fix gateway precision automatically",
        description_markdown="Turn this candidate into a requirement and run the workflow.",
        project_id=int(project.id),
        project_key=project.project_key,
        workflow_key="gateway_reliability_repair",
        priority="normal",
        risk_level="normal",
        status="pending",
        metadata_json=_candidate_metadata(),
    )
    db_session.add(candidate)
    db_session.commit()

    result = approve_and_run_candidate(db_session, int(candidate.id), operator="operator")
    requirement = db_session.get(RequirementRow, int(result["requirement_id"]))
    workflow = db_session.get(WorkflowRunRow, int(result["workflow_run_id"]))
    db_session.refresh(candidate)

    assert result["candidate"]["status"] == "materialized"
    assert result["auto_run_status"] in {"workflow_started", "workflow_completed", "workflow_needs_human"}
    assert result["next_action"] in {"view_workflow", "view_completion_evidence", "review_human_gate", "inspect_failure"}
    assert requirement is not None
    assert requirement.goal_key == "gateway_reliability"
    assert requirement.requirement_candidate_id == candidate.id
    assert workflow is not None
    assert workflow.requirement_id == requirement.id
    assert workflow.goal_key == "gateway_reliability"
    assert workflow.operating_manifest_id == manifest.id
    assert candidate.materialized_requirement_id == requirement.id


def test_candidate_approve_and_run_routes_high_risk_to_human_gate(db_session):
    project = _project(db_session)
    manifest = ensure_active_manifest(db_session)
    candidate = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key="gateway_reliability",
        candidate_fingerprint="fp-approve-run-high-risk",
        title="High risk gateway repair",
        description_markdown="This candidate should not bypass the workflow human gate.",
        project_id=int(project.id),
        project_key=project.project_key,
        workflow_key="agent_self_repair",
        priority="high",
        risk_level="high",
        status="pending",
        metadata_json=_candidate_metadata(),
    )
    db_session.add(candidate)
    db_session.commit()

    result = approve_and_run_candidate(db_session, int(candidate.id), operator="operator")
    workflow = db_session.get(WorkflowRunRow, int(result["workflow_run_id"]))
    gates = (
        db_session.query(HumanGateRequestRow)
        .filter(HumanGateRequestRow.workflow_run_id == int(result["workflow_run_id"]))
        .all()
    )

    assert workflow is not None
    assert workflow.risk_level == "high"
    assert result["auto_run_status"] == "workflow_needs_human"
    assert result["next_action"] == "review_human_gate"
    assert any(gate.status == "pending" for gate in gates)


def test_candidate_approve_and_run_api(db_session, client):
    project = _project(db_session)
    manifest = ensure_active_manifest(db_session)
    candidate = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key="gateway_reliability",
        candidate_fingerprint="fp-approve-run-api",
        title="API approve and run",
        description_markdown="Exercise the combined endpoint.",
        project_id=int(project.id),
        project_key=project.project_key,
        workflow_key="gateway_reliability_repair",
        priority="normal",
        risk_level="normal",
        status="pending",
        metadata_json=_candidate_metadata(),
    )
    db_session.add(candidate)
    db_session.commit()

    response = client.post(f"/api/planning/candidates/{int(candidate.id)}/approve-and-run", json={"operator": "operator"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate"]["status"] == "materialized"
    assert payload["requirement_id"] > 0
    assert payload["workflow_run_id"] > 0


def test_mission_control_api_groups_candidates_by_goal_and_includes_history(client, db_session):
    project = _project(db_session)
    manifest = ensure_active_manifest(db_session)
    payload = json.loads(manifest.payload_json)
    payload["goals"][1]["status"] = "dropped"
    manifest.payload_json = json.dumps(payload)
    db_session.add(
        RequirementCandidateRow(
            manifest_id=int(manifest.id),
            goal_key="gateway_reliability",
            candidate_fingerprint="fp-mission-pending",
            title="Add gateway guardrail",
            description_markdown="Candidate belongs to gateway reliability.",
            project_id=int(project.id),
            project_key=project.project_key,
            workflow_key="gateway_reliability_repair",
            status="pending",
        )
    )
    db_session.add(
        RequirementCandidateRow(
            manifest_id=int(manifest.id),
            goal_key="operator_growth",
            candidate_fingerprint="fp-mission-dropped",
            title="Old growth candidate",
            description_markdown="Candidate belongs to a dropped goal.",
            project_id=int(project.id),
            project_key=project.project_key,
            workflow_key="agent_self_repair",
            status="suppressed",
            suppression_reason="goal_dropped",
        )
    )
    db_session.commit()

    response = client.get("/api/planning/mission-control")
    assert response.status_code == 200
    payload = response.json()

    assert payload["manifest"]["id"] == manifest.id
    assert payload["global_steering"]["focus_weights"]["reliability"] == 0.6
    assert payload["candidate_totals"]["pending"] == 1
    assert payload["candidate_totals"]["suppressed"] == 1
    assert payload["history_preview"]["total"] >= 1

    lanes = {lane["goal_key"]: lane for lane in payload["goal_lanes"]}
    assert lanes["gateway_reliability"]["candidates"][0]["title"] == "Add gateway guardrail"
    assert lanes["gateway_reliability"]["rollup"]["candidate_status_counts"]["pending"] == 1
    assert lanes["operator_growth"]["goal"]["status"] == "dropped"
    assert lanes["operator_growth"]["candidates"][0]["suppression_reason"] == "goal_dropped"


def test_drop_goal_cascades_without_rollback(db_session):
    project = _project(db_session)
    manifest = ensure_active_manifest(db_session)
    pending_candidate = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key="gateway_reliability",
        candidate_fingerprint="fp-drop",
        title="Pending candidate",
        description_markdown="Pending.",
        project_id=int(project.id),
        project_key=project.project_key,
        status="pending",
    )
    draft_requirement = RequirementRow(
        title="Draft req",
        description_markdown="Draft",
        status="draft",
        priority="normal",
        source="test",
        intake_metadata_json="{}",
        operating_manifest_id=int(manifest.id),
        goal_key="gateway_reliability",
        project_id=int(project.id),
        project_key=project.project_key,
        project_display_name=project.display_name,
        target_project_path=project.root_path,
    )
    running_requirement = RequirementRow(
        title="Running req",
        description_markdown="Running",
        status="in_progress",
        priority="normal",
        source="test",
        intake_metadata_json="{}",
        operating_manifest_id=int(manifest.id),
        goal_key="gateway_reliability",
        project_id=int(project.id),
        project_key=project.project_key,
        project_display_name=project.display_name,
        target_project_path=project.root_path,
    )
    delivered_requirement = RequirementRow(
        title="Delivered req",
        description_markdown="Delivered",
        status="done",
        priority="normal",
        source="test",
        intake_metadata_json="{}",
        operating_manifest_id=int(manifest.id),
        goal_key="gateway_reliability",
        project_id=int(project.id),
        project_key=project.project_key,
        project_display_name=project.display_name,
        target_project_path=project.root_path,
    )
    db_session.add_all([pending_candidate, draft_requirement, running_requirement, delivered_requirement])
    db_session.flush()
    workflow = WorkflowRunRow(
        requirement_id=int(running_requirement.id),
        operating_manifest_id=int(manifest.id),
        goal_key="gateway_reliability",
        workflow_key="gateway_reliability_repair",
        current_state="patch",
        status="running",
        blackboard_json="{}",
    )
    db_session.add(workflow)
    db_session.flush()
    running_requirement.active_workflow_run_id = int(workflow.id)
    release = ReleaseRecordRow(
        requirement_id=int(delivered_requirement.id),
        operating_manifest_id=int(manifest.id),
        goal_key="gateway_reliability",
        status="released",
        delivery_state="completed",
    )
    db_session.add(release)
    db_session.commit()

    result = drop_goal(
        db_session,
        manifest_id=int(manifest.id),
        goal_key="gateway_reliability",
        reason="strategy changed",
    )

    db_session.refresh(pending_candidate)
    db_session.refresh(draft_requirement)
    db_session.refresh(workflow)
    db_session.refresh(release)

    assert pending_candidate.status == "suppressed"
    assert pending_candidate.suppression_reason == "goal_dropped"
    assert draft_requirement.status == "cancelled"
    assert workflow.status == "awaiting_operator"
    assert workflow.current_state == "awaiting_operator"
    assert release.status == "released"
    assert release.delivery_state == "completed"
    assert result["halt_summary"]["rollback_triggered"] is False
    assert db_session.query(WorkflowStateEventRow).filter(WorkflowStateEventRow.event_type == "goal_dropped_halt_requested").count() == 1
    assert db_session.query(HumanGateRequestRow).filter(HumanGateRequestRow.gate_type == "goal_dropped_halt").count() == 1
