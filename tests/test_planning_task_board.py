from datetime import timedelta

from server.database import (
    RequirementCandidateRow,
    RequirementRow,
    WorkflowRunRow,
    utcnow,
)
from server.services.planning.lifecycle import ensure_active_manifest
from server.services.planning.product_opportunities import (
    ProductOpportunityRow,
    ensure_product_opportunity_table,
)
from server.services.planning.task_board import (
    _iso,
    _requirement_next_action,
    planning_task_board_snapshot,
)


def _column(board, key: str):
    return next(column for column in board["columns"] if column["key"] == key)


def _card_titles(board, key: str):
    return [card["title"] for card in _column(board, key)["cards"]]


def test_task_board_maps_requirement_statuses_to_columns(db_session):
    manifest = ensure_active_manifest(db_session)
    rows = [
        RequirementRow(
            title="Clarify staging docs",
            description_markdown="draft",
            status="planning",
            operating_manifest_id=int(manifest.id),
            goal_key="goal_a",
        ),
        RequirementRow(
            title="Implement SDK quickstart",
            description_markdown="run",
            status="running",
            operating_manifest_id=int(manifest.id),
            goal_key="goal_a",
        ),
        RequirementRow(
            title="Review human gate",
            description_markdown="gate",
            status="awaiting_operator",
            operating_manifest_id=int(manifest.id),
            goal_key="goal_a",
        ),
        RequirementRow(
            title="Fix failing workflow",
            description_markdown="blocked",
            status="blocked",
            operating_manifest_id=int(manifest.id),
            goal_key="goal_a",
        ),
        RequirementRow(
            title="Open PR for release",
            description_markdown="delivery",
            status="pr_opened",
            operating_manifest_id=int(manifest.id),
            goal_key="goal_a",
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()

    board = planning_task_board_snapshot(db_session)

    assert "Clarify staging docs" in _card_titles(board, "backlog")
    assert "Implement SDK quickstart" in _card_titles(board, "in_progress")
    assert "Review human gate" in _card_titles(board, "human_review")
    assert "Fix failing workflow" in _card_titles(board, "rework")
    assert "Open PR for release" in _card_titles(board, "delivery")


def test_task_board_route_returns_board_projection(client, db_session):
    manifest = ensure_active_manifest(db_session)
    requirement = RequirementRow(
        title="Route-projected requirement",
        description_markdown="route",
        status="ready",
        operating_manifest_id=int(manifest.id),
        goal_key="goal_a",
    )
    db_session.add(requirement)
    db_session.commit()

    response = client.get("/api/planning/task-board?include_done_days=30")

    assert response.status_code == 200
    board = response.json()
    assert board["summary"]["include_done_days"] == 30
    assert "Route-projected requirement" in _card_titles(board, "todo")


def test_task_board_done_column_is_time_bounded(db_session):
    manifest = ensure_active_manifest(db_session)
    fresh = RequirementRow(
        title="Fresh completed requirement",
        description_markdown="done",
        status="completed",
        operating_manifest_id=int(manifest.id),
        goal_key="goal_a",
        updated_at=utcnow() - timedelta(days=2),
    )
    old = RequirementRow(
        title="Old completed requirement",
        description_markdown="done",
        status="completed",
        operating_manifest_id=int(manifest.id),
        goal_key="goal_a",
        updated_at=utcnow() - timedelta(days=20),
    )
    db_session.add_all([fresh, old])
    db_session.commit()

    default_board = planning_task_board_snapshot(db_session)
    expanded_board = planning_task_board_snapshot(db_session, include_done_days=30)

    assert "Fresh completed requirement" in _card_titles(default_board, "done")
    assert "Old completed requirement" not in _card_titles(default_board, "done")
    assert "Old completed requirement" in _card_titles(expanded_board, "done")


def test_task_board_requirement_cards_cover_fallback_and_delivery_labels(db_session):
    manifest = ensure_active_manifest(db_session)
    completed_at = utcnow()
    rows = [
        RequirementRow(
            title="Unknown status falls back to backlog",
            description_markdown="fallback",
            status="mystery",
            workflow_state="",
            phase="",
            operating_manifest_id=int(manifest.id),
            goal_key="goal_a",
        ),
        RequirementRow(
            title="Ready requirement has todo guidance",
            description_markdown="todo",
            status="ready",
            project_key="sdk",
            operating_manifest_id=int(manifest.id),
            goal_key="goal_a",
        ),
        RequirementRow(
            title="Completed requirement has completion evidence",
            description_markdown="done",
            status="completed",
            completed_at=completed_at,
            operating_manifest_id=int(manifest.id),
            goal_key="goal_a",
        ),
        RequirementRow(
            title="Failed requirement records failure evidence",
            description_markdown="failed",
            status="failed",
            failure_reason="verification failed",
            operating_manifest_id=int(manifest.id),
            goal_key="goal_a",
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()

    board = planning_task_board_snapshot(db_session)

    backlog = _column(board, "backlog")["cards"]
    todo = _column(board, "todo")["cards"]
    done = _column(board, "done")["cards"]
    rework = _column(board, "rework")["cards"]
    assert any(
        card["title"] == "Unknown status falls back to backlog" for card in backlog
    )
    ready_card = next(
        card for card in todo if card["title"] == "Ready requirement has todo guidance"
    )
    completed_card = next(
        card
        for card in done
        if card["title"] == "Completed requirement has completion evidence"
    )
    failed_card = next(
        card
        for card in rework
        if card["title"] == "Failed requirement records failure evidence"
    )
    assert (
        ready_card["next_action"]
        == "Start or resume the declarative workflow when policy allows."
    )
    assert ready_card["delivery_label"] == "sdk"
    assert completed_card["delivery_label"] == "Completed"
    assert failed_card["delivery_label"] == "Failure recorded"
    assert _iso(None) is None
    assert _requirement_next_action(rows[0], "unexpected") == "Inspect task history."


def test_task_board_links_latest_workflow_without_standalone_workflow_card(db_session):
    manifest = ensure_active_manifest(db_session)
    requirement = RequirementRow(
        title="Requirement with active workflow",
        description_markdown="workflow evidence lives in detail",
        status="running",
        operating_manifest_id=int(manifest.id),
        goal_key="goal_a",
    )
    db_session.add(requirement)
    db_session.flush()
    workflow = WorkflowRunRow(
        requirement_id=int(requirement.id),
        operating_manifest_id=int(manifest.id),
        goal_key="goal_a",
        workflow_key="agent_self_repair",
        current_state="generate_patch",
        status="running",
    )
    db_session.add(workflow)
    db_session.flush()
    requirement.active_workflow_run_id = int(workflow.id)
    db_session.commit()

    board = planning_task_board_snapshot(db_session)
    cards = _column(board, "in_progress")["cards"]
    requirement_cards = [card for card in cards if card["card_kind"] == "requirement"]

    assert [
        card
        for column in board["columns"]
        for card in column["cards"]
        if card["id"].startswith("workflow:")
    ] == []
    assert requirement_cards[0]["latest_workflow_run_id"] == int(workflow.id)
    assert requirement_cards[0]["delivery_label"] == f"Workflow #{int(workflow.id)}"


def test_task_board_surfaces_unmaterialized_intake_cards(db_session):
    manifest = ensure_active_manifest(db_session)
    ensure_product_opportunity_table(db_session)
    db_session.add(
        ProductOpportunityRow(
            manifest_id=int(manifest.id),
            title="Provider onboarding opportunity",
            problem="Providers need a public preview onboarding path.",
            suggested_goal_key="provider_onboarding",
            recommended_lane="software_engineer",
            status="proposed",
        )
    )
    db_session.add(
        RequirementCandidateRow(
            manifest_id=int(manifest.id),
            goal_key="sdk_developer_quickstart",
            candidate_fingerprint="candidate-sdk",
            title="SDK quickstart candidate",
            description_markdown="candidate details",
            workflow_key="agent_self_repair",
            status="approved",
        )
    )
    db_session.commit()

    board = planning_task_board_snapshot(db_session)

    backlog = _column(board, "backlog")["cards"]
    todo = _column(board, "todo")["cards"]
    assert any(card["id"].startswith("product_opportunity:") for card in backlog)
    assert any(card["id"].startswith("candidate:") for card in todo)
    assert any(card["card_kind"] == "intake" for card in [*backlog, *todo])
