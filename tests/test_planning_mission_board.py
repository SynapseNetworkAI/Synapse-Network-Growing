from pathlib import Path
import subprocess
from types import SimpleNamespace

from server.database import (
    RequirementCandidateRow,
    RequirementRow,
    WorkflowRunRow,
)
from server.services.planning.lifecycle import ensure_active_manifest
from server.services.planning.mission_lane_items import (
    candidate_next_action,
    release_next_action,
    requirement_next_action,
    workflow_next_action,
)
from server.services.planning.mission_board import mission_board_snapshot
from server.services.planning.product_opportunities import run_product_planning_sweep


def test_mission_board_returns_fixed_nested_lanes(db_session):
    manifest = ensure_active_manifest(db_session)
    run_product_planning_sweep(db_session)

    board = mission_board_snapshot(db_session)

    assert board["active_goal"] is not None
    assert set(board["lanes"]) == {
        "product_planner",
        "growth_lead",
        "software_engineer",
    }
    assert board["lanes"]["product_planner"]
    assert board["lane_summary"]["product_planner"]["count"] == len(
        board["lanes"]["product_planner"]
    )
    assert "nodes" not in board
    assert "edges" not in board
    assert board["manifest"]["id"] == manifest.id


def test_mission_board_api_returns_tree_not_graph(client):
    response = client.get("/api/planning/mission-board")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload["lanes"]) == {
        "product_planner",
        "growth_lead",
        "software_engineer",
    }
    assert "unassigned" in payload
    assert "next_actions" in payload
    assert "nodes" not in payload
    assert "edges" not in payload


def test_mission_board_projects_engineering_work_under_active_goal(db_session):
    manifest = ensure_active_manifest(db_session)
    active_goal_key = mission_board_snapshot(db_session)["active_goal"]["goal_key"]
    candidate = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key=active_goal_key,
        candidate_fingerprint="candidate-ship-core-loop",
        title="Implement core loop candidate",
        workflow_key="agent_self_repair",
        risk_level="normal",
        confidence=0.9,
        status="pending",
    )
    db_session.add(candidate)
    db_session.commit()

    board = mission_board_snapshot(db_session)

    titles = [item["title"] for item in board["lanes"]["software_engineer"]]
    assert "Implement core loop candidate" in titles


def test_mission_board_projects_active_goal_traction_proof(db_session):
    ensure_active_manifest(db_session)

    board = mission_board_snapshot(db_session)

    proof = board["traction_proof"]
    proof_keys = {item["key"] for item in proof["items"]}
    assert proof["status"] in {"present", "incomplete", "blocked"}
    assert {
        "docs_staging_visits",
        "provider_onboarding",
        "sdk_demo_completion",
        "x_engagement",
        "staging_release",
        "ops_lane_health",
    }.issubset(proof_keys)
    assert all(
        item["status"] in {"present", "missing", "blocked"} for item in proof["items"]
    )
    assert (
        next(item for item in proof["items"] if item["key"] == "docs_staging_visits")[
            "status"
        ]
        == "missing"
    )


def test_mission_board_surfaces_active_orphans_but_not_terminal_history(db_session):
    manifest = ensure_active_manifest(db_session)
    active_requirement = RequirementRow(
        title="Active orphan requirement",
        description_markdown="missing goal lineage",
        status="running",
        operating_manifest_id=int(manifest.id),
        goal_key="",
    )
    terminal_requirement = RequirementRow(
        title="Completed orphan requirement",
        description_markdown="historical missing lineage",
        status="completed",
        operating_manifest_id=int(manifest.id),
        goal_key="",
    )
    db_session.add_all([active_requirement, terminal_requirement])
    db_session.flush()
    db_session.add(
        WorkflowRunRow(
            requirement_id=int(active_requirement.id),
            operating_manifest_id=int(manifest.id),
            goal_key="",
            workflow_key="agent_self_repair",
            current_state="awaiting_operator",
            status="running",
        )
    )
    db_session.commit()

    board = mission_board_snapshot(db_session)

    titles = [item["title"] for item in board["unassigned"]["items"]]
    assert "Active orphan requirement" in titles
    assert "Completed orphan requirement" not in titles
    assert board["unassigned"]["count"] >= 2
    assert board["next_actions"][0]["lane"] == "unassigned"


def test_reset_goal_mission_lanes_requires_confirm():
    script = Path("scripts/dev/reset_goal_mission_lanes.py")
    result = subprocess.run(
        ["python3", str(script)],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "LOCAL_MISSION_RESET" in result.stdout


def test_mission_lane_next_actions_cover_status_variants():
    assert "Materialize" in candidate_next_action(SimpleNamespace(status="approved"))
    assert "Fail-Closed" in candidate_next_action(
        SimpleNamespace(status="validation_failed")
    )
    assert "Watch workflow" in requirement_next_action(
        SimpleNamespace(status="running")
    )
    assert "resolve blocker" in requirement_next_action(
        SimpleNamespace(status="blocked")
    )
    assert "human gate" in workflow_next_action(
        SimpleNamespace(status="running", current_state="awaiting_operator")
    )
    assert "root cause" in workflow_next_action(
        SimpleNamespace(status="failed", current_state="")
    )
    assert "Monitor" in workflow_next_action(
        SimpleNamespace(status="queued", current_state="")
    )
    assert "deploy staging" in release_next_action(SimpleNamespace(status="requested"))
    assert "deploy failure" in release_next_action(SimpleNamespace(status="failed"))
