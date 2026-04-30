from datetime import timedelta

from server.database import (
    DeploymentRecordRow,
    ProjectPolicyRow,
    ReleaseTaskRow,
    RequirementRow,
    SocialPostDraftRow,
    WorkflowRunRow,
    utcnow,
)
from server.services.social import daily_planner as social_daily_planner
from server.services.social import daily_planner_inventory as social_daily_inventory
from server.services.social import post_metrics as social_post_metrics
from server.services.social import product_change_signals
from server.services.social import publishing as social_publishing
from server.services.social.x_client import (
    XApiAuthError,
    XApiClient,
    XApiRateLimitError,
    XApiTransientError,
)


class FakeXAccessToken:
    access_token = "test-x-access-token"


class FakeXReadClient:
    def __init__(self, access_token: str):
        self.access_token = access_token

    def get_posts_by_ids(
        self, tweet_ids: list[str], *, include_owner_metrics: bool = False
    ):
        return [
            social_publishing.XPost(
                id=tweet_ids[0],
                text="Synapse Network launch update.",
                public_metrics={
                    "like_count": 11,
                    "reply_count": 3,
                    "retweet_count": 2,
                    "impression_count": 1200,
                },
                non_public_metrics={"impression_count": 1400, "url_link_clicks": 9}
                if include_owner_metrics
                else None,
                organic_metrics={"url_link_clicks": 7}
                if include_owner_metrics
                else None,
            )
        ]


def test_x_social_daily_planner_helper_edges(monkeypatch, db_session):
    account = social_publishing.ensure_default_social_account(db_session)
    bad_metadata = SocialPostDraftRow(
        platform="x",
        account_id=account.id,
        title="Bad metadata",
        body_text="metadata",
        raw_agent_output_json='{"planner_slot": "not-int"}',
    )
    assert social_daily_inventory._daily_planner_slot(bad_metadata) == 0
    bad_metadata.raw_agent_output_json = (
        '{"planner_run_key": "x_daily:1:2026-04-29:slot-7"}'
    )
    assert social_daily_inventory._daily_planner_slot(bad_metadata) == 7
    assert (
        social_daily_planner._campaign_goal_summary(None)[0]
        == "Build trust for Synapse Network official X"
    )
    assert "governed API access" in social_daily_planner._planner_variable_factor(
        "2026-04-29", 1, [], []
    )

    monkeypatch.setattr(
        social_publishing,
        "_finalize_generated_social_post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("agent unavailable")
        ),
    )
    row, _run_key, is_active = social_daily_planner._generate_daily_planner_slot(
        db_session, account_id=account.id, local_date="2026-04-29", daily_rows=[]
    )
    assert row.status == "generating"
    assert is_active is True


def test_x_social_daily_planner_records_failed_slot(monkeypatch, db_session):
    account = social_publishing.ensure_default_social_account(db_session)
    failed = SocialPostDraftRow(
        platform="x",
        account_id=account.id,
        source_type="daily_planner",
        title="Failed slot",
        body_text="",
        status="failed",
    )
    db_session.add(failed)
    db_session.flush()

    monkeypatch.setattr(
        social_daily_planner,
        "_generate_daily_planner_slot",
        lambda *_args, **_kwargs: (
            failed,
            f"x_daily:{account.id}:2026-04-29:slot-1",
            False,
        ),
    )
    created_ids, failed_ids, run_keys = (
        social_daily_planner._top_up_daily_planner_slots(
            db_session,
            account_id=account.id,
            local_date="2026-04-29",
            daily_rows=[],
            active_rows=[],
        )
    )
    assert created_ids == []
    assert failed_ids == [failed.id]
    assert run_keys == []


