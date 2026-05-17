import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { SdkPackageRelease, SdkPackageReleaseEvent, sdkPackagesApi } from '../sdkPackagesApi'
import { EmptyPane, LoadingPane, SectionFrame, StateBadge, useToast } from '../components/workbench'
import { SDK_CHANNEL_OPTIONS, SDK_STATUS_LABEL, formatSdkTime, isSemVer, openExternalUrl, sdkReleaseTone, syncSdkStatuses } from './sdkPackageUi'

export default function SdkPackageReleaseDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const toast = useToast()
  const releaseId = Number(id)
  const [item, setItem] = useState<SdkPackageRelease | null>(null)
  const [events, setEvents] = useState<SdkPackageReleaseEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [packageVersion, setPackageVersion] = useState('')
  const [channel, setChannel] = useState('preview')
  const [note, setNote] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const [nextItem, nextEvents] = await Promise.all([
        sdkPackagesApi.getSdkPackageRelease(releaseId),
        sdkPackagesApi.getSdkPackageReleaseEvents(releaseId),
      ])
      setItem(nextItem)
      setEvents(nextEvents)
      setPackageVersion(nextItem.package_version)
      setChannel(nextItem.channel || 'preview')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!Number.isFinite(releaseId)) return
    load().catch((error) => toast.error(error instanceof Error ? error.message : '加载 SDK package 失败'))
  }, [releaseId])

  const runAction = async (action: 'dry-run' | 'publish' | 'retry') => {
    if (!item) return
    if (!isSemVer(packageVersion)) {
      toast.error('请输入 SemVer package version，例如 0.1.0')
      return
    }
    setBusyAction(action)
    try {
      const payload = { actor: 'operator', package_version: packageVersion, channel, note: note || null }
      if (action === 'dry-run') await sdkPackagesApi.dryRunSdkPackageRelease(item.id, payload)
      if (action === 'publish') await sdkPackagesApi.publishSdkPackageRelease(item.id, payload)
      if (action === 'retry') await sdkPackagesApi.retrySdkPackageRelease(item.id, payload)
      toast.success(action === 'dry-run' ? 'Dry run 已触发' : action === 'publish' ? 'Publish 已触发' : 'Retry 已触发')
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'SDK package action failed')
    } finally {
      setBusyAction(null)
    }
  }

  const sync = async () => {
    await syncSdkStatuses({ load, setBusyAction, toast, busyKey: 'sync' })
  }

  if (loading || !item) {
    return <LoadingPane>正在加载 SDK package 发布详情…</LoadingPane>
  }

  const isGo = item.sdk_language === 'go'
  const terminal = item.status === 'published' || item.status === 'cancelled'
  const canRetry = item.status === 'failed'

  return (
    <div className="space-y-[var(--ops-section-gap)]">
      <SectionFrame
        eyebrow="SDK Package Release"
        title={`${item.sdk_language} · ${item.package_name}`}
        description="单个 SDK package 的 dry-run、publish、retry 和 patch version 都在这里操作；Growing 创建本地 publish run，不保存 registry token。"
        actions={
          <>
            <button type="button" className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/releases/sdk-trains/${encodeURIComponent(item.release_train_version)}`)}>
              查看 Train
            </button>
            <button type="button" className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate('/releases')}>
              返回 Releases
            </button>
          </>
        }
      >
        <div className="flex flex-wrap gap-2">
          <StateBadge tone={sdkReleaseTone(item.status)}>{SDK_STATUS_LABEL[item.status] || item.status}</StateBadge>
          <StateBadge tone="muted">train {item.release_train_version}</StateBadge>
          <StateBadge tone="muted">{item.registry}</StateBadge>
          <StateBadge tone="muted">{item.channel}</StateBadge>
        </div>
        <div className="mt-4 grid gap-3 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-2 xl:grid-cols-4">
          <div>package version：<span className="font-mono">{item.package_version}</span></div>
          <div>git tag：<span className="font-mono">{item.git_tag || '-'}</span></div>
          <div>published at：{formatSdkTime(item.published_at)}</div>
          <div>updated at：{formatSdkTime(item.updated_at || item.created_at)}</div>
        </div>
        {isGo ? (
          <div className="mt-4 rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.08] px-4 py-3 text-sm text-cyan-100">
            Go module 位于 <span className="font-mono">/go</span> 子目录，发布 tag 必须是 <span className="font-mono">go/v{item.package_version}</span>，不能用 root release tag 替代。
          </div>
        ) : null}
      </SectionFrame>

      <div className="grid gap-[var(--ops-section-gap)] xl:grid-cols-[minmax(0,1fr),420px]">
        <SectionFrame eyebrow="Actions" title="发布操作" description="先 dry-run，确认 package 构建和 registry 元数据，再逐个 publish。失败后可 bump patch version 再 retry。">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Package Version</span>
              <input
                className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-transparent px-4 py-3 text-sm"
                value={packageVersion}
                onChange={(event) => setPackageVersion(event.target.value)}
              />
              {!isSemVer(packageVersion) ? <span className="mt-2 block text-xs text-[color:var(--ops-state-blocked-text)]">请输入 SemVer，例如 0.1.0</span> : null}
            </label>
            <label className="block">
              <span className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Channel</span>
              <select
                className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm"
                value={channel}
                onChange={(event) => setChannel(event.target.value)}
              >
                {SDK_CHANNEL_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
          </div>
          <textarea
            className="mt-4 min-h-[110px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-transparent px-4 py-3 text-sm"
            value={note}
            placeholder="记录本次 dry-run / publish / retry 备注"
            onChange={(event) => setNote(event.target.value)}
          />
          <div className="mt-4 flex flex-wrap gap-2">
            {!terminal ? (
              <button type="button" className="rounded-2xl border border-[color:var(--ops-state-ready-border)] px-4 py-2 text-sm text-[color:var(--ops-state-ready-text)] disabled:opacity-60" disabled={Boolean(busyAction)} onClick={() => runAction('dry-run')}>
                {busyAction === 'dry-run' ? 'Dry Run 中…' : 'Dry Run'}
              </button>
            ) : null}
            {item.status === 'ready_to_publish' ? (
              <button type="button" className="rounded-2xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={Boolean(busyAction)} onClick={() => runAction('publish')}>
                {busyAction === 'publish' ? '发布中…' : 'Publish'}
              </button>
            ) : null}
            {canRetry ? (
              <button type="button" className="rounded-2xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={Boolean(busyAction)} onClick={() => runAction('retry')}>
                {busyAction === 'retry' ? '重试中…' : 'Retry with Patch'}
              </button>
            ) : null}
            <button type="button" className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm disabled:opacity-60" disabled={Boolean(busyAction)} onClick={sync}>
              {busyAction === 'sync' ? '同步中…' : 'Sync Status'}
            </button>
          </div>
          {item.failure_summary ? <div className="mt-4 rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-blocked-text)]">{item.failure_summary}</div> : null}
        </SectionFrame>

        <SectionFrame eyebrow="Links" title="本地发布链路">
          <div className="space-y-3 text-sm text-[color:var(--ops-text-muted)]">
            <div>Local run：<span className="font-mono">{item.workflow_run_url || '-'}</span></div>
            <div>Package：{item.package_url ? <button type="button" className="text-[color:var(--ops-state-running-text)] underline-offset-4 hover:underline" onClick={() => openExternalUrl(item.package_url)}>打开 Registry 页面</button> : '-'}</div>
            <div>Registry secrets：只存在本地 runner 环境 / Secret Manager，不进入 Growing DB。</div>
            <div>重复发布：registry 已发布同版本不可覆盖，必须 bump patch version。</div>
          </div>
        </SectionFrame>
      </div>

      <SectionFrame eyebrow="History" title="发布历史">
        {events.length ? (
          <div className="space-y-3">
            {events.map((event) => (
              <div key={event.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-semibold text-[color:var(--ops-text-title)]">{event.action}</div>
                  <div className="text-xs text-[color:var(--ops-text-caption)]">{formatSdkTime(event.created_at)}</div>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-[color:var(--ops-text-muted)]">
                  <StateBadge tone="muted">{event.from_status || '-'} → {event.to_status || '-'}</StateBadge>
                  {event.actor ? <StateBadge tone="muted">{event.actor}</StateBadge> : null}
                </div>
                {event.note ? <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">{event.note}</div> : null}
                {event.error_summary ? <div className="mt-2 text-sm text-[color:var(--ops-state-blocked-text)]">{event.error_summary}</div> : null}
              </div>
            ))}
          </div>
        ) : (
          <EmptyPane>暂无发布历史。</EmptyPane>
        )}
      </SectionFrame>
    </div>
  )
}
