import { useEffect, useState } from 'react'
import { api, type SocialContentAssetDetail, type SocialDistributionAccount, type SocialReplyItem, type SocialDistributionTask } from '../api'
import type { SocialDistributionBoard } from '../apiSocialDistribution'
import { ConfirmDialog, EmptyPane, OverlayModal, SectionFrame, useToast } from './workbench'
import { DistributionBoard } from './SocialDistributionBoard'
import { ContentTaskDetailModal, TaskDetailModal } from './SocialDistributionDetails'
export { DistributionSettingsPanel } from './SocialDistributionSettingsPanel'
import { useSocialDistributionAuthStatus } from './useSocialDistributionAuthStatus'
import { TaskKindFilterControl, filterBoardByKind, type TaskKindFilter } from './SocialDistributionTaskKindFilter'
import { ContentTaskForm } from './SocialDistributionWidgets'
import { formatXOAuthReconnectError } from '../lib/socialXAuth'
export { DistributionAssetsPanel } from './SocialDistributionAssetsPanel'

const DEFAULT_CONTENT_FORM = { title: '', task_type: 'x_media_post', source_material: '', target_audience: '一人公司创业者、独立开发者、AI agent builder', target_platforms: 'x', canonical_url: '', source_doc_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing/docs/plans/solo-company-codex-collaboration-content-series-outline.md', campaign_key: '', post_intent: 'brand_positioning' }

function openExternalUrlInNewTab(url: string): boolean {
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (opened) return true
  const link = document.createElement('a')
  link.href = url
  link.target = '_blank'
  link.rel = 'noopener noreferrer'
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  link.remove()
  return false
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
  const [auditVisibility, setAuditVisibility] = useState('visible')
  const [auditLayout, setAuditLayout] = useState('passed')
  const [showCreate, setShowCreate] = useState(false)
  const [busy, setBusy] = useState(false)
  const [xAuthNotice, setXAuthNotice] = useState<string | null>(null)
  const { authStatuses, authStatusBusy, checkAccountAuthStatuses } = useSocialDistributionAuthStatus()
  const [plannerBusy, setPlannerBusy] = useState(false)
  const [taskKindFilter, setTaskKindFilter] = useState<TaskKindFilter>('all')
  const [form, setForm] = useState({ ...DEFAULT_CONTENT_FORM })
  const [replyRegeneratePending, setReplyRegeneratePending] = useState(false)

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

  useEffect(() => {
    if (detail?.agent_metadata?.post_intent === 'engagement_reply') {
      void checkAccountAuthStatuses({ platform: 'x' })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.id])

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
        task_type: form.task_type,
        source_material: form.source_material,
        target_audience: form.target_audience,
        target_platforms: targetPlatformsForForm(form),
        canonical_url: form.canonical_url,
        source_doc_path: form.source_doc_path,
        campaign_key: form.campaign_key,
        post_intent: form.post_intent,
        created_by: 'operator',
      })
      setShowCreate(false)
      setDetail(created)
      setSelectedAccountIds([])
      setForm({ ...DEFAULT_CONTENT_FORM, source_doc_path: form.source_doc_path })
      await loadTasks()
      toast.success(created.agent_metadata.reused_existing ? '任务已存在，已打开已有任务' : '内容计划已创建')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建内容计划失败')
    } finally {
      setBusy(false)
    }
  }

  async function createXBrandWeekCampaign() {
    try {
      setBusy(true)
      const result = await api.createXBrandWeekCampaignTemplate()
      await loadTasks()
      if (result.assets[0]) {
        setDetail(result.assets[0])
        setSelectedAccountIds(result.assets[0].tasks.map((task) => task.account_id))
      }
      toast.success(`X 品牌周任务已准备：新增 ${result.created_count}，已存在 ${result.existing_count}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建 X 品牌周任务失败')
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

  async function generateXReplyBlock(forceConfirmed = false) {
    if (!detail) return
    const replyBlock = detail.agent_metadata?.reply_block as Record<string, unknown> | undefined
    const targetCount = numberValue(replyBlock?.target_count) || numberValue(replyBlock?.processed_source_count) || 5
    const failedCount = (detail.reply_items ?? []).filter((reply) => ['failed', 'rejected'].includes(reply.status)).length
    const forceRegenerate = (detail.reply_items ?? []).length >= targetCount && failedCount === 0
    if (forceRegenerate && !forceConfirmed) {
      setReplyRegeneratePending(true)
      return
    }
    try {
      setBusy(true)
      const result = await api.generateSocialXReplyBlock(detail.id, {
        actor: 'agent',
        target_count: targetCount,
        agent_review: true,
        force_regenerate: forceRegenerate,
      })
      setReplyRegeneratePending(false)
      setDetail(result.asset)
      await loadTasks()
      toast.success(`X 回复候选已生成：${result.reply_ids.length} 条，失败 ${result.failed_reply_ids.length} 条`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '生成 X 回复候选失败')
    } finally {
      setBusy(false)
    }
  }

  async function generateXArticlePack() {
    if (!detail) return
    try {
      setBusy(true)
      const result = await api.generateSocialDistributionXArticlePack(detail.id, { actor: 'operator' })
      setDetail(result.asset)
      setSelectedAccountIds(result.asset.tasks.map((task) => task.account_id))
      await loadTasks()
      toast.success('X Article Pack 已生成：正文、封面和 Teaser 任务已准备')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '生成 X Article Pack 失败')
    } finally {
      setBusy(false)
    }
  }

  async function refreshOpenAsset() {
    if (!detail) return
    const nextDetail = await api.getSocialContentAsset(detail.id)
    setDetail(nextDetail)
  }

  async function markReplyManualPublished(reply: SocialReplyItem) {
    try {
      setBusy(true)
      await api.updateSocialReply(reply.id, {
        status: 'published_manual',
        reviewed_by: 'operator',
        review_note: 'Marked manually published from publishing reply task detail.',
      })
      await refreshOpenAsset()
      await loadTasks()
      toast.success('已标记为人工发布')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '标记人工发布失败')
    } finally {
      setBusy(false)
    }
  }

  async function publishReplyToX(reply: SocialReplyItem) {
    try {
      setBusy(true)
      await api.publishSocialReplyToX(reply.id, { actor: 'agent' })
      await refreshOpenAsset()
      await loadTasks()
      toast.success('已通过 X API 发布回复')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'X API 发布回复失败')
    } finally {
      setBusy(false)
    }
  }

  async function regenerateReply(reply: SocialReplyItem) {
    if (!reply.source_candidate_id) {
      toast.error('该候选缺少 source candidate，无法重新生成')
      return
    }
    try {
      setBusy(true)
      await api.generateSocialReplyForRepostCandidate(reply.source_candidate_id, { actor: 'agent' })
      await refreshOpenAsset()
      await loadTasks()
      toast.success('回复候选已重新生成')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '重新生成回复失败')
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

  async function auditPublishedPage(task: SocialDistributionTask) {
    try {
      const updated = await api.auditSocialDistributionPublishedPage(task.id, {
        visibility_status: auditVisibility,
        layout_status: auditLayout,
        audit_note: manualNote,
        actor: 'operator',
      })
      setTaskDetail(updated)
      if (detail) setDetail(await api.getSocialContentAsset(detail.id))
      await loadTasks()
      toast.success('页面状态审计已记录')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '记录页面审计失败')
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
      setBusy(true)
      setXAuthNotice(null)
      const auth = await api.getSocialDistributionTaskXAuthStatus(task.id)
      if (!auth.can_publish) {
        const message = auth.auth_message || 'X 授权不可用，请重新授权后再点击发送。'
        if (auth.requires_authorization) {
          const start = await api.startSocialXOAuth(auth.account_id)
          openExternalUrlInNewTab(start.auth_url)
          const notice = 'X 授权页已打开。完成授权后回到这里，再点击发送。'
          setXAuthNotice(notice)
          toast.success(notice)
          return
        }
        setXAuthNotice(message)
        toast.error(message)
        return
      }
      const updated = await api.publishSocialDistributionTaskToX(task.id, { actor: 'operator' })
      setTaskDetail(updated)
      if (detail) setDetail(await api.getSocialContentAsset(detail.id))
      await loadTasks()
      if (updated.status === 'live') {
        toast.success('已发布到 X')
        return
      }
      const reason = updated.failure_summary || updated.manual_result_note || 'X 发布未完成'
      toast.error(reason)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '发布到 X 失败')
    } finally {
      setBusy(false)
    }
  }
  async function reconnectX() {
    try {
      setXAuthNotice(null)
      const start = await api.startSocialXOAuth()
      openExternalUrlInNewTab(start.auth_url)
      toast.success('X 授权页已打开。完成授权后回到这里，点击“重新检查状态”。')
    } catch (error) {
      const message = formatXOAuthReconnectError(error)
      setXAuthNotice(message)
      toast.error(message)
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
  const visibleBoard = board ? filterBoardByKind(board, taskKindFilter) : null
  const xAuthStatus = Object.values(authStatuses).find((item) => item.platform === 'x')
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
          <button type="button" disabled={busy} className="rounded-xl border border-emerald-300/40 px-4 py-2 text-sm font-semibold text-emerald-100 disabled:opacity-50" onClick={() => void createXBrandWeekCampaign()}>
            {busy ? '处理中…' : '创建 X 品牌周任务'}
          </button>
          <button type="button" disabled={authStatusBusy} className="rounded-xl border border-cyan-300/40 px-4 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50" onClick={() => void checkAccountAuthStatuses()}>
            {authStatusBusy ? '检查中…' : '检查登录状态'}
          </button>
          <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={() => setShowCreate(true)}>创建内容计划</button>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => void loadTasks()}>刷新</button>
        </div>
      }
    >
      {!board ? <EmptyPane>分发看板加载中。</EmptyPane> : null}
      {board && board.summary.total_assets === 0 ? <EmptyPane>暂无内容计划。点击“创建内容计划”，把一篇源内容变成多平台分发工作项。</EmptyPane> : null}
      {board ? <TaskKindFilterControl value={taskKindFilter} onChange={setTaskKindFilter} /> : null}
      {visibleBoard ? <DistributionBoard board={visibleBoard} formatDateTime={formatDateTime} onOpen={(card) => void openAsset(card.asset.id)} /> : null}
      <OverlayModal open={showCreate} eyebrow="Content Plan" title="创建内容计划" description="输入一篇源内容或大纲；创建后自动生成方案，审核通过后再生成平台文档。" actions={<button type="button" disabled={busy} className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={() => void createTask()}>{busy ? '创建中…' : '创建'}</button>} onClose={() => setShowCreate(false)}>
        <ContentTaskForm form={form} onChange={setForm} />
      </OverlayModal>
      <ContentTaskDetailModal
        asset={detail}
        accounts={accounts}
        selectedAccountIds={selectedAccountIds}
        formatDateTime={formatDateTime}
        busy={busy}
        toast={toast}
        onToggleAccount={(id) => setSelectedAccountIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])}
        onClose={() => { setReplyRegeneratePending(false); setDetail(null) }}
        onGeneratePlan={() => void generatePlan()}
        onExpandCanonicalArticle={() => void expandCanonicalArticle()}
        onApproveCanonicalArticle={(documentId) => void approveCanonicalArticle(documentId)}
        onApproveGenerate={() => void approveAndGenerate()}
        onGenerateXArticlePack={() => void generateXArticlePack()}
        onGenerateXReplyBlock={() => void generateXReplyBlock()}
        onReconnectX={() => void reconnectX()}
        onCheckXAuth={() => void checkAccountAuthStatuses({ platform: 'x' })}
        onMarkReplyManualPublished={(reply) => void markReplyManualPublished(reply)}
        onPublishReplyToX={(reply) => void publishReplyToX(reply)}
        onRegenerateReply={(reply) => void regenerateReply(reply)}
        xAuthStatus={xAuthStatus}
        xAuthNotice={xAuthNotice}
        onOpenTask={(task) => {
          setTaskDetail(task)
          setManualUrl(task.published_url ?? '')
          setManualNote(task.manual_result_note ?? '')
          setAuditVisibility(stringValue(task.metadata.visibility_status) || 'visible')
          setAuditLayout(stringValue(task.metadata.layout_status) || 'passed')
          setXAuthNotice(null)
        }}
      />
      <ConfirmDialog open={replyRegeneratePending} title="重新生成 X 回复候选" description="已存在完整 X 回复候选。重新生成会刷新候选内容，但不会自动发布；候选仍会停在人工发布队列。" confirmLabel="重新生成候选" cancelLabel="取消" loading={busy} onConfirm={() => void generateXReplyBlock(true)} onClose={() => setReplyRegeneratePending(false)} />
      <TaskDetailModal
        task={taskDetail}
        manualUrl={manualUrl}
        manualNote={manualNote}
        toast={toast}
        onManualUrlChange={setManualUrl}
        onManualNoteChange={setManualNote}
        auditVisibility={auditVisibility}
        auditLayout={auditLayout}
        onAuditVisibilityChange={setAuditVisibility}
        onAuditLayoutChange={setAuditLayout}
        onClose={() => setTaskDetail(null)}
        onMarkLive={() => taskDetail ? void markLive(taskDetail) : undefined}
        onMarkRemoved={() => taskDetail ? void markRemoved(taskDetail) : undefined}
        onSkip={() => taskDetail ? void skipTask(taskDetail) : undefined}
        onAuditPublishedPage={() => taskDetail ? void auditPublishedPage(taskDetail) : undefined}
        onPublishX={() => taskDetail ? void publishX(taskDetail) : undefined}
        publishBusy={busy}
        xAuthNotice={xAuthNotice}
        authStatus={taskDetail ? authStatuses[taskDetail.account_id] : undefined}
        onCheckAuth={() => void checkAccountAuthStatuses()}
      />
    </SectionFrame>
  )
}

const stringValue = (value: unknown): string => (typeof value === 'string' ? value : '')

function numberValue(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  return typeof value === 'string' && value.trim() && Number.isFinite(Number(value)) ? Number(value) : 0
}

function targetPlatformsForForm(form: typeof DEFAULT_CONTENT_FORM): string[] {
  return ['x_article_pack', 'x_media_post', 'x_reply_block'].includes(form.task_type) ? ['x'] : form.target_platforms.split(',').map((item) => item.trim()).filter(Boolean)
}
