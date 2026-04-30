import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from server.database import (
    PlanningGoalRow,
    RequirementCandidateRow,
    RequirementRow,
    SocialAccountRow,
    SocialPostMetricRow,
    SocialPostDraftRow,
    SocialReplyItemRow,
    SocialRepostCandidateRow,
    WorkflowRunRow,
    utcnow,
)
from server.services.planning.lifecycle import ensure_active_manifest
from server.services.planning.mission_lane_items import (
    candidate_next_action,
    release_next_action,
    requirement_next_action,
    workflow_next_action,
)
from server.services.planning import mission_workbench as mission_workbench_module
from server.services.planning.mission_board import (
    _primary_active_goal,
    _software_items_for_active_goals,
    mission_board_snapshot,
)
from server.services.planning.mission_process_stages import (
    _process_key_for_item_type,
    _process_stages,
)
from server.services.planning.mission_workbench import (
    _aggregate_stage_status,
    _detail_api_for_item,
    _normalize_stage_status,
    mission_workbench_snapshot,
)
from server.services.planning.product_opportunities import run_product_planning_sweep
from server.services.planning import social_mission_items


def test_mission_board_returns_fixed_nested_lanes(db_session):
    manifest = ensure_active_manifest(db_session)
    run_product_planning_sweep(db_session)

    board = mission_board_snapshot(db_session)

    assert board["active_goal"] is not None
    assert board["active_goals"]
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
    opportunity = board["lanes"]["product_planner"][0]
    assert opportunity["deep_link"].startswith(
        "/planning?tab=opportunities&opportunity="
    )


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
    assert "active_goals" in payload


def test_mission_workbench_api_returns_tree_grid_projection(client):
    response = client.get("/api/planning/mission-workbench")

    assert response.status_code == 200
    payload = response.json()
    assert "nodes" not in payload
    assert "edges" not in payload
    assert payload["root"] is not None
    assert payload["root"]["type"] == "company_goal"
    assert set(payload["root"]["stage_statuses"]) == {
        "opportunity",
        "candidate",
        "requirement",
        "workflow",
        "pr",
        "release",
        "online_record",
    }


def test_reply_drafts_stay_in_publishing_not_mission_tasks(db_session):
    ensure_active_manifest(db_session)
    reply = SocialReplyItemRow(
        platform="x",
        external_reply_id="reply-draft-local-only",
        source_author_handle="sama",
        incoming_text="Interesting agent economy signal.",
        suggested_reply="Relevant reply draft awaiting human review.",
        status="needs_review",
        source_url="https://x.com/sama/status/123",
    )
    db_session.add(reply)
    db_session.commit()

    board = mission_board_snapshot(db_session)
    growth_items = board["lanes"]["growth_lead"]
    assert f"social_reply:{reply.id}" not in {item["id"] for item in growth_items}
    assert all(item["type"] != "reply_draft" for item in growth_items)

    workbench = mission_workbench_snapshot(db_session)

    def walk(node):
        if not node:
            return []
        nodes = [node]
        for child in node["children"]:
            nodes.extend(walk(child))
        return nodes

    assert all(node["type"] != "reply_draft" for node in walk(workbench["root"]))


