import json
import subprocess

from server.services.artifact_registry_cleanup import cleanup_artifact_registry_versions


def _completed(stdout: object, returncode: int = 0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=json.dumps(stdout), stderr=""
    )


def test_artifact_registry_cleanup_dry_run_keeps_recent_and_promoted_versions():
    calls: list[list[str]] = []

    def runner(cmd):
        calls.append(cmd)
        if cmd[:5] == ["gcloud", "artifacts", "docker", "images", "list"]:
            return _completed(
                [
                    {
                        "name": f"us-central1-docker.pkg.dev/demo/repo/user-front@sha256:{idx}",
                        "version": f"sha256:{idx}",
                        "tags": ["production-main"] if idx == 1 else [],
                        "updateTime": f"2026-05-{idx:02d}T00:00:00Z",
                    }
                    for idx in range(1, 7)
                ]
            )
        raise AssertionError(f"unexpected command: {cmd}")

    result = cleanup_artifact_registry_versions(
        projects=["demo"],
        region="us-central1",
        repository="repo",
        keep=2,
        older_than_days=0,
        dry_run=True,
        runner=runner,
    )

    assert result["candidate_count"] == 3
    assert result["deleted_count"] == 0
    assert result["kept_count"] == 3
    assert not any("delete" in part for call in calls for part in call)


def test_artifact_registry_cleanup_apply_deletes_only_candidates():
    deleted: list[str] = []

    def runner(cmd):
        if cmd[:5] == ["gcloud", "artifacts", "docker", "images", "list"]:
            return _completed(
                [
                    {
                        "name": f"us-central1-docker.pkg.dev/demo/repo/docs-front@sha256:{idx}",
                        "version": f"sha256:{idx}",
                        "tags": [],
                        "updateTime": f"2026-05-{idx:02d}T00:00:00Z",
                    }
                    for idx in range(1, 4)
                ]
            )
        if cmd[:5] == ["gcloud", "artifacts", "docker", "images", "delete"]:
            deleted.append(cmd[5])
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )
        raise AssertionError(f"unexpected command: {cmd}")

    result = cleanup_artifact_registry_versions(
        projects=["demo"],
        region="us-central1",
        repository="repo",
        keep=1,
        older_than_days=0,
        dry_run=False,
        runner=runner,
    )

    assert result["candidate_count"] == 2
    assert result["deleted_count"] == 2
    assert deleted == [
        "us-central1-docker.pkg.dev/demo/repo/docs-front@sha256:2",
        "us-central1-docker.pkg.dev/demo/repo/docs-front@sha256:1",
    ]


def test_artifact_registry_cleanup_apply_deletes_digest_when_name_omits_digest():
    deleted: list[str] = []

    def runner(cmd):
        if cmd[:5] == ["gcloud", "artifacts", "docker", "images", "list"]:
            return _completed(
                [
                    {
                        "name": "us-central1-docker.pkg.dev/demo/repo/provider",
                        "version": f"sha256:{idx}",
                        "tags": [],
                        "updateTime": f"2026-05-{idx:02d}T00:00:00Z",
                    }
                    for idx in range(1, 4)
                ]
            )
        if cmd[:5] == ["gcloud", "artifacts", "docker", "images", "delete"]:
            deleted.append(cmd[5])
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )
        raise AssertionError(f"unexpected command: {cmd}")

    result = cleanup_artifact_registry_versions(
        projects=["demo"],
        region="us-central1",
        repository="repo",
        keep=1,
        older_than_days=0,
        dry_run=False,
        runner=runner,
    )

    assert result["deleted_count"] == 2
    assert deleted == [
        "us-central1-docker.pkg.dev/demo/repo/provider@sha256:2",
        "us-central1-docker.pkg.dev/demo/repo/provider@sha256:1",
    ]


def test_artifact_registry_cleanup_keeps_recent_versions_per_image_package():
    def runner(cmd):
        if cmd[:5] == ["gcloud", "artifacts", "docker", "images", "list"]:
            rows = []
            for service in ("gateway", "user-front"):
                rows.extend(
                    {
                        "name": f"us-central1-docker.pkg.dev/demo/repo/{service}@sha256:{service}-{idx}",
                        "version": f"sha256:{service}-{idx}",
                        "tags": [],
                        "updateTime": f"2026-05-{idx:02d}T00:00:00Z",
                    }
                    for idx in range(1, 5)
                )
            return _completed(rows)
        raise AssertionError(f"unexpected command: {cmd}")

    result = cleanup_artifact_registry_versions(
        targets=[{"project": "demo", "region": "us-central1", "repository": "repo"}],
        keep=3,
        older_than_days=0,
        dry_run=True,
        runner=runner,
    )

    assert result["candidate_count"] == 2
    assert result["kept_count"] == 6
    assert {item["digest"] for item in result["projects"][0]["candidates"]} == {
        "sha256:gateway-1",
        "sha256:user-front-1",
    }
