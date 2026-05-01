export const SDK_STATUS_LABEL: Record<string, string> = {
  planned: '已计划',
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
  if (state === 'building' || state === 'publishing') return 'running'
  if (state === 'failed' || state === 'cancelled') return 'blocked'
  return 'muted'
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
import { sdkPackagesApi } from '../sdkPackagesApi'