def test_mission_workbench_growth_lane_uses_social_summaries_not_repost_rows(db_session):
    ensure_active_manifest(db_session)
    repost = SocialRepostCandidateRow(
        platform="x",
        source_url="https://x.com/OpenAI/status/123",
        source_text="A relevant AI agent signal.",
        author_handle="OpenAI",
        suggested_quote="Synapse angle on agent payment rails.",
        relevance_score=90,
        status="candidate",
    )
    account = SocialAccountRow(
        platform="x",
        handle="SynapseNetworkA",
        display_name="Synapse Network",
        secret_ref="x-official",
    )
    db_session.add(account)
    db_session.flush()
    failed_draft = SocialPostDraftRow(
        platform="x",
        account_id=int(account.id),
        source_type="daily_planner",
        title="X planner draft failed",
        body_text="",
        status="failed",
        generated_by="x_social_daily_content_planner",
        failure_summary="agent_generation_failed: Codex CLI execution timed out after 180s",
    )
    draft = SocialPostDraftRow(
        platform="x",
        account_id=int(account.id),
        source_type="daily_planner",
        title="X planner draft ready",
        body_text="Reviewable X draft.",
        status="needs_review",
        generated_by="x_social_daily_content_planner",
    )
    published_draft = SocialPostDraftRow(
        platform="x",
        account_id=int(account.id),
        source_type="daily_planner",
        title="X planner draft published",
        body_text="Published X draft.",
        status="published",
        generated_by="x_social_daily_content_planner",
        external_post_id="2049401935174975542",
        published_at=utcnow(),
    )
    db_session.add_all([repost, failed_draft, draft, published_draft])
    db_session.flush()
    metric = SocialPostMetricRow(
        post_id=int(published_draft.id),
        external_post_id="2049401935174975542",
        impressions=100,
        likes=5,
        summary="Observed published post metrics.",
    )
    db_session.add(metric)
    db_session.commit()

    workbench = mission_workbench_snapshot(db_session)

    def walk(node):
        nodes = [node]
        for child in node["children"]:
            nodes.extend(walk(child))
        return nodes

    nodes = walk(workbench["root"])
    assert all(node["type"] != "repost_candidate" for node in nodes)
    assert any(node["type"] == "social_daily_inventory" for node in nodes)
    assert all(node["id"] != f"social_draft:{failed_draft.id}" for node in nodes)
    summary = next(node for node in nodes if node["type"] == "social_daily_inventory")
    assert "historical failures" in summary["evidence_label"]
    draft_node = next(node for node in nodes if node["id"] == f"social_draft:{draft.id}")
    labels = [stage["label"] for stage in draft_node["process_stages"]]
    assert labels == ["Generated", "Needs Review", "Approved/Edited", "Published", "Metrics"]
    assert "Requirement" not in labels
    assert draft_node["evidence_label"] == "19 chars"
    published_node = next(
        node for node in nodes if node["id"] == f"social_draft:{published_draft.id}"
    )
    assert published_node["status"] == "published"
    assert published_node["evidence_label"] == "X post 2049401935174975542"
    assert published_node["external_post_id"] == "2049401935174975542"
    assert published_node["external_url"].endswith(
        "/SynapseNetworkA/status/2049401935174975542"
    )
    assert [
        (stage["label"], stage["status"])
        for stage in published_node["process_stages"]
    ] == [
        ("Generated", "completed"),
        ("Needs Review", "completed"),
        ("Approved/Edited", "completed"),
        ("Published", "completed"),
        ("Metrics", "completed"),
    ]


def test_mission_workbench_status_helpers_cover_stage_variants():
    assert _normalize_stage_status("failed") == "blocked"
    assert _normalize_stage_status("queued") == "running"
    assert _normalize_stage_status("merged") == "completed"
    assert _normalize_stage_status("ready") == "active"
    assert _normalize_stage_status("unknown") == "missing"
    assert _aggregate_stage_status(["missing", "blocked"]) == "blocked"
    assert _aggregate_stage_status(["missing", "running"]) == "running"
    assert _aggregate_stage_status(["missing", "completed"]) == "completed"
    assert _detail_api_for_item("candidate:10") == "/api/planning/candidates/10"
    assert _detail_api_for_item("invalid") is None


