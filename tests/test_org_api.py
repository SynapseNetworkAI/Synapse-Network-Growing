"""Tests for the /api/org endpoint."""
import pytest
from unittest.mock import patch


@pytest.fixture
def mock_org_tree():
    return {
        "root": {
            "id": "roles",
            "display_name": "真实 Agent 角色",
            "type": "org",
            "goal": "Only roles discovered from roles/* are rendered here.",
            "children": [
                {
                    "id": "group-content",
                    "display_name": "content",
                    "type": "group",
                    "goal": "1 discovered roles",
                    "children": [
                        {
                            "id": "content_writer",
                            "display_name": "Content Writer",
                            "type": "agent",
                            "goal": "Writes launch copy",
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
    assert data["root"]["id"] == "roles"
    assert data["root"]["type"] == "org"


def test_org_tree_has_groups(client, mock_org_tree):
    with patch("server.main.build_org_tree", return_value=mock_org_tree):
        resp = client.get("/api/org")
    children = resp.json()["root"]["children"]
    assert len(children) == 1
    assert children[0]["id"] == "group-content"
    assert children[0]["type"] == "group"


def test_org_tree_group_has_agents(client, mock_org_tree):
    with patch("server.main.build_org_tree", return_value=mock_org_tree):
        resp = client.get("/api/org")
    group = resp.json()["root"]["children"][0]
    assert len(group["children"]) == 1
    assert group["children"][0]["type"] == "agent"
    assert group["children"][0]["display_name"] == "Content Writer"
