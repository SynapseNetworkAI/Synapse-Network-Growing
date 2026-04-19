from unittest.mock import patch

from server.database import ProjectRow, RequirementCandidateRow
from server.services.forum_feedback import run_forum_feedback_sweep


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _task(task_id: str, *, category: str, title: str, body: str):
    return {
        "responseTaskId": task_id,
        "topicId": f"topic-{task_id}",
        "status": "awaiting_response",
        "topic": {
            "topicId": f"topic-{task_id}",
            "title": title,
            "body": body,
            "category": category,
            "authorDisplay": "builder",
        },
    }


def test_forum_feedback_question_pushes_suggestion_without_candidate(db_session):
    pushes = []

    def fake_get(*args, **kwargs):
        return FakeResponse({"success": True, "data": {"items": [
            _task("task-q", category="Questions", title="How do I connect the SDK?", body="How do I connect the SDK to MCP?")
        ]}})

    def fake_post(url, json, headers, timeout):
        pushes.append(json)
        return FakeResponse({"success": True, "data": {"responseTaskId": "task-q"}})

    with patch("server.config.FORUM_FEEDBACK_GATEWAY_ADMIN_TOKEN", "test-token"), patch(
        "httpx.get", side_effect=fake_get
    ), patch("httpx.post", side_effect=fake_post):
        result = run_forum_feedback_sweep(db_session)

    assert result["created_candidate_ids"] == []
    assert result["pushed_task_ids"] == ["task-q"]
    assert pushes[0]["classification"] == "question"
    assert "linkedRequirementCandidateId" in pushes[0]
    assert db_session.query(RequirementCandidateRow).count() == 0


def test_forum_feedback_bug_creates_candidate_and_pushes_link(db_session):
    project = ProjectRow(project_key="synapse-network", display_name="Synapse Network", root_path="/tmp/synapse-network")
    db_session.add(project)
    db_session.commit()
    pushes = []

    def fake_get(*args, **kwargs):
        return FakeResponse({"success": True, "data": {"items": [
            _task("task-bug", category="Bugs", title="Gateway timeout opening FAQ", body="The forum FAQ route fails with timeout and 500.")
        ]}})

    def fake_post(url, json, headers, timeout):
        pushes.append(json)
        return FakeResponse({"success": True, "data": {"responseTaskId": "task-bug"}})

    with patch("server.config.FORUM_FEEDBACK_GATEWAY_ADMIN_TOKEN", "test-token"), patch(
        "httpx.get", side_effect=fake_get
    ), patch("httpx.post", side_effect=fake_post):
        result = run_forum_feedback_sweep(db_session)

    assert len(result["created_candidate_ids"]) == 1
    candidate = db_session.get(RequirementCandidateRow, result["created_candidate_ids"][0])
    assert candidate is not None
    assert candidate.status == "pending"
    assert candidate.workflow_key == "gateway_reliability_repair"
    assert candidate.project_key == "synapse-network"
    assert pushes[0]["classification"] == "bug"
    assert pushes[0]["linkedRequirementCandidateId"] == str(candidate.id)


def test_forum_feedback_reuses_existing_bug_candidate(db_session):
    project = ProjectRow(project_key="synapse-network", display_name="Synapse Network", root_path="/tmp/synapse-network")
    db_session.add(project)
    db_session.commit()
    task = _task("task-repeat", category="Bugs", title="Gateway timeout opening FAQ", body="The forum FAQ route fails with timeout and 500.")

    def fake_get(*args, **kwargs):
        return FakeResponse({"success": True, "data": {"items": [task]}})

    with patch("server.config.FORUM_FEEDBACK_GATEWAY_ADMIN_TOKEN", "test-token"), patch(
        "httpx.get", side_effect=fake_get
    ), patch("httpx.post", return_value=FakeResponse({"success": True, "data": {}})):
        first = run_forum_feedback_sweep(db_session)
        second = run_forum_feedback_sweep(db_session)

    assert len(first["created_candidate_ids"]) == 1
    assert second["created_candidate_ids"] == []
    assert second["reused_candidate_ids"] == first["created_candidate_ids"]
    assert db_session.query(RequirementCandidateRow).count() == 1
