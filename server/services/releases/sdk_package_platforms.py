"""Platform configuration for local SDK package publishing."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from server.services.releases.sdk_package_catalog import PACKAGE_CATALOG
from server.services.releases.sdk_package_helpers import clean, json_dump
from server.services.releases.sdk_package_models import SdkPackagePlatformRow
from server.services.releases.sdk_package_schemas import (
    SdkPackagePlatformOut,
    SdkPackagePlatformPatchRequest,
)


def _language_for_platform(platform_key: str) -> str:
    for language, catalog in PACKAGE_CATALOG.items():
        if clean(catalog.get("platform_key")) == platform_key:
            return language
    raise ValueError(f"Unsupported SDK package platform: {platform_key}")


def _catalog_for_platform(platform_key: str) -> dict[str, str]:
    return PACKAGE_CATALOG[_language_for_platform(platform_key)]


def _template_summary(platform_key: str) -> tuple[str, str, str, str]:
    if platform_key == "pypi":
        return (
            "python -m build python && python -m twine check python/dist/*",
            "python -m twine upload python/dist/*",
            "python -m pip index versions synapse-network-ai-sdk",
            "pip install synapse-network-ai-sdk=={version}",
        )
    if platform_key == "npm":
        return (
            "npm ci --prefix typescript && npm run build --prefix typescript && npm pack --prefix typescript --dry-run",
            "npm publish --prefix typescript --access public --tag {channel}",
            "npm view @synapse-network-ai/sdk@{version} version",
            "npm install @synapse-network-ai/sdk@{version}",
        )
    if platform_key == "go-module":
        return (
            "cd go && go test ./... && go list ./...",
            "git tag go/v{version} && git push origin go/v{version}",
            "go list -m -json github.com/SynapseNetworkAI/Synapse-Network-Sdk/go@v{version}",
            "go get github.com/SynapseNetworkAI/Synapse-Network-Sdk/go@v{version}",
        )
    if platform_key == "maven-central":
        return (
            "mvn -B -f java/pom.xml test package",
            "mvn -B -f java/pom.xml deploy",
            "mvn dependency:get -Dartifact=ai.synapsenetwork:synapse-network-sdk:{version}",
            "mvn dependency:get -Dartifact=ai.synapsenetwork:synapse-network-sdk:{version}",
        )
    return (
        "dotnet test dotnet/tests/SynapseNetwork.Sdk.Tests/SynapseNetwork.Sdk.Tests.csproj && dotnet pack dotnet/src/SynapseNetwork.Sdk/SynapseNetwork.Sdk.csproj -c Release",
        "dotnet nuget push dotnet/src/SynapseNetwork.Sdk/bin/Release/*.nupkg --source https://api.nuget.org/v3/index.json",
        "dotnet add package SynapseNetwork.Sdk --version {version}",
        "dotnet add package SynapseNetwork.Sdk --version {version}",
    )


def _row_or_default(
    db: Session, platform_key: str
) -> tuple[str, dict[str, str], SdkPackagePlatformRow | None]:
    language = _language_for_platform(platform_key)
    catalog = PACKAGE_CATALOG[language]
    row = (
        db.query(SdkPackagePlatformRow)
        .filter(SdkPackagePlatformRow.platform_key == platform_key)
        .first()
    )
    return language, catalog, row


def _platform_to_out(
    platform_key: str,
    language: str,
    catalog: dict[str, str],
    row: SdkPackagePlatformRow | None,
) -> SdkPackagePlatformOut:
    dry_run, publish, verify, install = _template_summary(platform_key)
    credential_env_var = clean(
        row.credential_env_var if row else catalog["credential_env_var"]
    )
    enabled = bool(row.enabled) if row else False
    return SdkPackagePlatformOut(
        platform_key=platform_key,
        sdk_language=language,
        registry=clean(row.registry if row else catalog["registry"]),
        package_name=clean(row.package_name if row else catalog["package_name"]),
        registry_url=clean(row.registry_url if row else catalog["registry_url"]),
        package_url_template=clean(
            row.package_url_template if row else catalog["package_url_template"]
        ),
        credential_env_var=credential_env_var,
        enabled=enabled,
        configured=bool(row and enabled),
        credential_present=bool(os.environ.get(credential_env_var)),
        dry_run_template=dry_run,
        publish_template=publish,
        verify_template=verify,
        install_command=install,
        notes=clean(row.notes if row else None) or None,
        metadata=_metadata(row),
        updated_at=_updated_at(row),
    )


def _metadata(row: SdkPackagePlatformRow | None) -> dict[str, Any]:
    if row is None or not row.metadata_json:
        return {}
    import json

    try:
        payload = json.loads(row.metadata_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _updated_at(row: SdkPackagePlatformRow | None) -> datetime | None:
    return row.updated_at if row is not None else None


def list_sdk_package_platforms(db: Session) -> list[SdkPackagePlatformOut]:
    result: list[SdkPackagePlatformOut] = []
    for catalog in PACKAGE_CATALOG.values():
        platform_key = clean(catalog["platform_key"])
        language, default_catalog, row = _row_or_default(db, platform_key)
        result.append(_platform_to_out(platform_key, language, default_catalog, row))
    return result


def get_sdk_package_platform(db: Session, platform_key: str) -> SdkPackagePlatformOut:
    key = clean(platform_key)
    language, catalog, row = _row_or_default(db, key)
    return _platform_to_out(key, language, catalog, row)


def update_sdk_package_platform(
    db: Session, platform_key: str, body: SdkPackagePlatformPatchRequest
) -> SdkPackagePlatformOut:
    key = clean(platform_key)
    language, catalog, row = _row_or_default(db, key)
    if row is None:
        row = SdkPackagePlatformRow(
            platform_key=key,
            sdk_language=language,
            registry=catalog["registry"],
            package_name=catalog["package_name"],
            registry_url=catalog["registry_url"],
            package_url_template=catalog["package_url_template"],
            credential_env_var=catalog["credential_env_var"],
            enabled=0,
            metadata_json=json_dump({"template_version": "sdk_publish_platform_v1"}),
        )
        db.add(row)
        db.flush()
    if body.enabled is not None:
        row.enabled = 1 if body.enabled else 0
    if clean(body.registry_url):
        row.registry_url = clean(body.registry_url)
    if clean(body.package_name):
        row.package_name = clean(body.package_name)
    if clean(body.package_url_template):
        row.package_url_template = clean(body.package_url_template)
    if clean(body.credential_env_var):
        row.credential_env_var = clean(body.credential_env_var)
    if body.notes is not None:
        row.notes = clean(body.notes) or None
    db.commit()
    db.refresh(row)
    return _platform_to_out(key, language, catalog, row)


def require_enabled_platform(db: Session, language: str) -> SdkPackagePlatformOut:
    catalog = PACKAGE_CATALOG[clean(language)]
    platform = get_sdk_package_platform(db, clean(catalog["platform_key"]))
    if not platform.enabled:
        raise ValueError(
            f"platform_config_missing: enable {platform.platform_key} before publishing this SDK package."
        )
    return platform
