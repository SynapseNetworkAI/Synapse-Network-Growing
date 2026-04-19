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

