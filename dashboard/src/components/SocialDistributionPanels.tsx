import { useEffect, useState } from 'react'
import {
  api,
  type SocialContentAssetDetail,
  type SocialDistributionAccount,
  type SocialDistributionTask,
} from '../api'
import type { SocialDistributionBoard } from '../apiSocialDistribution'
import { EmptyPane, OverlayModal, SectionFrame, useToast } from './workbench'
import { DistributionBoard } from './SocialDistributionBoard'
import { ContentTaskDetailModal, TaskDetailModal } from './SocialDistributionDetails'
import {
  AccountForm,
  ContentTaskForm,
  MetricCard,
  Pager,
  StateBadge,
  TaskLikeTable,
  pageSlice,
  statusTone,
} from './SocialDistributionWidgets'
export { DistributionAssetsPanel } from './SocialDistributionAssetsPanel'

const DEFAULT_CONTENT_FORM = {
  title: '',
  source_material: '',
  target_audience: '一人公司创业者、独立开发者、AI agent builder',
  target_platforms: 'x, v2ex, hacker_news, devto, hashnode, reddit',
  canonical_url: '',
  source_doc_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing/docs/plans/solo-company-codex-collaboration-content-series-outline.md',
}

export function DistributionTasksPanel({ formatDateTime }: { formatDateTime: (value: string | null | undefined) => string }) {
  const toast = useToast()
  const [board, setBoard] = useState<SocialDistributionBoard | null>(null)
  const [accounts, setAccounts] = useState<SocialDistributionAccount[]>([])
  const [detail, setDetail] = useState<SocialContentAssetDetail | null>(null)
  const [taskDetail, setTaskDetail] = useState<SocialDistributionTask | null>(null)
  const [selectedAccountIds, setSelectedAccountIds] = useState<number[]>([])
  const [manualUrl, setManualUrl] = useState('')
  const [manualNote, setManualNote] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({ ...DEFAULT_CONTENT_FORM })

  async function loadTasks() {
    try {
      const [nextBoard, accountRows] = await Promise.all([
        api.getSocialDistributionBoard(),
        api.getDistributionAccounts(),
      ])
      setBoard(nextBoard)
      setAccounts(accountRows)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载分发看板失败')
    }
  }

  useEffect(() => {
    void loadTasks()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function openAsset(assetId: number) {
    try {
      const row = await api.getSocialContentAsset(assetId)
      setDetail(row)
      setSelectedAccountIds(row.tasks.map((task) => task.account_id))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载内容任务失败')
    }
  }

  async function createTask() {
    try {
      setBusy(true)
      const created = await api.createSocialContentTask({
        title: form.title,
        source_material: form.source_material,
        target_audience: form.target_audience,
        target_platforms: form.target_platforms.split(',').map((item) => item.trim()).filter(Boolean),
        canonical_url: form.canonical_url,
        source_doc_path: form.source_doc_path,
        created_by: 'operator',
      })
      setShowCreate(false)
      setDetail(created)
      setSelectedAccountIds([])
      setForm({ ...DEFAULT_CONTENT_FORM, source_doc_path: form.source_doc_path })
      await loadTasks()
      toast.success('内容任务已创建')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建内容任务失败')
    } finally {
      setBusy(false)
    }
  }

  async function generatePlan() {
    if (!detail) return
    try {
      setBusy(true)
      const updated = await api.generateSocialDistributionContentPlan(detail.id, { actor: 'operator' })
      setDetail(updated)
      await loadTasks()
      toast.success('方案已重新生成')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '生成实现计划失败')
    } finally {
      setBusy(false)
    }
  }

  async function expandCanonicalArticle() {
    if (!detail) return
    try {
      setBusy(true)
      const updated = await api.expandSocialDistributionCanonicalArticle(detail.id, { actor: 'operator' })
      setDetail(updated)
      await loadTasks()
      toast.success('母稿已扩写，等待人工审核')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '扩写母稿失败')
    } finally {
      setBusy(false)
    }
  }

  async function approveCanonicalArticle(documentId: number | null) {
    if (!detail) return
    try {
      setBusy(true)
      const updated = await api.approveSocialDistributionCanonicalArticle(detail.id, {
        actor: 'operator',
        document_id: documentId,
      })
      setDetail(updated)
      await loadTasks()
      toast.success('母稿已审核通过，可以生成平台任务')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '审核母稿失败')
    } finally {
      setBusy(false)
    }
  }

  async function approveAndGenerate() {
    if (!detail) return
    try {
      setBusy(true)
      const result = await api.approveAndGenerateSocialDistributionTasks(detail.id, {
        account_ids: selectedAccountIds,
        action: 'post',
        actor: 'operator',
      })
      setDetail(result.asset)
      setSelectedAccountIds(result.asset.tasks.map((task) => task.account_id))
      await loadTasks()
      toast.success(`平台文档生成完成：${result.generated_task_ids.length} 成功，${result.failed_task_ids.length} 失败`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '生成平台文档失败')
    } finally {
      setBusy(false)
    }
  }

  async function markLive(task: SocialDistributionTask) {
    try {
      const updated = await api.markSocialDistributionTaskLive(task.id, { published_url: manualUrl, manual_result_note: manualNote, actor: 'operator' })
      setTaskDetail(updated)
      if (detail) setDetail(await api.getSocialContentAsset(detail.id))
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
      if (detail) setDetail(await api.getSocialContentAsset(detail.id))
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
      if (detail) setDetail(await api.getSocialContentAsset(detail.id))
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
      if (detail) setDetail(await api.getSocialContentAsset(detail.id))
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
      description="Symphony 式内容任务看板：一张卡是一篇源内容，平台文档、发布动作和事件证据都挂在卡片下。状态由后端投影，不支持拖拽改状态。"
      actions={
        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={() => setShowCreate(true)}>创建内容任务</button>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => void loadTasks()}>刷新</button>
        </div>
      }
    >
      {!board ? <EmptyPane>分发看板加载中。</EmptyPane> : null}
      {board && board.summary.total_assets === 0 ? <EmptyPane>暂无内容任务。点击“创建内容任务”，把一篇源内容变成多平台分发工作项。</EmptyPane> : null}
      {board ? <DistributionBoard board={board} formatDateTime={formatDateTime} onOpen={(card) => void openAsset(card.asset.id)} /> : null}
      <OverlayModal open={showCreate} eyebrow="Content Task" title="创建内容任务" description="输入一篇源内容或大纲；创建后自动生成方案，审核通过后再生成平台文档。" actions={<button type="button" disabled={busy} className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={() => void createTask()}>{busy ? '创建中…' : '创建'}</button>} onClose={() => setShowCreate(false)}>
        <ContentTaskForm form={form} onChange={setForm} />
      </OverlayModal>
      <ContentTaskDetailModal
        asset={detail}
        accounts={accounts}
        selectedAccountIds={selectedAccountIds}
        formatDateTime={formatDateTime}
        busy={busy}
        onToggleAccount={(id) => setSelectedAccountIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])}
        onClose={() => setDetail(null)}
        onGeneratePlan={() => void generatePlan()}
        onExpandCanonicalArticle={() => void expandCanonicalArticle()}
        onApproveCanonicalArticle={(documentId) => void approveCanonicalArticle(documentId)}
        onApproveGenerate={() => void approveAndGenerate()}
        onOpenTask={(task) => {
          setTaskDetail(task)
          setManualUrl(task.published_url ?? '')
          setManualNote(task.manual_result_note ?? '')
        }}
      />
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
