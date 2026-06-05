def test_ai_visibility_next_cycle_surfaces_mcp_deploy_blocker(synced_client):
    deploy_blocker = (
        "Local deploy runner cannot access fabled-archive-494108-k5 until gcloud "
        "credentials are refreshed."
    )
    next_action = (
        "Refresh gcloud credentials, then rerun docs-front and user-front staging "
        "before promoting production."
    )

    created = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "Deploy MCP paid API visibility assets",
            "platform": "deployment_validation",
            "answer_summary": "Production docs and www llms.txt are not live yet.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "missing_facts": [deploy_blocker],
            "next_action": next_action,
            "feed_key": "mcp_paid_api_discovery",
            "run_group": "2026-06-05-www-canonical-deploy-blocker",
            "metadata": {
                "official_homepage": "https://www.synapse-network.ai/",
                "docs_front_staging_task_id": 221,
                "user_front_staging_task_id": 222,
            },
        },
    )
    assert created.status_code == 201

    weekly_payload = synced_client.get("/api/growth/ai-visibility/weekly-report").json()
    assert weekly_payload["recommended_feed_key"] == "mcp_paid_api_discovery"
    assert deploy_blocker in weekly_payload["blockers"]
    assert next_action in weekly_payload["blockers"]

    next_cycle_payload = synced_client.get(
        "/api/growth/ai-visibility/next-cycle"
    ).json()
    assert next_cycle_payload["feed_key"] == "mcp_paid_api_discovery"
    assert deploy_blocker in next_cycle_payload["blockers"]
    assert next_action in next_cycle_payload["next_actions"]
    assert "mcp_paid_api_discovery" in next_cycle_payload["feed_validation_command"]
    assert "--execute" in next_cycle_payload["api_execute_command"]
