import { useEffect, useMemo, useState } from 'react'
import {
  api,
  type SocialContentAsset,
  type SocialContentAssetDetail,
  type SocialDistributionAccount,
  type SocialDistributionTask,
  type SocialDistributionTaskGroup,
} from '../api'
import { EmptyPane, OverlayModal, SectionFrame, useToast } from './workbench'
import { AssetDetail, TaskDetailModal } from './SocialDistributionDetails'
import {
  AccountForm,
  AssetForm,
  MetricCard,
  Pager,
  StateBadge,
  TaskLikeTable,
  inputClass,
  pageSlice,
  statusTone,
} from './SocialDistributionWidgets'

export function DistributionTasksPanel({ formatDateTime }: { formatDateTime: (value: string | null | undefined) => string }) {
  const toast = useToast()
  const [groups, setGroups] = useState<SocialDistributionTaskGroup[]>([])
  const [flatView, setFlatView] = useState(false)
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())
  const [taskDetail, setTaskDetail] = useState<SocialDistributionTask | null>(null)
  const [manualUrl, setManualUrl] = useState('')
  const [manualNote, setManualNote] = useState('')
  const [platformFilter, setPlatformFilter] = useState<string | null>(() => new URLSearchParams(window.location.search).get('platform'))
  const [channelFilter, setChannelFilter] = useState<string | null>(() => new URLSearchParams(window.location.search).get('channel_key'))
  const [statusFilter, setStatusFilter] = useState<string>(() => new URLSearchParams(window.location.search).get('status') ?? 'all')

  async function loadTasks() {
    try {
      const result = await api.getSocialDistributionTasks({
        platform: platformFilter,
        channel_key: channelFilter,
        status: statusFilter,
      })
      setGroups(result.groups)
      setExpandedIds((current) => current.size ? current : new Set(result.groups.slice(0, 1).map((group) => group.asset.id)))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载分发任务失败')
    }
  }

  useEffect(() => {
    void loadTasks()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [platformFilter, channelFilter, statusFilter])

  const flatTasks = useMemo(() => groups.flatMap((group) => group.tasks), [groups])
  const visibleGroups = groups

  async function markLive(task: SocialDistributionTask) {
    try {
      const updated = await api.markSocialDistributionTaskLive(task.id, { published_url: manualUrl, manual_result_note: manualNote, actor: 'operator' })
      setTaskDetail(updated)
      await loadTasks()
      toast.success('已记录 live 链接')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '标记 live 失败')
    }
  }

  async function markRemoved(task: SocialDistributionTask) {
    try {
      const updated = await api.markSocialDistributionTaskRemoved(task.id, { manual_result_note: manualNote, actor: 'operator' })
      setTaskDetail(updated)
      await loadTasks()
      toast.success('已标记 removed')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '标记 removed 失败')
    }
  }

  async function skipTask(task: SocialDistributionTask) {
    try {
      const updated = await api.updateSocialDistributionTask(task.id, { status: 'skipped', manual_result_note: manualNote })
      setTaskDetail(updated)
      await loadTasks()
      toast.success('已跳过该任务')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '跳过失败')
    }
  }

  async function publishX(task: SocialDistributionTask) {
    try {
      const updated = await api.publishSocialDistributionTaskToX(task.id, { actor: 'operator' })
      setTaskDetail(updated)
      await loadTasks()
      toast.success('已发布到 X')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '发布到 X 失败')
    }
  }

  return (
    <SectionFrame
      eyebrow="Distribution Tasks"
      title="Tasks"
      description="默认按内容资产分组，避免同一篇文章派生出的 X、HN、Reddit、V2EX、DEV 任务变成噪音列表。"
      actions={
        <div className="flex flex-wrap gap-2">
          {platformFilter ? <span className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100">平台：{platformFilter} / {channelFilter ?? 'all'}</span> : null}
          <select className={`${inputClass} w-auto py-2`} value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">全部</option>
            <option value="needs_review">待审核</option>
            <option value="draft_ready">草稿就绪</option>
            <option value="live">已发布</option>
            <option value="failed">失败</option>
            <option value="removed">removed</option>
          </select>
          {(platformFilter || channelFilter || statusFilter !== 'all') ? <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => { setPlatformFilter(null); setChannelFilter(null); setStatusFilter('all') }}>清除筛选</button> : null}
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => setFlatView((value) => !value)}>{flatView ? 'Grouped View' : 'Flat View'}</button>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => void loadTasks()}>刷新</button>
        </div>
      }
    >
      {groups.length === 0 ? <EmptyPane>暂无内容资产任务。先到 Assets 创建一份源内容，再串行生成渠道任务。</EmptyPane> : null}
      {flatView ? (
        <TaskTable tasks={flatTasks} formatDateTime={formatDateTime} onOpen={(task) => {
          setTaskDetail(task)
          setManualUrl(task.published_url ?? '')
          setManualNote(task.manual_result_note ?? '')
        }} />
      ) : (
        <div className="space-y-4">
          {visibleGroups.map((group) => {
            const expanded = expandedIds.has(group.asset.id)
            return (
              <article key={group.asset.id} className="rounded-[24px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)]">
                <button
                  type="button"
                  className="flex w-full items-start justify-between gap-4 px-5 py-4 text-left"
                  onClick={() => setExpandedIds((current) => {
                    const next = new Set(current)
                    if (next.has(group.asset.id)) next.delete(group.asset.id)
                    else next.add(group.asset.id)
                    return next
                  })}
                >
                  <AssetSummary asset={group.asset} taskCount={group.tasks.length} />
                  <span className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm">{expanded ? '收起' : '展开'}</span>
                </button>
                {expanded ? (
                  <div className="border-t border-[color:var(--ops-stroke-soft)] px-5 py-4">
                    <TaskTable tasks={group.tasks} formatDateTime={formatDateTime} onOpen={(task) => {
                      setTaskDetail(task)
                      setManualUrl(task.published_url ?? '')
                      setManualNote(task.manual_result_note ?? '')
                    }} />
                  </div>
                ) : null}
              </article>
            )
          })}
        </div>
      )}
      <TaskDetailModal
        task={taskDetail}
        manualUrl={manualUrl}
        manualNote={manualNote}
        toast={toast}
        onManualUrlChange={setManualUrl}
        onManualNoteChange={setManualNote}
        onClose={() => setTaskDetail(null)}
        onMarkLive={() => taskDetail ? void markLive(taskDetail) : undefined}
        onMarkRemoved={() => taskDetail ? void markRemoved(taskDetail) : undefined}
        onSkip={() => taskDetail ? void skipTask(taskDetail) : undefined}
        onPublishX={() => taskDetail ? void publishX(taskDetail) : undefined}
      />
    </SectionFrame>
  )
}

