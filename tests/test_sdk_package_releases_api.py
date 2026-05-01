from server.services.releases import sdk_packages as sdk_release_service
from server.services.releases.sdk_package_helpers import package_url_for
from server.services.releases.sdk_package_models import SdkPackageReleaseRow


def test_initialize_sdk_release_train_creates_default_package_records(synced_client):
    response = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.1.0",
            "channel": "preview",
            "release_notes": "First SDK train.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["sdk_language"] for item in payload] == [
        "python",
        "typescript",
        "go",
        "java",
        "dotnet",
    ]
    assert {item["package_version"] for item in payload} == {"0.1.0"}
    go_record = next(item for item in payload if item["sdk_language"] == "go")
    assert go_record["git_tag"] == "go/v0.1.0"
    assert go_record["registry"] == "go-module"

    list_response = synced_client.get("/api/releases/sdk-packages")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 5

    train_response = synced_client.get("/api/releases/sdk-trains/0.1.0")
    assert train_response.status_code == 200
    train_payload = train_response.json()
    assert train_payload["package_count"] == 5
    assert train_payload["status_counts"] == {"planned": 5}
    assert [item["sdk_language"] for item in train_payload["packages"]] == [
        "python",
        "typescript",
        "go",
        "java",
        "dotnet",
    ]

    package_response = synced_client.get(
        f"/api/releases/sdk-packages/{payload[0]['id']}"
    )
    assert package_response.status_code == 200
    assert package_response.json()["package_name"] == "synapse-client"

    events_response = synced_client.get(
        f"/api/releases/sdk-packages/{payload[0]['id']}/events"
    )
    assert events_response.status_code == 200
    assert events_response.json()[0]["action"] == "initialize_train"


def test_sdk_release_train_initialization_is_idempotent(synced_client):
    body = {
        "release_train_version": "0.1.0",
        "channel": "preview",
        "packages": ["python", "go"],
    }
    first = synced_client.post(
        "/api/releases/sdk-packages/initialize-train", json=body
    ).json()
    second = synced_client.post(
        "/api/releases/sdk-packages/initialize-train", json=body
    ).json()

    assert [item["id"] for item in second] == [item["id"] for item in first]
    assert len(synced_client.get("/api/releases/sdk-packages").json()) == 2


def test_sdk_package_list_filters_and_missing_resources(synced_client):
    synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.1.0",
            "channel": "preview",
            "packages": ["python", "typescript"],
        },
    )

    language_response = synced_client.get(
        "/api/releases/sdk-packages?sdk_language=python"
    )
    assert language_response.status_code == 200
    assert [item["sdk_language"] for item in language_response.json()] == ["python"]

    status_response = synced_client.get("/api/releases/sdk-packages?status=planned")
    assert status_response.status_code == 200
    assert len(status_response.json()) == 2

    assert synced_client.get("/api/releases/sdk-trains/9.9.9").status_code == 404
    assert synced_client.get("/api/releases/sdk-trains/not-semver").status_code == 400
    assert synced_client.get("/api/releases/sdk-packages/999").status_code == 404
    assert synced_client.get("/api/releases/sdk-packages/999/events").status_code == 404
    assert (
        synced_client.post(
            "/api/releases/sdk-packages/999/dry-run", json={"actor": "operator"}
        ).status_code
        == 404
    )
    assert (
        synced_client.post(
            "/api/releases/sdk-packages/999/publish", json={"actor": "operator"}
        ).status_code
        == 404
    )
    assert (
        synced_client.post(
            "/api/releases/sdk-packages/999/retry", json={"actor": "operator"}
        ).status_code
        == 404
    )


def test_sdk_package_publish_dispatches_workflow_and_records_inputs(
    monkeypatch, synced_client, db_session
):
    calls = []

    def fake_dispatch(**kwargs):
        calls.append(kwargs)
        return "https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/workflows/publish-sdk.yml"

    monkeypatch.setattr(sdk_release_service, "_dispatch_github_workflow", fake_dispatch)
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.1.0",
            "channel": "preview",
            "packages": ["go"],
        },
    ).json()[0]
    db_row = (
        db_session.query(SdkPackageReleaseRow)
        .filter(SdkPackageReleaseRow.id == row["id"])
        .one()
    )
    db_row.status = "ready_to_publish"
    db_session.commit()

    response = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/publish", json={"actor": "operator"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "publishing"
    assert calls[0]["repo_full_name"] == "SynapseNetworkAI/Synapse-Network-Sdk"
    assert calls[0]["workflow_file"] == "publish-sdk.yml"
    assert calls[0]["inputs"] == {
        "release_train_version": "0.1.0",
        "package": "go",
        "package_version": "0.1.0",
        "channel": "preview",
        "dry_run": "false",
    }

    events = synced_client.get(f"/api/releases/sdk-packages/{row['id']}/events").json()
    assert [event["action"] for event in events] == ["initialize_train", "publish"]
    assert events[-1]["from_status"] == "ready_to_publish"
    assert events[-1]["to_status"] == "publishing"


