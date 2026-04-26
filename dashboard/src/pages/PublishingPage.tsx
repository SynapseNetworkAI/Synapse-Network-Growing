import { useEffect, useMemo, useRef, useState } from 'react'
import {
  api,
  type SocialAccount,
  type SocialCampaignGoal,
  type SocialOpsOverview,
  type SocialPostDraft,
  type SocialPostMetric,
  type SocialReplyItem,
  type SocialRepostCandidate,
  type SocialTrendItem,
  type SocialWatchlistAccount,
} from '../api'
import { ConfirmDialog, EmptyPane, OverlayModal, SectionFrame, StateBadge, useToast } from '../components/workbench'

const statusTabs = [
  { key: '', label: 'All' },
  { key: 'generating', label: 'Generating' },
  { key: 'draft', label: 'Drafts' },
  { key: 'needs_review', label: 'Needs Review' },
  { key: 'approved', label: 'Approved' },
  { key: 'published', label: 'Published' },
  { key: 'failed', label: 'Failed' },
]

const opsTabs = [
  { key: 'queue', label: '今日队列' },
  { key: 'trends', label: '趋势雷达' },
  { key: 'replies', label: '回帖处理' },
  { key: 'reposts', label: '转发候选' },
  { key: 'metrics', label: '已发布效果' },
  { key: 'rules', label: '品牌规则' },
] as const

type OpsTab = (typeof opsTabs)[number]['key']

type DraftForm = {
  accountId: string
  prompt: string
  styleType: string
  mediaMode: string
  title: string
  bodyText: string
}

const emptyForm: DraftForm = {
  accountId: '',
  prompt: '',
  styleType: 'marketing',
  mediaMode: 'auto',
  title: '',
  bodyText: '',
}

const pageSize = 8

function statusTone(status: string): 'default' | 'ready' | 'running' | 'blocked' | 'validating' | 'delivered' | 'muted' {
  if (status === 'published') return 'delivered'
  if (status === 'approved') return 'ready'
  if (status === 'failed' || status === 'rejected') return 'blocked'
  if (status === 'publishing' || status === 'generating') return 'running'
  return 'validating'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    draft: '草稿',
    generating: '生成中',
    needs_review: '待审核',
    approved: '可发布',
    publishing: '发布中',
    published: '已发布',
    failed: '失败',
    rejected: '已拒绝',
  }
  return map[status] ?? status
}

function canPublish(post: SocialPostDraft) {
  const activeMedia = (post.media_assets ?? []).filter((asset) => asset.status !== 'removed')
  return (post.status === 'approved' || post.status === 'failed') && post.policy_check.status === 'passed' && Boolean(post.body_text?.trim()) && activeMedia.every((asset) => asset.status === 'ready' || asset.status === 'uploaded')
}

function accountAuthorized(account: SocialAccount | undefined) {
  return account?.auth_status === 'authorized'
}

function publishActionLabel(post: SocialPostDraft | null) {
  return post?.status === 'failed' ? '重新发送' : '发布到 X'
}

function activeMediaAssets(post: SocialPostDraft | null) {
  return (post?.media_assets ?? []).filter((asset) => asset.status !== 'removed')
}

