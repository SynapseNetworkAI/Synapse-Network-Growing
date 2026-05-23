import { useEffect, useState, type MouseEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { SdkPackageRelease, SdkPackageReleaseEvent, SdkPackageReleaseHistoryItem, SdkPackageReleaseHistoryPage, sdkPackagesApi } from '../sdkPackagesApi'
import { EmptyPane, LoadingPane, SectionFrame, StateBadge, useToast } from '../components/workbench'
import { SDK_CHANNEL_OPTIONS, SDK_STATUS_LABEL, formatSdkTime, isSemVer, openExternalUrl, sdkInstallCommand, sdkReleaseTone, syncSdkStatuses } from './sdkPackageUi'

const HISTORY_PAGE_SIZE = 10
const HISTORY_STATUS_OPTIONS = ['', 'planned', 'building', 'ready_to_publish', 'publishing', 'published', 'failed', 'cancelled']
const HISTORY_CHANNEL_OPTIONS = ['', ...SDK_CHANNEL_OPTIONS]

export default function SdkPackageReleaseDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const toast = useToast()
  const releaseId = Number(id)
  const [item, setItem] = useState<SdkPackageRelease | null>(null)
  const [events, setEvents] = useState<SdkPackageReleaseEvent[]>([])
  const [history, setHistory] = useState<SdkPackageReleaseHistoryPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [packageVersion, setPackageVersion] = useState('')
  const [channel, setChannel] = useState('preview')
  const [note, setNote] = useState('')
  const [historySearchDraft, setHistorySearchDraft] = useState('')
  const [historyStatusDraft, setHistoryStatusDraft] = useState('')
  const [historyChannelDraft, setHistoryChannelDraft] = useState('')
  const [historyFilters, setHistoryFilters] = useState({ q: '', status: '', channel: '' })
  const [historyOffset, setHistoryOffset] = useState(0)
  const [confirmPhrase, setConfirmPhrase] = useState('')

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

  const loadHistory = async (nextOffset = historyOffset, filters = historyFilters) => {
    setHistoryLoading(true)
    try {
      const nextHistory = await sdkPackagesApi.getSdkPackageReleaseHistory(releaseId, {
        q: filters.q || undefined,
        status: filters.status || undefined,
        channel: filters.channel || undefined,
        limit: HISTORY_PAGE_SIZE,
        offset: nextOffset,
      })
      setHistory(nextHistory)
      setHistoryOffset(nextHistory.offset)
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    if (!Number.isFinite(releaseId)) return
    load().catch((error) => toast.error(error instanceof Error ? error.message : '加载 SDK package 失败'))
  }, [releaseId])

  useEffect(() => {
    if (!Number.isFinite(releaseId)) return
    loadHistory(historyOffset).catch((error) => toast.error(error instanceof Error ? error.message : '加载 SDK package 发布历史失败'))
  }, [releaseId, historyOffset, historyFilters])

  const runAction = async (action: 'dry-run' | 'publish' | 'retry') => {
    if (!item) return
    if (!isSemVer(packageVersion)) {
      toast.error('请输入 SemVer package version，例如 0.1.0')
      return
    }
    setBusyAction(action)
    try {
      const payload = { actor: 'operator', package_version: packageVersion, channel, note: note || null, confirm_phrase: confirmPhrase || null }
      if (action === 'dry-run') await sdkPackagesApi.dryRunSdkPackageRelease(item.id, payload)
      if (action === 'publish') await sdkPackagesApi.publishSdkPackageRelease(item.id, payload)
      if (action === 'retry') await sdkPackagesApi.retrySdkPackageRelease(item.id, payload)
      toast.success(action === 'dry-run' ? 'Dry run 已触发' : action === 'publish' ? 'Publish 已触发' : 'Retry 已触发')
      await load()
      await loadHistory()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'SDK package action failed')
    } finally {
      setBusyAction(null)
    }
  }

  const sync = async () => {
    await syncSdkStatuses({ load: async () => { await load(); await loadHistory() }, setBusyAction, toast, busyKey: 'sync' })
  }

  const applyHistoryFilters = () => {
    setHistoryFilters({
      q: historySearchDraft.trim(),
      status: historyStatusDraft,
      channel: historyChannelDraft,
    })
    setHistoryOffset(0)
  }

  if (loading || !item) {
    return <LoadingPane>正在加载 SDK package 发布详情…</LoadingPane>
  }

  const isGo = item.sdk_language === 'go'
  const terminal = item.status === 'published' || item.status === 'cancelled'
  const canRetry = item.status === 'failed'
  const historyTotal = history?.total ?? 0
  const historyPage = Math.floor((history?.offset ?? 0) / HISTORY_PAGE_SIZE) + 1
  const canPrevHistory = (history?.offset ?? 0) > 0
  const canNextHistory = (history?.offset ?? 0) + HISTORY_PAGE_SIZE < historyTotal
  const expectedConfirmPhrase = `PUBLISH_SDK_${item.package_version}`
  const installCommand = sdkInstallCommand(item.sdk_language, item.package_name, item.package_version)

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
          {item.status === 'ready_to_publish' ? (
            <label className="mt-4 block">
              <span className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Human Gate Confirm Phrase</span>
              <input
                className="mt-2 w-full rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-transparent px-4 py-3 font-mono text-sm"
                value={confirmPhrase}
                placeholder={expectedConfirmPhrase}
                onChange={(event) => setConfirmPhrase(event.target.value)}
              />
              <span className="mt-2 block text-xs text-[color:var(--ops-text-muted)]">公共 SDK registry 版本不可覆盖；发布前请输入确认短语。</span>
            </label>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            {!terminal ? (
              <button type="button" className="rounded-2xl border border-[color:var(--ops-state-ready-border)] px-4 py-2 text-sm text-[color:var(--ops-state-ready-text)] disabled:opacity-60" disabled={Boolean(busyAction)} onClick={() => runAction('dry-run')}>
                {busyAction === 'dry-run' ? 'Dry Run 中…' : 'Dry Run'}
              </button>
            ) : null}
            {item.status === 'ready_to_publish' ? (
              <button type="button" className="rounded-2xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={Boolean(busyAction) || confirmPhrase !== expectedConfirmPhrase} onClick={() => runAction('publish')}>
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
            <div>Install：<span className="font-mono">{installCommand}</span></div>
            <div>Platform：<span className="font-mono">{String(item.metadata.platform_key || item.registry)}</span></div>
            <div>Verify：<span className="font-mono">{String((item.metadata.verify_result as { status?: string } | undefined)?.status || '-')}</span></div>
            <div>Registry secrets：只存在本地 runner 环境 / Secret Manager，不进入 Growing DB。</div>
            <div>重复发布：registry 已发布同版本不可覆盖，必须 bump patch version。</div>
          </div>
        </SectionFrame>
      </div>

      <SectionFrame
        eyebrow="Release Result History"
        title="发布结果历史"
        description="同一个 SDK package 的版本结果账本。这里展示 version/status/registry/tag/workflow，操作流水保留在下方时间线。"
        actions={
          <button type="button" className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm disabled:opacity-60" disabled={historyLoading} onClick={() => loadHistory()}>
            {historyLoading ? '刷新中…' : '刷新历史'}
          </button>
        }
      >
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr),180px,180px,auto]">
          <input
            className="rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-transparent px-4 py-3 text-sm"
            value={historySearchDraft}
            placeholder="搜索版本 / train / 状态 / registry / failure summary"
            onChange={(event) => setHistorySearchDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') applyHistoryFilters()
            }}
          />
          <select className="rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm" value={historyStatusDraft} onChange={(event) => setHistoryStatusDraft(event.target.value)}>
            {HISTORY_STATUS_OPTIONS.map((status) => <option key={status || 'all'} value={status}>{status ? SDK_STATUS_LABEL[status] || status : '全部状态'}</option>)}
          </select>
          <select className="rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm" value={historyChannelDraft} onChange={(event) => setHistoryChannelDraft(event.target.value)}>
            {HISTORY_CHANNEL_OPTIONS.map((option) => <option key={option || 'all'} value={option}>{option || '全部 Channel'}</option>)}
          </select>
          <button type="button" className="rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-60" disabled={historyLoading} onClick={applyHistoryFilters}>
            搜索
          </button>
        </div>
        {history?.items.length ? (
          <div className="mt-5 space-y-3">
            {history.items.map((release) => (
              <HistoryResultRow key={release.id} release={release} active={release.id === item.id} navigate={navigate} />
            ))}
          </div>
        ) : (
          <div className="mt-5"><EmptyPane>{historyLoading ? '正在加载发布结果历史…' : '暂无匹配的发布结果历史。'}</EmptyPane></div>
        )}
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm text-[color:var(--ops-text-muted)]">
          <span>第 {historyPage} 页 · 共 {historyTotal} 条结果</span>
          <div className="flex gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-2 disabled:opacity-40" disabled={!canPrevHistory || historyLoading} onClick={() => setHistoryOffset(Math.max(0, historyOffset - HISTORY_PAGE_SIZE))}>上一页</button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-2 disabled:opacity-40" disabled={!canNextHistory || historyLoading} onClick={() => setHistoryOffset(historyOffset + HISTORY_PAGE_SIZE)}>下一页</button>
          </div>
        </div>
      </SectionFrame>

      <SectionFrame eyebrow="Operation Timeline" title="操作时间线">
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
          <EmptyPane>暂无操作时间线。</EmptyPane>
        )}
      </SectionFrame>
    </div>
  )
}