export function DistributionAssetsPanel({ formatDateTime }: { formatDateTime: (value: string | null | undefined) => string }) {
  const toast = useToast()
  const [assets, setAssets] = useState<SocialContentAsset[]>([])
  const [accounts, setAccounts] = useState<SocialDistributionAccount[]>([])
  const [detail, setDetail] = useState<SocialContentAssetDetail | null>(null)
  const [selectedAccountIds, setSelectedAccountIds] = useState<number[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ title: '', summary: '', body: '', canonical_url: '', asset_type: 'article' })
  const [busyAssetId, setBusyAssetId] = useState<number | null>(null)
  const [plannerBusy, setPlannerBusy] = useState(false)

  async function loadAssets() {
    try {
      const [assetRows, accountRows] = await Promise.all([api.getSocialContentAssets(), api.getDistributionAccounts()])
      setAssets(assetRows)
      setAccounts(accountRows)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载内容资产失败')
    }
  }

  useEffect(() => {
    void loadAssets()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function createAsset() {
    try {
      const created = await api.createSocialContentAsset({ ...form, source_type: 'manual', created_by: 'operator' })
      setShowCreate(false)
      setForm({ title: '', summary: '', body: '', canonical_url: '', asset_type: 'article' })
      setDetail(created)
      await loadAssets()
      toast.success('内容资产已创建')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建内容资产失败')
    }
  }

  async function openAsset(id: number) {
    try {
      const row = await api.getSocialContentAsset(id)
      setDetail(row)
      setSelectedAccountIds(row.tasks.map((task) => task.account_id))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载资产详情失败')
    }
  }

  async function runAssetPlanner() {
    try {
      setPlannerBusy(true)
      const result = await api.runSocialAssetPlanner()
      if (result.asset) {
        setDetail(result.asset)
        setSelectedAccountIds(result.asset.tasks.map((task) => task.account_id))
        toast.success(`Asset Planner 已生成：${result.asset.title}`)
      } else {
        toast.success(result.already_satisfied ? '今日 Asset 库存已满足' : `未生成 Asset：${result.reason ?? 'no qualified signal'}`)
      }
      await loadAssets()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '运行 Asset Planner 失败')
    } finally {
      setPlannerBusy(false)
    }
  }

  async function approveAndGenerate(asset: SocialContentAssetDetail | SocialContentAsset) {
    try {
      setBusyAssetId(asset.id)
      const result = await api.approveAndGenerateSocialDistributionTasks(asset.id, {
        account_ids: detail?.id === asset.id ? selectedAccountIds : [],
        action: 'post',
        actor: 'operator',
      })
      setDetail(result.asset)
      setSelectedAccountIds(result.asset.tasks.map((task) => task.account_id))
      await loadAssets()
      toast.success(`批准并生成完成：${result.generated_task_ids.length} 成功，${result.failed_task_ids.length} 失败`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批准并生成渠道任务失败')
    } finally {
      setBusyAssetId(null)
    }
  }

  return (
    <SectionFrame
      eyebrow="Content Assets"
      title="Assets"
      description="一份源内容可以派生出多个平台任务；资产是新的 Social Distribution Source of Truth。"
      actions={
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={plannerBusy} className="rounded-xl border border-cyan-300/40 px-4 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50" onClick={() => void runAssetPlanner()}>
            {plannerBusy ? 'Asset Planner 运行中…' : '运行 Asset Planner'}
          </button>
          <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={() => setShowCreate(true)}>创建内容资产</button>
        </div>
      }
    >
      {assets.length === 0 ? <EmptyPane>暂无内容资产。</EmptyPane> : null}
      <div className="grid gap-3 lg:grid-cols-2">
        {assets.map((asset) => {
          const busy = busyAssetId === asset.id
          return (
            <article key={asset.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
              <button type="button" className="w-full text-left" onClick={() => void openAsset(asset.id)}>
                <AssetSummary asset={asset} taskCount={asset.task_count} />
                <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">updated {formatDateTime(asset.updated_at)}</div>
              </button>
              <div className="mt-4 flex flex-wrap gap-2">
                <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => void openAsset(asset.id)}>详情</button>
                <button type="button" disabled={busy} className="rounded-xl border border-emerald-300/40 px-3 py-2 text-sm font-semibold text-emerald-100 disabled:opacity-50" onClick={() => void approveAndGenerate(asset)}>
                  {busy ? '生成中…' : '批准并生成分发任务'}
                </button>
              </div>
            </article>
          )
        })}
      </div>
      <OverlayModal open={showCreate} eyebrow="Content Asset" title="创建内容资产" description="输入源文章、demo 或官方公告摘要；系统随后为各平台串行生成任务。" actions={<button type="button" className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={() => void createAsset()}>创建</button>} onClose={() => setShowCreate(false)}>
        <AssetForm form={form} onChange={setForm} />
      </OverlayModal>
      <OverlayModal
        open={Boolean(detail)}
        eyebrow="Content Asset"
        title={detail?.title ?? '内容资产'}
        description="选择渠道后批准并串行生成任务；某个平台失败不会回滚其它平台。"
        actions={
          <button type="button" disabled={!detail || busyAssetId === detail.id} className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={() => detail ? void approveAndGenerate(detail) : undefined}>
            {detail && busyAssetId === detail.id ? '生成中…' : '批准并生成分发任务'}
          </button>
        }
        onClose={() => setDetail(null)}
      >
        {detail ? <AssetDetail asset={detail} accounts={accounts} selectedAccountIds={selectedAccountIds} formatDateTime={formatDateTime} onToggle={(id) => setSelectedAccountIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])} /> : null}
      </OverlayModal>
    </SectionFrame>
  )
}

