from __future__ import annotations

import json

from server.database import ArtifactRow, CompanyOperatingReviewRow, RequirementRow


def test_company_review_aggregates_bottlenecks_incidents_and_recommendations(synced_client, db_session):
    ready_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "SDK onboarding hardening",
            "description_markdown": "Improve the SDK onboarding automation path.",
            "priority": "high",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Sdk",
        },
    )
    ready_id = ready_resp.json()["requirement"]["id"]

    blocked_requirement = RequirementRow(
        title="Network publish blocked",
        description_markdown="Release gate is blocked.",
        status="done",
        priority="high",
        source="manual",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        current_plan_version=1,
    )
    db_session.add(blocked_requirement)
    db_session.flush()
    db_session.add(
        ArtifactRow(
            requirement_id=blocked_requirement.id,
            artifact_type="delivery_state",
            content_summary="Blocked publish",
            machine_readable_payload=json.dumps({
                "publish_status": "blocked",
                "publish_blockers": ["required check pending: npm run build"],
            }),
        )
    )
    db_session.add(
        ArtifactRow(
            requirement_id=blocked_requirement.id,
            artifact_type="bug_report",
            content_summary="Critical bug in release path",
            human_readable_body="Critical bug in release path",
            machine_readable_payload=json.dumps({
                "severity": "high",
                "summary": "Release validation exploded in production-like flow.",
            }),
        )
    )
    db_session.commit()

    review_resp = synced_client.get("/api/company-review")

    assert review_resp.status_code == 200
    payload = review_resp.json()
    assert payload["title"] == "Company Operating Review"
    assert payload["portfolio_summary"]["open_signals"] >= 1
    assert any(item["project_key"] == "synapse-network-sdk" for item in payload["project_highlights"])
    assert any("publish gate is blocked" in item["title"] for item in payload["bottlenecks"])
    assert any(
        "Delivery blocker" in item["title"] or "Defect signal" in item["title"] for item in payload["incidents"]
    )
    assert any(
        item["source_ref"] in {f"requirement:{ready_id}", None} or item["project_key"] == "synapse-network-sdk"
        for item in payload["next_cycle_recommendations"]
    )


def test_company_review_refresh_persists_new_snapshot(synced_client, db_session):
    first = synced_client.post("/api/company-review/refresh")
    second = synced_client.post("/api/company-review/refresh")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] > first.json()["id"]

    rows = db_session.query(CompanyOperatingReviewRow).order_by(CompanyOperatingReviewRow.id.asc()).all()
    assert len(rows) >= 2

    latest = synced_client.get("/api/company-review")
    assert latest.status_code == 200
    assert latest.json()["id"] == rows[-1].id
