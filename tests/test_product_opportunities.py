from server.database import PlanningGoalRow
from server.services.planning.lifecycle import ensure_active_manifest
from server.services.planning.product_opportunities import (
    ProductOpportunityRow,
    create_goal_from_product_opportunity,
    defer_product_opportunity,
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
    opportunity = db_session.query(ProductOpportunityRow).filter(ProductOpportunityRow.status == "proposed").first()

    result = create_goal_from_product_opportunity(db_session, int(opportunity.id), operator="operator")

    assert result["goal"]["goal_key"] == opportunity.suggested_goal_key
    assert result["goal"]["metadata"]["source"] == "product_opportunity"
    assert result["opportunity"]["status"] == "goal_created"
    assert result["opportunity"]["converted_goal_id"] == result["goal"]["id"]


def test_rejected_and_deferred_opportunities_do_not_create_goals(db_session):
    run_product_planning_sweep(db_session)
    opportunities = db_session.query(ProductOpportunityRow).filter(ProductOpportunityRow.status == "proposed").limit(2).all()

    rejected = reject_product_opportunity(db_session, int(opportunities[0].id), operator="operator", reason="not_now")
    deferred = defer_product_opportunity(db_session, int(opportunities[1].id), operator="operator", reason="future_cycle")

    assert rejected["status"] == "rejected"
    assert deferred["status"] == "deferred"
