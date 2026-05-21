"""Local SDK package dry-run and publish runner."""

from __future__ import annotations

import os
import re
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from server.database import utcnow
from server.services.releases.sdk_package_catalog import PACKAGE_CATALOG
from server.services.releases.sdk_package_helpers import (
    clean,
    json_dump,
    package_url_for,
    record_event,
)
from server.services.releases.sdk_package_models import SdkPackageReleaseRow
from server.services.releases.sdk_package_platforms import get_sdk_package_platform

SDK_REPO = Path(
    os.environ.get(
        "SYNAPSE_SDK_REPO_PATH", "/Users/cliff/workspace/agent/Synapse-Network-Sdk"
    )
)


@dataclass(frozen=True)
class Step:
    key: str
    command: str
    needs_credential: bool = False


def _steps(language: str, *, publish: bool, version: str, channel: str) -> list[Step]:
    if language == "python":
        dry = [
            Step(
                "python_clean_artifacts",
                "rm -rf python/dist python/build python/*.egg-info",
            ),
            Step("python_build", "uvx --from build pyproject-build python"),
            Step("python_twine_check", "uvx --from twine twine check python/dist/*"),
        ]
        publish_steps = [
            Step(
                "python_twine_upload",
                "uvx --from twine twine upload python/dist/*",
                True,
            )
        ]
        return dry + (publish_steps if publish else [])
    if language == "typescript":
        dry = [
            Step("npm_clean_artifacts", "rm -f typescript/*.tgz"),
            Step("npm_ci", "npm ci --prefix typescript"),
            Step("npm_build", "npm run build --prefix typescript"),
            Step("npm_pack_dry_run", "cd typescript && npm pack --dry-run"),
        ]
        publish_steps = [
            Step(
                "npm_write_auth_config",
                "printf '//registry.npmjs.org/:_authToken=${NODE_AUTH_TOKEN}\\n"
                "registry=https://registry.npmjs.org\\n' > typescript/.npmrc",
                True,
            ),
            Step(
                "npm_publish",
                "cd typescript && npm publish --registry https://registry.npmjs.org "
                f"--access public --tag {channel}",
                True,
            ),
        ]
        return dry + (publish_steps if publish else [])
    if language == "go":
        dry = [
            Step("go_test", "cd go && go test ./..."),
            Step("go_list", "cd go && go list ./..."),
        ]
        publish_steps = [
            Step(
                "go_tag_push",
                f"git tag go/v{version} && git push origin go/v{version}",
                True,
            )
        ]
        return dry + (publish_steps if publish else [])
    if language == "java":
        dry = [Step("maven_package", "mvn -B -f java/pom.xml test package")]
        publish_steps = [Step("maven_deploy", "mvn -B -f java/pom.xml deploy", True)]
        return dry + (publish_steps if publish else [])
    dry = [
        Step(
            "dotnet_clean_artifacts",
            "rm -rf dotnet/src/SynapseNetwork.Sdk/bin/Release",
        ),
        Step(
            "dotnet_test",
            "dotnet test dotnet/tests/SynapseNetwork.Sdk.Tests/SynapseNetwork.Sdk.Tests.csproj",
        ),
        Step(
            "dotnet_pack",
            "dotnet pack dotnet/src/SynapseNetwork.Sdk/SynapseNetwork.Sdk.csproj -c Release",
        ),
    ]
    publish_steps = [
        Step(
            "dotnet_push",
            "dotnet nuget push dotnet/src/SynapseNetwork.Sdk/bin/Release/*.nupkg "
            '--source https://api.nuget.org/v3/index.json --api-key "$NUGET_API_KEY" --skip-duplicate',
            True,
        )
    ]
    return dry + (publish_steps if publish else [])


def _verification_step(language: str, version: str) -> Step:
    if language == "python":
        return Step(
            "verify_pypi",
            f"{sys.executable} -m pip index versions synapse-network-ai-sdk",
        )
    if language == "typescript":
        return Step(
            "verify_npm",
            "npm view --registry https://registry.npmjs.org "
            f"@synapse-network-ai/sdk@{version} version",
        )
    if language == "go":
        return Step(
            "verify_go_module",
            f"go list -m -json github.com/SynapseNetworkAI/Synapse-Network-Sdk/go@v{version}",
        )
    if language == "java":
        return Step(
            "verify_maven",
            f"mvn -q dependency:get -Dartifact=ai.synapsenetwork:synapse-network-sdk:{version}",
        )
    return Step(
        "verify_nuget",
        'tmpdir=$(mktemp -d) && dotnet new console -o "$tmpdir" >/dev/null '
        f'&& dotnet add "$tmpdir" package SynapseNetwork.Sdk --version {version} '
        "--source https://api.nuget.org/v3/index.json",
    )


def _runner_env(platform_key: str, credential_env_var: str) -> dict[str, str]:
    env = os.environ.copy()
    token = env.get(credential_env_var, "")
    if platform_key == "pypi" and token:
        env["TWINE_USERNAME"] = "__token__"
        env["TWINE_PASSWORD"] = token
    if platform_key == "npm" and token:
        env["NODE_AUTH_TOKEN"] = token
        env["NPM_CONFIG_REGISTRY"] = "https://registry.npmjs.org"
    if platform_key == "nuget":
        dotnet_root = Path(
            env.get(
                "SYNAPSE_E2E_DOTNET_DIR",
                str(Path.home() / ".synapse-network-sdk-e2e" / "dotnet"),
            )
        )
        if (dotnet_root / "dotnet").exists():
            env["DOTNET_ROOT"] = str(dotnet_root)
            env["PATH"] = f"{dotnet_root}{os.pathsep}{env.get('PATH', '')}"
    return env


