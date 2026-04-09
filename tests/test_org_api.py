"""Tests for the /api/org endpoint."""
import pytest
from unittest.mock import patch


@pytest.fixture
def mock_org_tree():
    return {
        "root": {
            "id": "cto",
            "display_name": "CTO / Manager",
            "type": "cto",
            "goal": "Synapse CTO",
            "icon": "🧠",
            "children": [
                {
                    "id": "growth",
                    "display_name": "Growth Ops",
                    "type": "domain",
                    "goal": "Growth",
                    "icon": "📈",
                    "color": "green",
                    "project": "Synapse-Network-Growing",
                    "children": [
                        {
                            "id": "content",
                            "display_name": "内容与布道",
                            "type": "team",
                            "goal": "",
                            "icon": "📢",
                            "color": "blue",
                            "children": [],
                        }
                    ],
                }
            ],
        }
    }


def test_get_org_tree_returns_root(client, mock_org_tree):
    with patch("server.main.build_org_tree", return_value=mock_org_tree):
        resp = client.get("/api/org")
    assert resp.status_code == 200
    data = resp.json()
    assert "root" in data
    assert data["root"]["id"] == "cto"
    assert data["root"]["type"] == "cto"


def test_org_tree_has_domains(client, mock_org_tree):
    with patch("server.main.build_org_tree", return_value=mock_org_tree):
        resp = client.get("/api/org")
    children = resp.json()["root"]["children"]
    assert len(children) == 1
    assert children[0]["id"] == "growth"
    assert children[0]["type"] == "domain"


def test_org_tree_domain_has_teams(client, mock_org_tree):
    with patch("server.main.build_org_tree", return_value=mock_org_tree):
        resp = client.get("/api/org")
    growth = resp.json()["root"]["children"][0]
    assert len(growth["children"]) == 1
    assert growth["children"][0]["type"] == "team"
    assert growth["children"][0]["display_name"] == "内容与布道"
