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


def test_sdk_package_dry_run_records_local_runner_reference(synced_client):
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
    assert payload["status"] == "building"
    assert payload["workflow_run_url"].startswith("local-sdk-run:dry-run:")
    events = synced_client.get(f"/api/releases/sdk-packages/{row['id']}/events").json()
    assert events[-1]["action"] == "dry_run"


def test_sdk_package_publish_records_local_runner_reference(synced_client, db_session):
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
    assert payload["workflow_run_url"].startswith("local-sdk-run:publish:")
    events = synced_client.get(f"/api/releases/sdk-packages/{row['id']}/events").json()
    assert [event["action"] for event in events] == ["initialize_train", "publish"]


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
    assert "dry-run" in response.json()["detail"].lower()


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