def test_x_social_daily_planner_reuses_inactive_slots(db_session):
    account = social_publishing.ensure_default_social_account(db_session)
    local_date = "2026-04-29"
    rows = [
        SocialPostDraftRow(
            platform="x",
            account_id=account.id,
            source_type="daily_planner",
            title="Published slot 1",
            body_text="Published.",
            status="published",
            raw_agent_output_json=social_publishing._json_dumps(
                {
                    "planner_local_date": local_date,
                    "planner_slot": 1,
                    "planner_run_key": f"x_daily:{account.id}:{local_date}:slot-1",
                }
            ),
        ),
        SocialPostDraftRow(
            platform="x",
            account_id=account.id,
            source_type="daily_planner",
            title="Failed slot 2",
            body_text="",
            status="failed",
            raw_agent_output_json=social_publishing._json_dumps(
                {
                    "planner_local_date": local_date,
                    "planner_slot": 2,
                    "planner_run_key": f"x_daily:{account.id}:{local_date}:slot-2",
                }
            ),
        ),
        SocialPostDraftRow(
            platform="x",
            account_id=account.id,
            source_type="daily_planner",
            title="Active slot 3",
            body_text="Needs review.",
            status="needs_review",
            raw_agent_output_json=social_publishing._json_dumps(
                {
                    "planner_local_date": local_date,
                    "planner_slot": 3,
                    "planner_run_key": f"x_daily:{account.id}:{local_date}:slot-3",
                }
            ),
        ),
    ]

    assert social_daily_inventory._next_daily_planner_slot(rows) == 1


def test_x_social_daily_planner_expires_stale_generating_drafts(
    monkeypatch, db_session
):
    account = social_publishing.ensure_default_social_account(db_session)
    local_date = social_publishing._operator_local_date()
    stale_time = utcnow() - timedelta(minutes=30)
    stale = SocialPostDraftRow(
        platform="x",
        account_id=account.id,
        source_type="daily_planner",
        title="Stale generating slot",
        body_text="",
        status="generating",
        generated_by="x_social_daily_content_planner",
        created_at=stale_time,
        updated_at=stale_time,
        raw_agent_output_json=social_publishing._json_dumps(
            {
                "planner_local_date": local_date,
                "planner_slot": 1,
                "planner_run_key": f"x_daily:{account.id}:{local_date}:slot-1",
            }
        ),
    )
    db_session.add(stale)
    db_session.commit()

    monkeypatch.setattr(
        social_publishing,
        "_generate_x_post_copy",
        lambda *args, **kwargs: social_publishing.GeneratedXPost(
            title="Fresh replacement",
            body_text="A replacement draft after stale generation timeout. #AIAgents",
            media_decision="text",
            model="test-model",
        ),
    )

    result = social_daily_planner.run_x_social_daily_content_planner(db_session)

    db_session.refresh(stale)
    assert stale.status == "failed"
    assert "daily_planner_generation_timeout" in stale.failure_summary
    assert result["expired_generating_post_ids"] == [stale.id]
    assert len(result["created_post_ids"]) == 3
    replacements = [
        db_session.get(SocialPostDraftRow, post_id)
        for post_id in result["created_post_ids"]
    ]
    assert all(row.status == "needs_review" for row in replacements if row)


def test_x_social_daily_planner_stops_when_inventory_is_full(monkeypatch, db_session):
    account = social_publishing.ensure_default_social_account(db_session)
    local_date = social_publishing._operator_local_date()
    db_session.add_all(
        [
            SocialPostDraftRow(
                platform="x",
                account_id=account.id,
                source_type="daily_planner",
                title=f"Active slot {slot}",
                body_text="Ready for review.",
                status="needs_review",
                generated_by="x_social_daily_content_planner",
                raw_agent_output_json=social_publishing._json_dumps(
                    {
                        "planner_local_date": local_date,
                        "planner_slot": slot,
                        "planner_run_key": f"x_daily:{account.id}:{local_date}:slot-{slot}",
                    }
                ),
            )
            for slot in (1, 2, 3)
        ]
    )
    db_session.commit()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError(
            "daily planner should not call Agent when 3 active drafts exist"
        )

    monkeypatch.setattr(
        social_daily_planner, "_generate_daily_planner_slot", fail_if_called
    )

    result = social_daily_planner.run_x_social_daily_content_planner(db_session)

    assert result["already_satisfied"] is True
    assert result["active_count"] == 3
    assert result["created_post_ids"] == []