export function DistributionSettingsPanel({ formatDateTime }: { formatDateTime: (value: string | null | undefined) => string }) {
  const toast = useToast()
  const [accounts, setAccounts] = useState<SocialDistributionAccount[]>([])
  const [editing, setEditing] = useState<SocialDistributionAccount | null>(null)
  const [form, setForm] = useState({
    profile_url: '',
    status: 'planned',
    email_hint: '',
    two_factor_status: 'unknown',
    publish_mode: 'manual_only',
    api_capability: 'none',
    credential_ref: '',
    notes: '',
  })
  const [page, setPage] = useState(1)

  async function loadAccounts() {
    try {
      setAccounts(await api.getDistributionAccounts())
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载渠道失败')
    }
  }
  useEffect(() => {
    void loadAccounts()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function saveAccount() {
    if (!editing) return
    try {
      await api.updateDistributionAccount(editing.id, {
        ...form,
        credential_ref: form.credential_ref.trim() ? form.credential_ref : undefined,
      })
      setEditing(null)
      await loadAccounts()
      toast.success('渠道设置已保存')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存失败')
    }
  }

  const paged = pageSlice(accounts, page)
  return (
    <SectionFrame eyebrow="Settings" title="Settings" description="管理分发渠道账号、Profile、2FA 状态和人工发布规则。">
      <TaskLikeTable
        headers={['平台 / 渠道', '状态', '治理', '更新', '操作']}
        rows={paged.map((account) => [
          <div key="name"><b>{account.display_name}</b><div className="font-mono text-xs text-[color:var(--ops-text-caption)]">{account.platform} · {account.channel_key}</div></div>,
          <StateBadge key="status" tone={statusTone(account.status)}>{account.status}</StateBadge>,
          <div key="gov" className="text-xs text-[color:var(--ops-text-muted)]">{account.publish_mode} · {account.api_capability} · 2FA {account.two_factor_status}{account.credential_ref_configured ? ' · secret ref set' : ''}</div>,
          <span key="time" className="text-xs text-[color:var(--ops-text-muted)]">{formatDateTime(account.updated_at)}</span>,
          <div key="actions" className="flex flex-wrap gap-2">
            <button type="button" className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" onClick={() => { window.location.href = `/publishing?tab=tasks&platform=${encodeURIComponent(account.platform)}&channel_key=${encodeURIComponent(account.channel_key)}` }}>历史</button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => {
              setEditing(account)
              setForm({
                profile_url: account.profile_url ?? '',
                status: account.status,
                email_hint: account.email_hint ?? '',
                two_factor_status: account.two_factor_status,
                publish_mode: account.publish_mode,
                api_capability: account.api_capability,
                credential_ref: '',
                notes: account.notes ?? '',
              })
            }}>编辑</button>
          </div>,
        ])}
      />
      <Pager page={page} total={accounts.length} onPageChange={setPage} />
      <OverlayModal open={Boolean(editing)} eyebrow="Distribution Account" title={editing ? `编辑 ${editing.display_name}` : '编辑渠道'} actions={<button type="button" className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={() => void saveAccount()}>保存</button>} onClose={() => setEditing(null)}>
        <AccountForm form={form} onChange={setForm} />
      </OverlayModal>
    </SectionFrame>
  )
}