function mediaStatusLabel(status: string) {
  const map: Record<string, string> = {
    generating: '图片生成中',
    ready: '图片已生成',
    uploaded: '图片已上传',
    failed: '图片失败',
    removed: '已移除',
  }
  return map[status] ?? status
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function promptExcerpt(post: SocialPostDraft | null) {
  const rawOutput = post?.raw_agent_output ?? {}
  const direct = rawOutput.prompt_excerpt
  if (typeof direct === 'string' && direct.trim()) return direct
  const events = post?.events ?? []
  const eventPayload = [...events].reverse().find((event) => typeof event.payload?.prompt_excerpt === 'string')?.payload
  const eventPrompt = eventPayload?.prompt_excerpt
  return typeof eventPrompt === 'string' && eventPrompt.trim() ? eventPrompt : ''
}

export default function PublishingPage() {
  const toast = useToast()
  const [accounts, setAccounts] = useState<SocialAccount[]>([])
  const [posts, setPosts] = useState<SocialPostDraft[]>([])
  const [overview, setOverview] = useState<SocialOpsOverview | null>(null)
  const [campaignGoals, setCampaignGoals] = useState<SocialCampaignGoal[]>([])
  const [trends, setTrends] = useState<SocialTrendItem[]>([])
  const [watchlist, setWatchlist] = useState<SocialWatchlistAccount[]>([])
  const [replies, setReplies] = useState<SocialReplyItem[]>([])
  const [reposts, setReposts] = useState<SocialRepostCandidate[]>([])
  const [metrics, setMetrics] = useState<SocialPostMetric[]>([])
  const [opsTab, setOpsTab] = useState<OpsTab>('queue')
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<SocialPostDraft | null>(null)
  const [publishTarget, setPublishTarget] = useState<SocialPostDraft | null>(null)
  const [form, setForm] = useState<DraftForm>(emptyForm)
  const [savingDraft, setSavingDraft] = useState(false)
  const [page, setPage] = useState(1)
  const [selectedImageFile, setSelectedImageFile] = useState<File | null>(null)
  const [selectedImagePreview, setSelectedImagePreview] = useState<string | null>(null)
  const [selectedImageAltText, setSelectedImageAltText] = useState('')
  const generationPollRef = useRef<number | null>(null)
  const imageInputRef = useRef<HTMLInputElement | null>(null)

  const activeAccount = useMemo(() => accounts.find((account) => String(account.id) === form.accountId) ?? accounts[0], [accounts, form.accountId])
  const accountById = useMemo(() => new Map(accounts.map((account) => [account.id, account])), [accounts])
  const canSave = editing ? form.bodyText.trim().length > 0 : form.prompt.trim().length > 0
  const totalPages = Math.max(1, Math.ceil(posts.length / pageSize))
  const pagedPosts = posts.slice((page - 1) * pageSize, page * pageSize)

  async function load(nextFilter = filter) {
    setLoading(true)
    try {
      const [
        accountRows,
        postRows,
        overviewRow,
        goalRows,
        trendRows,
        watchlistRows,
        replyRows,
        repostRows,
        metricRows,
      ] = await Promise.all([
        api.getSocialAccounts(),
        api.getSocialPosts(nextFilter ? { status: nextFilter } : undefined),
        api.getSocialOpsOverview(),
        api.getSocialCampaignGoals(),
        api.getSocialTrends(),
        api.getSocialWatchlist(),
        api.getSocialReplies(),
        api.getSocialRepostCandidates(),
        api.getSocialPostMetrics(),
      ])
      setAccounts(accountRows)
      setPosts(postRows)
      setOverview(overviewRow)
      setCampaignGoals(goalRows)
      setTrends(trendRows)
      setWatchlist(watchlistRows)
      setReplies(replyRows)
      setReposts(repostRows)
      setMetrics(metricRows)
      if (!form.accountId && accountRows[0]) {
        setForm((current) => ({ ...current, accountId: String(accountRows[0].id) }))
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to load publishing drafts')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setPage(1)
    void load(filter)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter])

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages)
    }
  }, [page, totalPages])

  useEffect(() => {
    return () => {
      if (generationPollRef.current) {
        window.clearTimeout(generationPollRef.current)
      }
      if (selectedImagePreview) {
        URL.revokeObjectURL(selectedImagePreview)
      }
    }
  }, [selectedImagePreview])

  function clearSelectedImage() {
    if (selectedImagePreview) {
      URL.revokeObjectURL(selectedImagePreview)
    }
    setSelectedImageFile(null)
    setSelectedImagePreview(null)
    setSelectedImageAltText('')
    if (imageInputRef.current) {
      imageInputRef.current.value = ''
    }
  }

  function selectImageFile(file: File | null) {
    if (!file) return
    if (!file.type.startsWith('image/')) {
      toast.error('只能上传图片文件')
      return
    }
    if (file.size > 8 * 1024 * 1024) {
      toast.error('图片不能超过 8MB')
      return
    }
    if (selectedImagePreview) {
      URL.revokeObjectURL(selectedImagePreview)
    }
    setSelectedImageFile(file)
    setSelectedImagePreview(URL.createObjectURL(file))
    setSelectedImageAltText((current) => current || 'Synapse Network X post image')
  }

  async function uploadSelectedImage(post: SocialPostDraft) {
    if (!selectedImageFile) return post
    const updated = await api.uploadSocialPostImage(post.id, selectedImageFile, {
      actor: 'operator',
      alt_text: selectedImageAltText || 'Synapse Network X post image',
    })
    clearSelectedImage()
    return updated
  }

  function openCreateModal() {
    setEditing(null)
    clearSelectedImage()
    setForm({ ...emptyForm, accountId: accounts[0] ? String(accounts[0].id) : '' })
    setModalOpen(true)
  }

  function openEditModal(post: SocialPostDraft) {
    if (post.status === 'generating') {
      toast.info('Agent 仍在生成草稿，完成后才能编辑。')
      return
    }
    setEditing(post)
    clearSelectedImage()
    setForm({
      accountId: String(post.account_id),
      prompt: '',
      styleType: typeof post.raw_agent_output?.style_type === 'string' ? post.raw_agent_output.style_type : 'marketing',
      mediaMode: typeof post.raw_agent_output?.media_mode === 'string' ? post.raw_agent_output.media_mode : 'auto',
      title: post.title ?? '',
      bodyText: post.body_text,
    })
    setModalOpen(true)
  }

  async function pollGeneration(postId: number, attemptsRemaining = 60) {
    if (generationPollRef.current) {
      window.clearTimeout(generationPollRef.current)
    }
    generationPollRef.current = window.setTimeout(async () => {
      try {
        const postRows = await api.getSocialPosts()
        setPosts(postRows)
        const row = postRows.find((post) => post.id === postId)
        if (row && row.status !== 'generating') {
          generationPollRef.current = null
          if (row.status === 'approved') {
            toast.success('Agent 已生成标题和正文，可检查后发布到 X')
          } else if (row.status === 'failed') {
            toast.error(row.failure_summary || 'Agent 生成失败')
          }
          return
        }
        if (attemptsRemaining > 1) {
          void pollGeneration(postId, attemptsRemaining - 1)
        } else {
          generationPollRef.current = null
        }
      } catch (error) {
        generationPollRef.current = null
        toast.error(error instanceof Error ? error.message : '刷新生成状态失败')
      }
    }, 2000)
  }

  async function connectXAccount(accountId?: number | null) {
    try {
      const result = await api.startSocialXOAuth(accountId)
      window.open(result.auth_url, '_blank', 'noopener,noreferrer')
      toast.info('已打开 X 授权页面，授权完成后回到本页刷新。')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '无法启动 X 授权')
    }
  }

  async function saveDraft() {
    if (savingDraft) return
    setSavingDraft(true)
    try {
      if (editing) {
        let updated = await api.updateSocialPost(editing.id, {
          title: form.title,
          body_text: form.bodyText,
          status: 'approved',
          reviewed_by: 'operator',
        })
        updated = await uploadSelectedImage(updated)
        setEditing(updated)
        setPosts((current) => current.map((item) => (item.id === updated.id ? updated : item)))
        toast.success('草稿已更新')
      } else {
        const queued = await api.generateSocialPostDraft({
          account_id: activeAccount?.id ?? null,
          prompt: form.prompt,
          style_type: form.styleType,
          media_mode: selectedImageFile ? 'text_only' : form.mediaMode,
          actor: 'operator',
        })
        if (selectedImageFile) {
          await uploadSelectedImage(queued)
        }
        toast.success('已保存，Agent 正在生成草稿')
        setFilter('')
        void pollGeneration(queued.id)
      }
      setModalOpen(false)
      await load(editing ? filter : '')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存草稿失败')
    } finally {
      setSavingDraft(false)
    }
  }

  async function rejectPost(post: SocialPostDraft) {
    if (busyId) return
    setBusyId(post.id)
    try {
      await api.updateSocialPost(post.id, { status: 'rejected', reviewed_by: 'operator' })
      toast.success('已拒绝')
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '操作失败')
    } finally {
      setBusyId(null)
    }
  }

  async function publishToX() {
    if (!publishTarget || busyId) return
    setBusyId(publishTarget.id)
    try {
      const updated = await api.publishSocialPostToX(publishTarget.id, { actor: 'operator' })
      setPosts((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      if (updated.status === 'published') {
        toast.success('已发布到 X')
      } else if (updated.status === 'failed') {
        toast.error(updated.failure_summary || '发送失败，请修复后重新发送')
      } else {
        toast.info(`发布请求已记录，当前状态：${statusLabel(updated.status)}`)
      }
      setPublishTarget(null)
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '发布失败')
    } finally {
      setBusyId(null)
    }
  }

  async function regenerateImage(post: SocialPostDraft) {
    if (busyId) return
    setBusyId(post.id)
    try {
      const updated = await api.regenerateSocialPostImage(post.id, { actor: 'operator' })
      setEditing(updated)
      setPosts((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      toast.success('图片已重新生成')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '重新生成图片失败')
    } finally {
      setBusyId(null)
    }
  }

  async function removeImage(post: SocialPostDraft, mediaId: number) {
    if (busyId) return
    setBusyId(post.id)
    try {
      const updated = await api.removeSocialPostMedia(post.id, mediaId)
      setEditing(updated)
      setPosts((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      toast.success('图片已移除')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '移除图片失败')
    } finally {
      setBusyId(null)
    }
  }

  function imageUploadControl(label = '手动上传图片') {
    return (
      <div
        className="mt-4 rounded-2xl border border-dashed border-cyan-300/25 bg-cyan-300/[0.04] p-4"
        onPaste={(event) => {
          const file = Array.from(event.clipboardData.files).find((item) => item.type.startsWith('image/')) ?? null
          if (file) {
            event.preventDefault()
            selectImageFile(file)
          }
        }}
        onDrop={(event) => {
          event.preventDefault()
          const file = Array.from(event.dataTransfer.files).find((item) => item.type.startsWith('image/')) ?? null
          selectImageFile(file)
        }}
        onDragOver={(event) => event.preventDefault()}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{label}</div>
            <div className="mt-1 text-xs leading-5 text-[color:var(--ops-text-muted)]">支持选择文件、拖拽，或直接复制图片后在此区域粘贴。最多 8MB，v1 只保留一张活动图片。</div>
          </div>
          <button type="button" className="rounded-xl border border-cyan-300/35 px-3 py-2 text-sm text-cyan-100" onClick={() => imageInputRef.current?.click()}>
            选择图片
          </button>
        </div>
        <input
          ref={imageInputRef}
          type="file"
          accept="image/*"
          aria-label="选择图片文件"
          className="hidden"
          onChange={(event) => selectImageFile(event.target.files?.[0] ?? null)}
        />
        {selectedImagePreview ? (
          <div className="mt-4 grid gap-3 md:grid-cols-[160px_1fr]">
            <img src={selectedImagePreview} alt="Selected upload preview" className="h-36 w-full rounded-xl object-cover" />
            <div className="space-y-3">
              <label className="block text-sm">
                <span className="text-[color:var(--ops-text-muted)]">图片 alt text</span>
                <input
                  className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-3 py-2"
                  value={selectedImageAltText}
                  onChange={(event) => setSelectedImageAltText(event.target.value)}
                />
              </label>
              <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={clearSelectedImage}>
                移除待上传图片
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-4 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-sm text-[color:var(--ops-text-caption)]">
            当前没有选择待上传图片。
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <SectionFrame
        eyebrow="Social Publishing"
        title="官方账号内容发布"
        description="输入 Prompt，Agent 生成 X 标题、正文和可选配图；公开发布必须由人类点击确认。v1 支持 @SynapseNetworkA 单条图文 Post。"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {activeAccount ? (
              accountAuthorized(activeAccount) ? (
                <span className="rounded-xl border border-emerald-300/25 bg-emerald-300/10 px-3 py-2 text-sm text-emerald-100">X 已授权</span>
              ) : (
                <button type="button" className="rounded-xl border border-amber-300/35 px-4 py-2 text-sm font-semibold text-amber-100" onClick={() => void connectXAccount(activeAccount.id)}>
                  连接 X 官方账号
                </button>
              )
            ) : null}
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => load()}>
              刷新
            </button>
            <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={openCreateModal}>
              让 Agent 写草稿
            </button>
          </div>
        }
      >
        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
              <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Active Goals</div>
              <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{overview?.active_goal_count ?? '-'}</div>
            </div>
            <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
              <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Draft Queue</div>
              <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{overview?.draft_queue_count ?? '-'}</div>
            </div>
            <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
              <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Signals</div>
              <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{(overview?.trend_count ?? 0) + (overview?.reply_needs_review_count ?? 0) + (overview?.repost_candidate_count ?? 0)}</div>
            </div>
            <div className="rounded-3xl border border-amber-300/25 bg-amber-300/10 p-4">
              <div className="text-[10px] uppercase tracking-[0.18em] text-amber-100/80">Human Gate</div>
              <div className="mt-2 text-sm leading-6 text-amber-100">发布、回复、引用转发、删除均需人类确认。</div>
            </div>
          </div>
          {activeAccount && !accountAuthorized(activeAccount) ? (
            <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 px-4 py-3 text-sm leading-6 text-amber-100">
              X 官方账号未完成 OAuth2 授权：{activeAccount.auth_message || '需要连接 @SynapseNetworkA 后才能发布或重新发送。'}
            </div>
          ) : null}
          {campaignGoals[0] ? (
            <div className="rounded-3xl border border-cyan-300/20 bg-cyan-300/[0.08] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.18em] text-cyan-100/70">Current Campaign Goal</div>
                  <div className="mt-2 text-lg font-semibold text-[color:var(--ops-text-title)]">{campaignGoals[0].title}</div>
                  <div className="mt-1 max-w-4xl text-sm leading-6 text-[color:var(--ops-text-muted)]">{campaignGoals[0].objective}</div>
                </div>
                <StateBadge tone="ready">{campaignGoals[0].cadence}</StateBadge>
              </div>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {opsTabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                className={[
                  'rounded-full border px-4 py-2 text-sm transition',
                  opsTab === tab.key
                    ? 'border-cyan-300/40 bg-cyan-300/14 text-cyan-100'
                    : 'border-[color:var(--ops-stroke-soft)] text-[color:var(--ops-text-muted)] hover:bg-white/[0.04]',
                ].join(' ')}
                onClick={() => setOpsTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>
          {opsTab === 'queue' ? (
            <div className="flex flex-wrap gap-2">
              {statusTabs.map((tab) => (
                <button
                  key={tab.key || 'all'}
                  type="button"
                  className={[
                    'rounded-full border px-4 py-2 text-sm transition',
                    filter === tab.key
                      ? 'border-cyan-300/40 bg-cyan-300/14 text-cyan-100'
                      : 'border-[color:var(--ops-stroke-soft)] text-[color:var(--ops-text-muted)] hover:bg-white/[0.04]',
                  ].join(' ')}
                  onClick={() => setFilter(tab.key)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </SectionFrame>

      {opsTab === 'queue' ? <SectionFrame
        eyebrow="Review Queue"
        title="内容草稿"
        description="列表只展示标题、状态、字符数和风险检查；详情和调试信息收进编辑或 Debug。"
      >
        {loading ? <EmptyPane>正在加载内容草稿...</EmptyPane> : null}
        {!loading && posts.length === 0 ? <EmptyPane>当前没有内容草稿。可以先新建一条，或让 Agent 在工作流里生成候选内容。</EmptyPane> : null}
        {!loading && posts.length > 0 ? (
          <div className="overflow-hidden rounded-[24px] border border-[color:var(--ops-stroke-soft)]">
            <table className="w-full min-w-[860px] border-collapse text-left text-sm">
              <thead className="bg-[color:var(--ops-panel-subtle)] text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                <tr>
                  <th className="px-5 py-4 font-medium">标题</th>
                  <th className="px-5 py-4 font-medium">状态</th>
                  <th className="px-5 py-4 font-medium">风险 / 字符</th>
                  <th className="px-5 py-4 font-medium">更新</th>
                  <th className="px-5 py-4 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[color:var(--ops-stroke-soft)]">
                {pagedPosts.map((post) => {
                  const postAccount = accountById.get(post.account_id)
                  return (
                  <tr key={post.id} className="bg-[color:var(--ops-workspace-bg)] align-top">
                    <td className="max-w-[420px] px-5 py-4">
                      <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">X · @{post.account_handle ?? 'SynapseNetworkA'}</div>
                      <div className="mt-1 font-semibold text-[color:var(--ops-text-title)]">{post.title || `X draft #${post.id}`}</div>
                      <div className="mt-2 line-clamp-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">
                        {post.status === 'generating' && !post.body_text ? 'Agent 正在生成标题和正文...' : post.body_text}
                      </div>
                      {activeMediaAssets(post)[0] ? (
                        <div className="mt-3 flex items-center gap-3 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-2">
                          {activeMediaAssets(post)[0].preview_url && activeMediaAssets(post)[0].status !== 'failed' ? (
                            <img
                              src={activeMediaAssets(post)[0].preview_url ?? ''}
                              alt={activeMediaAssets(post)[0].alt_text ?? 'Generated X image preview'}
                              className="h-14 w-14 rounded-xl object-cover"
                            />
                          ) : (
                            <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-[color:var(--ops-panel-strong)] text-[10px] text-[color:var(--ops-text-caption)]">
                              image
                            </div>
                          )}
                          <div className="min-w-0 text-xs">
                            <div className="font-semibold text-[color:var(--ops-text-body)]">{mediaStatusLabel(activeMediaAssets(post)[0].status)}</div>
                            {activeMediaAssets(post)[0].failure_summary ? <div className="mt-1 line-clamp-1 text-rose-200">{activeMediaAssets(post)[0].failure_summary}</div> : null}
                          </div>
                        </div>
                      ) : null}
                      {post.external_post_id ? (
                        <a className="mt-2 inline-flex text-xs font-semibold text-cyan-100 underline" href={post.external_url ?? '#'} target="_blank" rel="noreferrer">
                          Open on X · {post.external_post_id}
                        </a>
                      ) : null}
                    </td>
                    <td className="px-5 py-4">
                      <StateBadge tone={statusTone(post.status)}>{statusLabel(post.status)}</StateBadge>
                      <div className="mt-2 text-xs text-[color:var(--ops-text-muted)]">Generated by {post.generated_by}</div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="text-[color:var(--ops-text-body)]">{post.status === 'generating' ? 'running' : post.policy_check.status}</div>
                      <div className="mt-1 text-xs text-[color:var(--ops-text-muted)]">{post.policy_check.character_count} chars</div>
                      {post.policy_check.status === 'blocked' ? <div className="mt-1 max-w-[260px] text-xs text-rose-200">Blocked: {post.policy_check.blocked_reasons.join(', ')}</div> : null}
                      {activeMediaAssets(post).some((asset) => asset.status === 'failed') ? <div className="mt-1 max-w-[260px] text-xs text-rose-200">Image failed: {activeMediaAssets(post).find((asset) => asset.status === 'failed')?.failure_summary ?? 'regenerate or remove image'}</div> : null}
                      {post.failure_summary ? <div className="mt-1 max-w-[260px] text-xs text-rose-200">{post.failure_summary}</div> : null}
                    </td>
                    <td className="px-5 py-4 text-xs text-[color:var(--ops-text-muted)]">{formatDateTime(post.updated_at)}</td>
                    <td className="px-5 py-4">
                      <div className="flex flex-wrap justify-end gap-2">
                        <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-40" disabled={post.status === 'generating'} onClick={() => openEditModal(post)}>
                          编辑
                        </button>
                        {post.status !== 'published' && post.status !== 'rejected' && post.status !== 'generating' ? (
                          <button type="button" className="rounded-xl border border-rose-300/30 px-3 py-2 text-sm text-rose-100" disabled={busyId === post.id} onClick={() => rejectPost(post)}>
                            拒绝
                          </button>
                        ) : null}
                        {canPublish(post) && accountAuthorized(postAccount) ? (
                          <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={busyId === post.id} onClick={() => setPublishTarget(post)}>
                            {publishActionLabel(post)}
                          </button>
                        ) : null}
                        {canPublish(post) && !accountAuthorized(postAccount) ? (
                          <button type="button" className="rounded-xl border border-amber-300/35 px-3 py-2 text-sm font-semibold text-amber-100" onClick={() => void connectXAccount(post.account_id)}>
                            连接 X 官方账号
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                  )
                })}
              </tbody>
            </table>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]">
              <span>第 {page} / {totalPages} 页 · 共 {posts.length} 条草稿</span>
              <div className="flex gap-2">
                <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>
                  上一页
                </button>
                <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={page >= totalPages} onClick={() => setPage((current) => Math.min(totalPages, current + 1))}>
                  下一页
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </SectionFrame> : null}

      {opsTab === 'trends' ? (
        <SectionFrame
          eyebrow="Trend Radar"
          title="趋势雷达"
          description="只读采集 AI / agent / API / payment 相关热点，保留来源链接；Agent 只能摘要和推荐跟进，不会自动互动。"
        >
          <div className="grid gap-4 lg:grid-cols-[1fr_0.8fr]">
            <div className="space-y-3">
              {trends.length === 0 ? <EmptyPane>暂无趋势素材。后续由 social_trend_radar_sweep 只读采集。</EmptyPane> : null}
              {trends.map((trend) => (
                <div key={trend.id} className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="font-semibold text-[color:var(--ops-text-title)]">{trend.topic}</div>
                    <StateBadge tone="validating">score {Math.round(trend.relevance_score * 100)}</StateBadge>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{trend.summary}</p>
                  {trend.source_url ? <a className="mt-3 inline-flex text-xs font-semibold text-cyan-100 underline" href={trend.source_url} target="_blank" rel="noreferrer">打开来源</a> : null}
                </div>
              ))}
            </div>
            <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
              <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">Watchlist</div>
              <div className="mt-3 space-y-3">
                {watchlist.map((account) => (
                  <div key={account.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-3">
                    <div className="font-semibold text-[color:var(--ops-text-body)]">@{account.handle}</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-muted)]">{account.category} · {account.rationale}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </SectionFrame>
      ) : null}

      {opsTab === 'replies' ? (
        <SectionFrame
          eyebrow="Reply Inbox"
          title="回帖处理"
          description="系统可以生成回复草稿，但公开回复必须由人类确认；v1 不做自动回复。"
        >
          {replies.length === 0 ? <EmptyPane>暂无待处理回帖。接入 X read 权限后，social_reply_inbox_sweep 会把 mention/reply 转为审核项。</EmptyPane> : null}
          <div className="grid gap-4 md:grid-cols-2">
            {replies.map((reply) => (
              <div key={reply.id} className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">@{reply.author_handle ?? 'unknown'}</div>
                  <StateBadge tone={reply.risk_level === 'high' ? 'blocked' : 'validating'}>{reply.intent}</StateBadge>
                </div>
                <p className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">{reply.incoming_text}</p>
                <div className="mt-3 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-3 text-sm leading-6 text-[color:var(--ops-text-body)]">
                  {reply.suggested_reply || 'Agent 尚未生成回复草稿。'}
                </div>
              </div>
            ))}
          </div>
        </SectionFrame>
      ) : null}

      {opsTab === 'reposts' ? (
        <SectionFrame
          eyebrow="Repost Candidates"
          title="转发 / 引用候选"
          description="推荐品牌相关的高质量 X 内容；Agent 只拟引用文案，人类点击后才会引用转发。"
        >
          {reposts.length === 0 ? <EmptyPane>暂无转发候选。后续由 social_repost_candidate_sweep 从趋势和 watchlist 中生成。</EmptyPane> : null}
          <div className="grid gap-4 md:grid-cols-2">
            {reposts.map((candidate) => (
              <div key={candidate.id} className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">@{candidate.author_handle ?? 'unknown'}</div>
                  <StateBadge tone="validating">fit {Math.round(candidate.relevance_score * 100)}</StateBadge>
                </div>
                <p className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">{candidate.source_text}</p>
                <div className="mt-3 rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.08] p-3 text-sm leading-6 text-cyan-50">
                  {candidate.suggested_quote || 'Agent 尚未生成引用文案。'}
                </div>
                {candidate.source_url ? <a className="mt-3 inline-flex text-xs font-semibold text-cyan-100 underline" href={candidate.source_url} target="_blank" rel="noreferrer">查看原帖</a> : null}
              </div>
            ))}
          </div>
        </SectionFrame>
      ) : null}

      {opsTab === 'metrics' ? (
        <SectionFrame
          eyebrow="Published & Metrics"
          title="已发布效果"
          description="发布后观察 impressions、互动、链接点击和高质量回复，用于反哺下一轮内容 planner。"
        >
          {metrics.length === 0 ? <EmptyPane>暂无发布效果记录。发布成功后，social_post_observer_sweep 会拉取 1h / 24h 指标。</EmptyPane> : null}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {metrics.map((metric) => (
              <div key={metric.id} className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Post {metric.external_post_id ?? metric.post_id ?? '-'}</div>
                <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                  <div><span className="text-[color:var(--ops-text-caption)]">Impressions</span><div className="font-semibold">{metric.impressions}</div></div>
                  <div><span className="text-[color:var(--ops-text-caption)]">Likes</span><div className="font-semibold">{metric.likes}</div></div>
                  <div><span className="text-[color:var(--ops-text-caption)]">Replies</span><div className="font-semibold">{metric.replies}</div></div>
                  <div><span className="text-[color:var(--ops-text-caption)]">Clicks</span><div className="font-semibold">{metric.link_clicks}</div></div>
                </div>
                {metric.summary ? <p className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">{metric.summary}</p> : null}
              </div>
            ))}
          </div>
        </SectionFrame>
      ) : null}

      {opsTab === 'rules' ? (
        <SectionFrame
          eyebrow="Brand Rules"
          title="品牌与安全规则"
          description="这些规则是 Social Ops 的硬边界：Agent 可以写稿和分析，但不能代表官方账号自动行动。"
        >
          <div className="grid gap-4 md:grid-cols-2">
            {[
              ['Human Gate', '发布、回复、引用转发、删除 X 内容都必须由 operator 明确点击确认。'],
              ['Official API First', '生产链路优先使用官方 X API；浏览器 / Cookie 自动化不是默认方案。'],
              ['Read-only Trends', '趋势采集、watchlist 和爆款摘要只能读取和归档，不自动点赞、关注、回复或转发。'],
              ['No Secret Leakage', '任何 token、secret、本地路径、workflow JSON 或 acceptance matrix 泄露都会 Fail Closed。'],
              ['Brand Trust', '内容必须解释 Synapse Network 的产品价值、开发者收益和安全边界，避免夸大收益承诺。'],
              ['Metrics Loop', '发布效果只用于改进下一轮内容建议，不作为自动发布授权。'],
            ].map(([title, body]) => (
              <div key={title} className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
                <div className="font-semibold text-[color:var(--ops-text-title)]">{title}</div>
                <p className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{body}</p>
              </div>
            ))}
          </div>
        </SectionFrame>
      ) : null}

      <OverlayModal
        open={modalOpen}
        eyebrow="X official account"
        title={editing ? '编辑内容草稿' : '让 Agent 写草稿'}
        description={editing ? '这里只编辑标题和正文，不会发布到 X。' : '输入 Prompt，Agent 会生成标题和正文；发布仍需人工确认点击。'}
        onClose={() => {
          if (!savingDraft) setModalOpen(false)
        }}
        actions={
          <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={!canSave || savingDraft} onClick={saveDraft}>
            {savingDraft ? (editing ? '保存中...' : '生成中...') : editing ? '保存草稿' : '生成草稿'}
          </button>
        }
      >
        <div className="space-y-4">
          <label className="block text-sm">
            <span className="text-[color:var(--ops-text-muted)]">账号</span>
            <select className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3" value={form.accountId} onChange={(event) => setForm((current) => ({ ...current, accountId: event.target.value }))}>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  @{account.handle} · {account.display_name || account.platform}
                </option>
              ))}
            </select>
          </label>
          {!editing ? (
            <>
              <label className="block text-sm">
                <span className="text-[color:var(--ops-text-muted)]">内容风格</span>
                <select
                  aria-label="内容风格"
                  className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3"
                  value={form.styleType}
                  onChange={(event) => setForm((current) => ({ ...current, styleType: event.target.value }))}
                >
                  <option value="marketing">Marketing · 品牌信任和产品价值</option>
                  <option value="technical">Technical · 技术可信和开发者价值</option>
                  <option value="visionary">Visionary · Agent 经济愿景</option>
                </select>
              </label>
              <label className="block text-sm">
                <span className="text-[color:var(--ops-text-muted)]">媒体策略</span>
                <select
                  aria-label="媒体策略"
                  className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3"
                  value={form.mediaMode}
                  onChange={(event) => setForm((current) => ({ ...current, mediaMode: event.target.value }))}
                >
                  <option value="auto">Agent 决定 · 需要时生成一张图</option>
                  <option value="text_only">纯文字 · 不生成图片</option>
                  <option value="image_required">必须配图 · 生成一张图片</option>
                </select>
              </label>
              {imageUploadControl('手动配图（可选）')}
              <label className="block text-sm">
                <span className="text-[color:var(--ops-text-muted)]">目标 / Prompt</span>
                <textarea
                  aria-label="目标 / Prompt"
                  className="mt-2 min-h-40 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3"
                  placeholder="例如：发布 staging 自动发布链路已经跑通，强调 PR checks、人审、staging deploy 和上线记录。语气专业、克制。"
                  value={form.prompt}
                  onChange={(event) => setForm((current) => ({ ...current, prompt: event.target.value }))}
                />
                <span className="mt-1 block text-xs text-[color:var(--ops-text-caption)]">Agent 只生成可检查草稿，不会发布到 X；v1 最多生成一张图片，不生成视频、GIF 或 thread。</span>
              </label>
            </>
          ) : (
            <>
              <label className="block text-sm">
                <span className="text-[color:var(--ops-text-muted)]">标题</span>
                <input className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3" value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
              </label>
              <label className="block text-sm">
                <span className="text-[color:var(--ops-text-muted)]">目标 / Prompt</span>
                <textarea
                  aria-label="目标 / Prompt"
                  className="mt-2 min-h-28 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-[color:var(--ops-text-muted)]"
                  value={promptExcerpt(editing) || '此草稿没有保存原始 Prompt。'}
                  readOnly
                />
                <span className="mt-1 block text-xs text-[color:var(--ops-text-caption)]">只读：用于回看 Agent 生成目标，不会随正文编辑改变。</span>
              </label>
              <label className="block text-sm">
                <span className="text-[color:var(--ops-text-muted)]">最终发布正文</span>
                <textarea aria-label="最终发布正文" className="mt-2 min-h-40 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3" value={form.bodyText} onChange={(event) => setForm((current) => ({ ...current, bodyText: event.target.value }))} />
                <span className="mt-1 block text-xs text-[color:var(--ops-text-caption)]">{form.bodyText.length} chars</span>
              </label>
              <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">图片资产</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-muted)]">v1 只支持单张图片；图片失败时不会降级成纯文字发布。</div>
                  </div>
                  {editing ? (
                    <button
                      type="button"
                      className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-40"
                      disabled={busyId === editing.id}
                      onClick={() => regenerateImage(editing)}
                    >
                      重新生成图片
                    </button>
                  ) : null}
                </div>
                {activeMediaAssets(editing).length === 0 ? (
                  <div className="mt-4 rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] px-4 py-5 text-sm text-[color:var(--ops-text-muted)]">
                    这条草稿当前没有配图。
                  </div>
                ) : (
                  <div className="mt-4 space-y-3">
                    {activeMediaAssets(editing).map((asset) => (
                      <div key={asset.id} className="grid gap-4 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-3 md:grid-cols-[160px_1fr]">
                        {asset.preview_url && asset.status !== 'failed' ? (
                          <img src={asset.preview_url} alt={asset.alt_text ?? 'Generated X image preview'} className="h-40 w-full rounded-xl object-cover" />
                        ) : (
                          <div className="flex h-40 items-center justify-center rounded-xl bg-[color:var(--ops-panel-strong)] text-xs text-[color:var(--ops-text-caption)]">
                            {mediaStatusLabel(asset.status)}
                          </div>
                        )}
                        <div className="min-w-0 space-y-2 text-sm">
                          <StateBadge tone={asset.status === 'failed' ? 'blocked' : asset.status === 'generating' ? 'running' : 'ready'}>{mediaStatusLabel(asset.status)}</StateBadge>
                          <div>
                            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Alt text</div>
                            <div className="mt-1 text-[color:var(--ops-text-body)]">{asset.alt_text || '-'}</div>
                          </div>
                          {asset.failure_summary ? <div className="rounded-xl border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-xs text-rose-100">{asset.failure_summary}</div> : null}
                          {editing ? (
                            <button
                              type="button"
                              className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-40"
                              disabled={busyId === editing.id}
                              onClick={() => removeImage(editing, asset.id)}
                            >
                              移除图片
                            </button>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {imageUploadControl('上传替换图片')}
              </div>
            </>
          )}
          <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 px-4 py-3 text-sm leading-6 text-amber-100">
            发布前确认：这会代表 @SynapseNetworkA 公开发布内容到 X。确认后不可由系统自动撤回。
          </div>
        </div>
      </OverlayModal>

      <ConfirmDialog
        open={Boolean(publishTarget)}
        title="确认发布到 X"
        description={
          activeMediaAssets(publishTarget).length > 0
            ? `这会代表 @SynapseNetworkA 公开发布内容到 X，并附带 ${activeMediaAssets(publishTarget).length} 张图片。确认后不可由系统自动撤回。`
            : '这会代表 @SynapseNetworkA 公开发布内容到 X。确认后不可由系统自动撤回。'
        }
        confirmLabel={publishActionLabel(publishTarget)}
        loading={Boolean(publishTarget && busyId === publishTarget.id)}
        onConfirm={publishToX}
        onClose={() => setPublishTarget(null)}
      />
    </div>
  )
}
