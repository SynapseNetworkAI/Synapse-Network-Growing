from server.database import PlanningGoalRow
from server.services.planning.lifecycle import (
    _ensure_default_goals,
    ensure_active_manifest,
)


def test_ensure_default_goals_reseeds_empty_active_manifest(db_session):
    manifest = ensure_active_manifest(db_session)
    db_session.query(PlanningGoalRow).filter(
        PlanningGoalRow.manifest_id == manifest.id
    ).delete()
    db_session.commit()

    _ensure_default_goals(db_session, manifest)

    goals = (
        db_session.query(PlanningGoalRow)
        .filter(PlanningGoalRow.manifest_id == manifest.id)
        .all()
    )
    assert {goal.goal_key for goal in goals} == {
        "gateway_reliability",
        "operator_growth",
    }