export function DistributionSignalsMetricsPanel({ formatDateTime }: { formatDateTime: (value: string | null | undefined) => string }) {
  const toast = useToast()
  const [trends, setTrends] = useState<Array<{ id: number; topic: string; summary: string; source_url: string | null; author_handle: string | null; relevance_score: number; collected_at: string | null }>>([])
  const [summary, setSummary] = useState<{ observed_post_count: number; total_impressions: number; total_likes: number; total_replies: number; total_reposts: number; total_link_clicks: number; last_observed_at: string | null; diagnostic?: string | null } | null>(null)

  async function load() {
    try {
      const [trendRows, metricSummary] = await Promise.all([api.getSocialTrends(), api.getSocialPostMetricSummary()])
      setTrends(trendRows.slice(0, 20))
      setSummary(metricSummary)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载 Signals & Metrics 失败')
    }
  }
  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <SectionFrame eyebrow="Signals & Metrics" title="Signals & Metrics" description="这里只读本地 DB：趋势、watchlist 信号、已发布效果摘要，不在页面刷新时触发 X read。">
      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Observed posts" value={summary?.observed_post_count ?? 0} />
        <MetricCard label="Impressions" value={summary?.total_impressions ?? 0} />
        <MetricCard label="Engagement" value={(summary?.total_likes ?? 0) + (summary?.total_replies ?? 0) + (summary?.total_reposts ?? 0)} />
      </div>
      {summary?.diagnostic ? <div className="mt-4 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4 text-sm text-[color:var(--ops-text-muted)]">{summary.diagnostic}</div> : null}
      <div className="mt-5 space-y-3">
        {trends.map((trend) => (
          <div key={trend.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-[color:var(--ops-text-title)]">{trend.topic}</div>
                <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{trend.summary}</div>
              </div>
              <StateBadge tone={trend.source_url ? 'ready' : 'muted'}>{trend.source_url ? 'X source' : 'local seed'}</StateBadge>
            </div>
            <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">{trend.author_handle ?? '@unknown'} · score {Math.round(trend.relevance_score * 100)} · {formatDateTime(trend.collected_at)}</div>
          </div>
        ))}
      </div>
    </SectionFrame>
  )
}

