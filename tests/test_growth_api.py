from server.database_growth import (
    GrowthDiscoveryListingRow,
    GrowthLeadRow,
    GrowthOutreachEventRow,
    GrowthOutreachMessageRow,
)
from server.services.growth.draft_agent import GrowthDraftResult


def _investor_payload(**overrides):
    payload = {
        "lead_type": "investor",
        "project_key": "growing",
        "name": "Ada Seed",
        "organization": "Agent Infra Capital",
        "role_title": "Partner",
        "public_profile_urls": ["https://example.com/ada"],
        "contact_channels": [{"kind": "email", "value": "ada@example.com"}],
        "source_kind": "manual",
        "source_url": "https://example.com/ada",
        "fit_score": 88,
        "confidence_score": 75,
        "evidence": [{"source": "portfolio", "reason": "agent infra thesis"}],
        "next_action": "Draft intro",
    }
    payload.update(overrides)
    return payload


def _provider_payload(**overrides):
    payload = _investor_payload(
        lead_type="provider",
        name="MCP Weather API",
        organization="Weather Tools",
        role_title="Maintainer",
        source_url="https://github.com/example/mcp-weather",
        fit_score=82,
        next_action="Invite provider onboarding",
    )
    payload.update(overrides)
    return payload


def test_growth_leads_import_list_filter_and_dedupe(synced_client, db_session):
    created = synced_client.post("/api/growth/leads", json=_investor_payload())
    assert created.status_code == 201
    assert created.json()["lead_type"] == "investor"

    imported = synced_client.post(
        "/api/growth/leads/import",
        json={"leads": [_investor_payload(), _provider_payload()]},
    )
    assert imported.status_code == 201
    assert imported.json()["created"] == 1
    assert imported.json()["reused"] == 1

    filtered = synced_client.get("/api/growth/leads?lead_type=provider&q=Weather")
    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "MCP Weather API"
    assert payload["lead_type_counts"]["investor"] == 1
    assert db_session.query(GrowthLeadRow).count() == 2
    assert db_session.query(GrowthOutreachEventRow).count() == 2


def test_growth_draft_agent_success_and_fail_closed(
    monkeypatch, synced_client, db_session
):
    lead = synced_client.post("/api/growth/leads", json=_investor_payload()).json()

    def fake_draft(**kwargs):
        return GrowthDraftResult(
            subject="Synapse as an agent settlement layer",
            body="Ada, your agent infra thesis looks close to what Synapse is building.",
            personalization_evidence=[
                {"source": "portfolio", "reason": "agent infrastructure fit"}
            ],
            metadata={"model": "fake"},
        )

    monkeypatch.setattr(
        "server.services.growth.workbench.generate_outreach_draft", fake_draft
    )
    draft = synced_client.post(
        f"/api/growth/leads/{lead['id']}/draft-message",
        json={"channel": "email", "actor": "codex"},
    )
    assert draft.status_code == 201
    assert draft.json()["status"] == "needs_review"
    assert db_session.query(GrowthOutreachMessageRow).count() == 1

    def broken_draft(**kwargs):
        raise ValueError("agent_json_parse_failed")

    monkeypatch.setattr(
        "server.services.growth.workbench.generate_outreach_draft", broken_draft
    )
    failed = synced_client.post(
        f"/api/growth/leads/{lead['id']}/draft-message",
        json={"channel": "email", "actor": "codex"},
    )
    assert failed.status_code == 400
    assert db_session.query(GrowthOutreachMessageRow).count() == 1


def test_growth_message_lifecycle_and_do_not_contact(synced_client, monkeypatch):
    lead = synced_client.post("/api/growth/leads", json=_provider_payload()).json()
    monkeypatch.setattr(
        "server.services.growth.workbench.generate_outreach_draft",
        lambda **kwargs: GrowthDraftResult(
            subject="List your MCP API on Synapse",
            body="Your MCP Weather API could become a paid agent-callable service.",
            personalization_evidence=[{"source": "repo", "reason": "MCP server"}],
            metadata={"model": "fake"},
        ),
    )
    message = synced_client.post(
        f"/api/growth/leads/{lead['id']}/draft-message",
        json={"channel": "email", "actor": "codex"},
    ).json()

    approved = synced_client.post(
        f"/api/growth/messages/{message['id']}/approve",
        json={"actor": "operator"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    queued = synced_client.post(
        f"/api/growth/messages/{message['id']}/queue",
        json={"actor": "operator"},
    )
    assert queued.status_code == 200
    assert queued.json()["status"] == "queued"

    sent = synced_client.post(
        f"/api/growth/messages/{message['id']}/mark-sent",
        json={"actor": "operator", "metadata": {"channel_result": "manual"}},
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"

    reply = synced_client.post(
        f"/api/growth/messages/{message['id']}/reply",
        json={
            "actor": "operator",
            "reply_summary": "Interested in provider onboarding.",
            "interested": True,
        },
    )
    assert reply.status_code == 200
    detail = synced_client.get(f"/api/growth/leads/{lead['id']}").json()
    assert detail["lead"]["status"] == "interested"
    assert {event["event_type"] for event in detail["events"]} >= {
        "message_approved",
        "message_queued",
        "message_sent",
        "reply_received",
    }

    blocked = synced_client.post(
        f"/api/growth/leads/{lead['id']}/do-not-contact",
        json={"actor": "operator", "summary": "Asked to stop."},
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "do_not_contact"


def test_growth_ai_visibility_and_discovery_listing(synced_client, db_session):
    check = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "MCP monetization platform",
            "platform": "perplexity",
            "answer_summary": "Synapse was not mentioned.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "competitor_mentions": ["RapidAPI"],
            "next_action": "Create MCP monetization answer block.",
        },
    )
    assert check.status_code == 201
    assert (
        synced_client.get("/api/growth/ai-visibility/checks?q=MCP").json()["total"] == 1
    )

    listing = synced_client.post(
        "/api/growth/discovery-listings",
        json={
            "surface": "official_mcp_registry",
            "target_repo": "SynapseNetworkAI/Synapse-MCP",
            "package_name": "synapse-network-mcp",
            "status": "candidate",
        },
    )
    assert listing.status_code == 201
    listing_id = listing.json()["id"]
    patched = synced_client.patch(
        f"/api/growth/discovery-listings/{listing_id}",
        json={
            "status": "listed",
            "listing_url": "https://registry.modelcontextprotocol.io/servers/synapse",
            "verification_evidence": {"checked_by": "operator"},
        },
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "listed"
    assert db_session.query(GrowthDiscoveryListingRow).count() == 1


def test_growth_overview_counts(synced_client):
    synced_client.post("/api/growth/leads", json=_investor_payload())
    synced_client.post("/api/growth/leads", json=_provider_payload())
    synced_client.post(
        "/api/growth/discovery-listings",
        json={"surface": "glama", "status": "candidate"},
    )

    overview = synced_client.get("/api/growth/overview")
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["lead_counts"]["investor"] == 1
    assert payload["lead_counts"]["provider"] == 1
    assert payload["discovery_counts"]["candidate"] == 1
