from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from server.services.releases.sdk_package_models import SdkPackagePlatformRow
from server.services.releases.sdk_package_models import SdkPackageReleaseRow
from server.services.releases.sdk_package_platforms import (
    _catalog_for_platform,
    _language_for_platform,
    get_sdk_package_platform,
)
from server.services.releases.sdk_package_runner import process_sdk_package_release
from server.services.releases.sdk_package_runner import (
    _manifest_version,
    _runner_env,
    _steps,
    _verification_step,
)


def enable_platform(synced_client, platform_key: str):
    response = synced_client.patch(
        f"/api/releases/sdk-packages/platforms/{platform_key}",
        json={"enabled": True},
    )
    assert response.status_code == 200
    return response.json()


def test_initialize_sdk_release_train_creates_default_package_records(synced_client):
    response = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "1.0.0",
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
    assert {item["package_version"] for item in payload} == {"1.0.0"}
    ts_record = next(item for item in payload if item["sdk_language"] == "typescript")
    assert ts_record["package_name"] == "@synapse-network-ai/sdk"
    go_record = next(item for item in payload if item["sdk_language"] == "go")
    assert go_record["git_tag"] == "go/v1.0.0"
    assert go_record["registry"] == "go-module"
    java_record = next(item for item in payload if item["sdk_language"] == "java")
    assert java_record["package_name"] == "ai.synapse-network:synapse-network-sdk"


def test_sdk_package_platforms_can_be_configured(synced_client):
    response = synced_client.get("/api/releases/sdk-packages/platforms")
    assert response.status_code == 200
    payload = response.json()
    assert {item["platform_key"] for item in payload} == {
        "pypi",
        "npm",
        "go-module",
        "maven-central",
        "nuget",
    }
    assert not next(item for item in payload if item["platform_key"] == "pypi")[
        "enabled"
    ]

    updated = enable_platform(synced_client, "pypi")

    assert updated["enabled"] is True
    assert updated["configured"] is True
    assert updated["credential_env_var"] == "PYPI_API_TOKEN"


