import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SdkPackagePlatform, SdkPackageRelease, SdkPackageReleasePage, sdkPackagesApi } from '../sdkPackagesApi'
import { EmptyPane, FieldLabel, OverlayModal, StateBadge, useToast } from '../components/workbench'
import { SDK_STATUS_LABEL, formatSdkTime, isSemVer, openExternalUrl, sdkReleaseTone } from './sdkPackageUi'

const PAGE_SIZE = 10
const STATUS_OPTIONS = ['', 'planned', 'dry_running', 'ready_to_publish', 'publishing', 'published', 'failed', 'cancelled']
const LANGUAGE_OPTIONS = ['', 'python', 'typescript', 'go', 'java', 'dotnet']
const REGISTRY_OPTIONS = ['', 'pypi', 'npm', 'go-module', 'maven-central', 'nuget']
const PACKAGE_OPTIONS = [
  { key: 'python', label: 'Python · synapse-network-ai-sdk · PyPI' },
  { key: 'typescript', label: 'TypeScript · @synapse-network-ai/sdk · npm' },
  { key: 'go', label: 'Go · module /go · GitHub tag' },
  { key: 'java', label: 'Java · Maven Central / GitHub Packages' },
  { key: 'dotnet', label: '.NET · SynapseNetwork.Sdk · NuGet' },
]

function emptyPage(): SdkPackageReleasePage {
  return { items: [], total: 0, page: 1, page_size: PAGE_SIZE, total_pages: 0 }
}

function defaultRecordDraft() {
  return { release_train_version: '1.0.1', channel: 'latest', release_notes: '', packages: ['python'] }
}

function disableReason(draft: ReturnType<typeof defaultRecordDraft>, busy: boolean) {
  if (busy) return '正在创建，请稍候'
  if (!draft.release_train_version.trim()) return '请输入 SemVer 版本，例如 1.0.1'
  if (!isSemVer(draft.release_train_version)) return '版本格式必须是 SemVer，例如 1.0.1'
  if (draft.packages.length === 0) return '至少选择一个 SDK package'
  return null
}

