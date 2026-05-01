"""SDK package release catalog constants."""

SDK_REPO_FULL_NAME = "SynapseNetworkAI/Synapse-Network-Sdk"
SDK_PUBLISH_WORKFLOW_FILE = "publish-sdk.yml"
SDK_PUBLISH_REF = "main"
VALID_CHANNELS = {"preview", "latest", "beta", "next"}
TERMINAL_STATUSES = {"published", "failed", "cancelled"}
PACKAGE_CATALOG: dict[str, dict[str, str]] = {
    "python": {"package_name": "synapse-client", "registry": "pypi"},
    "typescript": {"package_name": "@synapse-network/sdk", "registry": "npm"},
    "go": {
        "package_name": "github.com/SynapseNetworkAI/Synapse-Network-Sdk/go",
        "registry": "go-module",
    },
    "java": {
        "package_name": "ai.synapsenetwork:synapse-network-sdk",
        "registry": "maven-central",
    },
    "dotnet": {"package_name": "SynapseNetwork.Sdk", "registry": "nuget"},
}
DEFAULT_PACKAGE_ORDER = ["python", "typescript", "go", "java", "dotnet"]