def test_sdk_package_platform_patch_updates_optional_fields(synced_client, monkeypatch):
    monkeypatch.setenv("CUSTOM_PYPI_TOKEN", "token")

    response = synced_client.patch(
        "/api/releases/sdk-packages/platforms/pypi",
        json={
            "enabled": True,
            "registry_url": "https://upload.pypi.example/legacy/",
            "package_name": "custom-synapse-sdk",
            "package_url_template": "https://example.test/{version}",
            "credential_env_var": "CUSTOM_PYPI_TOKEN",
            "notes": "custom registry smoke",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["registry_url"] == "https://upload.pypi.example/legacy/"
    assert payload["package_name"] == "custom-synapse-sdk"
    assert payload["package_url_template"] == "https://example.test/{version}"
    assert payload["credential_env_var"] == "CUSTOM_PYPI_TOKEN"
    assert payload["credential_present"] is True
    assert payload["notes"] == "custom registry smoke"


def test_sdk_package_platform_unknown_key_and_invalid_metadata(db_session):
    assert _language_for_platform("pypi") == "python"
    assert _catalog_for_platform("npm")["package_name"] == "@synapse-network-ai/sdk"
    with pytest.raises(ValueError):
        _language_for_platform("unknown-registry")

    row = SdkPackagePlatformRow(
        platform_key="pypi",
        sdk_language="python",
        registry="pypi",
        package_name="synapse-network-ai-sdk",
        registry_url="https://upload.pypi.org/legacy/",
        package_url_template="https://pypi.org/project/synapse-network-ai-sdk/{version}/",
        credential_env_var="PYPI_API_TOKEN",
        enabled=1,
        metadata_json="{not-json",
    )
    db_session.add(row)
    db_session.commit()

    platform = get_sdk_package_platform(db_session, "pypi")

    assert platform.metadata == {}


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
    language_payload = language_response.json()
    assert language_payload["total"] == 1
    assert language_payload["page"] == 1
    assert language_payload["page_size"] == 10
    assert [item["sdk_language"] for item in language_payload["items"]] == ["python"]

    status_response = synced_client.get("/api/releases/sdk-packages?status=planned")
    assert status_response.status_code == 200
    assert status_response.json()["total"] == 2

    registry_response = synced_client.get("/api/releases/sdk-packages?registry=npm")
    assert registry_response.status_code == 200
    assert [item["registry"] for item in registry_response.json()["items"]] == ["npm"]

    search_response = synced_client.get(
        "/api/releases/sdk-packages?search=synapse-network-ai-sdk"
    )
    assert search_response.status_code == 200
    assert [item["sdk_language"] for item in search_response.json()["items"]] == [
        "python"
    ]

    page_response = synced_client.get("/api/releases/sdk-packages?page=2&page_size=1")
    assert page_response.status_code == 200
    assert page_response.json()["total"] == 2
    assert page_response.json()["page"] == 2
    assert page_response.json()["total_pages"] == 2
    assert len(page_response.json()["items"]) == 1

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
    assert (
        synced_client.get("/api/releases/sdk-packages/999/history").status_code == 404
    )


def test_sdk_package_release_history_filters_pages_and_links(synced_client, db_session):
    records = []
    for index, version in enumerate(["0.1.0", "0.2.0", "0.3.0", "0.4.0"]):
        payload = synced_client.post(
            "/api/releases/sdk-packages/initialize-train",
            json={
                "release_train_version": version,
                "channel": "preview" if version != "0.3.0" else "next",
                "packages": ["python"],
            },
        ).json()[0]
        db_row = (
            db_session.query(SdkPackageReleaseRow)
            .filter(SdkPackageReleaseRow.id == payload["id"])
            .one()
        )
        db_row.updated_at = datetime(2026, 5, 1, tzinfo=timezone.utc) + timedelta(
            minutes=index
        )
        if version == "0.2.0":
            db_row.status = "published"
            db_row.package_url = (
                "https://pypi.org/project/synapse-network-ai-sdk/0.2.0/"
            )
            db_row.published_at = db_row.updated_at
            db_row.workflow_run_url = "https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/runs/202"
        if version == "0.4.0":
            db_row.status = "failed"
            db_row.failure_summary = "registry rejected version"
        records.append(payload)

    other_package = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.5.0",
            "channel": "preview",
            "packages": ["typescript"],
        },
    ).json()[0]
    db_session.commit()

    anchor_id = next(
        item["id"] for item in records if item["package_version"] == "0.2.0"
    )
    response = synced_client.get(f"/api/releases/sdk-packages/{anchor_id}/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert [item["package_version"] for item in payload["items"]] == [
        "0.4.0",
        "0.3.0",
        "0.2.0",
        "0.1.0",
    ]
    assert other_package["id"] not in [item["id"] for item in payload["items"]]
    published = next(
        item for item in payload["items"] if item["package_version"] == "0.2.0"
    )
    assert published["status"] == "published"
    assert (
        published["package_url"]
        == "https://pypi.org/project/synapse-network-ai-sdk/0.2.0/"
    )
    assert (
        published["repo_url"]
        == "https://github.com/SynapseNetworkAI/Synapse-Network-Sdk"
    )
    assert (
        published["git_tag_url"]
        == "https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/tree/sdk/v0.2.0"
    )
    assert published["workflow_run_url"].endswith("/actions/runs/202")

    page = synced_client.get(
        f"/api/releases/sdk-packages/{anchor_id}/history?limit=2&offset=1"
    ).json()
    assert page["total"] == 4
    assert page["limit"] == 2
    assert page["offset"] == 1
    assert [item["package_version"] for item in page["items"]] == ["0.3.0", "0.2.0"]

    search = synced_client.get(
        f"/api/releases/sdk-packages/{anchor_id}/history?q=rejected"
    ).json()
    assert [item["package_version"] for item in search["items"]] == ["0.4.0"]

    status = synced_client.get(
        f"/api/releases/sdk-packages/{anchor_id}/history?status=published"
    ).json()
    assert [item["package_version"] for item in status["items"]] == ["0.2.0"]

    channel = synced_client.get(
        f"/api/releases/sdk-packages/{anchor_id}/history?channel=next"
    ).json()
    assert [item["package_version"] for item in channel["items"]] == ["0.3.0"]


def test_sdk_package_dry_run_records_local_runner_reference(synced_client):
    enable_platform(synced_client, "pypi")
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "1.0.0",
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
    assert payload["status"] == "dry_running"
    assert payload["workflow_run_url"].startswith("local-sdk-run:dry-run:")
    assert payload["metadata"]["platform_key"] == "pypi"
    events = synced_client.get(f"/api/releases/sdk-packages/{row['id']}/events").json()
    assert events[-1]["action"] == "dry_run"


