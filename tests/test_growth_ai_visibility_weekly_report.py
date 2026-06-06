def test_weekly_report_ignores_resolved_collision_blocker(synced_client):
    for run_group, competitors in (
        ("2026-06-05-brand-collision-check", ["synapse.network"]),
        ("2026-06-06-brand-collision-resolved", []),
    ):
        for platform in ("chatgpt", "claude", "grok"):
            response = synced_client.post(
                "/api/growth/ai-visibility/checks",
                json={
                    "query": "What is Synapse Network for AI agents?",
                    "platform": platform,
                    "answer_summary": "Synapse Network is cited by an official source.",
                    "synapse_mentioned": True,
                    "synapse_cited": True,
                    "cited_urls": ["https://www.synapse-network.ai/"],
                    "competitor_mentions": competitors if platform == "chatgpt" else [],
                    "next_action": "Schedule weekly stability probe.",
                    "feed_key": "brand_disambiguation_www",
                    "run_group": run_group,
                },
            )
            assert response.status_code == 201

    report = synced_client.get("/api/growth/ai-visibility/weekly-report")

    assert report.status_code == 200
    payload = report.json()
    blocker_text = " ".join(payload["blockers"])
    action_text = " ".join(payload["next_actions"])
    assert "synapse.network" not in blocker_text
    assert "synapse.network" not in action_text
    assert payload["latest_run_group"] == "2026-06-06-brand-collision-resolved"
    assert payload["feed_reports"][0]["known_collision_competitors"] == []
