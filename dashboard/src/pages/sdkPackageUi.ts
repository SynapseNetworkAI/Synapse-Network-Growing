import { sdkPackagesApi } from '../sdkPackagesApi'

export const SDK_SOURCE_REPO_URL = 'https://github.com/SynapseNetworkAI/Synapse-Network-Sdk'

export const SDK_PUBLIC_PACKAGE_LINKS = [
  {
    language: 'python',
    registry: 'PyPI',
    packageName: 'synapse-network-ai-sdk',
    url: 'https://pypi.org/project/synapse-network-ai-sdk/1.0.0/',
    installCommand: 'pip install synapse-network-ai-sdk==1.0.0',
  },
  {
    language: 'typescript',
    registry: 'npm',
    packageName: '@synapse-network-ai/sdk',
    url: 'https://www.npmjs.com/package/@synapse-network-ai/sdk/v/1.0.0',
    installCommand: 'npm install @synapse-network-ai/sdk@1.0.0',
  },
  {
    language: 'go',
    registry: 'Go module',
    packageName: 'github.com/SynapseNetworkAI/Synapse-Network-Sdk/go',
    url: 'https://pkg.go.dev/github.com/SynapseNetworkAI/Synapse-Network-Sdk/go@v1.0.0',
    installCommand: 'go get github.com/SynapseNetworkAI/Synapse-Network-Sdk/go@v1.0.0',
  },
  {
    language: 'java',
    registry: 'Maven Central',
    packageName: 'ai.synapse-network:synapse-network-sdk',
    url: 'https://repo1.maven.org/maven2/ai/synapse-network/synapse-network-sdk/1.0.0/',
    installCommand: 'mvn dependency:get -Dartifact=ai.synapse-network:synapse-network-sdk:1.0.0',
  },
  {
    language: 'dotnet',
    registry: 'NuGet',
    packageName: 'SynapseNetwork.Sdk',
    url: 'https://www.nuget.org/packages/SynapseNetwork.Sdk/1.0.0',
    installCommand: 'dotnet add package SynapseNetwork.Sdk --version 1.0.0',
  },
]

export const SDK_STATUS_LABEL: Record<string, string> = {
  planned: '已计划',
  dry_running: 'Dry Run 中',
  building: 'Dry Run 中',
  ready_to_publish: '可发布',
  publishing: '发布中',
  published: '已发布',
  failed: '失败',
  cancelled: '已取消',
}

export const SDK_CHANNEL_OPTIONS = ['preview', 'next', 'beta', 'latest']

export function sdkReleaseTone(state: string | null | undefined) {
  if (state === 'published') return 'delivered'
  if (state === 'planned' || state === 'ready_to_publish') return 'ready'
  if (state === 'dry_running' || state === 'building' || state === 'publishing') return 'running'
  if (state === 'failed' || state === 'cancelled') return 'blocked'
  return 'muted'
}

export function sdkInstallCommand(language: string, packageName: string, version: string) {
  if (language === 'python') return `pip install ${packageName}==${version}`
  if (language === 'typescript') return `npm install ${packageName}@${version}`
  if (language === 'go') return `go get ${packageName}@v${version}`
  if (language === 'java') return `mvn dependency:get -Dartifact=${packageName}:${version}`
  if (language === 'dotnet') return `dotnet add package ${packageName} --version ${version}`
  return `${packageName}@${version}`
}

export function formatSdkTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

export function openExternalUrl(url: string | null | undefined) {
  if (!url) return
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (opened) opened.opener = null
}

export function isSemVer(value: string) {
  return /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(value.trim())
}

export async function syncSdkStatuses({
  load,
  setBusyAction,
  toast,
  busyKey,
}: {
  load: () => Promise<void>
  setBusyAction: (value: string | null) => void
  toast: { success: (message: string) => void; error: (message: string) => void }
  busyKey: string
}) {
  setBusyAction(busyKey)
  try {
    await sdkPackagesApi.syncSdkPackageReleaseStatuses()
    toast.success('SDK package 状态已同步')
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '同步失败')
  } finally {
    setBusyAction(null)
  }
}