def test_sdk_package_dry_run_records_dispatch_failure(monkeypatch, synced_client):
    def fail_dispatch(**kwargs):
        raise ValueError("workflow dispatch failed")

    monkeypatch.setattr(sdk_release_service, "_dispatch_github_workflow", fail_dispatch)
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.1.0",
            "channel": "preview",
            "packages": ["python"],
        },
    ).json()[0]

    response = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/dry-run",
        json={"actor": "operator", "note": "check package"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["failure_summary"] == "workflow dispatch failed"
    events = synced_client.get(f"/api/releases/sdk-packages/{row['id']}/events").json()
    assert events[-1]["action"] == "dry_run"
    assert events[-1]["error_summary"] == "workflow dispatch failed"


def test_sdk_package_release_allows_patch_version_before_publish(
    monkeypatch, synced_client
):
    monkeypatch.setattr(
        sdk_release_service,
        "_dispatch_github_workflow",
        lambda **kwargs: (
            "https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/workflows/publish-sdk.yml"
        ),
    )
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.1.0",
            "channel": "preview",
            "packages": ["python"],
        },
    ).json()[0]

    response = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/dry-run",
        json={"package_version": "0.1.1", "channel": "next"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["package_version"] == "0.1.1"
    assert payload["release_train_version"] == "0.1.0"
    assert payload["channel"] == "next"


def test_sdk_package_release_blocks_published_version_overwrite(
    synced_client, db_session
):
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.1.0",
            "channel": "preview",
            "packages": ["python"],
        },
    ).json()[0]
    db_row = (
        db_session.query(SdkPackageReleaseRow)
        .filter(SdkPackageReleaseRow.id == row["id"])
        .one()
    )
    db_row.status = "published"
    db_row.package_url = "https://pypi.org/project/synapse-client/0.1.0/"
    db_session.commit()

    response = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/publish",
        json={"package_version": "0.1.0", "actor": "operator"},
    )

    assert response.status_code == 400
    assert "already published" in response.json()["detail"]


def test_sdk_package_publish_requires_successful_dry_run(synced_client):
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.1.0",
            "channel": "preview",
            "packages": ["python"],
        },
    ).json()[0]

    response = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/publish",
        json={"actor": "operator"},
    )

    assert response.status_code == 400
    assert "dry-run" in response.json()["detail"]


def test_sdk_package_release_rejects_terminal_and_invalid_actions(
    synced_client, db_session
):
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.1.0",
            "channel": "preview",
            "packages": ["python"],
        },
    ).json()[0]
    db_row = (
        db_session.query(SdkPackageReleaseRow)
        .filter(SdkPackageReleaseRow.id == row["id"])
        .one()
    )

    db_row.status = "published"
    db_session.commit()
    dry_run = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/dry-run", json={"actor": "operator"}
    )
    assert dry_run.status_code == 400
    assert "Terminal" in dry_run.json()["detail"]

    db_row.status = "cancelled"
    db_session.commit()
    publish = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/publish", json={"actor": "operator"}
    )
    assert publish.status_code == 400
    assert "Cancelled" in publish.json()["detail"]

    db_row.status = "planned"
    db_session.commit()
    retry = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/retry", json={"actor": "operator"}
    )
    assert retry.status_code == 400
    assert "Only failed" in retry.json()["detail"]

    db_row.status = "failed"
    db_session.commit()
    bad_channel = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/retry",
        json={"actor": "operator", "channel": "nightly"},
    )
    assert bad_channel.status_code == 400
    assert "channel must be one of" in bad_channel.json()["detail"]


