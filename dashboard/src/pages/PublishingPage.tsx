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
  if (status === 'published' || status === 'replied') return 'delivered'
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
    replied: '已回帖',
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

function gcpAdcExpired(account: SocialAccount | undefined) {
  const message = `${account?.auth_message ?? ''}`.toLowerCase()
  return account?.auth_status === 'gcp_adc_expired' || message.includes('application-default login') || message.includes('reauthentication is needed')
}

function needsXReconnect(post: SocialPostDraft) {
  const reason = `${post.failure_summary ?? ''} ${(post.media_assets ?? []).map((asset) => asset.failure_summary ?? '').join(' ')}`.toLowerCase()
  return (
    post.status === 'failed' &&
    (reason.includes('oauth') ||
      reason.includes('authentication failed') ||
      reason.includes('media.write') ||
      reason.includes('reconnect the x official account') ||
      reason.includes('token secret'))
  )
}

function postSortRank(post: SocialPostDraft) {
  const ranks: Record<string, number> = {
    publishing: 0,
    generating: 1,
    approved: 2,
    failed: 3,
    needs_review: 4,
    draft: 5,
    published: 8,
    rejected: 9,
  }
  return ranks[post.status] ?? 6
}

function signalStatusTone(status: string): 'default' | 'ready' | 'running' | 'blocked' | 'validating' | 'delivered' | 'muted' {
  if (status === 'published') return 'delivered'
  if (status === 'publishing') return 'running'
  if (status === 'failed' || status === 'rejected') return 'blocked'
  if (status === 'candidate' || status === 'needs_review') return 'ready'
  return 'validating'
}

function repostStatusLabel(status: string) {
  const map: Record<string, string> = {
    candidate: '候选',
    needs_review: '待审核',
    publishing: '发布中',
    published: '已发布',
    failed: '失败',
    rejected: '已拒绝',
  }
  return map[status] ?? status
}

function replyStatusLabel(status: string) {
  const map: Record<string, string> = {
    needs_review: '待审核',
    approved: '可回复',
    publishing: '回复中',
    published: '已回复',
    failed: '失败',
    rejected: '已拒绝',
  }
  return map[status] ?? status
}

function replySortRank(reply: SocialReplyItem) {
  const ranks: Record<string, number> = {
    publishing: 0,
    approved: 1,
    needs_review: 2,
    failed: 3,
    published: 8,
    rejected: 9,
  }
  return ranks[reply.status] ?? 5
}

