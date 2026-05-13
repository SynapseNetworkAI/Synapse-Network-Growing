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
  const [plannerBusy, setPlannerBusy] = useState(false)
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
      toast.success('内容计划已创建')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建内容计划失败')
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

  async function runAssetPlanner() {
    try {
      setPlannerBusy(true)
      const result = await api.runSocialAssetPlanner()
      if (result.asset) {
        setDetail(result.asset)
        setSelectedAccountIds(result.asset.tasks.map((task) => task.account_id))
        toast.success(`已从信号生成内容计划：${result.asset.title}`)
      } else {
        toast.success(result.already_satisfied ? '今日内容计划库存已满足' : `未生成内容计划：${result.reason ?? 'no qualified signal'}`)
      }
      await loadTasks()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '从信号生成内容计划失败')
    } finally {
      setPlannerBusy(false)
    }
  }

  return (
    <SectionFrame
      eyebrow="Distribution Tasks"
      title="Tasks"
      description="Symphony 式内容任务看板：一张卡是一篇源内容，平台文档、发布动作和事件证据都挂在卡片下。状态由后端投影，不支持拖拽改状态。"
      actions={
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={plannerBusy} className="rounded-xl border border-cyan-300/40 px-4 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50" onClick={() => void runAssetPlanner()}>
            {plannerBusy ? '生成中…' : '从信号生成内容计划'}
          </button>
          <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={() => setShowCreate(true)}>创建内容计划</button>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => void loadTasks()}>刷新</button>
        </div>
      }
    >
      {!board ? <EmptyPane>分发看板加载中。</EmptyPane> : null}
      {board && board.summary.total_assets === 0 ? <EmptyPane>暂无内容计划。点击“创建内容计划”，把一篇源内容变成多平台分发工作项。</EmptyPane> : null}
      {board ? <DistributionBoard board={board} formatDateTime={formatDateTime} onOpen={(card) => void openAsset(card.asset.id)} /> : null}
      <OverlayModal open={showCreate} eyebrow="Content Plan" title="创建内容计划" description="输入一篇源内容或大纲；创建后自动生成方案，审核通过后再生成平台文档。" actions={<button type="button" disabled={busy} className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={() => void createTask()}>{busy ? '创建中…' : '创建'}</button>} onClose={() => setShowCreate(false)}>
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
