import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SdkPackagePlatform, SdkPackageRelease, sdkPackagesApi } from '../sdkPackagesApi'
import { EmptyPane, FieldLabel, OverlayModal, StateBadge, useToast } from '../components/workbench'
import { SDK_STATUS_LABEL, isSemVer, openExternalUrl, sdkReleaseTone } from './sdkPackageUi'

const STATUS_OPTIONS = ['', 'planned', 'dry_running', 'ready_to_publish', 'publishing', 'published', 'failed', 'cancelled']
const LANGUAGE_OPTIONS = ['', 'python', 'typescript', 'go', 'java', 'dotnet']
const PACKAGE_OPTIONS = [
  { key: 'python', label: 'Python · synapse-network-ai-sdk · PyPI' },
  { key: 'typescript', label: 'TypeScript · @synapse-network-ai/sdk · npm' },
  { key: 'go', label: 'Go · module /go · GitHub tag' },
  { key: 'java', label: 'Java · Maven Central / GitHub Packages' },
  { key: 'dotnet', label: '.NET · SynapseNetwork.Sdk · NuGet' },
]

function defaultTrainDraft() {
  return { release_train_version: '1.0.0', channel: 'latest', release_notes: '', packages: PACKAGE_OPTIONS.map((item) => item.key) }
}

function disableReason(draft: ReturnType<typeof defaultTrainDraft>, busy: boolean) {
  if (busy) return '正在初始化，请稍候'
  if (!draft.release_train_version.trim()) return '请输入 SemVer 版本，例如 0.1.0'
  if (!isSemVer(draft.release_train_version)) return '版本格式必须是 SemVer，例如 0.1.0'
  if (draft.packages.length === 0) return '至少选择一个 SDK package'
  return null
}