export default function SdkPackagesPanel({ search }: Readonly<{ search: string }>) {
  const navigate = useNavigate()
  const toast = useToast()
  const [pageData, setPageData] = useState<SdkPackageReleasePage>(emptyPage())
  const [loading, setLoading] = useState(true)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [draft, setDraft] = useState(defaultRecordDraft())
  const [statusFilter, setStatusFilter] = useState('')
  const [languageFilter, setLanguageFilter] = useState('')
  const [registryFilter, setRegistryFilter] = useState('')
  const [page, setPage] = useState(1)
  const [platforms, setPlatforms] = useState<SdkPackagePlatform[]>([])
  const [platformModalOpen, setPlatformModalOpen] = useState(false)
  const [publishTarget, setPublishTarget] = useState<SdkPackageRelease | null>(null)
  const [confirmPhrase, setConfirmPhrase] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const [nextPackages, nextPlatforms] = await Promise.all([
        sdkPackagesApi.getSdkPackageReleases({
          page,
          page_size: PAGE_SIZE,
          search: search.trim() || undefined,
          sdk_language: languageFilter || undefined,
          registry: registryFilter || undefined,
          status: statusFilter || undefined,
        }),
        sdkPackagesApi.getSdkPackagePlatforms(),
      ])
      setPageData(nextPackages)
      setPlatforms(nextPlatforms)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch((error) => toast.error(error instanceof Error ? error.message : '加载 SDK 发布历史失败'))
  }, [page, search, languageFilter, registryFilter, statusFilter])

  useEffect(() => {
    setPage(1)
  }, [search])

  const resetPage = (change: () => void) => {
    change()
    setPage(1)
  }

  const createRecords = async () => {
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
      toast.success(draft.packages.length === 1 ? 'SDK 发布记录已创建' : 'SDK release train 已创建')
      setModalOpen(false)
      setDraft(defaultRecordDraft())
      setPage(1)
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建 SDK 发布记录失败')
    } finally {
      setBusyAction(null)
    }
  }

  const runAction = async (item: SdkPackageRelease, action: 'dry-run' | 'retry') => {
    const key = `sdk-package-${item.id}-${action}`
    setBusyAction(key)
    try {
      if (action === 'dry-run') await sdkPackagesApi.dryRunSdkPackageRelease(item.id, { actor: 'operator' })
      if (action === 'retry') await sdkPackagesApi.retrySdkPackageRelease(item.id, { actor: 'operator' })
      toast.success(action === 'dry-run' ? 'Dry Run 已触发' : 'Retry 已触发')
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'SDK package 操作失败')
    } finally {
      setBusyAction(null)
    }
  }

  const publish = async () => {
    if (!publishTarget) return
    setBusyAction(`sdk-package-${publishTarget.id}-publish`)
    try {
      await sdkPackagesApi.publishSdkPackageRelease(publishTarget.id, {
        actor: 'operator',
        confirm_phrase: confirmPhrase,
      })
      toast.success('Publish 已触发，本地 SDK runner 会更新结果和 registry 地址')
      setPublishTarget(null)
      setConfirmPhrase('')
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'SDK package 发布失败')
    } finally {
      setBusyAction(null)
    }
  }

  const openPublishGate = (item: SdkPackageRelease) => {
    setPublishTarget(item)
    setConfirmPhrase('')
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={languageFilter} onChange={(event) => resetPage(() => setLanguageFilter(event.target.value))}>
            {LANGUAGE_OPTIONS.map((language) => <option key={language || 'all'} value={language}>{language || '全部语言'}</option>)}
          </select>
          <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={registryFilter} onChange={(event) => resetPage(() => setRegistryFilter(event.target.value))}>
            {REGISTRY_OPTIONS.map((registry) => <option key={registry || 'all'} value={registry}>{registry || '全部平台'}</option>)}
          </select>
          <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={statusFilter} onChange={(event) => resetPage(() => setStatusFilter(event.target.value))}>
            {STATUS_OPTIONS.map((status) => <option key={status || 'all'} value={status}>{status ? SDK_STATUS_LABEL[status] : '全部状态'}</option>)}
          </select>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded-xl border border-[color:var(--ops-state-running-border)] px-4 py-2.5 text-sm font-semibold text-[color:var(--ops-state-running-text)]" onClick={() => setPlatformModalOpen(true)}>
            Platform Settings
          </button>
          <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white" onClick={() => setModalOpen(true)}>
            新增发布记录
          </button>
        </div>
      </div>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4">
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">SDK Release History</div>
            <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
              每个平台、每个版本是一条发布记录；发布成功后保存 registry URL，例如 PyPI / npm / NuGet 页面。
            </div>
          </div>
          <div className="text-sm text-[color:var(--ops-text-muted)]">共 {pageData.total} 条 · 第 {pageData.page || page} / {pageData.total_pages || 1} 页</div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-[color:var(--ops-stroke-soft)] text-left text-sm">
            <thead className="bg-[color:var(--ops-panel-subtle)] text-xs uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">
              <tr>
                <th className="px-5 py-3">版本</th>
                <th className="px-5 py-3">语言 / 平台</th>
                <th className="px-5 py-3">包名</th>
                <th className="px-5 py-3">状态</th>
                <th className="px-5 py-3">发布地址</th>
                <th className="px-5 py-3">更新时间</th>
                <th className="px-5 py-3 text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--ops-stroke-soft)]">
              {pageData.items.map((item) => {
                const busyPrefix = `sdk-package-${item.id}-`
                return (
                  <tr key={item.id} className="align-top">
                    <td className="px-5 py-4">
                      <button type="button" className="font-mono font-semibold text-[color:var(--ops-text-title)] hover:underline" onClick={() => navigate(`/releases/sdk-trains/${encodeURIComponent(item.release_train_version)}`)}>
                        {item.release_train_version}
                      </button>
                      <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">package {item.package_version} · {item.channel}</div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="font-semibold text-[color:var(--ops-text-title)]">{item.sdk_language}</div>
                      <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{item.registry}</div>
                    </td>
                    <td className="px-5 py-4">
                      <button type="button" className="max-w-xs break-all text-left hover:underline" onClick={() => navigate(`/releases/sdk-packages/${item.id}`)}>
                        {item.package_name}
                      </button>
                      <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{item.git_tag || '-'}</div>
                    </td>
                    <td className="px-5 py-4">
                      <StateBadge tone={sdkReleaseTone(item.status)}>{SDK_STATUS_LABEL[item.status] || item.status}</StateBadge>
                      {item.failure_summary ? <div className="mt-2 line-clamp-2 max-w-xs text-xs text-[color:var(--ops-state-blocked-text)]">{item.failure_summary}</div> : null}
                    </td>
                    <td className="px-5 py-4">
                      {item.package_url ? (
                        <button type="button" className="text-[color:var(--ops-state-running-text)] underline-offset-4 hover:underline" onClick={() => openExternalUrl(item.package_url)}>
                          打开 Package
                        </button>
                      ) : (
                        <span className="text-[color:var(--ops-text-caption)]">-</span>
                      )}
                    </td>
                    <td className="px-5 py-4 text-[color:var(--ops-text-muted)]">
                      <div>{formatSdkTime(item.published_at || item.updated_at || item.created_at)}</div>
                      {item.workflow_run_url ? <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">Local Runner</div> : null}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex flex-wrap justify-end gap-2">
                        <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/releases/sdk-packages/${item.id}`)}>
                          详情
                        </button>
                        {item.status === 'planned' || item.status === 'dry_running' ? (
                          <button type="button" className="rounded-lg border border-[color:var(--ops-state-ready-border)] px-3 py-2 text-sm text-[color:var(--ops-state-ready-text)] disabled:opacity-50" disabled={Boolean(busyAction)} onClick={() => runAction(item, 'dry-run')}>
                            {busyAction === `${busyPrefix}dry-run` ? '验证中…' : '先 Dry Run'}
                          </button>
                        ) : null}
                        {item.status === 'failed' ? (
                          <button type="button" className="rounded-lg border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50" disabled={Boolean(busyAction)} onClick={() => runAction(item, 'retry')}>
                            {busyAction === `${busyPrefix}retry` ? '重试中…' : '重试'}
                          </button>
                        ) : null}
                        {item.status === 'ready_to_publish' ? (
                          <button type="button" className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={Boolean(busyAction)} onClick={() => openPublishGate(item)}>
                            发布
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {!loading && pageData.items.length === 0 ? <div className="p-6"><EmptyPane>暂无 SDK 发布记录。点击 “新增发布记录” 创建单个平台或完整 train。</EmptyPane></div> : null}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--ops-stroke-soft)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]">
          <span>每页 {PAGE_SIZE} 条</span>
          <div className="flex gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-2 disabled:opacity-50" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-2 disabled:opacity-50" disabled={page >= (pageData.total_pages || 1) || loading} onClick={() => setPage((value) => value + 1)}>下一页</button>
          </div>
        </div>
      </section>

      <InitializeRecordModal open={modalOpen} draft={draft} busy={busyAction === 'initialize'} onClose={() => setModalOpen(false)} onDraftChange={setDraft} onSubmit={createRecords} />
      <PublishGateModal target={publishTarget} confirmPhrase={confirmPhrase} busy={busyAction === `sdk-package-${publishTarget?.id}-publish`} onClose={() => setPublishTarget(null)} onConfirmPhraseChange={setConfirmPhrase} onSubmit={publish} />
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
              <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-60" disabled={busy === `platform-${platform.platform_key}`} onClick={() => onUpdate(platform.platform_key, !platform.enabled)}>
                {platform.enabled ? 'Disable' : 'Enable'}
              </button>
            </div>
          </article>
        ))}
      </div>
    </OverlayModal>
  )
}

function InitializeRecordModal({
  open,
  draft,
  busy,
  onClose,
  onDraftChange,
  onSubmit,
}: Readonly<{
  open: boolean
  draft: ReturnType<typeof defaultRecordDraft>
  busy: boolean
  onClose: () => void
  onDraftChange: (draft: ReturnType<typeof defaultRecordDraft>) => void
  onSubmit: () => void
}>) {
  const reason = disableReason(draft, busy)
  return (
    <OverlayModal open={open} eyebrow="SDK Release Record" title="新增 SDK 发布记录" description="可以只创建一个平台版本记录，也可以选择全部平台创建完整 release train。" onClose={onClose}>
      <div className="space-y-5">
        {reason ? <div className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-blocked-text)]">{reason}</div> : null}
        <label className="block space-y-2">
          <FieldLabel>Version</FieldLabel>
          <input className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm" placeholder="1.0.1" value={draft.release_train_version} onChange={(event) => onDraftChange({ ...draft, release_train_version: event.target.value })} />
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
          <div className="flex flex-wrap items-center justify-between gap-2">
            <FieldLabel>Platforms</FieldLabel>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-3 py-1.5 text-xs" onClick={() => onDraftChange({ ...draft, packages: PACKAGE_OPTIONS.map((item) => item.key) })}>
              创建完整 train
            </button>
          </div>
          {PACKAGE_OPTIONS.map((item) => (
            <label key={item.key} className="flex items-center gap-3 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-sm">
              <input type="checkbox" checked={draft.packages.includes(item.key)} onChange={(event) => onDraftChange({ ...draft, packages: event.target.checked ? [...draft.packages, item.key] : draft.packages.filter((value) => value !== item.key) })} />
              <span>{item.label}</span>
            </label>
          ))}
        </section>
        <label className="block space-y-2">
          <FieldLabel>Release notes</FieldLabel>
          <textarea className="min-h-32 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm" placeholder="本轮 SDK release 的开发者可见变化。" value={draft.release_notes} onChange={(event) => onDraftChange({ ...draft, release_notes: event.target.value })} />
        </label>
        <div className="rounded-2xl border border-[color:var(--ops-state-ready-border)] bg-[color:var(--ops-state-ready-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-ready-text)]">
          新增只创建 planned 记录，不会发布到公共 registry。发布必须先 dry-run，再 Human Gate。
        </div>
        <button type="button" className="w-full rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white shadow-[0_18px_40px_rgba(37,99,235,0.25)] disabled:opacity-50" disabled={Boolean(reason)} onClick={onSubmit}>
          {busy ? '创建中…' : draft.packages.length === 1 ? '新增发布记录' : '创建 Release Train'}
        </button>
      </div>
    </OverlayModal>
  )
}

function PublishGateModal({
  target,
  confirmPhrase,
  busy,
  onClose,
  onConfirmPhraseChange,
  onSubmit,
}: Readonly<{
  target: SdkPackageRelease | null
  confirmPhrase: string
  busy: boolean
  onClose: () => void
  onConfirmPhraseChange: (value: string) => void
  onSubmit: () => void
}>) {
  const expected = target ? `PUBLISH_SDK_${target.package_version}` : ''
  return (
    <OverlayModal open={Boolean(target)} eyebrow="Human Gate" title="发布 SDK 到公共仓库" description="公共 registry 版本不可覆盖；确认后本地 runner 会执行真实 publish 并回写 package URL。" onClose={onClose}>
      {target ? (
        <div className="space-y-5">
          <div className="grid gap-3 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4 text-sm md:grid-cols-2">
            <div><span className="text-[color:var(--ops-text-caption)]">Package</span><div className="mt-1 font-semibold">{target.package_name}</div></div>
            <div><span className="text-[color:var(--ops-text-caption)]">Registry</span><div className="mt-1 font-mono">{target.registry}</div></div>
            <div><span className="text-[color:var(--ops-text-caption)]">Version</span><div className="mt-1 font-mono">{target.package_version}</div></div>
            <div><span className="text-[color:var(--ops-text-caption)]">Channel</span><div className="mt-1 font-mono">{target.channel}</div></div>
          </div>
          <label className="block space-y-2">
            <FieldLabel>确认短语</FieldLabel>
            <input className="w-full rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-transparent px-4 py-3 font-mono text-sm" value={confirmPhrase} placeholder={expected} onChange={(event) => onConfirmPhraseChange(event.target.value)} />
          </label>
          <button type="button" className="w-full rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-50" disabled={busy || confirmPhrase !== expected} onClick={onSubmit}>
            {busy ? '发布中…' : '确认发布'}
          </button>
        </div>
      ) : null}
    </OverlayModal>
  )
}
