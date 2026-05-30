from server.database_social_distribution import SocialDistributionAccountRow
from server.services.social import distribution_account_auth
from server.services.social.publishing import SocialPublishError, XOAuth2AccessToken


def test_distribution_account_auth_statuses_are_computed_not_published(
    synced_client, db_session, monkeypatch
):
    monkeypatch.setattr(
        distribution_account_auth.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: XOAuth2AccessToken("access-token", refreshed=True),
    )
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    x_account = next(row for row in accounts if row["platform"] == "x")
    hn_account = next(row for row in accounts if row["platform"] == "hacker_news")

    response = synced_client.get("/api/social/distribution/accounts/auth-status")

    assert response.status_code == 200
    payload = response.json()
    by_account = {row["account_id"]: row for row in payload["items"]}
    assert by_account[x_account["id"]]["publish_path"] == "official_api"
    assert by_account[x_account["id"]]["api_status"] == "ready"
    assert by_account[x_account["id"]]["oauth_status"] == "authorized"
    assert by_account[x_account["id"]]["api_supported"] is True
    assert by_account[x_account["id"]]["login_url"] == x_account["signup_url"]
    assert by_account[hn_account["id"]]["publish_path"] in {
        "manual_only",
        "browser_assisted",
    }
    assert by_account[hn_account["id"]]["can_publish_via_api"] is False
    assert all(row["private_web_adapter_enabled"] is False for row in payload["items"])
    assert db_session.query(SocialDistributionAccountRow).count() == len(accounts)