def test_sdk_package_publish_records_local_runner_reference(
    synced_client, db_session, monkeypatch
):
    enable_platform(synced_client, "go-module")
    monkeypatch.setenv("SDK_GITHUB_TOKEN", "test-token")
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
        f"/api/releases/sdk-packages/{row['id']}/publish",
        json={"actor": "operator", "confirm_phrase": "PUBLISH_SDK_0.1.0"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "publishing"
    assert payload["workflow_run_url"].startswith("local-sdk-run:publish:")
    events = synced_client.get(f"/api/releases/sdk-packages/{row['id']}/events").json()
    assert [event["action"] for event in events] == ["initialize_train", "publish"]


def test_sdk_package_publish_requires_successful_dry_run(synced_client):
    enable_platform(synced_client, "pypi")
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "1.0.0",
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
    db_row.package_url = "https://pypi.org/project/synapse-network-ai-sdk/0.1.0/"
    db_session.commit()

    response = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/publish",
        json={"package_version": "0.1.0", "actor": "operator"},
    )

    assert response.status_code == 400
    assert "already published" in response.json()["detail"]


def test_sdk_package_dry_run_requires_enabled_platform(synced_client):
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
        json={"actor": "operator"},
    )

    assert response.status_code == 400
    assert "platform_config_missing" in response.json()["detail"]


def test_sdk_package_publish_requires_confirm_phrase_and_credential(
    synced_client, db_session, monkeypatch
):
    monkeypatch.delenv("PYPI_API_TOKEN", raising=False)
    enable_platform(synced_client, "pypi")
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
    db_row.status = "ready_to_publish"
    db_session.commit()

    bad_confirm = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/publish",
        json={"actor": "operator", "confirm_phrase": "YES"},
    )
    assert bad_confirm.status_code == 400
    assert "confirm_phrase" in bad_confirm.json()["detail"]

    missing_credential = synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/publish",
        json={"actor": "operator", "confirm_phrase": "PUBLISH_SDK_0.1.0"},
    )
    assert missing_credential.status_code == 400
    assert "credential_missing" in missing_credential.json()["detail"]


