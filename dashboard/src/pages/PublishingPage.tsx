import { useEffect, useMemo, useState } from 'react'
import { api, type SocialAccount, type SocialPostDraft } from '../api'
import { ConfirmDialog, EmptyPane, OverlayDrawer, SectionFrame, StateBadge, useToast } from '../components/workbench'

const statusTabs = [
  { key: '', label: 'All' },
  { key: 'draft', label: 'Drafts' },
  { key: 'needs_review', label: 'Needs Review' },
  { key: 'approved', label: 'Approved' },
  { key: 'published', label: 'Published' },
  { key: 'failed', label: 'Failed' },
]

type DraftForm = {
  accountId: string
  prompt: string
  title: string
  bodyText: string
}

const emptyForm: DraftForm = {
  accountId: '',
  prompt: '',
  title: '',
  bodyText: '',
}

const pageSize = 8

function statusTone(status: string): 'default' | 'ready' | 'running' | 'blocked' | 'validating' | 'delivered' | 'muted' {
  if (status === 'published') return 'delivered'
  if (status === 'approved') return 'ready'
  if (status === 'failed' || status === 'rejected') return 'blocked'
  if (status === 'publishing') return 'running'
  return 'validating'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    draft: '草稿',
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
  return post.status === 'approved' && post.policy_check.status === 'passed'
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

export default function PublishingPage() {
  const toast = useToast()
  const [accounts, setAccounts] = useState<SocialAccount[]>([])
  const [posts, setPosts] = useState<SocialPostDraft[]>([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<SocialPostDraft | null>(null)
  const [publishTarget, setPublishTarget] = useState<SocialPostDraft | null>(null)
  const [form, setForm] = useState<DraftForm>(emptyForm)
  const [page, setPage] = useState(1)

  const activeAccount = useMemo(() => accounts.find((account) => String(account.id) === form.accountId) ?? accounts[0], [accounts, form.accountId])
  const canSave = editing ? form.bodyText.trim().length > 0 : form.prompt.trim().length > 0
  const totalPages = Math.max(1, Math.ceil(posts.length / pageSize))
  const pagedPosts = posts.slice((page - 1) * pageSize, page * pageSize)

  async function load(nextFilter = filter) {
    setLoading(true)
    try {
      const [accountRows, postRows] = await Promise.all([
        api.getSocialAccounts(),
        api.getSocialPosts(nextFilter ? { status: nextFilter } : undefined),
      ])
      setAccounts(accountRows)
      setPosts(postRows)
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

  function openCreateDrawer() {
    setEditing(null)
    setForm({ ...emptyForm, accountId: accounts[0] ? String(accounts[0].id) : '' })
    setDrawerOpen(true)
  }

  function openEditDrawer(post: SocialPostDraft) {
    setEditing(post)
    setForm({
      accountId: String(post.account_id),
      prompt: '',
      title: post.title ?? '',
      bodyText: post.body_text,
    })
    setDrawerOpen(true)
  }

  async function saveDraft() {
    try {
      if (editing) {
        await api.updateSocialPost(editing.id, {
          title: form.title,
          body_text: form.bodyText,
          status: 'approved',
          reviewed_by: 'operator',
        })
        toast.success('草稿已更新')
      } else {
        await api.generateSocialPostDraft({
          account_id: activeAccount?.id ?? null,
          prompt: form.prompt,
          actor: 'operator',
        })
        toast.success('Agent 已生成标题和正文，可检查后发布到 X')
      }
      setDrawerOpen(false)
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存草稿失败')
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
      await api.publishSocialPostToX(publishTarget.id, { actor: 'operator' })
      toast.success('已发布到 X')
      setPublishTarget(null)
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '发布失败')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-5">
      <SectionFrame
        eyebrow="Social Publishing"
        title="官方账号内容发布"
        description="输入 Prompt，Agent 生成 X 标题和正文；公开发布必须由人类点击确认。v1 只支持 @SynapseNetworkA 纯文本单条 Post。"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => load()}>
              刷新
            </button>
            <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={openCreateDrawer}>
              让 Agent 写草稿
            </button>
          </div>
        }
      >
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
      </SectionFrame>

      <SectionFrame
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
                {pagedPosts.map((post) => (
                  <tr key={post.id} className="bg-[color:var(--ops-workspace-bg)] align-top">
                    <td className="max-w-[420px] px-5 py-4">
                      <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">X · @{post.account_handle ?? 'SynapseNetworkA'}</div>
                      <div className="mt-1 font-semibold text-[color:var(--ops-text-title)]">{post.title || `X draft #${post.id}`}</div>
                      <div className="mt-2 line-clamp-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">{post.body_text}</div>
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
                      <div className="text-[color:var(--ops-text-body)]">{post.policy_check.status}</div>
                      <div className="mt-1 text-xs text-[color:var(--ops-text-muted)]">{post.policy_check.character_count}/280 chars</div>
                      {post.policy_check.status === 'blocked' ? <div className="mt-1 max-w-[260px] text-xs text-rose-200">Blocked: {post.policy_check.blocked_reasons.join(', ')}</div> : null}
                      {post.failure_summary ? <div className="mt-1 max-w-[260px] text-xs text-rose-200">{post.failure_summary}</div> : null}
                    </td>
                    <td className="px-5 py-4 text-xs text-[color:var(--ops-text-muted)]">{formatDateTime(post.updated_at)}</td>
                    <td className="px-5 py-4">
                      <div className="flex flex-wrap justify-end gap-2">
                        <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => openEditDrawer(post)}>
                          编辑
                        </button>
                        {post.status !== 'published' && post.status !== 'rejected' ? (
                          <button type="button" className="rounded-xl border border-rose-300/30 px-3 py-2 text-sm text-rose-100" disabled={busyId === post.id} onClick={() => rejectPost(post)}>
                            拒绝
                          </button>
                        ) : null}
                        {post.status === 'approved' ? (
                          <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={busyId === post.id || !canPublish(post)} onClick={() => setPublishTarget(post)}>
                            发布到 X
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
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
      </SectionFrame>

      <OverlayDrawer
        open={drawerOpen}
        eyebrow="X official account"
        title={editing ? '编辑内容草稿' : '让 Agent 写草稿'}
        description={editing ? '这里只编辑标题和正文，不会发布到 X。' : '输入 Prompt，Agent 会生成标题和正文；发布仍需人工确认点击。'}
        onClose={() => setDrawerOpen(false)}
        actions={
          <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={!canSave} onClick={saveDraft}>
            {editing ? '保存草稿' : '生成草稿'}
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
            <label className="block text-sm">
              <span className="text-[color:var(--ops-text-muted)]">目标 / Prompt</span>
              <textarea
                aria-label="目标 / Prompt"
                className="mt-2 min-h-40 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3"
                placeholder="例如：发布 staging 自动发布链路已经跑通，强调 PR checks、人审、staging deploy 和上线记录。语气专业、克制。"
                value={form.prompt}
                onChange={(event) => setForm((current) => ({ ...current, prompt: event.target.value }))}
              />
              <span className="mt-1 block text-xs text-[color:var(--ops-text-caption)]">Agent 只生成可检查草稿，不会发布到 X；v1 仅支持纯文本，不生成图片或视频。</span>
            </label>
          ) : (
            <>
              <label className="block text-sm">
                <span className="text-[color:var(--ops-text-muted)]">标题</span>
                <input className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3" value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
              </label>
              <label className="block text-sm">
                <span className="text-[color:var(--ops-text-muted)]">最终发布正文</span>
                <textarea aria-label="最终发布正文" className="mt-2 min-h-40 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3" value={form.bodyText} onChange={(event) => setForm((current) => ({ ...current, bodyText: event.target.value }))} />
                <span className={['mt-1 block text-xs', form.bodyText.length > 280 ? 'text-rose-200' : 'text-[color:var(--ops-text-caption)]'].join(' ')}>{form.bodyText.length}/280</span>
              </label>
            </>
          )}
          <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 px-4 py-3 text-sm leading-6 text-amber-100">
            发布前确认：这会代表 @SynapseNetworkA 公开发布内容到 X。确认后不可由系统自动撤回。
          </div>
        </div>
      </OverlayDrawer>

      <ConfirmDialog
        open={Boolean(publishTarget)}
        title="确认发布到 X"
        description="这会代表 @SynapseNetworkA 公开发布内容到 X。确认后不可由系统自动撤回。"
        confirmLabel="发布到 X"
        loading={Boolean(publishTarget && busyId === publishTarget.id)}
        onConfirm={publishToX}
        onClose={() => setPublishTarget(null)}
      />
    </div>
  )
}
