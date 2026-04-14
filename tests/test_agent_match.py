"""Tests for the GET /api/agents/match skill-matching endpoint."""
import json
import pytest
from unittest.mock import patch
from server.services.agents.loader import ensure_agents_loaded


def _mock_agents():
    """Return agent dicts matching the discover_agents() format."""
    return [
        {"id": "seo_strategist", "display_name": "SEO Strategist",
         "goal": "关键词优化", "group": "optimization", "persona_path": None,
         "skills": json.dumps(["seo-audit", "ai-seo", "site-architecture"])},
        {"id": "content_writer", "display_name": "Content Writer",
         "goal": "文案写作", "group": "content", "persona_path": None,
         "skills": json.dumps(["copywriting", "copy-editing", "cold-email"])},
        {"id": "dev_rel", "display_name": "DevRel Engineer",
         "goal": "技术布道", "group": "content", "persona_path": None,
         "skills": json.dumps(["content-strategy", "community-marketing"])},
        {"id": "cro_optimizer", "display_name": "CRO Optimizer",
         "goal": "转化优化", "group": "optimization", "persona_path": None,
         "skills": json.dumps(["page-cro", "ab-test-setup", "analytics-tracking"])},
        {"id": "growth_lead", "display_name": "Growth Lead",
         "goal": "增长策略", "group": "growth", "persona_path": None,
         "skills": json.dumps(["marketing-ideas", "launch-strategy"])},
    ]


@pytest.fixture
def seeded_client(client, db_session):
    """Seed mocked agents into DB and return the test client."""
    with patch("server.services.agents.loader.discover_agents", return_value=_mock_agents()):
        ensure_agents_loaded(db_session)
        db_session.commit()
    return client


def test_match_single_skill(seeded_client):
    resp = seeded_client.get("/api/agents/match?skills=seo-audit")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "seo_strategist"
    assert data[0]["confidence"] == 1.0
    assert data[0]["matched_skills"] == ["seo-audit"]


def test_match_multiple_skills(seeded_client):
    resp = seeded_client.get("/api/agents/match?skills=seo-audit,copywriting")
    assert resp.status_code == 200
    data = resp.json()
    # Both agents match one skill each → confidence 0.5 each
    assert len(data) == 2
    ids = {d["id"] for d in data}
    assert ids == {"seo_strategist", "content_writer"}
    for d in data:
        assert d["confidence"] == 0.5


def test_match_ranks_by_confidence(seeded_client):
    resp = seeded_client.get("/api/agents/match?skills=seo-audit,ai-seo,site-architecture")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "seo_strategist"
    assert data[0]["confidence"] == 1.0
    assert set(data[0]["matched_skills"]) == {"seo-audit", "ai-seo", "site-architecture"}


def test_match_no_results(seeded_client):
    resp = seeded_client.get("/api/agents/match?skills=blockchain,smart-contracts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_match_empty_skills(seeded_client):
    resp = seeded_client.get("/api/agents/match?skills=")
    assert resp.status_code == 200
    assert resp.json() == []


def test_match_case_insensitive(seeded_client):
    resp = seeded_client.get("/api/agents/match?skills=SEO-AUDIT")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "seo_strategist"


def test_match_limit_param(seeded_client):
    # All 5 agents have at least one skill; search for a broad set
    resp = seeded_client.get(
        "/api/agents/match?skills=seo-audit,copywriting,content-strategy,page-cro,marketing-ideas&limit=2"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) <= 2


def test_match_returns_full_skills_list(seeded_client):
    """matched_skills is the intersection, skills is the full agent skill list."""
    resp = seeded_client.get("/api/agents/match?skills=copywriting")
    assert resp.status_code == 200
    data = resp.json()
    agent = data[0]
    assert agent["matched_skills"] == ["copywriting"]
    assert set(agent["skills"]) == {"copywriting", "copy-editing", "cold-email"}


def test_match_includes_agent_metadata(seeded_client):
    resp = seeded_client.get("/api/agents/match?skills=launch-strategy")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    agent = data[0]
    assert agent["id"] == "growth_lead"
    assert agent["display_name"] == "Growth Lead"
    assert agent["goal"] == "增长策略"
    assert agent["group"] == "growth"