def test_x_social_daily_planner_product_change_signals_are_public_safe(db_session):
    requirement = RequirementRow(
        title="SDK quickstart improved with /Users/cliff/workspace/agent/Synapse-Network-Sdk docs and token=abc",
        description_markdown="Shipped docs.",
        status="completed",
        project_key="synapse-network-sdk",
        project_display_name="Synapse Network SDK",
    )
    db_session.add(requirement)
    db_session.flush()
    db_session.add_all(
        [
            DeploymentRecordRow(
                project_key="synapse-network-provider",
                environment="staging",
                action="deploy",
                status="succeeded",
                notes="Provider Cloud Run deploy succeeded from ops/feature-public-branch with API_KEY=abc",
            ),
            ReleaseTaskRow(
                project_key="synapse-network",
                project_display_name="Synapse Network",
                service_key="gateway",
                branch_name="main",
                environment="staging",
                status="completed",
            ),
            WorkflowRunRow(
                requirement_id=requirement.id,
                goal_key="sdk_developer_quickstart",
                workflow_key="agent_self_repair",
                status="completed",
            ),
        ]
    )
    db_session.commit()

    signals = product_change_signals.recent_product_change_signals(db_session)
    joined = "\n".join(signals).lower()

    assert any("sdk quickstart improved" in signal.lower() for signal in signals)
    assert any(
        "provider cloud run deploy succeeded" in signal.lower() for signal in signals
    )
    assert "/users/" not in joined
    assert "api_key" not in joined
    assert "token=" not in joined
    assert "[path]" in joined
    assert "[internal branch]" in joined


def test_x_social_product_change_git_signal_edges(monkeypatch, tmp_path, db_session):
    monkeypatch.setattr(product_change_signals.shutil, "which", lambda _name: None)
    assert product_change_signals.recent_git_change_signals(db_session) == []

    db_session.add(
        ProjectPolicyRow(
            project_key="synapse-network-sdk",
            display_name="Synapse SDK",
            root_path=str(tmp_path),
            status="active",
        )
    )
    db_session.commit()

    monkeypatch.setattr(
        product_change_signals.shutil, "which", lambda _name: "/usr/bin/git"
    )
    assert product_change_signals.recent_git_change_signals(db_session) == []

    (tmp_path / ".git").mkdir()

    def raise_os_error(*_args, **_kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr(product_change_signals.subprocess, "run", raise_os_error)
    assert product_change_signals.recent_git_change_signals(db_session) == []

    class FailedGitResult:
        returncode = 1
        stdout = "ignored"

    monkeypatch.setattr(
        product_change_signals.subprocess,
        "run",
        lambda *_args, **_kwargs: FailedGitResult(),
    )
    assert product_change_signals.recent_git_change_signals(db_session) == []

    class SuccessfulGitResult:
        returncode = 0
        stdout = "Ship SDK quickstart\n\nFix ops/noisy-branch leak\n"

    monkeypatch.setattr(
        product_change_signals.subprocess,
        "run",
        lambda *_args, **_kwargs: SuccessfulGitResult(),
    )

    signals = product_change_signals.recent_git_change_signals(db_session, limit=1)

    assert signals == ["Synapse SDK: recent repo change - Ship SDK quickstart"]


def test_x_social_product_change_signal_dedupe_and_limit():
    signals = product_change_signals._dedupe_signals(
        ["", "Provider deploy shipped", "Provider deploy shipped", "SDK docs shipped"],
        limit=1,
    )

    assert signals == ["Provider deploy shipped"]


def test_x_social_post_metrics_empty_and_missing_branches(monkeypatch, db_session):
    summary = social_post_metrics.social_post_metrics_summary(db_session)
    assert summary.diagnostic
    assert (
        social_post_metrics._metric_value(None, {"value": "bad"}, keys=("value",)) == 0
    )

    empty_result = social_post_metrics.run_x_social_post_observer_sweep(db_session)
    assert empty_result["observed_count"] == 0
    assert "No published X posts" in empty_result["diagnostic"]

    account = social_publishing.ensure_default_social_account(db_session)
    post = SocialPostDraftRow(
        platform="x",
        account_id=account.id,
        source_type="manual_prompt",
        title="Missing metric source",
        body_text="Published post.",
        status="published",
        generated_by="operator",
        external_post_id="missing-x-post",
        published_at=utcnow(),
    )
    db_session.add(post)
    db_session.commit()

    class MissingXReadClient(FakeXReadClient):
        def get_posts_by_ids(
            self, tweet_ids: list[str], *, include_owner_metrics: bool = False
        ):
            return []

    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )
    monkeypatch.setattr(social_post_metrics, "XApiClient", MissingXReadClient)

    missing_result = social_post_metrics.run_x_social_post_observer_sweep(db_session)
    assert missing_result["created_metric_ids"] == []
    assert missing_result["missing_external_ids"] == ["missing-x-post"]


