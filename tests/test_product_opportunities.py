from server.database import PlanningGoalRow
from server.services.planning.lifecycle import ensure_active_manifest
from server.services.planning.product_opportunities import (
    ProductOpportunityRow,
    create_goal_from_product_opportunity,
    defer_product_opportunity,
    get_product_opportunity,
    product_opportunity_summary,
    reject_product_opportunity,
    run_product_planning_sweep,
)


def test_product_planning_sweep_generates_opportunity_without_goal(db_session):
    ensure_active_manifest(db_session)
    before_goals = db_session.query(PlanningGoalRow).count()

    result = run_product_planning_sweep(db_session)

    assert result["auto_create_goal"] is False
    assert result["created_count"] >= 1
    assert db_session.query(ProductOpportunityRow).count() >= 1
    assert db_session.query(PlanningGoalRow).count() == before_goals


def test_product_opportunity_can_create_goal_with_lineage(db_session):
    run_product_planning_sweep(db_session)
    opportunity = (
        db_session.query(ProductOpportunityRow)
        .filter(ProductOpportunityRow.status == "proposed")
        .first()
    )

    result = create_goal_from_product_opportunity(
        db_session, int(opportunity.id), operator="operator"
    )

    assert result["goal"]["goal_key"] == opportunity.suggested_goal_key
    assert result["goal"]["metadata"]["source"] == "product_opportunity"
    assert result["opportunity"]["status"] == "goal_created"
    assert result["opportunity"]["converted_goal_id"] == result["goal"]["id"]


def test_rejected_and_deferred_opportunities_do_not_create_goals(db_session):
    run_product_planning_sweep(db_session)
    opportunities = (
        db_session.query(ProductOpportunityRow)
        .filter(ProductOpportunityRow.status == "proposed")
        .limit(2)
        .all()
    )

    rejected = reject_product_opportunity(
        db_session, int(opportunities[0].id), operator="operator", reason="not_now"
    )
    deferred = defer_product_opportunity(
        db_session, int(opportunities[1].id), operator="operator", reason="future_cycle"
    )

    assert rejected["status"] == "rejected"
    assert deferred["status"] == "deferred"


def test_product_opportunity_summary_counts_review_states(db_session):
    run_product_planning_sweep(db_session)
    opportunities = (
        db_session.query(ProductOpportunityRow)
        .filter(ProductOpportunityRow.status == "proposed")
        .limit(2)
        .all()
    )
    reject_product_opportunity(
        db_session, int(opportunities[0].id), operator="operator", reason="not_now"
    )
    defer_product_opportunity(
        db_session, int(opportunities[1].id), operator="operator", reason="later"
    )

    summary = product_opportunity_summary(db_session)

    assert summary["total"] >= 2
    assert summary["counts"]["rejected"] == 1
    assert summary["counts"]["deferred"] == 1
    assert summary["pending_review"] == summary["counts"]["proposed"]


def test_product_opportunity_api_routes_cover_review_actions(client, db_session):
    run_product_planning_sweep(db_session)
    opportunities = (
        db_session.query(ProductOpportunityRow)
        .filter(ProductOpportunityRow.status == "proposed")
        .limit(3)
        .all()
    )

    listed = client.get("/api/planning/product-opportunities")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 3

    detail = client.get(f"/api/planning/product-opportunities/{opportunities[0].id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == opportunities[0].id

    created = client.post(
        f"/api/planning/product-opportunities/{opportunities[0].id}/create-goal",
        json={"operator": "operator"},
    )
    assert created.status_code == 200
    assert created.json()["already_created"] is False
    repeat = client.post(
        f"/api/planning/product-opportunities/{opportunities[0].id}/create-goal",
        json={"operator": "operator"},
    )
    assert repeat.status_code == 200
    assert repeat.json()["already_created"] is True

    rejected = client.post(
        f"/api/planning/product-opportunities/{opportunities[1].id}/reject",
        json={"operator": "operator", "reason": "not_now"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    deferred = client.post(
        f"/api/planning/product-opportunities/{opportunities[2].id}/defer",
        json={"operator": "operator", "reason": "later"},
    )
    assert deferred.status_code == 200
    assert deferred.json()["status"] == "deferred"


def test_product_opportunity_error_paths(db_session):
    run_product_planning_sweep(db_session)
    opportunity = db_session.query(ProductOpportunityRow).first()
    reject_product_opportunity(
        db_session, int(opportunity.id), operator="operator", reason="no"
    )

    try:
        create_goal_from_product_opportunity(
            db_session, int(opportunity.id), operator="operator"
        )
    except ValueError as exc:
        assert "cannot create goals" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("rejected opportunity created a goal")

    try:
        get_product_opportunity(db_session, 999999)
    except ValueError as exc:
        assert "not found" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("missing opportunity returned")