def test_candidate_detail_api_returns_single_candidate(client, db_session):
    manifest = ensure_active_manifest(db_session)
    goal = PlanningGoalRow(
        manifest_id=int(manifest.id),
        goal_key="sdk_developer_quickstart",
        title="SDK & Developer Experience quickstart",
        intent_markdown="Ship a 5-minute SDK quickstart.",
        success_metric="Quickstart completes with receipt evidence.",
        status="active",
        workflow_key="agent_self_repair",
        project_key="synapse-network-sdk",
    )
    db_session.add(goal)
    db_session.flush()
    candidate = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key="sdk_developer_quickstart",
        candidate_fingerprint="sdk-candidate-detail",
        title="Ship a 5-minute SDK quickstart with runnable agent demo",
        description_markdown="Build SDK quickstart docs and smoke evidence.",
        project_key="synapse-network-sdk",
        workflow_key="agent_self_repair",
        status="validation_failed",
        metadata_json='{"acceptance_validation_error": "safe rg command was not allowlisted"}',
    )
    db_session.add(candidate)
    db_session.commit()

    response = client.get(f"/api/planning/candidates/{candidate.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == candidate.id
    assert payload["goal_key"] == "sdk_developer_quickstart"
    assert payload["project_key"] == "synapse-network-sdk"
    assert payload["metadata"]["acceptance_validation_error"] == "safe rg command was not allowlisted"


def test_candidate_detail_api_returns_404_for_missing_candidate(client):
    response = client.get("/api/planning/candidates/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "candidate not found"


def test_candidate_retry_validation_clones_failed_candidate_when_contract_now_passes(client, db_session):
    manifest = ensure_active_manifest(db_session)
    db_session.add(
        PlanningGoalRow(
            manifest_id=int(manifest.id),
            goal_key="sdk_developer_quickstart",
            title="SDK & Developer Experience quickstart",
            intent_markdown="Ship a 5-minute SDK quickstart.",
            success_metric="Quickstart completes with receipt evidence.",
            status="active",
            workflow_key="agent_self_repair",
            project_key="synapse-network-sdk",
        )
    )
    contract = {
        "acceptance_kind": "business",
        "execution_acceptance_steps": [
            {
                "step_key": "sdk_rg",
                "title": "SDK quickstart evidence exists",
                "expected_result": "SDK docs include quickstart and receipt evidence.",
                "required_commands": [
                    'cd /Users/cliff/workspace/agent/Synapse-Network-Sdk && rg -n "quickstart|receipt" README.md docs/sdk'
                ],
            }
        ],
    }
    candidate = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key="sdk_developer_quickstart",
        candidate_fingerprint="sdk-candidate-retry",
        title="Ship SDK quickstart",
        description_markdown="Build SDK quickstart docs and smoke evidence.",
        project_key="synapse-network-sdk",
        workflow_key="agent_self_repair",
        status="validation_failed",
        metadata_json='{"acceptance_validation_error": "old allowlist", "acceptance_contract": %s}' % json.dumps(contract),
    )
    db_session.add(candidate)
    db_session.commit()

    response = client.post(f"/api/planning/candidates/{candidate.id}/retry-validation", json={"operator": "tester"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] != candidate.id
    assert payload["status"] == "pending"
    assert payload["metadata"]["retry_of_candidate_id"] == candidate.id
    assert "acceptance_validation_error" not in payload["metadata"]


def test_candidate_retry_validation_reports_retry_errors(client, db_session):
    manifest = ensure_active_manifest(db_session)
    invalid_contract = {
        "acceptance_kind": "business",
        "execution_acceptance_steps": [
            {
                "step_key": "unsafe",
                "title": "Unsafe evidence is rejected",
                "expected_result": "Unsafe commands cannot run.",
                "required_commands": ["deploy production"],
            }
        ],
    }
    candidate = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key="sdk_developer_quickstart",
        candidate_fingerprint="sdk-candidate-retry-failure",
        title="Ship SDK quickstart",
        description_markdown="Build SDK quickstart docs and smoke evidence.",
        project_key="synapse-network-sdk",
        workflow_key="agent_self_repair",
        status="validation_failed",
        metadata_json='{"acceptance_contract": %s}' % json.dumps(invalid_contract),
    )
    pending_candidate = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key="sdk_developer_quickstart",
        candidate_fingerprint="sdk-candidate-not-retryable",
        title="Pending SDK quickstart",
        description_markdown="Pending rows are not retryable.",
        project_key="synapse-network-sdk",
        workflow_key="agent_self_repair",
        status="pending",
        metadata_json="{}",
    )
    db_session.add_all([candidate, pending_candidate])
    db_session.commit()

    missing = client.post("/api/planning/candidates/999999/retry-validation", json={"operator": "tester"})
    not_retryable = client.post(f"/api/planning/candidates/{pending_candidate.id}/retry-validation", json={"operator": "tester"})
    invalid = client.post(f"/api/planning/candidates/{candidate.id}/retry-validation", json={"operator": "tester"})

    assert missing.status_code == 400
    assert not_retryable.status_code == 400
    assert invalid.status_code == 400
    db_session.refresh(candidate)
    metadata = json.loads(candidate.metadata_json or "{}")
    assert "deploy" in metadata["last_retry_validation_error"]
    assert metadata["last_retry_validation_at"]