def test_x_social_post_metrics_observer_respects_daily_read_budget(
    monkeypatch, db_session
):
    account = social_publishing.ensure_default_social_account(db_session)
    post = SocialPostDraftRow(
        platform="x",
        account_id=account.id,
        source_type="manual_prompt",
        title="Published post",
        body_text="Published post with external id.",
        status="published",
        generated_by="operator",
        external_post_id="tweet-budget",
        published_at=utcnow(),
    )
    db_session.add(post)
    db_session.commit()

    class BudgetShouldNotCallXClient(FakeXReadClient):
        def __init__(self, access_token: str):
            raise AssertionError(
                "X metrics client must not run after read budget is exhausted"
            )

    monkeypatch.setattr(social_publishing.config, "X_READ_DAILY_REQUEST_BUDGET", 0)
    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("token refresh must not happen after budget exhaustion")
        ),
    )
    monkeypatch.setattr(social_post_metrics, "XApiClient", BudgetShouldNotCallXClient)

    result = social_post_metrics.run_x_social_post_observer_sweep(db_session)

    assert result["budget_exhausted"] is True
    assert result["created_metric_ids"] == []
    assert "budget exhausted" in result["diagnostic"].lower()


def test_x_social_post_metrics_auth_fallback_and_rate_limit(monkeypatch):
    class OwnerMetricsForbiddenClient(FakeXReadClient):
        def get_posts_by_ids(
            self, tweet_ids: list[str], *, include_owner_metrics: bool = False
        ):
            if include_owner_metrics:
                raise XApiAuthError("owner metrics forbidden")
            return super().get_posts_by_ids(
                tweet_ids, include_owner_metrics=include_owner_metrics
            )

    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )
    monkeypatch.setattr(social_post_metrics, "XApiClient", OwnerMetricsForbiddenClient)
    posts, diagnostic, private_available = social_post_metrics._lookup_x_metric_posts(
        ["tweet-1"]
    )
    assert posts
    assert private_available is False
    assert "Owner metrics unavailable" in diagnostic

    class RateLimitedClient(FakeXReadClient):
        def get_posts_by_ids(
            self, tweet_ids: list[str], *, include_owner_metrics: bool = False
        ):
            raise XApiRateLimitError("rate limited")

    monkeypatch.setattr(social_post_metrics, "XApiClient", RateLimitedClient)
    try:
        social_post_metrics._lookup_x_metric_posts(["tweet-1"])
    except XApiRateLimitError as exc:
        assert "rate limited" in str(exc)
    else:
        raise AssertionError("rate limit should bubble to observer")


def test_x_social_post_metrics_public_only_lookup_records_budget(
    monkeypatch, db_session
):
    monkeypatch.setattr(
        social_publishing.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: FakeXAccessToken(),
    )
    monkeypatch.setattr(social_post_metrics, "XApiClient", FakeXReadClient)

    posts, diagnostic, private_available = social_post_metrics._lookup_x_metric_posts(
        ["tweet-1"],
        db=db_session,
        local_date="2026-04-29",
        allow_owner_metrics=False,
    )

    assert posts
    assert private_available is False
    assert "Owner metrics skipped" in diagnostic
    assert (
        social_publishing._x_read_budget_usage(
            db_session,
            local_date="2026-04-29",
        )["request_count"]
        == 1
    )


def test_x_client_post_lookup_response_shapes(monkeypatch):
    client = XApiClient("token")
    captured: dict[str, object] = {}

    def fake_get_json(path, params):
        captured["path"] = path
        captured["params"] = params
        return {
            "data": [
                {
                    "id": "tweet-1",
                    "text": "Metric lookup post",
                    "public_metrics": {"like_count": 1},
                    "non_public_metrics": {"impression_count": 5},
                    "organic_metrics": {"url_link_clicks": 2},
                }
            ]
        }

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    assert client.get_posts_by_ids([]) == []
    posts = client.get_posts_by_ids(["tweet-1"], include_owner_metrics=True)
    assert posts[0].id == "tweet-1"
    assert posts[0].non_public_metrics["impression_count"] == 5
    assert "non_public_metrics" in captured["params"]["tweet.fields"]

    monkeypatch.setattr(client, "_get_json", lambda *_args, **_kwargs: {})
    assert client.get_posts_by_ids(["tweet-1"]) == []

    monkeypatch.setattr(client, "_get_json", lambda *_args, **_kwargs: {"data": {}})
    try:
        client.get_posts_by_ids(["tweet-1"])
    except XApiTransientError as exc:
        assert "not a list" in str(exc)
    else:
        raise AssertionError("non-list X response should fail closed")
