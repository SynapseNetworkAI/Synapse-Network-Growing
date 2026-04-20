import json

from server.database import (
    AtomInvocationRow,
    ProjectRow,
    RequirementCandidateRow,
    RequirementRow,
    WorkflowArtifactRow,
    WorkflowRunRow,
    WorkflowStateEventRow,
)


def _ensure_project(db_session):
    project = ProjectRow(
        project_key="synapse-network-growing",
        display_name="Synapse-Network-Growing",
        root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        status="active",
        default_branch="main",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _goalb_manifest_payload():
    return {
        "global_budget": {
            "daily_usd_limit": 25,
            "max_concurrent_workers": 2,
        },
        "focus_weights": {
            "reliability": 0.6,
            "growth": 0.3,
            "ops": 0.1,
        },
        "global_constraints": [
            "No production deploy without human approval.",
            "Dogfood validation must not send real Lark notifications.",
        ],
        "goals": [
            {
                "goal_key": "goalb",
                "domain": "ops",
                "status": "active",
                "intent": "验证 Growing 可以根据目标自动拆分任务，转成正式需求，并由 declarative workflow 自动执行跑通。",
                "success_metric": "goalb_demo_workflow_completed == true",
                "workflow_key": "gateway_reliability_repair",
                "project_key": "synapse-network-growing",
                "priority": "normal",
                "risk_level": "normal",
                "weight": 0.1,
            }
        ],
    }


def test_goalb_manifest_to_completed_workflow_product_flow(synced_client, db_session):
    _ensure_project(db_session)

    save_response = synced_client.put(
        "/api/planning/manifest/active",
        json={
            "version_name": "GoalB Dogfood",
            "cycle_label": "2026-W16",
            "payload": _goalb_manifest_payload(),
            "operator": "test",
        },
    )
    assert save_response.status_code == 200
    manifest = save_response.json()
    assert any(goal["goal_key"] == "goalb" for goal in manifest["payload"]["goals"])

    sweep_response = synced_client.post(
        "/api/planning/sweeps/run",
        json={"dry_run": False, "triggered_by": "goalb_test"},
    )
    assert sweep_response.status_code == 200
    sweep = sweep_response.json()
    assert sweep["status"] == "succeeded"
    assert len(sweep["created_candidate_ids"]) == 1, sweep
    candidate_id = int(sweep["created_candidate_ids"][0])

    candidate = db_session.get(RequirementCandidateRow, candidate_id)
    assert candidate is not None
    assert candidate.goal_key == "goalb"
    assert candidate.workflow_key == "gateway_reliability_repair"
    assert candidate.project_key == "synapse-network-growing"
    assert candidate.status == "materialized"
    metadata = json.loads(candidate.metadata_json or "{}")
    assert metadata["routing_decision"] == "auto_materialize_and_start"
    assert metadata["auto_materialized_requirement_id"]
    assert metadata["auto_started_workflow_run_id"]
    assert sweep["auto_materialized_requirement_ids"] == [metadata["auto_materialized_requirement_id"]]
    assert sweep["auto_started_workflow_run_ids"] == [metadata["auto_started_workflow_run_id"]]

    requirement_id = int(metadata["auto_materialized_requirement_id"])

    requirement = db_session.get(RequirementRow, requirement_id)
    assert requirement is not None
    assert requirement.goal_key == "goalb"
    assert requirement.requirement_candidate_id == candidate_id
    assert requirement.operating_manifest_id == manifest["id"]
    requirement_metadata = json.loads(requirement.intake_metadata_json or "{}")
    assert requirement_metadata["workflow_key"] == "gateway_reliability_repair"

    workflow_run_id = int(metadata["auto_started_workflow_run_id"])
    workflow_row = db_session.get(WorkflowRunRow, workflow_run_id)
    assert workflow_row is not None
    workflow = synced_client.get(f"/api/workflows/runs/{workflow_run_id}").json()
    assert workflow["requirement_id"] == requirement_id
    assert workflow["workflow_key"] == "gateway_reliability_repair"
    assert workflow["status"] in {"succeeded", "completed", "done"}
    assert workflow["current_state"] == "done"
    assert workflow["blackboard"]["pr"]["created"] is True
    assert workflow["blackboard"]["observation"]["restored"] is True

    run = db_session.get(WorkflowRunRow, workflow_run_id)
    assert run is not None
    assert run.goal_key == "goalb"
    assert run.operating_manifest_id == manifest["id"]
    assert run.requirement_id == requirement_id

    assert db_session.query(WorkflowStateEventRow).filter_by(workflow_run_id=workflow_run_id).count() >= 1
    assert db_session.query(AtomInvocationRow).filter_by(workflow_run_id=workflow_run_id).count() >= 1
    assert db_session.query(WorkflowArtifactRow).filter_by(workflow_run_id=workflow_run_id).count() >= 1

    completed_response = synced_client.get("/api/workflows/runs?tab=completed&page=1&page_size=20")
    assert completed_response.status_code == 200
    completed_items = completed_response.json()["items"]
    item = next(row for row in completed_items if row["id"] == workflow_run_id)
    assert item["goal_key"] == "goalb"
    assert item["requirement_id"] == requirement_id
    assert item["artifact_count"] >= 1
    assert item["atom_count"] >= 1

    mission_response = synced_client.get("/api/planning/mission-control")
    assert mission_response.status_code == 200
    lanes = {lane["goal_key"]: lane for lane in mission_response.json()["goal_lanes"]}
    assert lanes["goalb"]["rollup"]["candidate_status_counts"]["materialized"] == 1
    assert lanes["goalb"]["rollup"]["requirement_status_counts"]["completed"] == 1

    second_sweep_response = synced_client.post(
        "/api/planning/sweeps/run",
        json={"dry_run": False, "triggered_by": "goalb_second_pass"},
    )
    assert second_sweep_response.status_code == 200
    second_sweep = second_sweep_response.json()
    assert second_sweep["created_candidate_ids"], second_sweep
    assert second_sweep["auto_started_workflow_run_ids"], second_sweep
