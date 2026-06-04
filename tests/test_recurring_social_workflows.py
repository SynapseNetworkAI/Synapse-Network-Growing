from server.services.scheduling import (
    recurring_workflows as recurring_workflows_service,
)
from server.services.scheduling.recurring_workflows import (
    run_recurring_workflow,
    sync_recurring_workflows,
)


def test_x_social_post_observer_dry_run(synced_client):
    response = synced_client.post(
        "/api/recurring-workflows/x_social_post_observer_sweep/run",
        json={"dry_run": True},
    )
    assert response.status_code == 200
    assert response.json()["result"]["read_only"] is True


def test_x_daily_content_task_planner_recurring_dry_run(synced_client):
    response = synced_client.get("/api/recurring-workflows")
    assert response.status_code == 200
    workflow_keys = {row["workflow_key"] for row in response.json()}
    assert "x_social_daily_content_task_planner" in workflow_keys

    dry_run = synced_client.post(
        "/api/recurring-workflows/x_social_daily_content_task_planner/run",
        json={"dry_run": True},
    )

    assert dry_run.status_code == 200
    payload = dry_run.json()
    assert payload["status"] == "completed"
    assert payload["result"]["task_types"] == ["x_article_pack", "x_media_post"]
    assert payload["result"]["auto_publish"] is False
    assert payload["result"]["human_gate_required"] is True


def test_x_social_post_observer_sweep_recurring_run_invokes_service(
    db_session, monkeypatch
):
    sync_recurring_workflows(db_session)

    def fake_observer_sweep(db):
        assert db is db_session
        return {"observed_count": 1, "created_metric_ids": [9], "read_only": True}

    monkeypatch.setattr(
        "server.services.scheduling.recurring_workflows.run_x_social_post_observer_sweep",
        fake_observer_sweep,
    )

    result = run_recurring_workflow(
        db_session, workflow_key="x_social_post_observer_sweep", dry_run=False
    )

    assert result["status"] == "completed"
    assert result["result"]["created_metric_ids"] == [9]


def test_x_social_workflow_runner_dispatches_each_branch(db_session, monkeypatch):
    monkeypatch.setattr(
        recurring_workflows_service,
        "run_x_social_daily_content_planner",
        lambda db: {"branch": "daily", "db_matches": db is db_session},
    )
    monkeypatch.setattr(
        recurring_workflows_service,
        "run_x_social_daily_content_task_planner",
        lambda db: {"branch": "daily_tasks", "db_matches": db is db_session},
    )
    monkeypatch.setattr(
        recurring_workflows_service,
        "run_x_social_trend_radar_sweep",
        lambda db: {"branch": "trend", "db_matches": db is db_session},
    )
    monkeypatch.setattr(
        recurring_workflows_service,
        "run_x_social_repost_candidate_sweep",
        lambda db: {"branch": "repost", "db_matches": db is db_session},
    )
    monkeypatch.setattr(
        recurring_workflows_service,
        "run_x_social_weekly_analytics_review",
        lambda db: {"branch": "weekly", "db_matches": db is db_session},
    )

    assert (
        recurring_workflows_service._run_x_social_workflow(
            db_session, "x_social_daily_content_planner"
        )["branch"]
        == "daily"
    )
    assert (
        recurring_workflows_service._run_x_social_workflow(
            db_session, "x_social_daily_content_task_planner"
        )["branch"]
        == "daily_tasks"
    )
    assert (
        recurring_workflows_service._run_x_social_workflow(
            db_session, "x_social_trend_radar_sweep"
        )["branch"]
        == "trend"
    )
    assert (
        recurring_workflows_service._run_x_social_workflow(
            db_session, "x_social_repost_candidate_sweep"
        )["branch"]
        == "repost"
    )
    assert (
        recurring_workflows_service._run_x_social_workflow(
            db_session, "x_social_weekly_analytics_review"
        )["branch"]
        == "weekly"
    )
