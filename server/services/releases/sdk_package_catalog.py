"""SDK package release catalog constants."""

SDK_REPO_FULL_NAME = "SynapseNetworkAI/Synapse-Network-Sdk"
SDK_PUBLISH_WORKFLOW_FILE = "local_sdk_publish_runner"
SDK_PUBLISH_REF = "main"
VALID_CHANNELS = {"preview", "latest", "beta", "next"}
TERMINAL_STATUSES = {"published", "failed", "cancelled"}
PACKAGE_CATALOG: dict[str, dict[str, str]] = {
    "python": {
        "package_name": "synapse-network-ai-sdk",
        "registry": "pypi",
        "platform_key": "pypi",
        "credential_env_var": "PYPI_API_TOKEN",
        "registry_url": "https://pypi.org",
        "package_url_template": "https://pypi.org/project/{package_name}/{version}/",
    },
    "typescript": {
        "package_name": "@synapse-network-ai/sdk",
        "registry": "npm",
        "platform_key": "npm",
        "credential_env_var": "NPM_TOKEN",
        "registry_url": "https://registry.npmjs.org",
        "package_url_template": "https://www.npmjs.com/package/{package_name}/v/{version}",
    },
    "go": {
        "package_name": "github.com/SynapseNetworkAI/Synapse-Network-Sdk/go",
        "registry": "go-module",
        "platform_key": "go-module",
        "credential_env_var": "SDK_GITHUB_TOKEN",
        "registry_url": "https://pkg.go.dev",
        "package_url_template": "https://pkg.go.dev/{package_name}@v{version}",
    },
    "java": {
        "package_name": "ai.synapse-network:synapse-network-sdk",
        "registry": "maven-central",
        "platform_key": "maven-central",
        "credential_env_var": "MAVEN_TOKEN",
        "registry_url": "https://repo1.maven.org/maven2",
        "package_url_template": "https://repo1.maven.org/maven2/{group_path}/{artifact}/{version}/",
    },
    "dotnet": {
        "package_name": "SynapseNetwork.Sdk",
        "registry": "nuget",
        "platform_key": "nuget",
        "credential_env_var": "NUGET_API_KEY",
        "registry_url": "https://www.nuget.org",
        "package_url_template": "https://www.nuget.org/packages/{package_name}/{version}",
    },
}
DEFAULT_PACKAGE_ORDER = ["python", "typescript", "go", "java", "dotnet"]
SDK_PACKAGE_STATUSES = {
    "planned",
    "dry_running",
    "ready_to_publish",
    "publishing",
    "published",
    "failed",
    "cancelled",
}