def test_mission_workbench_returns_empty_tree_without_active_goal(
    db_session, monkeypatch
):
    manifest = ensure_active_manifest(db_session)
    monkeypatch.setattr(
        mission_workbench_module, "_active_goals", lambda _db, _manifest_id: []
    )

    payload = mission_workbench_snapshot(db_session)

    assert payload["root"] is None
    assert payload["summary"]["active_goal_count"] == 0
    assert payload["manifest"]["id"] == manifest.id


def test_mission_board_private_helpers_cover_primary_and_dedup(db_session, monkeypatch):
    company = {"goal_key": "company", "domain": "company"}
    product = {"goal_key": "product", "domain": "product"}
    assert _primary_active_goal([]) is None
    assert _primary_active_goal([product, company]) == company

    def fake_software_items(_db, _manifest_id, goal_key):
        return [
            {
                "id": "candidate:1",
                "type": "requirement_candidate",
                "title": f"Shared item {goal_key}",
                "status": "pending",
                "risk_level": "normal",
                "next_action": "Review.",
                "deep_link": "/planning?tab=engineering",
                "evidence_label": "",
                "updated_at": None,
            }
        ]

    monkeypatch.setattr(
        "server.services.planning.mission_board.software_items", fake_software_items
    )
    items = _software_items_for_active_goals(
        db_session,
        1,
        [{"goal_key": ""}, {"goal_key": "a"}, {"goal_key": "b"}],
    )
    assert [item["id"] for item in items] == ["candidate:1"]


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


def test_mission_board_aggregates_engineering_work_across_active_goals(db_session):
    manifest = ensure_active_manifest(db_session)
    db_session.add(
        PlanningGoalRow(
            manifest_id=int(manifest.id),
            goal_key="sdk_developer_quickstart",
            title="SDK & Developer Experience quickstart",
            intent_markdown="Ship SDK quickstart proof.",
            success_metric="SDK demo completes with receipt evidence.",
            domain="product",
            status="active",
            workflow_key="agent_self_repair",
            project_key="synapse-network-sdk",
        )
    )
    db_session.add(
        RequirementCandidateRow(
            manifest_id=int(manifest.id),
            goal_key="sdk_developer_quickstart",
            candidate_fingerprint="candidate-sdk-quickstart",
            title="Create SDK quickstart evidence candidate",
            workflow_key="agent_self_repair",
            risk_level="normal",
            confidence=0.9,
            status="pending",
        )
    )
    db_session.commit()

    board = mission_board_snapshot(db_session)

    assert len(board["active_goals"]) >= 2
    titles = [item["title"] for item in board["lanes"]["software_engineer"]]
    assert "Create SDK quickstart evidence candidate" in titles


