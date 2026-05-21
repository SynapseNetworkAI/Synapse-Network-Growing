import json
import subprocess

from server.services.secret_manager_cleanup import cleanup_secret_manager_versions


def _completed(stdout: object, returncode: int = 0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=json.dumps(stdout), stderr=""
    )


def test_secret_manager_cleanup_dry_run_keeps_latest_three_without_destroy():
    calls: list[list[str]] = []

    def runner(cmd):
        calls.append(cmd)
        if cmd[:3] == ["gcloud", "secrets", "list"]:
            return _completed(
                [{"name": "projects/demo/secrets/x-official-oauth2-refresh-token"}]
            )
        if cmd[:4] == ["gcloud", "secrets", "versions", "list"]:
            return _completed(
                [
                    {
                        "name": f"projects/demo/secrets/x/versions/{version}",
                        "state": "ENABLED",
                        "createTime": f"2026-05-{version:02d}T00:00:00Z",
                    }
                    for version in range(1, 7)
                ]
                + [{"name": "projects/demo/secrets/x/versions/7", "state": "DESTROYED"}]
            )
        raise AssertionError(f"unexpected command: {cmd}")

    result = cleanup_secret_manager_versions(
        projects=["demo"], keep=3, dry_run=True, runner=runner
    )

    assert result["candidate_count"] == 3
    assert result["destroyed_count"] == 0
    assert [item["version"] for item in result["projects"][0]["candidates"]] == [
        "3",
        "2",
        "1",
    ]
    assert not any("destroy" in command for call in calls for command in call)


def test_secret_manager_cleanup_apply_destroys_only_old_active_versions():
    destroyed: list[str] = []

    def runner(cmd):
        if cmd[:3] == ["gcloud", "secrets", "list"]:
            return _completed([{"name": "projects/demo/secrets/app-secret"}])
        if cmd[:4] == ["gcloud", "secrets", "versions", "list"]:
            return _completed(
                [
                    {
                        "name": f"projects/demo/secrets/app-secret/versions/{version}",
                        "state": "DISABLED" if version == 1 else "ENABLED",
                    }
                    for version in range(1, 5)
                ]
            )
        if cmd[:4] == ["gcloud", "secrets", "versions", "destroy"]:
            destroyed.append(cmd[4])
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )
        raise AssertionError(f"unexpected command: {cmd}")

    result = cleanup_secret_manager_versions(
        projects=["demo"], keep=3, dry_run=False, runner=runner
    )

    assert destroyed == ["1"]
    assert result["destroyed_count"] == 1
    assert result["candidate_count"] == 1


def test_secret_manager_cleanup_apply_can_be_limited_to_secret_ids():
    listed_versions: list[str] = []
    destroyed: list[tuple[str, str]] = []

    def runner(cmd):
        if cmd[:3] == ["gcloud", "secrets", "list"]:
            return _completed(
                [
                    {"name": "projects/demo/secrets/schedule-e2e-cleanup-test"},
                    {"name": "projects/demo/secrets/prod-runtime-secret"},
                ]
            )
        if cmd[:4] == ["gcloud", "secrets", "versions", "list"]:
            listed_versions.append(cmd[4])
            return _completed(
                [
                    {
                        "name": f"projects/demo/secrets/{cmd[4]}/versions/{version}",
                        "state": "ENABLED",
                    }
                    for version in range(1, 6)
                ]
            )
        if cmd[:4] == ["gcloud", "secrets", "versions", "destroy"]:
            destroyed.append((cmd[6], cmd[4]))
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )
        raise AssertionError(f"unexpected command: {cmd}")

    result = cleanup_secret_manager_versions(
        projects=["demo"],
        secret_ids=["schedule-e2e-cleanup-test"],
        keep=3,
        dry_run=False,
        runner=runner,
    )

    assert listed_versions == ["schedule-e2e-cleanup-test"]
    assert destroyed == [
        ("schedule-e2e-cleanup-test", "2"),
        ("schedule-e2e-cleanup-test", "1"),
    ]
    assert result["secret_count"] == 1
    assert result["destroyed_count"] == 2