def test_distribution_account_auth_status_reports_rotated_x_token(
    synced_client, monkeypatch
):
    monkeypatch.setattr(
        distribution_account_auth.x_oauth_token_provider,
        "get_access_token",
        lambda *_args, **_kwargs: XOAuth2AccessToken(
            "access-token", refreshed=True, refresh_token_rotated=True
        ),
    )
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    x_account = next(row for row in accounts if row["platform"] == "x")

    response = synced_client.get(
        f"/api/social/distribution/accounts/auth-status?account_id={x_account['id']}"
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["api_status"] == "ready"
    assert item["oauth_status"] == "authorized"
    assert "rotated locally" in item["auth_message"]
    assert item["requires_authorization"] is False


def test_distribution_account_auth_status_reports_x_oauth_blockers(
    synced_client, monkeypatch
):
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    x_account = next(row for row in accounts if row["platform"] == "x")

    cases = [
        (
            SocialPublishError("x_refresh_failed", "Value passed for the token was invalid."),
            "invalid_refresh_token",
        ),
        (
            SocialPublishError("x_auth_failed", "Operator needs to authorize X."),
            "needs_authorization",
        ),
        (
            SocialPublishError(
                "x_secret_missing", "local secret x-official-oauth2-refresh-token not found"
            ),
            "missing_local_secret",
        ),
        (SocialPublishError("x_unknown", "Unexpected OAuth issue."), "error"),
    ]

    for exc, expected_status in cases:
        def raise_error(*_args, _exc=exc, **_kwargs):
            raise _exc

        monkeypatch.setattr(
            distribution_account_auth.x_oauth_token_provider,
            "get_access_token",
            raise_error,
        )

        response = synced_client.get(
            f"/api/social/distribution/accounts/auth-status?account_id={x_account['id']}"
        )

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["api_status"] == "blocked"
        assert item["oauth_status"] == expected_status
        assert expected_status in item["blockers"]
        assert item["requires_authorization"] is True


def test_distribution_account_auth_status_reports_missing_x_client_config(
    synced_client, monkeypatch
):
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    x_account = next(row for row in accounts if row["platform"] == "x")

    def raise_missing_client_config(*_args, **_kwargs):
        raise ValueError("X_OAUTH_CLIENT_ID is required in local environment configuration.")

    monkeypatch.setattr(
        distribution_account_auth.x_oauth_token_provider,
        "get_access_token",
        raise_missing_client_config,
    )

    response = synced_client.get(
        f"/api/social/distribution/accounts/auth-status?account_id={x_account['id']}"
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["api_status"] == "blocked"
    assert item["oauth_status"] == "missing_client_config"
    assert "missing_client_config" in item["blockers"]
    assert item["requires_authorization"] is True
    assert "X_OAUTH_CLIENT_ID is required" in item["auth_message"]


def test_distribution_account_auth_status_marks_api_supported_but_unconfigured(
    synced_client,
):
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    dev = next(row for row in accounts if row["platform"] == "devto")

    response = synced_client.get(
        f"/api/social/distribution/accounts/auth-status?account_id={dev['id']}"
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["api_supported"] is True
    assert item["api_status"] == "available_not_configured"
    assert item["can_publish_via_api"] is False
    assert "api_credential_not_configured" in item["blockers"]


def test_distribution_account_auth_status_blocks_v2ex_zero_balance(
    synced_client, db_session
):
    accounts = synced_client.get("/api/social/distribution/accounts").json()
    v2ex = next(row for row in accounts if row["platform"] == "v2ex")
    row = db_session.get(SocialDistributionAccountRow, v2ex["id"])
    row.status = "active"
    row.notes = "Operator observed 0.0 coins; cannot create topic."
    db_session.commit()

    response = synced_client.get(
        f"/api/social/distribution/accounts/auth-status?account_id={v2ex['id']}"
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["publish_path"] == "blocked"
    assert item["browser_status"] == "blocked"
    assert "v2ex_insufficient_balance" in item["blockers"]


def test_distribution_account_auth_status_covers_api_and_browser_edges(
    synced_client, db_session
):
    hn = SocialDistributionAccountRow(
        platform="hacker_news",
        channel_key="news.ycombinator.com/e2e",
        display_name="HN",
        signup_url="https://news.ycombinator.com/login",
        priority="P1",
        status="active",
        publish_mode="manual_only",
        api_capability="none",
    )
    product_hunt = SocialDistributionAccountRow(
        platform="product_hunt",
        channel_key="producthunt.com/e2e",
        display_name="Product Hunt",
        signup_url="https://www.producthunt.com/login",
        priority="P1",
        status="active",
        publish_mode="manual_only",
        api_capability="none",
    )
    hashnode = SocialDistributionAccountRow(
        platform="hashnode",
        channel_key="hashnode.com/e2e",
        display_name="Hashnode",
        signup_url="https://hashnode.com/login",
        priority="P1",
        status="active",
        publish_mode="api_human_gated",
        credential_ref="hashnode-token",
        api_capability="article",
    )
    reddit = SocialDistributionAccountRow(
        platform="reddit",
        channel_key="r/test",
        display_name="Reddit Test",
        signup_url="https://www.reddit.com/login",
        priority="P1",
        status="active",
        publish_mode="api_human_gated",
        credential_ref="reddit-token",
        api_capability="post",
    )
    paused_dev = SocialDistributionAccountRow(
        platform="devto",
        channel_key="dev.to/e2e",
        display_name="Paused DEV",
        signup_url="https://dev.to/enter",
        priority="P1",
        status="paused",
        publish_mode="manual_only",
        api_capability="article",
    )
    unknown = SocialDistributionAccountRow(
        platform="mastodon",
        channel_key="example.social",
        display_name="Mastodon",
        signup_url="https://example.social",
        priority="P1",
        status="planned",
        publish_mode="manual_only",
        api_capability="none",
    )
    db_session.add_all([hn, product_hunt, hashnode, reddit, paused_dev, unknown])
    db_session.commit()

    def status_for(account_id: int):
        response = synced_client.get(
            f"/api/social/distribution/accounts/auth-status?account_id={account_id}"
        )
        assert response.status_code == 200
        return response.json()["items"][0]

    assert status_for(hn.id)["publish_path"] == "browser_assisted"
    product_hunt_status = status_for(product_hunt.id)
    assert product_hunt_status["publish_path"] == "manual_only"
    assert (
        "product_hunt_launch_requires_manual_operator_flow"
        in product_hunt_status["blockers"]
    )
    hashnode_status = status_for(hashnode.id)
    assert hashnode_status["api_status"] == "manual_setup_required"
    assert hashnode_status["publish_path"] == "blocked"
    assert "hashnode_publication_or_blog_missing" in hashnode_status["blockers"]
    reddit_status = status_for(reddit.id)
    assert reddit_status["api_status"] == "ready"
    assert reddit_status["publish_path"] == "official_api"
    paused_status = status_for(paused_dev.id)
    assert paused_status["browser_status"] == "blocked"
    assert "account_paused" in paused_status["blockers"]
    unknown_status = status_for(unknown.id)
    assert unknown_status["api_status"] == "unsupported"
    assert unknown_status["publish_path"] == "manual_only"
