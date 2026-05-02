from pathlib import Path

import pytest

from server.services.social.context_tags import (
    ContextTagContract,
    InsufficientSourceContextError,
    check_required_context_tags,
    resolve_required_context_tag,
)


def _contracts() -> tuple[ContextTagContract, ...]:
    return (
        ContextTagContract(
            ref_key="synapse-network-sdk:quickstart",
            project_key="synapse-network-sdk",
            root_dir_name="Synapse-Network-Sdk",
            label="quickstart",
            whitelist_globs=("docs/**/*.md", "python/examples/**/*.py"),
        ),
    )


def test_resolve_required_context_tag_reads_tagged_whitelist_snippet(tmp_path: Path):
    docs = tmp_path / "Synapse-Network-Sdk" / "docs" / "sdk"
    docs.mkdir(parents=True)
    (docs / "quickstart.md").write_text(
        "# Quickstart\n"
        "<!-- @synapse-context:quickstart -->\n"
        "Use SynapseClient.search() and SynapseClient.invoke().\n"
        "Do not leak /Users/cliff/workspace/agent/private.\n",
        encoding="utf-8",
    )

    snippet = resolve_required_context_tag(
        "synapse-network-sdk:quickstart",
        workspace_root=tmp_path,
        contracts=_contracts(),
    )

    assert snippet.project_key == "synapse-network-sdk"
    assert snippet.file_path == "docs/sdk/quickstart.md"
    assert "SynapseClient.invoke" in snippet.excerpt
    assert "/Users/" not in snippet.excerpt
    assert snippet.content_hash


def test_context_tag_missing_returns_insufficient_source_context(tmp_path: Path):
    (tmp_path / "Synapse-Network-Sdk" / "docs").mkdir(parents=True)
    with pytest.raises(
        InsufficientSourceContextError, match="insufficient_source_context"
    ):
        resolve_required_context_tag(
            "synapse-network-sdk:quickstart",
            workspace_root=tmp_path,
            contracts=_contracts(),
        )

    result = check_required_context_tags(
        ref_keys=["synapse-network-sdk:quickstart"],
        workspace_root=tmp_path,
        contracts=_contracts(),
    )
    assert result.checked == ["synapse-network-sdk:quickstart"]
    assert result.missing == ["synapse-network-sdk:quickstart"]
    assert result.snippets == []


def test_context_tag_resolver_ignores_non_whitelist_files(tmp_path: Path):
    root = tmp_path / "Synapse-Network-Sdk"
    (root / "tmp").mkdir(parents=True)
    (root / "tmp" / "notes.txt").write_text(
        "@synapse-context:quickstart\nwrong place", encoding="utf-8"
    )

    with pytest.raises(InsufficientSourceContextError):
        resolve_required_context_tag(
            "synapse-network-sdk:quickstart",
            workspace_root=tmp_path,
            contracts=_contracts(),
        )