function HistoryResultRow({
  release,
  active,
  navigate,
}: Readonly<{
  release: SdkPackageReleaseHistoryItem
  active: boolean
  navigate: (to: string) => void
}>) {
  const openLink = (event: MouseEvent<HTMLButtonElement>, url: string | null) => {
    event.stopPropagation()
    openExternalUrl(url)
  }
  const openDetail = () => navigate(`/releases/sdk-packages/${release.id}`)
  return (
    <article
      role="button"
      tabIndex={0}
      className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-4 transition hover:border-[color:var(--ops-stroke-strong)]"
      onClick={openDetail}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') openDetail()
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-lg font-semibold text-[color:var(--ops-text-title)]">{release.package_version}</span>
            <StateBadge tone={sdkReleaseTone(release.status)}>{SDK_STATUS_LABEL[release.status] || release.status}</StateBadge>
            {active ? <StateBadge tone="running">当前</StateBadge> : null}
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-[color:var(--ops-text-muted)]">
            <span>train <span className="font-mono">{release.release_train_version}</span></span>
            <span>channel <span className="font-mono">{release.channel}</span></span>
            <span>{release.registry}</span>
            <span>{release.git_tag || 'no tag'}</span>
          </div>
        </div>
        <div className="text-right text-xs text-[color:var(--ops-text-caption)]">
          <div>updated {formatSdkTime(release.updated_at)}</div>
          <div className="mt-1">published {formatSdkTime(release.published_at)}</div>
        </div>
      </div>
      {release.failure_summary ? <div className="mt-3 text-sm text-[color:var(--ops-state-blocked-text)]">{release.failure_summary}</div> : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={(event) => { event.stopPropagation(); openDetail() }}>
          查看详情
        </button>
        {release.package_url ? <button type="button" className="rounded-xl border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)]" onClick={(event) => openLink(event, release.package_url)}>打开 Registry</button> : null}
        {release.git_tag_url ? <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={(event) => openLink(event, release.git_tag_url)}>打开 GitHub Tag</button> : null}
        {release.workflow_run_url ? <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={(event) => openLink(event, release.workflow_run_url)}>打开 Workflow</button> : null}
      </div>
    </article>
  )
}