def test_mission_workbench_nests_goal_lane_and_candidate(db_session):
    manifest = ensure_active_manifest(db_session)
    db_session.add(
        PlanningGoalRow(
            manifest_id=int(manifest.id),
            goal_key="sdk_developer_quickstart",
            title="SDK & Developer Experience quickstart",
            intent_markdown="Ship SDK quickstart proof.",
            success_metric="SDK demo completes with receipt evidence.",
            domain="product",
            status="active",
            workflow_key="agent_self_repair",
            project_key="synapse-network-sdk",
        )
    )
    db_session.add(
        RequirementCandidateRow(
            manifest_id=int(manifest.id),
            goal_key="sdk_developer_quickstart",
            candidate_fingerprint="candidate-sdk-quickstart-workbench",
            title="Create SDK quickstart evidence candidate",
            workflow_key="agent_self_repair",
            risk_level="normal",
            confidence=0.9,
            status="pending",
        )
    )
    db_session.commit()

    workbench = mission_workbench_snapshot(db_session)

    root = workbench["root"]
    sdk_goal = next(
        child
        for child in root["children"]
        if child["id"] == "goal:sdk_developer_quickstart"
    )
    software_lane = next(
        child for child in sdk_goal["children"] if child["lane"] == "software_engineer"
    )
    assert software_lane["stage_statuses"]["candidate"] == "waiting"
    assert any(
        child["title"] == "Create SDK quickstart evidence candidate"
        for child in software_lane["children"]
    )


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


def test_process_stage_variants_cover_non_engineering_flows():
    assert _process_key_for_item_type("unknown") == "mission_context"
    assert _process_stages("unknown", "active", "waiting") == []
    assert _process_stages("product_opportunity", "rejected", "blocked")[-1] == {
        "key": "closed",
        "label": "Deferred/Rejected",
        "status": "blocked",
    }
    assert _process_stages("product_opportunity", "approved", "completed")[2][
        "status"
    ] == "completed"
    assert _process_stages("publishing_draft", "published", "completed")[3][
        "status"
    ] == "completed"
    assert _process_stages("publishing_draft", "approved", "waiting")[2][
        "status"
    ] == "waiting"
    assert _process_stages("social_metrics_loop", "completed", "completed")[-1][
        "status"
    ] == "completed"
    assert _process_stages("release_task", "requested", "waiting")[4][
        "key"
    ] == "release"


def test_social_mission_item_helper_branches():
    assert social_mission_items._daily_inventory_status(3, 0) == "needs_review"
    assert social_mission_items._daily_inventory_status(0, 1) == "blocked"
    assert social_mission_items._daily_inventory_status(1, 0) == "needs_review"
    assert social_mission_items._daily_inventory_status(0, 0) == "pending"

    published = SimpleNamespace(
        status="published",
        external_post_id="post-1",
        account=SimpleNamespace(handle="SynapseNetworkA"),
        published_at=None,
        body_text="published",
        failure_summary=None,
    )
    approved = SimpleNamespace(
        status="approved",
        external_post_id=None,
        account=None,
        published_at=None,
        body_text="approved body",
        failure_summary=None,
    )
    failed = SimpleNamespace(status="failed")
    generating = SimpleNamespace(status="generating")
    unknown = SimpleNamespace(status="mystery")

    assert "Published" in social_mission_items._social_draft_next_action(published)
    assert "Publish to X" in social_mission_items._social_draft_next_action(approved)
    assert social_mission_items._social_draft_evidence_label(published) == "X post post-1"
    assert social_mission_items._social_draft_external_url(published).endswith(
        "/SynapseNetworkA/status/post-1"
    )
    assert social_mission_items._social_draft_external_url(approved) is None
    assert social_mission_items._social_draft_process_stages(failed, False)[0][
        "status"
    ] == "blocked"
    assert social_mission_items._social_draft_process_stages(generating, False)[0][
        "status"
    ] == "running"
    assert social_mission_items._social_draft_process_stages(approved, False)[2][
        "status"
    ] == "waiting"
    assert social_mission_items._social_draft_process_stages(unknown, False)[0][
        "status"
    ] == "missing"