def test_sdk_package_retry_allows_patch_after_failure(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        sdk_release_service,
        "_dispatch_github_workflow",
        lambda **kwargs: (
            "https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/runs/123"
        ),
    )
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.1.0",
            "channel": "preview",
            "packages": ["typescript"],
        },
    ).json()[0]
    db_row = (
        db_session.query(SdkPackageReleaseRow)
        .filter(SdkPackageReleaseRow.id == row["id"])
        .one()
    )
    db_row.status = "failed"
    db_row.failure_summary = "previous publish failed"
    db_session.commit()

    response = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/retry",
        json={"actor": "operator", "package_version": "0.1.1", "channel": "latest"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "publishing"
    assert payload["package_version"] == "0.1.1"
    assert payload["channel"] == "latest"
    assert payload["failure_summary"] is None


def test_sdk_package_sync_statuses_handles_ready_published_failed_and_pending(
    monkeypatch, synced_client, db_session
):
    rows = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.1.0",
            "channel": "preview",
            "packages": ["python", "typescript", "go", "java", "dotnet"],
        },
    ).json()
    db_rows = (
        db_session.query(SdkPackageReleaseRow)
        .order_by(SdkPackageReleaseRow.id.asc())
        .all()
    )
    statuses = ["building", "publishing", "publishing", "building", "publishing"]
    urls = [
        "https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/runs/101",
        "https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/runs/102",
        "https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/runs/103",
        "https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/runs/104",
        None,
    ]
    for row, status, url in zip(db_rows, statuses, urls, strict=True):
        row.status = status
        row.workflow_run_url = url
    db_session.commit()

    def fake_run_view(repo_full_name, run_id):
        payloads = {
            "101": {"status": "completed", "conclusion": "success"},
            "102": {"status": "completed", "conclusion": "success"},
            "103": {"status": "completed", "conclusion": "failure"},
            "104": {"status": "in_progress", "conclusion": None},
        }
        return payloads[run_id], None

    monkeypatch.setattr(sdk_release_service, "_github_actions_run_view", fake_run_view)

    response = synced_client.post("/api/releases/sdk-packages/sync-statuses")

    assert response.status_code == 200
    payload = response.json()
    assert payload["processed_count"] == 5
    assert payload["ready_ids"] == [rows[0]["id"]]
    assert payload["published_ids"] == [rows[1]["id"]]
    assert payload["failed_ids"] == [rows[2]["id"]]
    assert set(payload["publishing_ids"]) == {rows[3]["id"], rows[4]["id"]}

    updated = synced_client.get(f"/api/releases/sdk-packages/{rows[1]['id']}").json()
    assert updated["status"] == "published"
    assert (
        updated["package_url"]
        == "https://www.npmjs.com/package/@synapse-network/sdk/v/0.1.0"
    )

    failed = synced_client.get(f"/api/releases/sdk-packages/{rows[2]['id']}").json()
    assert failed["status"] == "failed"
    assert failed["failure_summary"] == "GitHub Actions concluded with failure."


def test_sdk_package_sync_statuses_records_github_lookup_error(
    monkeypatch, synced_client, db_session
):
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.1.0",
            "channel": "preview",
            "packages": ["python"],
        },
    ).json()[0]
    db_row = (
        db_session.query(SdkPackageReleaseRow)
        .filter(SdkPackageReleaseRow.id == row["id"])
        .one()
    )
    db_row.status = "building"
    db_row.workflow_run_url = (
        "https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/runs/501"
    )
    db_session.commit()

    monkeypatch.setattr(
        sdk_release_service,
        "_github_actions_run_view",
        lambda repo_full_name, run_id: (None, "not found"),
    )

    response = synced_client.post("/api/releases/sdk-packages/sync-statuses")

    assert response.status_code == 200
    assert response.json()["error_ids"] == [row["id"]]


def test_sdk_package_urls_cover_all_registries(synced_client, db_session):
    synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={"release_train_version": "0.1.0", "channel": "preview"},
    )
    rows = (
        db_session.query(SdkPackageReleaseRow).order_by(SdkPackageReleaseRow.id).all()
    )

    urls = {row.sdk_language: package_url_for(row) for row in rows}

    assert urls == {
        "python": "https://pypi.org/project/synapse-client/0.1.0/",
        "typescript": "https://www.npmjs.com/package/@synapse-network/sdk/v/0.1.0",
        "go": "https://pkg.go.dev/github.com/SynapseNetworkAI/Synapse-Network-Sdk/go@v0.1.0",
        "java": "https://repo1.maven.org/maven2/ai/synapsenetwork/synapse-network-sdk/0.1.0/",
        "dotnet": "https://www.nuget.org/packages/SynapseNetwork.Sdk/0.1.0",
    }


def test_sdk_package_release_rejects_invalid_version_and_unknown_language(
    synced_client,
):
    bad_version = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={"release_train_version": "v0.1", "channel": "preview"},
    )
    assert bad_version.status_code == 400
    assert "SemVer" in bad_version.json()["detail"]

    bad_language = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={"release_train_version": "0.1.0", "packages": ["ruby"]},
    )
    assert bad_language.status_code == 400
    assert "Unsupported SDK package language" in bad_language.json()["detail"]