function repostSortRank(candidate: SocialRepostCandidate) {
  const ranks: Record<string, number> = {
    publishing: 0,
    candidate: 1,
    needs_review: 1,
    failed: 2,
    replied: 7,
    published: 8,
    rejected: 9,
  }
  return ranks[candidate.status] ?? 5
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

function compactJson(value: unknown) {
  if (!value || (typeof value === 'object' && Object.keys(value as Record<string, unknown>).length === 0)) {
    return '{}'
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
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
  const [detailPost, setDetailPost] = useState<SocialPostDraft | null>(null)
  const [detailLoadingId, setDetailLoadingId] = useState<number | null>(null)
  const [publishTarget, setPublishTarget] = useState<SocialPostDraft | null>(null)
  const [form, setForm] = useState<DraftForm>(emptyForm)
  const [savingDraft, setSavingDraft] = useState(false)
  const [page, setPage] = useState(1)
  const [trendPage, setTrendPage] = useState(1)
  const [watchlistPage, setWatchlistPage] = useState(1)
  const [repostPage, setRepostPage] = useState(1)
  const [repostDetail, setRepostDetail] = useState<SocialRepostCandidate | null>(null)
  const [repostPublishTarget, setRepostPublishTarget] = useState<SocialRepostCandidate | null>(null)
  const [repostPublishAction, setRepostPublishAction] = useState<'quote' | 'repost'>('quote')
  const [repostBusyId, setRepostBusyId] = useState<number | null>(null)
  const [replyPage, setReplyPage] = useState(1)
  const [replyDetail, setReplyDetail] = useState<SocialReplyItem | null>(null)
  const [replyDraftText, setReplyDraftText] = useState('')
  const [replyPublishTarget, setReplyPublishTarget] = useState<SocialReplyItem | null>(null)
  const [replyBusyId, setReplyBusyId] = useState<number | null>(null)
  const [selectedImageFile, setSelectedImageFile] = useState<File | null>(null)
  const [selectedImagePreview, setSelectedImagePreview] = useState<string | null>(null)
  const [selectedImageAltText, setSelectedImageAltText] = useState('')
  const generationPollRef = useRef<number | null>(null)
  const imageInputRef = useRef<HTMLInputElement | null>(null)

  const activeAccount = useMemo(() => accounts.find((account) => String(account.id) === form.accountId) ?? accounts[0], [accounts, form.accountId])
  const accountById = useMemo(() => new Map(accounts.map((account) => [account.id, account])), [accounts])
  const canSave = editing ? form.bodyText.trim().length > 0 : form.prompt.trim().length > 0
  const sortedPosts = useMemo(
    () =>
      [...posts].sort((left, right) => {
        const rankDelta = postSortRank(left) - postSortRank(right)
        if (rankDelta !== 0) return rankDelta
        return new Date(right.updated_at ?? 0).getTime() - new Date(left.updated_at ?? 0).getTime()
      }),
    [posts],
  )
  const totalPages = Math.max(1, Math.ceil(sortedPosts.length / pageSize))
  const pagedPosts = sortedPosts.slice((page - 1) * pageSize, page * pageSize)
  const sortedTrends = useMemo(
    () => [...trends].sort((left, right) => (right.relevance_score ?? 0) - (left.relevance_score ?? 0) || new Date(right.updated_at ?? 0).getTime() - new Date(left.updated_at ?? 0).getTime()),
    [trends],
  )
  const trendTotalPages = Math.max(1, Math.ceil(sortedTrends.length / pageSize))
  const pagedTrends = sortedTrends.slice((trendPage - 1) * pageSize, trendPage * pageSize)
  const watchlistTotalPages = Math.max(1, Math.ceil(watchlist.length / pageSize))
  const pagedWatchlist = watchlist.slice((watchlistPage - 1) * pageSize, watchlistPage * pageSize)
  const sortedReposts = useMemo(
    () =>
      [...reposts].sort((left, right) => {
        const rankDelta = repostSortRank(left) - repostSortRank(right)
        if (rankDelta !== 0) return rankDelta
        return (right.relevance_score ?? 0) - (left.relevance_score ?? 0) || new Date(right.updated_at ?? 0).getTime() - new Date(left.updated_at ?? 0).getTime()
      }),
    [reposts],
  )
  const repostTotalPages = Math.max(1, Math.ceil(sortedReposts.length / pageSize))
  const pagedReposts = sortedReposts.slice((repostPage - 1) * pageSize, repostPage * pageSize)
  const sortedReplies = useMemo(
    () =>
      [...replies].sort((left, right) => {
        const rankDelta = replySortRank(left) - replySortRank(right)
        if (rankDelta !== 0) return rankDelta
        return new Date(right.updated_at ?? 0).getTime() - new Date(left.updated_at ?? 0).getTime()
      }),
    [replies],
  )
  const replyTotalPages = Math.max(1, Math.ceil(sortedReplies.length / pageSize))
  const pagedReplies = sortedReplies.slice((replyPage - 1) * pageSize, replyPage * pageSize)
  const replyByCandidateId = useMemo(() => {
    const mapping = new Map<number, SocialReplyItem>()
    for (const reply of replies) {
      if (reply.source_candidate_id) mapping.set(reply.source_candidate_id, reply)
    }
    return mapping
  }, [replies])

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
    if (trendPage > trendTotalPages) {
      setTrendPage(trendTotalPages)
    }
  }, [trendPage, trendTotalPages])

  useEffect(() => {
    if (watchlistPage > watchlistTotalPages) {
      setWatchlistPage(watchlistTotalPages)
    }
  }, [watchlistPage, watchlistTotalPages])

  useEffect(() => {
    if (repostPage > repostTotalPages) {
      setRepostPage(repostTotalPages)
    }
  }, [repostPage, repostTotalPages])

  useEffect(() => {
    if (replyPage > replyTotalPages) {
      setReplyPage(replyTotalPages)
    }
  }, [replyPage, replyTotalPages])

  useEffect(() => {
    setTrendPage(1)
    setWatchlistPage(1)
    setRepostPage(1)
    setReplyPage(1)
  }, [opsTab])

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

  async function openDetailModal(post: SocialPostDraft) {
    setDetailPost(post)
    setDetailLoadingId(post.id)
    try {
      const detail = await api.getSocialPost(post.id)
      setDetailPost(detail)
      setPosts((current) => current.map((item) => (item.id === detail.id ? detail : item)))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载草稿详情失败')
    } finally {
      setDetailLoadingId(null)
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

  async function approvePost(post: SocialPostDraft) {
    if (busyId) return
    setBusyId(post.id)
    try {
      const updated = await api.updateSocialPost(post.id, { status: 'approved', reviewed_by: 'operator' })
      setPosts((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      toast.success('已审核通过，可以发布到 X')
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '审核失败')
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

  async function publishRepostCandidateToX() {
    if (!repostPublishTarget || repostBusyId) return
    setRepostBusyId(repostPublishTarget.id)
    try {
      const updated = await api.publishSocialRepostCandidateToX(repostPublishTarget.id, {
        actor: 'operator',
        action: repostPublishAction,
      })
      setReposts((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setRepostDetail((current) => (current?.id === updated.id ? updated : current))
      toast.success(repostPublishAction === 'quote' ? '已引用发布到 X' : '已转发链接到 X')
      setRepostPublishTarget(null)
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '发布候选失败')
    } finally {
      setRepostBusyId(null)
    }
  }

  async function generateReplyForCandidate(candidate: SocialRepostCandidate) {
    if (replyBusyId) return
    setReplyBusyId(candidate.id)
    try {
      const reply = await api.generateSocialReplyForRepostCandidate(candidate.id, { actor: 'operator' })
      setReplies((current) => {
        const exists = current.some((item) => item.id === reply.id)
        return exists ? current.map((item) => (item.id === reply.id ? reply : item)) : [reply, ...current]
      })
      setReplyDetail(reply)
      setReplyDraftText(reply.suggested_reply || '')
      toast.success('已生成回帖草稿，等待人工审核')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '生成回帖失败')
    } finally {
      setReplyBusyId(null)
    }
  }

  async function saveReplyDraft(nextStatus = 'approved') {
    if (!replyDetail || replyBusyId) return
    setReplyBusyId(replyDetail.id)
    try {
      const updated = await api.updateSocialReply(replyDetail.id, {
        suggested_reply: replyDraftText,
        status: nextStatus,
        reviewed_by: 'operator',
      })
      setReplies((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setReplyDetail(updated)
      setReplyDraftText(updated.suggested_reply || '')
      toast.success(nextStatus === 'rejected' ? '已拒绝回帖' : '回帖草稿已保存')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存回帖失败')
    } finally {
      setReplyBusyId(null)
    }
  }

  async function publishReplyToX(target = replyPublishTarget) {
    if (!target || replyBusyId) return
    setReplyBusyId(target.id)
    try {
      const updated = await api.publishSocialReplyToX(target.id, { actor: 'operator' })
      setReplies((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setReplyDetail((current) => (current?.id === updated.id ? updated : current))
      if (updated.status === 'published') {
        toast.success('已回复到 X')
      } else {
        toast.error(updated.failure_summary || '回复失败')
      }
      setReplyPublishTarget(null)
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '回复到 X 失败')
    } finally {
      setReplyBusyId(null)
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
              ) : gcpAdcExpired(activeAccount) ? (
                <span className="rounded-xl border border-rose-300/30 bg-rose-300/10 px-3 py-2 text-sm font-semibold text-rose-100">GCP 凭据过期</span>
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
          {activeAccount && gcpAdcExpired(activeAccount) ? (
            <div className="rounded-2xl border border-rose-300/25 bg-rose-300/10 px-4 py-3 text-sm leading-6 text-rose-100">
              <div className="font-semibold">本地 GCP 凭据已过期，暂时无法读取 Secret Manager 里的 X OAuth refresh token。</div>
              <div className="mt-1">请在本机终端执行 <code className="rounded bg-black/30 px-2 py-1 font-mono text-xs">gcloud auth application-default login</code>，完成后刷新本页。</div>
              {activeAccount.auth_message ? <div className="mt-1 text-xs text-rose-100/80">{activeAccount.auth_message}</div> : null}
            </div>
          ) : activeAccount && !accountAuthorized(activeAccount) ? (
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
            <table className="w-full min-w-[980px] border-collapse text-left text-sm">
              <thead className="bg-[color:var(--ops-panel-subtle)] text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                <tr>
                  <th className="px-5 py-4 font-medium">ID</th>
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
                  const reconnectRequired = needsXReconnect(post)
                  return (
                  <tr key={post.id} className="bg-[color:var(--ops-workspace-bg)] align-top">
                    <td className="whitespace-nowrap px-5 py-4 font-mono text-xs text-[color:var(--ops-text-caption)]">#{post.id}</td>
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
                        <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-40" disabled={detailLoadingId === post.id} onClick={() => openDetailModal(post)}>
                          {detailLoadingId === post.id ? '加载中...' : '详情'}
                        </button>
                        <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-40" disabled={post.status === 'generating'} onClick={() => openEditModal(post)}>
                          编辑
                        </button>
                        {post.status !== 'published' && post.status !== 'rejected' && post.status !== 'generating' ? (
                          <button type="button" className="rounded-xl border border-rose-300/30 px-3 py-2 text-sm text-rose-100" disabled={busyId === post.id} onClick={() => rejectPost(post)}>
                            拒绝
                          </button>
                        ) : null}
                        {post.status === 'needs_review' && post.policy_check.status === 'passed' ? (
                          <button type="button" className="rounded-xl border border-emerald-300/35 px-3 py-2 text-sm font-semibold text-emerald-100 disabled:opacity-40" disabled={busyId === post.id} onClick={() => approvePost(post)}>
                            审核通过
                          </button>
                        ) : null}
                        {canPublish(post) && reconnectRequired && !accountAuthorized(postAccount) && !gcpAdcExpired(postAccount) ? (
                          <button type="button" className="rounded-xl border border-amber-300/35 px-3 py-2 text-sm font-semibold text-amber-100" onClick={() => void connectXAccount(post.account_id)}>
                            重新连接 X 官方账号
                          </button>
                        ) : null}
                        {canPublish(post) && accountAuthorized(postAccount) ? (
                          <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={busyId === post.id} onClick={() => setPublishTarget(post)}>
                            {publishActionLabel(post)}
                          </button>
                        ) : null}
                        {canPublish(post) && reconnectRequired && accountAuthorized(postAccount) ? (
                          <button type="button" className="rounded-xl border border-amber-300/35 px-3 py-2 text-sm font-semibold text-amber-100" onClick={() => void connectXAccount(post.account_id)}>
                            重新连接 X 官方账号
                          </button>
                        ) : null}
                        {canPublish(post) && !accountAuthorized(postAccount) && !reconnectRequired && !gcpAdcExpired(postAccount) ? (
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
          actions={
            <a
              className="rounded-2xl border border-cyan-300/35 px-4 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-300/10"
              href="/publishing/trends"
            >
              查看全部趋势
            </a>
          }
        >
          <div className="space-y-4">
            <div className="overflow-hidden rounded-[24px] border border-[color:var(--ops-stroke-soft)]">
              {trends.length === 0 ? <EmptyPane>暂无趋势素材。后续由 social_trend_radar_sweep 只读采集。</EmptyPane> : null}
              {trends.length > 0 ? (
                <>
                  <table className="w-full min-w-[720px] border-collapse text-left text-sm">
                    <thead className="bg-[color:var(--ops-panel-subtle)] text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                      <tr>
                        <th className="px-5 py-4 font-medium">主题</th>
                        <th className="px-5 py-4 font-medium">来源</th>
                        <th className="px-5 py-4 font-medium">分数</th>
                        <th className="px-5 py-4 text-right font-medium">操作</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[color:var(--ops-stroke-soft)]">
                      {pagedTrends.map((trend) => (
                        <tr key={trend.id} className="bg-[color:var(--ops-workspace-bg)] align-top">
                          <td className="max-w-[460px] px-5 py-4">
                            <div className="font-semibold text-[color:var(--ops-text-title)]">{trend.topic}</div>
                            <div className="mt-2 line-clamp-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">{trend.summary}</div>
                          </td>
                          <td className="px-5 py-4">
                            <div className="font-semibold text-[color:var(--ops-text-body)]">@{trend.author_handle ?? 'unknown'}</div>
                            <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">
                              {trend.source_url ? '来源：X 原帖' : '来源：本地趋势种子'}
                            </div>
                            <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{formatDateTime(trend.updated_at)}</div>
                          </td>
                          <td className="px-5 py-4">
                            <StateBadge tone="validating">score {Math.round(trend.relevance_score * 100)}</StateBadge>
                          </td>
                          <td className="px-5 py-4 text-right">
                            {trend.source_url ? <a className="inline-flex rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" href={trend.source_url} target="_blank" rel="noreferrer">打开来源</a> : <span className="text-xs text-[color:var(--ops-text-caption)]">无来源链接</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]">
                    <span>第 {trendPage} / {trendTotalPages} 页 · 共 {trends.length} 条趋势</span>
                    <div className="flex gap-2">
                      <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={trendPage <= 1} onClick={() => setTrendPage((current) => Math.max(1, current - 1))}>上一页</button>
                      <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={trendPage >= trendTotalPages} onClick={() => setTrendPage((current) => Math.min(trendTotalPages, current + 1))}>下一页</button>
                    </div>
                  </div>
                </>
              ) : null}
            </div>
            <div className="overflow-hidden rounded-[24px] border border-[color:var(--ops-stroke-soft)] bg-white/[0.03]">
              <div className="border-b border-[color:var(--ops-stroke-soft)] px-5 py-4 text-sm font-semibold text-[color:var(--ops-text-title)]">Watchlist</div>
              <div className="divide-y divide-[color:var(--ops-stroke-soft)]">
                {pagedWatchlist.map((account) => (
                  <div key={account.id} className="bg-[color:var(--ops-panel-subtle)] px-5 py-4">
                    <div className="font-semibold text-[color:var(--ops-text-body)]">@{account.handle}</div>
                    <div className="mt-1 text-xs leading-5 text-[color:var(--ops-text-muted)]">{account.category} · {account.rationale}</div>
                    {account.latest_summary ? <div className="mt-2 line-clamp-2 text-xs text-[color:var(--ops-text-caption)]">{account.latest_summary}</div> : null}
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]">
                <span>第 {watchlistPage} / {watchlistTotalPages} 页 · 共 {watchlist.length} 个账号</span>
                <div className="flex gap-2">
                  <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={watchlistPage <= 1} onClick={() => setWatchlistPage((current) => Math.max(1, current - 1))}>上一页</button>
                  <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={watchlistPage >= watchlistTotalPages} onClick={() => setWatchlistPage((current) => Math.min(watchlistTotalPages, current + 1))}>下一页</button>
                </div>
              </div>
            </div>
          </div>
        </SectionFrame>
      ) : null}

      {opsTab === 'replies' ? (
        <SectionFrame
          eyebrow="Reply Inbox"
          title="回帖处理"
          description="每 30 分钟可从真实 X 候选中生成 1 条正向相关的回复草稿；公开回复必须由人类确认。"
        >
          {replies.length === 0 ? <EmptyPane>暂无待处理回帖。可以先在“转发候选”中点击“生成回帖”，或等待 x_social_reply_candidate_sweep 自动生成待审核草稿。</EmptyPane> : null}
          {replies.length > 0 ? (
            <div className="overflow-hidden rounded-[24px] border border-[color:var(--ops-stroke-soft)]">
              <table className="w-full min-w-[980px] border-collapse text-left text-sm">
                <thead className="bg-[color:var(--ops-panel-subtle)] text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                  <tr>
                    <th className="px-5 py-4 font-medium">ID</th>
                    <th className="px-5 py-4 font-medium">来源</th>
                    <th className="px-5 py-4 font-medium">状态 / 风险</th>
                    <th className="px-5 py-4 font-medium">回复草稿</th>
                    <th className="px-5 py-4 font-medium">更新</th>
                    <th className="px-5 py-4 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[color:var(--ops-stroke-soft)]">
                  {pagedReplies.map((reply) => (
                    <tr key={reply.id} className="bg-[color:var(--ops-workspace-bg)] align-top">
                      <td className="whitespace-nowrap px-5 py-4 font-mono text-xs text-[color:var(--ops-text-caption)]">#{reply.id}</td>
                      <td className="max-w-[320px] px-5 py-4">
                        <div className="font-semibold text-[color:var(--ops-text-title)]">@{reply.source_author_handle || reply.author_handle || 'unknown'}</div>
                        <div className="mt-2 line-clamp-3 text-xs leading-5 text-[color:var(--ops-text-muted)]">{reply.source_text || reply.incoming_text}</div>
                      </td>
                      <td className="px-5 py-4">
                        <StateBadge tone={signalStatusTone(reply.status)}>{replyStatusLabel(reply.status)}</StateBadge>
                        <div className="mt-2 text-xs text-[color:var(--ops-text-muted)]">risk {reply.risk_level}</div>
                        {reply.failure_summary ? <div className="mt-2 max-w-[220px] text-xs leading-5 text-rose-200">{reply.failure_summary}</div> : null}
                      </td>
                      <td className="max-w-[360px] px-5 py-4">
                        <div className="line-clamp-3 rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.08] px-3 py-2 text-xs leading-5 text-cyan-50">
                          {reply.suggested_reply || 'Agent 尚未生成回复草稿。'}
                        </div>
                      </td>
                      <td className="px-5 py-4 text-xs text-[color:var(--ops-text-muted)]">{formatDateTime(reply.updated_at)}</td>
                      <td className="px-5 py-4">
                        <div className="flex flex-wrap justify-end gap-2">
                          <button
                            type="button"
                            className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
                            onClick={() => {
                              setReplyDetail(reply)
                              setReplyDraftText(reply.suggested_reply || '')
                            }}
                          >
                            详情
                          </button>
                          {reply.source_url ? <a className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" href={reply.source_url} target="_blank" rel="noreferrer">查看原帖</a> : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]">
                <span>第 {replyPage} / {replyTotalPages} 页 · 共 {replies.length} 条回帖草稿</span>
                <div className="flex gap-2">
                  <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={replyPage <= 1} onClick={() => setReplyPage((current) => Math.max(1, current - 1))}>上一页</button>
                  <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={replyPage >= replyTotalPages} onClick={() => setReplyPage((current) => Math.min(replyTotalPages, current + 1))}>下一页</button>
                </div>
              </div>
            </div>
          ) : null}
        </SectionFrame>
      ) : null}

      {opsTab === 'reposts' ? (
        <SectionFrame
          eyebrow="Repost Candidates"
          title="转发 / 引用候选"
          description="推荐品牌相关的高质量 X 内容；Agent 只拟引用文案，人类点击后才会引用转发。"
        >
          {reposts.length === 0 ? <EmptyPane>暂无转发候选。后续由 social_repost_candidate_sweep 从趋势和 watchlist 中生成。</EmptyPane> : null}
          {reposts.length > 0 ? (
            <div className="overflow-hidden rounded-[24px] border border-[color:var(--ops-stroke-soft)]">
              <table className="w-full min-w-[980px] border-collapse text-left text-sm">
                <thead className="bg-[color:var(--ops-panel-subtle)] text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                  <tr>
                    <th className="px-5 py-4 font-medium">ID</th>
                    <th className="px-5 py-4 font-medium">来源内容</th>
                    <th className="px-5 py-4 font-medium">状态 / Fit</th>
                    <th className="px-5 py-4 font-medium">引用文案</th>
                    <th className="px-5 py-4 font-medium">更新</th>
                    <th className="px-5 py-4 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[color:var(--ops-stroke-soft)]">
                  {pagedReposts.map((candidate) => {
                    const candidateReply = replyByCandidateId.get(candidate.id)
                    return (
                    <tr key={candidate.id} className="bg-[color:var(--ops-workspace-bg)] align-top">
                      <td className="whitespace-nowrap px-5 py-4 font-mono text-xs text-[color:var(--ops-text-caption)]">#{candidate.id}</td>
                      <td className="max-w-[320px] px-5 py-4">
                        <div className="font-semibold text-[color:var(--ops-text-title)]">@{candidate.author_handle ?? 'unknown'}</div>
                        <div className="mt-2 line-clamp-3 text-xs leading-5 text-[color:var(--ops-text-muted)]">{candidate.source_text}</div>
                      </td>
                      <td className="px-5 py-4">
                        <StateBadge tone={signalStatusTone(candidate.status)}>{repostStatusLabel(candidate.status)}</StateBadge>
                        <div className="mt-2 text-xs text-[color:var(--ops-text-muted)]">fit {Math.round(candidate.relevance_score * 100)}</div>
                      </td>
                      <td className="max-w-[340px] px-5 py-4">
                        <div className="line-clamp-3 rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.08] px-3 py-2 text-xs leading-5 text-cyan-50">
                          {candidate.suggested_quote || 'Agent 尚未生成引用文案。'}
                        </div>
                      </td>
                      <td className="px-5 py-4 text-xs text-[color:var(--ops-text-muted)]">{formatDateTime(candidate.updated_at)}</td>
	                      <td className="px-5 py-4">
	                        <div className="flex flex-wrap justify-end gap-2">
	                          {candidateReply ? (
	                            <button
	                              type="button"
	                              className="rounded-xl border border-emerald-300/30 px-3 py-2 text-sm text-emerald-100"
	                              onClick={() => {
	                                setReplyDetail(candidateReply)
	                                setReplyDraftText(candidateReply.suggested_reply || '')
	                              }}
	                            >
	                              查看回帖
	                            </button>
	                          ) : candidate.source_url && candidate.status === 'candidate' ? (
	                            <button
	                              type="button"
	                              className="rounded-xl border border-emerald-300/30 px-3 py-2 text-sm text-emerald-100 disabled:opacity-50"
	                              disabled={replyBusyId === candidate.id}
	                              onClick={() => generateReplyForCandidate(candidate)}
	                            >
	                              {replyBusyId === candidate.id ? '生成中...' : '生成回帖'}
	                            </button>
	                          ) : null}
	                          {candidate.source_url && accountAuthorized(activeAccount) && candidate.status !== 'published' && candidate.status !== 'publishing' ? (
	                            <button
	                              type="button"
	                              className="rounded-xl border border-cyan-300/35 px-3 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50"
	                              disabled={repostBusyId === candidate.id}
	                              onClick={() => {
	                                setRepostPublishAction('repost')
	                                setRepostPublishTarget(candidate)
	                              }}
	                            >
	                              转发到 X
	                            </button>
	                          ) : null}
	                          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => setRepostDetail(candidate)}>详情</button>
	                          {candidate.source_url ? <a className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" href={candidate.source_url} target="_blank" rel="noreferrer">查看原帖</a> : null}
	                        </div>
	                      </td>
                    </tr>
                    )
                  })}
                </tbody>
              </table>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]">
                <span>第 {repostPage} / {repostTotalPages} 页 · 共 {reposts.length} 条候选</span>
                <div className="flex gap-2">
                  <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={repostPage <= 1} onClick={() => setRepostPage((current) => Math.max(1, current - 1))}>上一页</button>
                  <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={repostPage >= repostTotalPages} onClick={() => setRepostPage((current) => Math.min(repostTotalPages, current + 1))}>下一页</button>
                </div>
              </div>
            </div>
          ) : null}
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
        open={Boolean(repostDetail)}
        eyebrow="Repost Candidate"
        title={repostDetail ? `转发 / 引用候选 #${repostDetail.id}` : '转发 / 引用候选'}
        description="这里展示候选来源、Agent 拟写引用文案和公开操作。发布到 X 前必须由 operator 明确确认。"
        onClose={() => setRepostDetail(null)}
        actions={
          <>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => setRepostDetail(null)}>
              关闭
            </button>
            {repostDetail && !accountAuthorized(activeAccount) ? (
              <button type="button" className="rounded-xl border border-amber-300/35 px-4 py-2 text-sm font-semibold text-amber-100" onClick={() => void connectXAccount(activeAccount?.id)}>
                连接 X 官方账号
              </button>
            ) : null}
            {repostDetail && accountAuthorized(activeAccount) && repostDetail.status !== 'published' && repostDetail.status !== 'publishing' ? (
              <>
                <button
                  type="button"
                  className="rounded-xl border border-cyan-300/35 px-4 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50"
                  disabled={!repostDetail.source_url || repostBusyId === repostDetail.id}
                  onClick={() => {
                    setRepostPublishAction('repost')
                    setRepostPublishTarget(repostDetail)
                  }}
                >
                  转发链接到 X
                </button>
                <button
                  type="button"
                  className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  disabled={!repostDetail.source_url || !repostDetail.suggested_quote || repostBusyId === repostDetail.id}
                  onClick={() => {
                    setRepostPublishAction('quote')
                    setRepostPublishTarget(repostDetail)
                  }}
                >
                  引用发布到 X
                </button>
              </>
            ) : null}
          </>
        }
      >
        {repostDetail ? (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Author</div>
                <div className="mt-2 font-semibold">@{repostDetail.author_handle ?? 'unknown'}</div>
              </div>
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Status</div>
                <div className="mt-2"><StateBadge tone={signalStatusTone(repostDetail.status)}>{repostStatusLabel(repostDetail.status)}</StateBadge></div>
              </div>
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Fit Score</div>
                <div className="mt-2 font-semibold">{Math.round(repostDetail.relevance_score * 100)}</div>
              </div>
            </div>
              <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Source Post</div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-body)]">{repostDetail.source_text}</p>
                {repostDetail.source_url ? <a className="mt-3 inline-flex text-sm font-semibold text-cyan-100 underline" href={repostDetail.source_url} target="_blank" rel="noreferrer">打开原帖</a> : null}
                {!repostDetail.source_url ? (
                  <div className="mt-3 rounded-2xl border border-amber-300/25 bg-amber-300/10 px-3 py-2 text-xs leading-5 text-amber-100">
                    这条候选没有 X 原帖链接，只能作为内容灵感，不能执行转发或引用发布。
                  </div>
                ) : null}
              </div>
            <div className="rounded-3xl border border-cyan-300/20 bg-cyan-300/[0.08] p-4">
              <div className="text-[10px] uppercase tracking-[0.18em] text-cyan-100/75">Suggested Quote</div>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-cyan-50">{repostDetail.suggested_quote || 'Agent 尚未生成引用文案。'}</p>
            </div>
            <div className="rounded-3xl border border-emerald-300/20 bg-emerald-300/[0.07] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.18em] text-emerald-100/75">Reply Draft</div>
                  <p className="mt-3 text-sm leading-6 text-emerald-50">
                    {replyByCandidateId.get(repostDetail.id)?.suggested_reply || '还没有回帖草稿。可以让 Agent 根据原帖生成一条正向、相关、有观点的评论。'}
                  </p>
                </div>
                {replyByCandidateId.get(repostDetail.id) ? (
                  <button
                    type="button"
                    className="rounded-xl border border-emerald-300/35 px-3 py-2 text-sm font-semibold text-emerald-100"
                    onClick={() => {
                      const reply = replyByCandidateId.get(repostDetail.id)
                      if (reply) {
                        setReplyDetail(reply)
                        setReplyDraftText(reply.suggested_reply || '')
                      }
                    }}
                  >
                    查看回帖
                  </button>
                ) : (
                  <button
                    type="button"
                    className="rounded-xl border border-emerald-300/35 px-3 py-2 text-sm font-semibold text-emerald-100 disabled:opacity-50"
                    disabled={!repostDetail.source_url || replyBusyId === repostDetail.id}
                    onClick={() => generateReplyForCandidate(repostDetail)}
                  >
                    {replyBusyId === repostDetail.id ? '生成中...' : '生成回帖'}
                  </button>
                )}
              </div>
            </div>
            <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 px-4 py-3 text-sm leading-6 text-amber-100">
              Human Gate：引用发布或转发链接都会代表 @SynapseNetworkA 公开发声。系统不会自动点赞、关注、删除或绕过 X OAuth。
            </div>
          </div>
        ) : null}
      </OverlayModal>

      <OverlayModal
        open={Boolean(replyDetail)}
        eyebrow="X Reply Review"
        title={replyDetail ? `回帖草稿 #${replyDetail.id}` : '回帖草稿'}
        description="Agent 可以生成正向相关的评论草稿；回复到 X 前必须由 operator 明确确认。"
        onClose={() => setReplyDetail(null)}
        actions={
          <>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => setReplyDetail(null)}>
              关闭
            </button>
            {replyDetail && replyDetail.status !== 'published' && replyDetail.status !== 'rejected' ? (
              <button
                type="button"
                className="rounded-xl border border-rose-300/30 px-4 py-2 text-sm text-rose-100 disabled:opacity-50"
                disabled={replyBusyId === replyDetail.id}
                onClick={() => void saveReplyDraft('rejected')}
              >
                拒绝
              </button>
            ) : null}
            {replyDetail && replyDetail.status !== 'published' && replyDetail.status !== 'rejected' ? (
              <button
                type="button"
                className="rounded-xl border border-emerald-300/35 px-4 py-2 text-sm font-semibold text-emerald-100 disabled:opacity-50"
                disabled={!replyDraftText.trim() || replyBusyId === replyDetail.id}
                onClick={() => void saveReplyDraft('approved')}
              >
                保存并审核通过
              </button>
            ) : null}
            {replyDetail && ['approved', 'failed'].includes(replyDetail.status) && accountAuthorized(activeAccount) ? (
              <button
                type="button"
                className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                disabled={!replyDraftText.trim() || replyBusyId === replyDetail.id}
                onClick={() => {
                  setReplyPublishTarget({ ...replyDetail, suggested_reply: replyDraftText })
                }}
              >
                回复到 X
              </button>
            ) : null}
          </>
        }
      >
        {replyDetail ? (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Author</div>
                <div className="mt-2 font-semibold">@{replyDetail.source_author_handle || replyDetail.author_handle || 'unknown'}</div>
              </div>
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Status</div>
                <div className="mt-2"><StateBadge tone={signalStatusTone(replyDetail.status)}>{replyStatusLabel(replyDetail.status)}</StateBadge></div>
              </div>
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Risk</div>
                <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">{replyDetail.risk_level}</div>
              </div>
            </div>
            <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
              <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Source Post</div>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-body)]">{replyDetail.source_text || replyDetail.incoming_text}</p>
              {replyDetail.source_url ? <a className="mt-3 inline-flex text-sm font-semibold text-cyan-100 underline" href={replyDetail.source_url} target="_blank" rel="noreferrer">打开原帖</a> : null}
            </div>
            <label className="block text-sm">
              <span className="text-[color:var(--ops-text-muted)]">Agent 回帖草稿</span>
              <textarea
                aria-label="Agent 回帖草稿"
                className="mt-2 min-h-36 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3"
                value={replyDraftText}
                onChange={(event) => setReplyDraftText(event.target.value)}
              />
              <span className="mt-1 block text-xs text-[color:var(--ops-text-caption)]">{replyDraftText.length} chars · 回复必须相关、正向、有额外观点。</span>
            </label>
            {replyDetail.generation_reason ? (
              <div className="rounded-3xl border border-emerald-300/20 bg-emerald-300/[0.07] p-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-emerald-100/75">Generation Reason</div>
                <p className="mt-3 text-sm leading-6 text-emerald-50">{replyDetail.generation_reason}</p>
              </div>
            ) : null}
            {replyDetail.failure_summary ? (
              <div className="rounded-2xl border border-rose-300/25 bg-rose-300/10 px-4 py-3 text-sm leading-6 text-rose-100">{replyDetail.failure_summary}</div>
            ) : null}
            {replyDetail.published_external_post_id ? (
              <div className="rounded-2xl border border-cyan-300/25 bg-cyan-300/10 px-4 py-3 text-sm leading-6 text-cyan-50">
                已回复到 X：{replyDetail.published_external_post_id}
              </div>
            ) : null}
            <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 px-4 py-3 text-sm leading-6 text-amber-100">
              Human Gate：点击“回复到 X”会代表 @SynapseNetworkA 公开评论该原帖。系统不会自动点赞、关注、删除或私信。
            </div>
          </div>
        ) : null}
      </OverlayModal>

      <OverlayModal
        open={Boolean(detailPost)}
        eyebrow="X official account"
        title={detailPost ? `内容草稿 #${detailPost.id}` : '内容草稿详情'}
        description="记录这条草稿从生成、审核、图片处理到发布结果的全过程数据。"
        onClose={() => setDetailPost(null)}
      >
        {detailPost ? (
          <div className="space-y-5">
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Status</div>
                <div className="mt-2"><StateBadge tone={statusTone(detailPost.status)}>{statusLabel(detailPost.status)}</StateBadge></div>
              </div>
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Policy</div>
                <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">{detailPost.policy_check.status} · {detailPost.policy_check.character_count} chars</div>
              </div>
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Created</div>
                <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">{formatDateTime(detailPost.created_at)}</div>
              </div>
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Updated</div>
                <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">{formatDateTime(detailPost.updated_at)}</div>
              </div>
            </div>

            <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
              <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Draft Content</div>
              <div className="mt-3 text-lg font-semibold text-[color:var(--ops-text-title)]">{detailPost.title || `X draft #${detailPost.id}`}</div>
              <div className="mt-3 whitespace-pre-wrap rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4 text-sm leading-6 text-[color:var(--ops-text-body)]">{detailPost.body_text || '-'}</div>
              {promptExcerpt(detailPost) ? (
                <div className="mt-3 rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.06] p-4">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-cyan-100/70">Original Prompt</div>
                  <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-cyan-50">{promptExcerpt(detailPost)}</div>
                </div>
              ) : null}
              {detailPost.failure_summary ? (
                <div className="mt-3 rounded-2xl border border-rose-300/25 bg-rose-300/10 p-4 text-sm leading-6 text-rose-100">{detailPost.failure_summary}</div>
              ) : null}
              {detailPost.external_post_id ? (
                <a className="mt-3 inline-flex rounded-xl border border-cyan-300/35 px-3 py-2 text-sm font-semibold text-cyan-100" href={detailPost.external_url ?? '#'} target="_blank" rel="noreferrer">
                  Open on X · {detailPost.external_post_id}
                </a>
              ) : null}
            </div>

            <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
              <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">图片资产</div>
              {activeMediaAssets(detailPost).length === 0 ? (
                <div className="mt-3 rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] px-4 py-5 text-sm text-[color:var(--ops-text-muted)]">这条草稿没有活动图片。</div>
              ) : (
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  {activeMediaAssets(detailPost).map((asset) => (
                    <div key={asset.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-3">
                      {asset.preview_url && asset.status !== 'failed' ? <img src={asset.preview_url} alt={asset.alt_text ?? 'X image preview'} className="h-36 w-full rounded-xl object-cover" /> : null}
                      <div className="mt-3 flex items-center justify-between gap-3">
                        <StateBadge tone={asset.status === 'failed' ? 'blocked' : asset.status === 'generating' ? 'running' : 'ready'}>{mediaStatusLabel(asset.status)}</StateBadge>
                        <span className="font-mono text-xs text-[color:var(--ops-text-caption)]">media #{asset.id}</span>
                      </div>
                      <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{asset.alt_text || asset.prompt || '-'}</div>
                      {asset.x_media_id ? <div className="mt-2 font-mono text-xs text-[color:var(--ops-text-caption)]">x_media_id: {asset.x_media_id}</div> : null}
                      {asset.failure_summary ? <div className="mt-2 text-xs text-rose-200">{asset.failure_summary}</div> : null}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">任务过程 Timeline</div>
                <span className="text-xs text-[color:var(--ops-text-caption)]">{detailPost.events.length} events</span>
              </div>
              {detailPost.events.length === 0 ? (
                <div className="mt-3 rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] px-4 py-5 text-sm text-[color:var(--ops-text-muted)]">暂无过程事件。</div>
              ) : (
                <div className="mt-4 space-y-3">
                  {detailPost.events.map((event) => (
                    <div key={event.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="font-mono text-xs uppercase tracking-[0.12em] text-cyan-100">{event.event_type}</div>
                          <div className="mt-1 text-sm text-[color:var(--ops-text-body)]">{event.summary || '-'}</div>
                        </div>
                        <div className="text-right text-xs text-[color:var(--ops-text-caption)]">
                          <div>{formatDateTime(event.created_at)}</div>
                          <div>by {event.actor}</div>
                        </div>
                      </div>
                      <details className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] px-3 py-2">
                        <summary className="cursor-pointer text-xs text-[color:var(--ops-text-muted)]">查看事件 payload</summary>
                        <pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-[color:var(--ops-text-body)]">{compactJson(event.payload)}</pre>
                      </details>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <details className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
              <summary className="cursor-pointer text-sm font-semibold text-[color:var(--ops-text-title)]">Debug metadata</summary>
              <pre className="mt-4 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-2xl bg-[color:var(--ops-panel-strong)] p-4 text-xs leading-5 text-[color:var(--ops-text-body)]">{compactJson(detailPost.raw_agent_output)}</pre>
            </details>
          </div>
        ) : null}
      </OverlayModal>

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
            {savingDraft ? (editing ? '保存中...' : '生成中...') : editing ? (editing.status === 'needs_review' ? '保存并审核通过' : '保存草稿') : '生成草稿'}
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

      <ConfirmDialog
        open={Boolean(repostPublishTarget)}
        title={repostPublishAction === 'quote' ? '确认引用发布到 X' : '确认转发链接到 X'}
        description={
          repostPublishAction === 'quote'
            ? '这会代表 @SynapseNetworkA 公开发布 Agent 拟写的引用文案，并附带原帖链接。确认后不可由系统自动撤回。'
            : '这会代表 @SynapseNetworkA 公开发布原帖链接。确认后不可由系统自动撤回。'
        }
        confirmLabel={repostPublishAction === 'quote' ? '引用发布到 X' : '转发链接到 X'}
        loading={Boolean(repostPublishTarget && repostBusyId === repostPublishTarget.id)}
        onConfirm={publishRepostCandidateToX}
        onClose={() => setRepostPublishTarget(null)}
      />

      <ConfirmDialog
        open={Boolean(replyPublishTarget)}
        title="确认回复到 X"
        description="这会代表 @SynapseNetworkA 公开评论该 X 原帖。确认后不可由系统自动撤回，也不会自动点赞、关注或私信。"
        confirmLabel="回复到 X"
        loading={Boolean(replyPublishTarget && replyBusyId === replyPublishTarget.id)}
        onConfirm={async () => {
          let target = replyPublishTarget
          if (replyDetail && replyDraftText.trim() && replyDetail.id === replyPublishTarget?.id) {
            const updated = await api.updateSocialReply(replyDetail.id, {
              suggested_reply: replyDraftText,
              status: 'approved',
              reviewed_by: 'operator',
            })
            setReplies((current) => current.map((item) => (item.id === updated.id ? updated : item)))
            setReplyDetail(updated)
            target = updated
          }
          await publishReplyToX(target)
        }}
        onClose={() => setReplyPublishTarget(null)}
      />
    </div>
  )
}