export default function SdkPackagesPanel({ search }: Readonly<{ search: string }>) {
  const navigate = useNavigate()
  const toast = useToast()
  const [packages, setPackages] = useState<SdkPackageRelease[]>([])
  const [loading, setLoading] = useState(true)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [draft, setDraft] = useState(defaultTrainDraft())
  const [statusFilter, setStatusFilter] = useState('')
  const [languageFilter, setLanguageFilter] = useState('')
  const [platforms, setPlatforms] = useState<SdkPackagePlatform[]>([])
  const [platformModalOpen, setPlatformModalOpen] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [nextPackages, nextPlatforms] = await Promise.all([
        sdkPackagesApi.getSdkPackageReleases(),
        sdkPackagesApi.getSdkPackagePlatforms(),
      ])
      setPackages(nextPackages)
      setPlatforms(nextPlatforms)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch((error) => toast.error(error instanceof Error ? error.message : '加载 SDK packages 失败'))
  }, [])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return packages.filter((item) => {
      if (statusFilter && item.status !== statusFilter) return false
      if (languageFilter && item.sdk_language !== languageFilter) return false
      if (!needle) return true
      return [
        item.release_train_version,
        item.sdk_language,
        item.package_name,
        item.registry,
        item.channel,
        item.package_version,
        item.git_tag || '',
        item.status,
        item.failure_summary || '',
      ].join('\n').toLowerCase().includes(needle)
    })
  }, [packages, languageFilter, statusFilter, search])

  const trains = useMemo(() => {
    const grouped = new Map<string, SdkPackageRelease[]>()
    filtered.forEach((item) => grouped.set(item.release_train_version, [...(grouped.get(item.release_train_version) || []), item]))
    return Array.from(grouped.entries()).map(([version, items]) => ({
      version,
      items,
      statusCounts: items.reduce<Record<string, number>>((acc, item) => ({ ...acc, [item.status]: (acc[item.status] || 0) + 1 }), {}),
    }))
  }, [filtered])

  const initializeTrain = async () => {
    const reason = disableReason(draft, busyAction === 'initialize')
    if (reason) {
      toast.error(reason)
      return
    }
    const nextVersion = draft.release_train_version.trim()
    setBusyAction('initialize')
    try {
      await sdkPackagesApi.initializeSdkReleaseTrain({
        release_train_version: nextVersion,
        channel: draft.channel,
        release_notes: draft.release_notes || null,
        packages: draft.packages,
      })
      toast.success('SDK release train 已初始化')
      setModalOpen(false)
      setDraft(defaultTrainDraft())
      await load()
      navigate(`/releases/sdk-trains/${encodeURIComponent(nextVersion)}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '初始化 SDK release train 失败')
    } finally {
      setBusyAction(null)
    }
  }

  const runAction = async (item: SdkPackageRelease, action: 'dry-run' | 'publish' | 'retry') => {
    const key = `sdk-package-${item.id}-${action}`
    setBusyAction(key)
    try {
      if (action === 'dry-run') await sdkPackagesApi.dryRunSdkPackageRelease(item.id, { actor: 'operator' })
      if (action === 'publish') await sdkPackagesApi.publishSdkPackageRelease(item.id, { actor: 'operator' })
      if (action === 'retry') await sdkPackagesApi.retrySdkPackageRelease(item.id, { actor: 'operator' })
      toast.success(`SDK package ${action} 已触发`)
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'SDK package 操作失败')
    } finally {
      setBusyAction(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={languageFilter} onChange={(event) => setLanguageFilter(event.target.value)}>
            {LANGUAGE_OPTIONS.map((language) => <option key={language || 'all'} value={language}>{language || '全部语言'}</option>)}
          </select>
          <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            {STATUS_OPTIONS.map((status) => <option key={status || 'all'} value={status}>{status ? SDK_STATUS_LABEL[status] : '全部状态'}</option>)}
          </select>
        </div>
        <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white" onClick={() => setModalOpen(true)}>
          Initialize Release Train
        </button>
        <button type="button" className="rounded-xl border border-[color:var(--ops-state-running-border)] px-4 py-2.5 text-sm font-semibold text-[color:var(--ops-state-running-text)]" onClick={() => setPlatformModalOpen(true)}>
          Platform Settings
        </button>
      </div>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
        <div className="border-b border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4">
          <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">SDK Packages</div>
          <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
            SDK 发布按 registry/channel/version 管理，不使用 staging / production deployment 环境。已发布同版本不可覆盖，修复走更高 patch version。
          </div>
        </div>
        <div className="space-y-5 p-5">
          {trains.map((train) => (
            <section key={train.version} className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Release Train</div>
                  <button type="button" className="mt-1 font-mono text-xl font-semibold text-[color:var(--ops-text-title)] hover:underline" onClick={() => navigate(`/releases/sdk-trains/${encodeURIComponent(train.version)}`)}>
                    {train.version}
                  </button>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {Object.entries(train.statusCounts).map(([status, count]) => (
                      <StateBadge key={status} tone={sdkReleaseTone(status)}>{SDK_STATUS_LABEL[status] || status}: {count}</StateBadge>
                    ))}
                  </div>
                </div>
                <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/releases/sdk-trains/${encodeURIComponent(train.version)}`)}>
                  打开 Train Cockpit
                </button>
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
                {train.items.map((item) => {
                  const busyPrefix = `sdk-package-${item.id}-`
                  return (
                    <article key={item.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
                      <div className="flex items-start justify-between gap-3">
                        <button type="button" className="text-left" onClick={() => navigate(`/releases/sdk-packages/${item.id}`)}>
                          <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{item.package_name}</div>
                          <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{item.sdk_language} · {item.registry}</div>
                        </button>
                        <StateBadge tone={sdkReleaseTone(item.status)}>{SDK_STATUS_LABEL[item.status] || item.status}</StateBadge>
                      </div>
                      <div className="mt-4 grid gap-2 text-xs text-[color:var(--ops-text-muted)]">
                        <div>Channel: <span className="font-mono">{item.channel}</span></div>
                        <div>Package version: <span className="font-mono">{item.package_version}</span></div>
                        <div>Git tag: <span className="font-mono">{item.git_tag || '-'}</span></div>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/releases/sdk-packages/${item.id}`)}>
                          发布页
                        </button>
                        {item.workflow_run_url ? <span className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm">Local Run</span> : null}
                        {item.package_url ? <button type="button" className="rounded-lg border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)]" onClick={() => openExternalUrl(item.package_url)}>Package</button> : null}
                        {item.status !== 'published' && item.status !== 'cancelled' ? <button type="button" className="rounded-lg border border-[color:var(--ops-state-ready-border)] px-3 py-2 text-sm text-[color:var(--ops-state-ready-text)] disabled:opacity-50" disabled={Boolean(busyAction)} onClick={() => runAction(item, 'dry-run')}>{busyAction === `${busyPrefix}dry-run` ? '验证中…' : 'Dry Run'}</button> : null}
                        {item.status === 'failed' ? <button type="button" className="rounded-lg border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50" disabled={Boolean(busyAction)} onClick={() => runAction(item, 'retry')}>{busyAction === `${busyPrefix}retry` ? '重试中…' : 'Retry'}</button> : null}
                        {item.status === 'ready_to_publish' ? <button type="button" className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white" onClick={() => navigate(`/releases/sdk-packages/${item.id}`)}>Human Gate Publish</button> : null}
                      </div>
                      {item.failure_summary ? <div className="mt-3 line-clamp-2 text-xs text-[color:var(--ops-state-blocked-text)]">{item.failure_summary}</div> : null}
                    </article>
                  )
                })}
              </div>
            </section>
          ))}
        </div>
        {!loading && packages.length === 0 ? <div className="p-6"><EmptyPane>暂无 SDK package release。点击 “Initialize Release Train” 批量创建五种语言的 planned records。</EmptyPane></div> : null}
      </section>

      <InitializeTrainModal open={modalOpen} draft={draft} busy={busyAction === 'initialize'} onClose={() => setModalOpen(false)} onDraftChange={setDraft} onSubmit={initializeTrain} />
      <PlatformSettingsModal
        open={platformModalOpen}
        platforms={platforms}
        busy={busyAction}
        onClose={() => setPlatformModalOpen(false)}
        onUpdate={async (platformKey, enabled) => {
          setBusyAction(`platform-${platformKey}`)
          try {
            await sdkPackagesApi.updateSdkPackagePlatform(platformKey, { enabled })
            toast.success('SDK platform 配置已更新')
            await load()
          } catch (error) {
            toast.error(error instanceof Error ? error.message : '更新 SDK platform 失败')
          } finally {
            setBusyAction(null)
          }
        }}
      />
    </div>
  )
}

function PlatformSettingsModal({
  open,
  platforms,
  busy,
  onClose,
  onUpdate,
}: Readonly<{
  open: boolean
  platforms: SdkPackagePlatform[]
  busy: string | null
  onClose: () => void
  onUpdate: (platformKey: string, enabled: boolean) => Promise<void>
}>) {
  return (
    <OverlayModal open={open} eyebrow="SDK Platform Settings" title="SDK 发布平台配置" description="这里只启用 allowlisted registry template；凭据来自本地 runner env，不进入数据库。" onClose={onClose}>
      <div className="space-y-3">
        {platforms.map((platform) => (
          <article key={platform.platform_key} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-[color:var(--ops-text-title)]">{platform.package_name}</div>
                <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{platform.sdk_language} · {platform.platform_key} · {platform.registry_url}</div>
              </div>
              <StateBadge tone={platform.enabled ? (platform.credential_present ? 'delivered' : 'ready') : 'blocked'}>
                {platform.enabled ? (platform.credential_present ? 'enabled + credential' : 'enabled · missing credential') : 'disabled'}
              </StateBadge>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-[color:var(--ops-text-muted)]">
              <div>Credential env: <span className="font-mono">{platform.credential_env_var}</span></div>
              <div>Dry run: <span className="font-mono">{platform.dry_run_template}</span></div>
              <div>Publish: <span className="font-mono">{platform.publish_template}</span></div>
              <div>Verify: <span className="font-mono">{platform.verify_template}</span></div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-60"
                disabled={busy === `platform-${platform.platform_key}`}
                onClick={() => onUpdate(platform.platform_key, !platform.enabled)}
              >
                {platform.enabled ? 'Disable' : 'Enable'}
              </button>
            </div>
          </article>
        ))}
      </div>
    </OverlayModal>
  )
}

function InitializeTrainModal({
  open,
  draft,
  busy,
  onClose,
  onDraftChange,
  onSubmit,
}: Readonly<{
  open: boolean
  draft: ReturnType<typeof defaultTrainDraft>
  busy: boolean
  onClose: () => void
  onDraftChange: (draft: ReturnType<typeof defaultTrainDraft>) => void
  onSubmit: () => void
}>) {
  const reason = disableReason(draft, busy)
  return (
    <OverlayModal open={open} eyebrow="SDK Release Train" title="Initialize SDK Release Train" description="SDK 是包发布物：这里创建 registry/channel 记录，不创建 staging/prod deployment。" onClose={onClose}>
      <div className="space-y-5">
        {reason ? <div className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-blocked-text)]">{reason}</div> : null}
        <label className="block space-y-2">
          <FieldLabel>Release train version</FieldLabel>
          <input className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm" placeholder="0.1.0" value={draft.release_train_version} onChange={(event) => onDraftChange({ ...draft, release_train_version: event.target.value })} />
        </label>
        <label className="block space-y-2">
          <FieldLabel>Registry channel</FieldLabel>
          <select className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm" value={draft.channel} onChange={(event) => onDraftChange({ ...draft, channel: event.target.value })}>
            <option value="preview">preview</option>
            <option value="next">next</option>
            <option value="beta">beta</option>
            <option value="latest">latest</option>
          </select>
        </label>
        <section className="space-y-3">
          <FieldLabel>Packages</FieldLabel>
          {PACKAGE_OPTIONS.map((item) => (
            <label key={item.key} className="flex items-center gap-3 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-sm">
              <input type="checkbox" checked={draft.packages.includes(item.key)} onChange={(event) => onDraftChange({ ...draft, packages: event.target.checked ? [...draft.packages, item.key] : draft.packages.filter((value) => value !== item.key) })} />
              <span>{item.label}</span>
            </label>
          ))}
        </section>
        <label className="block space-y-2">
          <FieldLabel>Release notes</FieldLabel>
          <textarea className="min-h-32 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm" placeholder="本轮 SDK release train 的开发者可见变化。" value={draft.release_notes} onChange={(event) => onDraftChange({ ...draft, release_notes: event.target.value })} />
        </label>
        <div className="rounded-2xl border border-[color:var(--ops-state-ready-border)] bg-[color:var(--ops-state-ready-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-ready-text)]">
          初始化只创建 planned records，不会发布到 PyPI/npm/NuGet/Maven，也不会创建 Go tag。
        </div>
        <button type="button" className="w-full rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white shadow-[0_18px_40px_rgba(37,99,235,0.25)] disabled:opacity-50" disabled={Boolean(reason)} onClick={onSubmit}>
          {busy ? '初始化中…' : 'Initialize Train'}
        </button>
      </div>
    </OverlayModal>
  )
}
