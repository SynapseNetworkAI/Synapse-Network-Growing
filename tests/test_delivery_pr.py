from __future__ import annotations

from unittest.mock import patch

from server.services.delivery.pull_request import sync_requirement_review_pr


def test_sync_requirement_review_pr_creates_draft_pr():
    calls: list[tuple[str, ...]] = []

    def fake_run_gh(*args: str, check: bool = True):
        calls.append(args)
        if args[:3] == ("pr", "view", "ops/req-17-incident-recovery"):
            if len(calls) == 1:
                class Missing:
                    returncode = 1
                    stdout = ""
                    stderr = "no pull requests found"

                return Missing()
            class View:
                returncode = 0
                stdout = (
                    '{"number":17,"url":"https://github.com/openai/synapse-network-growing/pull/17",'
                    '"isDraft":true,"state":"OPEN","headRefName":"ops/req-17-incident-recovery",'
                    '"baseRefName":"main","title":"ops(req-17): Incident recovery"}'
                )
                stderr = ""

            return View()
        class Ok:
            returncode = 0
            stdout = "https://github.com/openai/synapse-network-growing/pull/17\n"
            stderr = ""

        return Ok()

    with patch("server.services.delivery.pull_request._run_gh", side_effect=fake_run_gh):
        payload = sync_requirement_review_pr(
            requirement_id=17,
            requirement_title="Incident recovery",
            branch_name="ops/req-17-incident-recovery",
            base_branch="main",
            compare_url="https://github.com/openai/synapse-network-growing/compare/main...ops/req-17-incident-recovery",
            latest_commit_sha="abc123def456",
            latest_remote_sha="abc123def456",
            last_pushed_at="2026-04-13T00:00:00Z",
            review_surface_summary="Requirement #17 review-ready bundle.",
            promotion_checklist=[],
            vcs_payload={
                "repositories": [
                    {
                        "remote_url": "git@github.com:openai/synapse-network-growing.git",
                    }
                ]
            },
        )

    assert payload["status"] == "synced"
    assert payload["pr_status"] == "draft"
    assert payload["pr_number"] == 17
    assert payload["pr_url"] == "https://github.com/openai/synapse-network-growing/pull/17"
    assert any(args[:3] == ("pr", "create", "--repo") for args in calls)


def test_sync_requirement_review_pr_updates_existing_pr():
    calls: list[tuple[str, ...]] = []

    def fake_run_gh(*args: str, check: bool = True):
        calls.append(args)
        class View:
            returncode = 0
            stdout = (
                '{"number":18,"url":"https://github.com/openai/synapse-network-growing/pull/18",'
                '"isDraft":false,"state":"OPEN","headRefName":"ops/req-18-followup",'
                '"baseRefName":"main","title":"ops(req-18): Followup"}'
            )
            stderr = ""

        class Ok:
            returncode = 0
            stdout = ""
            stderr = ""

        if args[:3] == ("pr", "view", "ops/req-18-followup"):
            return View()
        return Ok()

    with patch("server.services.delivery.pull_request._run_gh", side_effect=fake_run_gh):
        payload = sync_requirement_review_pr(
            requirement_id=18,
            requirement_title="Followup",
            branch_name="ops/req-18-followup",
            base_branch="main",
            compare_url=None,
            latest_commit_sha="def456abc123",
            latest_remote_sha="def456abc123",
            last_pushed_at="2026-04-13T00:00:00Z",
            review_surface_summary="Requirement #18 review-ready bundle.",
            promotion_checklist=[],
            vcs_payload={
                "repositories": [
                    {
                        "remote_url": "git@github.com:openai/synapse-network-growing.git",
                    }
                ]
            },
        )

    assert payload["status"] == "synced"
    assert payload["pr_status"] == "ready_for_review"
    assert payload["pr_number"] == 18
    assert any(args[:3] == ("pr", "edit", "18") for args in calls)