def _manifest_version(language: str) -> str | None:
    if language == "python":
        import tomllib

        return tomllib.loads((SDK_REPO / "python/pyproject.toml").read_text())[
            "project"
        ]["version"]
    if language == "typescript":
        import json

        return json.loads((SDK_REPO / "typescript/package.json").read_text())["version"]
    if language == "java":
        text = (SDK_REPO / "java/pom.xml").read_text()
        match = re.search(r"<version>([^<]+)</version>", text)
        return match.group(1).strip() if match else None
    if language == "dotnet":
        text = (
            SDK_REPO / "dotnet/src/SynapseNetwork.Sdk/SynapseNetwork.Sdk.csproj"
        ).read_text()
        match = re.search(r"<Version>([^<]+)</Version>", text)
        return match.group(1).strip() if match else None
    return None


def _assert_manifest_version(row: SdkPackageReleaseRow) -> None:
    language = clean(row.sdk_language)
    version = _manifest_version(language)
    if version is None:
        return
    expected = clean(row.package_version)
    if version != expected:
        raise RuntimeError(
            f"manifest_version_mismatch: {language} manifest has {version}, expected {expected}"
        )


def _run_step(
    db: Session, row: SdkPackageReleaseRow, step: Step, env: dict[str, str]
) -> None:
    record_event(
        db,
        row,
        action="runner_step_started",
        from_status=clean(row.status),
        to_status=clean(row.status),
        metadata={"step": step.key, "command": step.command},
    )
    db.commit()
    result = subprocess.run(  # nosec B603
        ["/bin/bash", "-lc", step.command],
        cwd=str(SDK_REPO),
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=1800,
    )
    metadata = {
        "step": step.key,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    record_event(
        db,
        row,
        action="runner_step_finished",
        from_status=clean(row.status),
        to_status=clean(row.status),
        metadata=metadata,
    )
    db.commit()
    if result.returncode != 0:
        summary = (
            (result.stderr or result.stdout or f"{step.key} failed")
            .strip()
            .splitlines()
        )
        raise RuntimeError(summary[-1][:800] if summary else f"{step.key} failed")


def _set_failure(db: Session, row: SdkPackageReleaseRow, message: str) -> None:
    from_status = clean(row.status)
    row.status = "failed"
    row.failure_summary = message[:1000]
    row.updated_at = utcnow()
    record_event(
        db,
        row,
        action="runner_failed",
        from_status=from_status,
        to_status="failed",
        error_summary=row.failure_summary,
    )
    db.commit()


def process_sdk_package_release(db: Session, *, release_id: int | None = None) -> int:
    query = db.query(SdkPackageReleaseRow).filter(
        SdkPackageReleaseRow.status.in_(["dry_running", "publishing"])
    )
    if release_id is not None:
        query = query.filter(SdkPackageReleaseRow.id == release_id)
    rows = (
        query.order_by(SdkPackageReleaseRow.updated_at.asc())
        .limit(1 if release_id else 20)
        .all()
    )
    processed = 0
    for row in rows:
        processed += 1
        try:
            _process_one(db, row)
        except Exception as exc:  # noqa: BLE001 - runner must capture root cause into DB.
            _set_failure(db, row, str(exc))
    return processed


def _process_one(db: Session, row: SdkPackageReleaseRow) -> None:
    if not SDK_REPO.exists():
        raise RuntimeError(f"SDK repo path not found: {SDK_REPO}")
    language = clean(row.sdk_language)
    publish = clean(row.status) == "publishing"
    platform = get_sdk_package_platform(
        db, clean(PACKAGE_CATALOG[language]["platform_key"])
    )
    if not platform.enabled:
        raise RuntimeError(f"platform_config_missing: {platform.platform_key}")
    if publish and not platform.credential_present:
        raise RuntimeError(f"credential_missing: {platform.credential_env_var}")
    env = _runner_env(platform.platform_key, platform.credential_env_var)
    from_status = clean(row.status)
    _assert_manifest_version(row)
    for step in _steps(
        language,
        publish=publish,
        version=clean(row.package_version),
        channel=clean(row.channel),
    ):
        if (
            step.needs_credential
            and publish
            and not env.get(platform.credential_env_var)
        ):
            raise RuntimeError(f"credential_missing: {platform.credential_env_var}")
        _run_step(db, row, step, env)
    if publish:
        _run_step(
            db, row, _verification_step(language, clean(row.package_version)), env
        )
        row.status = "published"
        row.package_url = package_url_for(row)
        row.published_at = utcnow()
    else:
        row.status = "ready_to_publish"
    row.failure_summary = None
    row.metadata_json = _metadata_with_manifest(row)
    row.updated_at = utcnow()
    record_event(
        db,
        row,
        action="runner_succeeded",
        from_status=from_status,
        to_status=clean(row.status),
        metadata={"package_url": row.package_url},
    )
    db.commit()


def _metadata_with_manifest(row: SdkPackageReleaseRow) -> str:
    import json

    try:
        metadata = json.loads(row.metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["artifact_manifest"] = {
        "sdk_language": clean(row.sdk_language),
        "registry": clean(row.registry),
        "package_name": clean(row.package_name),
        "package_version": clean(row.package_version),
        "channel": clean(row.channel),
        "git_tag": clean(row.git_tag),
        "package_url": clean(row.package_url) or None,
    }
    metadata["verify_result"] = {
        "status": "passed" if clean(row.status) == "published" else "dry_run_passed"
    }
    return json_dump(metadata)
