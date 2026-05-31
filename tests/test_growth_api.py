from server.database_growth import (
    GrowthDiscoveryListingRow,
    GrowthLeadRow,
    GrowthOutreachEventRow,
    GrowthOutreachMessageRow,
    GrowthResearchRunRow,
)
from server.services.local_secrets import write_local_secret_version
from server.services.growth.draft_agent import GrowthDraftResult
from server.services.growth.provider_sources import run_enabled_provider_sources


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


def test_growth_source_config_crud_and_firecrawl_dry_run(synced_client, db_session):
    created = synced_client.post(
        "/api/growth/source-configs",
        json={
            "name": "Provider Discovery: MCP + API Services",
            "config_type": "github_mcp_repos",
            "query": {
                "queries": ["mcp server search api"],
                "seed_urls": ["https://github.com/firecrawl/firecrawl-mcp-server"],
            },
            "thresholds": {"create_lead_score": 70, "auto_draft_score": 80},
        },
    )
    assert created.status_code == 201
    source = created.json()
    assert source["config_type"] == "github_mcp_repos"

    listed = synced_client.get("/api/growth/source-configs").json()
    assert listed["total"] == 1

    patched = synced_client.patch(
        f"/api/growth/source-configs/{source['id']}",
        json={"status": "paused"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "paused"
    synced_client.patch(f"/api/growth/source-configs/{source['id']}", json={"status": "enabled"})

    dry_run = synced_client.post(
        f"/api/growth/source-configs/{source['id']}/run",
        json={"dry_run": True, "create_drafts": True},
    )
    assert dry_run.status_code == 200
    payload = dry_run.json()
    assert payload["dry_run"] is True
    assert payload["candidate_count"] == 1
    assert payload["created_count"] == 0
    assert payload["result"]["candidates"][0]["name"] == "Firecrawl"
    assert db_session.query(GrowthLeadRow).count() == 0
    assert db_session.query(GrowthResearchRunRow).count() == 1


def test_growth_provider_source_apply_creates_firecrawl_and_draft(
    synced_client, db_session, monkeypatch
):
    monkeypatch.setattr(
        "server.services.growth.workbench.generate_outreach_draft",
        lambda **kwargs: GrowthDraftResult(
            subject="Synapse provider onboarding",
            body="Firecrawl could expose metered agent web-data calls through Synapse.",
            personalization_evidence=[{"source": "github", "reason": "MCP server"}],
            metadata={"model": "fake"},
        ),
    )
    source = synced_client.post("/api/growth/source-configs/default-provider").json()

    apply_run = synced_client.post(
        f"/api/growth/source-configs/{source['id']}/run",
        json={"dry_run": False, "create_drafts": True},
    )
    assert apply_run.status_code == 200
    payload = apply_run.json()
    assert payload["created_count"] == 1
    assert payload["drafted_count"] == 1

    lead = db_session.query(GrowthLeadRow).one()
    assert lead.name == "Firecrawl"
    assert lead.status == "drafted"
    assert "firecrawl" in lead.source_url
    assert "partnerships@firecrawl.dev" in lead.contact_channels_json
    assert "partner-integration" in lead.metadata_json
    assert db_session.query(GrowthOutreachMessageRow).count() == 1
    message = db_session.query(GrowthOutreachMessageRow).one()
    assert "manual_gmail_draft_only" in message.metadata_json
    assert "partnerships@firecrawl.dev" in message.metadata_json
    assert (
        db_session.query(GrowthOutreachEventRow)
        .filter(GrowthOutreachEventRow.event_type == "message_drafted")
        .count()
        == 1
    )

    second_run = synced_client.post(
        f"/api/growth/source-configs/{source['id']}/run",
        json={"dry_run": False, "create_drafts": True},
    ).json()
    assert second_run["created_count"] == 0
    assert second_run["reused_count"] == 1
    assert db_session.query(GrowthLeadRow).count() == 1


def test_growth_provider_source_does_not_draft_without_trusted_email(
    synced_client, db_session
):
    source = synced_client.post(
        "/api/growth/source-configs",
        json={
            "name": "Tavily provider discovery",
            "config_type": "github_mcp_repos",
            "query": {
                "queries": ["tavily mcp"],
                "seed_urls": ["https://github.com/tavily-ai/tavily-mcp"],
            },
            "thresholds": {"create_lead_score": 70, "auto_draft_score": 80},
        },
    ).json()

    apply_run = synced_client.post(
        f"/api/growth/source-configs/{source['id']}/run",
        json={"dry_run": False, "create_drafts": True},
    )
    assert apply_run.status_code == 200
    payload = apply_run.json()
    assert payload["created_count"] == 1
    assert payload["drafted_count"] == 0
    assert "blocked_missing_trusted_contact_email" in payload["error_summary"]
    assert db_session.query(GrowthLeadRow).count() == 1
    assert db_session.query(GrowthOutreachMessageRow).count() == 0


def test_growth_gmail_draft_requires_approval_and_auth(synced_client, monkeypatch):
    monkeypatch.setattr(
        "server.services.growth.workbench.generate_outreach_draft",
        lambda **kwargs: GrowthDraftResult(
            subject="Provider onboarding",
            body="Would you review Synapse provider onboarding?",
            personalization_evidence=[{"source": "repo", "reason": "provider fit"}],
            metadata={"model": "fake"},
        ),
    )
    lead = synced_client.post("/api/growth/leads", json=_provider_payload()).json()
    message = synced_client.post(
        f"/api/growth/leads/{lead['id']}/draft-message",
        json={"channel": "email", "actor": "codex"},
    ).json()

    not_approved = synced_client.post(
        f"/api/growth/messages/{message['id']}/create-gmail-draft",
        json={"actor": "operator"},
    )
    assert not_approved.status_code == 400
    assert "approved" in not_approved.json()["detail"]

    synced_client.post(
        f"/api/growth/messages/{message['id']}/approve",
        json={"actor": "operator"},
    )
    no_auth = synced_client.post(
        f"/api/growth/messages/{message['id']}/create-gmail-draft",
        json={"actor": "operator"},
    )
    assert no_auth.status_code == 400
    assert "gmail_auth_required" in no_auth.json()["detail"]


def test_growth_gmail_draft_records_evidence_without_sending(
    synced_client, db_session, monkeypatch
):
    monkeypatch.setattr(
        "server.services.growth.workbench.generate_outreach_draft",
        lambda **kwargs: GrowthDraftResult(
            subject="Provider onboarding",
            body="Would you review Synapse provider onboarding?",
            personalization_evidence=[{"source": "repo", "reason": "provider fit"}],
            metadata={"model": "fake", "contact_email": "partnerships@firecrawl.dev"},
        ),
    )
    lead = synced_client.post(
        "/api/growth/leads",
        json=_provider_payload(
            contact_channels=[
                {
                    "kind": "email",
                    "value": "partnerships@firecrawl.dev",
                    "confidence": "high",
                    "source_url": "https://docs.firecrawl.dev/partner-integration",
                }
            ],
        ),
    ).json()
    message = synced_client.post(
        f"/api/growth/leads/{lead['id']}/draft-message",
        json={"channel": "email", "actor": "codex"},
    ).json()
    synced_client.post(
        f"/api/growth/messages/{message['id']}/approve",
        json={"actor": "operator"},
    )
    monkeypatch.setattr("server.config.GMAIL_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setattr("server.config.GMAIL_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr("server.config.GMAIL_SENDER_EMAIL", "cliff@synapse-network.ai")
    monkeypatch.setattr("server.config.GMAIL_OAUTH_REFRESH_TOKEN_LOCAL_KEY", "gmail-test")
    monkeypatch.setattr("server.config.OPS_LOCAL_SECRET_ENCRYPTION_KEY", "test-local-secret-key")
    write_local_secret_version(db_session, "gmail-test", "refresh-token")
    db_session.commit()

    calls: list[str] = []

    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def json(self):
            return self._payload

    def fake_post(url, **kwargs):
        calls.append(url)
        if "oauth2.googleapis.com/token" in url:
            return FakeResponse({"access_token": "access-token"})
        if "gmail.googleapis.com/gmail/v1/users/me/drafts" in url:
            assert "Authorization" in kwargs["headers"]
            return FakeResponse({"id": "draft-123", "message": {"id": "msg-123", "threadId": "thread-123"}})
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("server.services.growth.gmail_drafts.httpx.post", fake_post)

    created = synced_client.post(
        f"/api/growth/messages/{message['id']}/create-gmail-draft",
        json={"actor": "operator", "metadata": {"human_gate": True}},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["status"] == "queued"
    assert payload["metadata"]["gmail_draft_id"] == "draft-123"
    assert payload["metadata"]["contact_email"] == "partnerships@firecrawl.dev"
    assert any("drafts" in call for call in calls)
    assert all("send" not in call for call in calls)
    assert (
        db_session.query(GrowthOutreachEventRow)
        .filter(GrowthOutreachEventRow.event_type == "gmail_draft_created")
        .count()
        == 1
    )


def test_growth_source_config_rejects_unknown_type(synced_client):
    response = synced_client.post(
        "/api/growth/source-configs",
        json={"name": "Bad source", "config_type": "scrape_everything"},
    )
    assert response.status_code == 400


def test_growth_source_config_reuse_patch_runs_and_error_paths(synced_client):
    request = {
        "name": "Reusable Provider Source",
        "config_type": "github_mcp_repos",
        "query": {"queries": ["firecrawl mcp"], "seed_urls": []},
    }
    first = synced_client.post("/api/growth/source-configs", json=request)
    duplicate = synced_client.post("/api/growth/source-configs", json=request)
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == first.json()["id"]

    source_id = first.json()["id"]
    patched = synced_client.patch(
        f"/api/growth/source-configs/{source_id}",
        json={
            "name": "Reusable Provider Source Updated",
            "description": "GitHub and MCP provider discovery",
            "query": {"queries": ["tavily mcp"], "seed_urls": []},
            "cadence": {"kind": "manual"},
            "thresholds": {"create_lead_score": 75, "auto_draft_score": 85},
        },
    )
    assert patched.status_code == 200
    assert patched.json()["name"].endswith("Updated")

    disabled = synced_client.patch(
        f"/api/growth/source-configs/{source_id}", json={"status": "paused"}
    )
    assert disabled.status_code == 200
    blocked_run = synced_client.post(
        f"/api/growth/source-configs/{source_id}/run",
        json={"dry_run": True},
    )
    assert blocked_run.status_code == 400
    assert "not enabled" in blocked_run.json()["detail"]

    synced_client.patch(f"/api/growth/source-configs/{source_id}", json={"status": "enabled"})
    run = synced_client.post(
        f"/api/growth/source-configs/{source_id}/run",
        json={"dry_run": True, "max_results": 1, "create_drafts": False},
    )
    assert run.status_code == 200
    run_id = run.json()["id"]
    runs = synced_client.get(f"/api/growth/source-configs/{source_id}/runs?limit=1&offset=0")
    assert runs.status_code == 200
    assert runs.json()["total"] == 1
    assert runs.json()["items"][0]["id"] == run_id
    assert synced_client.get(f"/api/growth/research-runs/{run_id}").status_code == 200
    assert synced_client.get("/api/growth/source-configs/999999/runs").status_code == 404
    assert synced_client.get("/api/growth/research-runs/999999").status_code == 404


def test_growth_provider_source_sweep_bootstraps_default_source(db_session):
    result = run_enabled_provider_sources(db_session, dry_run=True)
    assert result.dry_run is True
    assert result.source_count == 1
    assert result.candidate_count >= 1
    assert db_session.query(GrowthResearchRunRow).count() == 1


def test_growth_gmail_draft_edge_cases(synced_client, db_session, monkeypatch):
    lead = synced_client.post(
        "/api/growth/leads",
        json=_provider_payload(contact_channels=[]),
    ).json()
    monkeypatch.setattr(
        "server.services.growth.workbench.generate_outreach_draft",
        lambda **kwargs: GrowthDraftResult(
            subject="Provider onboarding",
            body="Would you review Synapse provider onboarding?",
            personalization_evidence=[{"source": "repo", "reason": "provider fit"}],
            metadata={"model": "fake"},
        ),
    )
    message = synced_client.post(
        f"/api/growth/leads/{lead['id']}/draft-message",
        json={"channel": "email", "actor": "codex"},
    ).json()
    synced_client.post(
        f"/api/growth/messages/{message['id']}/approve",
        json={"actor": "operator"},
    )
    missing_contact = synced_client.post(
        f"/api/growth/messages/{message['id']}/create-gmail-draft",
        json={"actor": "operator"},
    )
    assert missing_contact.status_code == 400
    assert "trusted_contact_email" in missing_contact.json()["detail"]

    row = db_session.query(GrowthOutreachMessageRow).filter_by(id=message["id"]).one()
    row.metadata_json = '{"gmail_draft_id":"existing-draft"}'
    db_session.commit()
    existing = synced_client.post(
        f"/api/growth/messages/{message['id']}/create-gmail-draft",
        json={"actor": "operator"},
    )
    assert existing.status_code == 200
    assert existing.json()["metadata"]["gmail_draft_id"] == "existing-draft"