def test_sdk_package_local_runner_marks_dry_run_ready(
    synced_client, db_session, monkeypatch
):
    package_version = _manifest_version("python") or "1.0.0"
    enable_platform(synced_client, "pypi")
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": package_version,
            "channel": "preview",
            "packages": ["python"],
        },
    ).json()[0]
    synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/dry-run",
        json={"actor": "operator"},
    )

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(
        "server.services.releases.sdk_package_runner.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    assert process_sdk_package_release(db_session, release_id=row["id"]) == 1

    db_session.expire_all()
    db_row = (
        db_session.query(SdkPackageReleaseRow)
        .filter(SdkPackageReleaseRow.id == row["id"])
        .one()
    )
    assert db_row.status == "ready_to_publish"
    assert "artifact_manifest" in db_row.metadata_json


def test_sdk_package_runner_templates_and_env(monkeypatch, tmp_path):
    dotnet_root = tmp_path / "dotnet-root"
    dotnet_root.mkdir()
    (dotnet_root / "dotnet").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("PYPI_API_TOKEN", "pypi-token")
    monkeypatch.setenv("NPM_TOKEN", "npm-token")
    monkeypatch.setenv("NUGET_API_KEY", "nuget-token")
    monkeypatch.setenv("SYNAPSE_E2E_DOTNET_DIR", str(dotnet_root))

    assert "python_twine_upload" in {
        step.key
        for step in _steps("python", publish=True, version="1.0.0", channel="latest")
    }
    assert {"npm_write_auth_config", "npm_publish"}.issubset(
        {
            step.key
            for step in _steps(
                "typescript", publish=True, version="1.0.0", channel="latest"
            )
        }
    )
    assert "go_tag_push" in {
        step.key
        for step in _steps("go", publish=True, version="1.0.0", channel="latest")
    }
    assert "maven_central_deploy" in {
        step.key
        for step in _steps("java", publish=True, version="1.0.0", channel="latest")
    }
    assert "dotnet_push" in {
        step.key
        for step in _steps("dotnet", publish=True, version="1.0.0", channel="latest")
    }

    assert "synapse-network-ai-sdk" in _verification_step("python", "1.0.0").command
    assert (
        "--registry https://registry.npmjs.org"
        in _verification_step("typescript", "1.0.0").command
    )
    assert "go list -m -json" in _verification_step("go", "1.0.0").command
    assert "mvn -q dependency:get" in _verification_step("java", "1.0.0").command
    assert "ai.synapse-network:synapse-network-sdk" in _verification_step(
        "java", "1.0.0"
    ).command
    assert "dotnet add" in _verification_step("dotnet", "1.0.0").command

    pypi_env = _runner_env("pypi", "PYPI_API_TOKEN")
    assert pypi_env["TWINE_USERNAME"] == "__token__"
    assert pypi_env["TWINE_PASSWORD"] == "pypi-token"
    npm_env = _runner_env("npm", "NPM_TOKEN")
    assert npm_env["NODE_AUTH_TOKEN"] == "npm-token"
    assert npm_env["NPM_CONFIG_REGISTRY"] == "https://registry.npmjs.org"
    monkeypatch.setenv("MAVEN_TOKEN", "central-user:central-password")
    maven_env = _runner_env("maven-central", "MAVEN_TOKEN")
    assert maven_env["MAVEN_CENTRAL_USERNAME"] == "central-user"
    assert maven_env["MAVEN_CENTRAL_PASSWORD"] == "central-password"
    dotnet_env = _runner_env("nuget", "NUGET_API_KEY")
    assert dotnet_env["DOTNET_ROOT"] == str(dotnet_root)
    assert str(dotnet_root) in dotnet_env["PATH"]


def test_sdk_package_runner_reads_manifest_versions():
    sdk_repo = Path("/Users/cliff/workspace/agent/Synapse-Network-Sdk")
    if not sdk_repo.exists():
        pytest.skip("SDK repo checkout is required for manifest version smoke.")

    package_version = _manifest_version("python")
    assert package_version
    assert _manifest_version("typescript") == package_version
    assert _manifest_version("java") == package_version
    assert _manifest_version("dotnet") == package_version
    assert _manifest_version("go") is None


def test_sdk_package_retry_and_sync_statuses(synced_client, db_session):
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "0.2.0",
            "channel": "preview",
            "packages": ["python", "typescript", "go"],
        },
    ).json()
    failed_without_url = row[0]
    failed_with_url = row[1]
    publishing = row[2]

    for item, status in [
        (failed_without_url, "failed"),
        (failed_with_url, "failed"),
        (publishing, "publishing"),
    ]:
        db_row = (
            db_session.query(SdkPackageReleaseRow)
            .filter(SdkPackageReleaseRow.id == item["id"])
            .one()
        )
        db_row.status = status
        db_row.failure_summary = "previous failure"
        if item["id"] == failed_with_url["id"]:
            db_row.package_url = "https://registry.example/sdk/0.2.0"
        db_session.commit()

    retry_dry_run = synced_client.post(
        f"/api/releases/sdk-packages/{failed_without_url['id']}/retry",
        json={"actor": "operator", "note": "retry dry run"},
    )
    assert retry_dry_run.status_code == 200
    assert retry_dry_run.json()["status"] == "dry_running"

    retry_publish_ready = synced_client.post(
        f"/api/releases/sdk-packages/{failed_with_url['id']}/retry",
        json={"actor": "operator", "note": "retry publish"},
    )
    assert retry_publish_ready.status_code == 200
    assert retry_publish_ready.json()["status"] == "ready_to_publish"

    sync_response = synced_client.post("/api/releases/sdk-packages/sync-statuses")
    assert sync_response.status_code == 200
    payload = sync_response.json()
    assert failed_without_url["id"] in payload["ready_ids"]
    assert publishing["id"] in payload["publishing_ids"]

    db_session.expire_all()
    events = synced_client.get(
        f"/api/releases/sdk-packages/{publishing['id']}/events"
    ).json()
    assert events[-1]["action"] == "sync_status"


def test_sdk_package_local_runner_fails_on_manifest_version_mismatch(
    synced_client, db_session, monkeypatch
):
    enable_platform(synced_client, "pypi")
    row = synced_client.post(
        "/api/releases/sdk-packages/initialize-train",
        json={
            "release_train_version": "9.9.9",
            "channel": "preview",
            "packages": ["python"],
        },
    ).json()[0]
    synced_client.post(
        f"/api/releases/sdk-packages/{row['id']}/dry-run",
        json={"actor": "operator"},
    )
    monkeypatch.setattr(
        "server.services.releases.sdk_package_runner._manifest_version",
        lambda _language: "1.0.0",
    )

    assert process_sdk_package_release(db_session, release_id=row["id"]) == 1

    db_session.expire_all()
    db_row = (
        db_session.query(SdkPackageReleaseRow)
        .filter(SdkPackageReleaseRow.id == row["id"])
        .one()
    )
    assert db_row.status == "failed"
    assert "manifest_version_mismatch" in db_row.failure_summary