function AssetSummary({ asset, taskCount }: { asset: SocialContentAsset; taskCount: number }) {
  const counts = Object.entries(asset.status_counts ?? {}).map(([status, count]) => `${count} ${status}`).join(' / ')
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2"><b className="text-[color:var(--ops-text-title)]">{asset.title}</b><StateBadge tone={statusTone(asset.status)}>{asset.status}</StateBadge></div>
      <div className="mt-2 line-clamp-2 text-sm text-[color:var(--ops-text-muted)]">{asset.summary || asset.body || 'No summary yet.'}</div>
      <div className="mt-3 font-mono text-xs text-[color:var(--ops-text-caption)]">{asset.asset_type} · {asset.source_type} · {taskCount} tasks{counts ? ` · ${counts}` : ''}</div>
    </div>
  )
}

function TaskTable({ tasks, formatDateTime, onOpen }: { tasks: SocialDistributionTask[]; formatDateTime: (value: string | null | undefined) => string; onOpen: (task: SocialDistributionTask) => void }) {
  return (
    <TaskLikeTable
      headers={['平台任务', '状态', '正文摘要', '更新', '操作']}
      rows={tasks.map((task) => [
        <div key="name"><b>{task.account_display_name ?? task.channel_key}</b><div className="font-mono text-xs text-[color:var(--ops-text-caption)]">{task.platform} · {task.action}</div></div>,
        <StateBadge key="status" tone={statusTone(task.status)}>{task.status}</StateBadge>,
        <div key="body" className="line-clamp-3 max-w-[520px] text-xs leading-5 text-[color:var(--ops-text-muted)]">{task.platform_body || task.failure_summary || 'No draft yet.'}</div>,
        <span key="time" className="text-xs text-[color:var(--ops-text-muted)]">{formatDateTime(task.updated_at)}</span>,
        <button key="open" type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => onOpen(task)}>详情</button>,
      ])}
    />
  )
}
