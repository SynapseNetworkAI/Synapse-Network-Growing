from server.database_social_distribution import (
    SocialDistributionDocumentRow,
    SocialDistributionTaskRow,
)
from server.services.social.agent_content_pack import AgentDistributionDraft


def test_distribution_generation_commits_each_platform_result(
    synced_client, db_session, monkeypatch
):
    calls = []

    def fake_platform_draft(**kwargs):
        calls.append(kwargs["platform"])
        if len(calls) == 2:
            db_session.expire_all()
            assert db_session.query(SocialDistributionTaskRow).count() == 1
            assert db_session.query(SocialDistributionDocumentRow).count() == 2
        return AgentDistributionDraft(
            title=f"{kwargs['platform']} title",
            body=f"{kwargs['platform']} body",
            checklist="Human Gate required.",
            risk_level="normal",
            rationale="transaction test",
            metadata={"generated_by": "test"},
        )

    monkeypatch.setattr(
        "server.services.social.distribution_generation.generate_platform_task_draft",
        fake_platform_draft,
    )
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    selected = [
        row["id"]
        for row in accounts
        if (row["platform"], row["channel_key"])
        in {("x", "official"), ("hacker_news", "news.ycombinator.com")}
    ]
    asset = synced_client.post(
        "/api/social/distribution/assets",
        json={"title": "Incremental generation", "summary": "Persist each channel."},
    ).json()

    response = synced_client.post(
        f"/api/social/distribution/assets/{asset['id']}/generate-tasks",
        json={"account_ids": selected},
    )

    assert response.status_code == 200
    assert len(response.json()["generated_task_ids"]) == 2
    assert db_session.query(SocialDistributionTaskRow).count() == 2
    assert db_session.query(SocialDistributionDocumentRow).count() == 3
