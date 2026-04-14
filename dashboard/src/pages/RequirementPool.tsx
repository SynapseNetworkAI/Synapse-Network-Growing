import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AgentRequirement, api } from '../api'
import { EmptyPane, FieldLabel, OverlayDrawer, OverlayModal, StateBadge } from '../components/workbench'

type DrawerMode = 'closed' | 'create' | 'edit'

type RequirementDraft = {
  title: string
  description_markdown: string
  priority: string
  target_project_path: string
}

const EMPTY_DRAFT: RequirementDraft = {
  title: '',
  description_markdown: '',
  priority: 'normal',
  target_project_path: '',
}

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  ready: '待执行',
  running: '执行中',
  blocked: '阻塞',
  needs_revision: '需修订',
  delivery_ready: '待发布',
  done: '已完成',
  cancelled: '已取消',
  deleted: '已删除',
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function statusTone(status: string) {
  if (status === 'done' || status === 'delivery_ready') return 'delivered'
  if (status === 'running') return 'running'
  if (status === 'blocked' || status === 'needs_revision' || status === 'cancelled') return 'blocked'
  if (status === 'ready') return 'ready'
  return 'muted'
}

function buildDraft(requirement?: AgentRequirement | null): RequirementDraft {
  if (!requirement) return { ...EMPTY_DRAFT }
  return {
    title: requirement.title,
    description_markdown: requirement.description_markdown,
    priority: requirement.priority,
    target_project_path: requirement.target_project_path || '',
  }
}

function RequirementForm({
  draft,
  saving,
  onChange,
  onClose,
  onSubmit,
}: Readonly<{
  draft: RequirementDraft
  saving: boolean
  onChange: (patch: Partial<RequirementDraft>) => void
  onClose: () => void
  onSubmit: () => Promise<void>
}>) {
  return (
    <div className="grid gap-5">
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <FieldLabel>标题</FieldLabel>
          <input
            className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
            placeholder="输入需求标题"
            value={draft.title}
            onChange={(event) => onChange({ title: event.target.value })}
          />
        </div>
        <div>
          <FieldLabel>目标项目</FieldLabel>
          <input
            className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
            placeholder="输入项目路径"
            value={draft.target_project_path}
            onChange={(event) => onChange({ target_project_path: event.target.value })}
          />
        </div>
      </div>

      <div>
        <FieldLabel>需求描述</FieldLabel>
        <textarea
          className="mt-2 min-h-[200px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
          placeholder="输入需求描述"
          value={draft.description_markdown}
          onChange={(event) => onChange({ description_markdown: event.target.value })}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-[220px,1fr]">
        <div>
          <FieldLabel>优先级</FieldLabel>
          <select
            className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
            value={draft.priority}
            onChange={(event) => onChange({ priority: event.target.value })}
          >
            <option value="low">low</option>
            <option value="normal">normal</option>
            <option value="high">high</option>
          </select>
        </div>
        <div className="flex items-end justify-end gap-3">
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="rounded-xl bg-[color:var(--ops-accent-strong)] px-5 py-3 text-sm font-medium text-white disabled:opacity-60"
            disabled={saving || !draft.title.trim() || !draft.description_markdown.trim()}
            onClick={() => {
              onSubmit().catch(() => {})
            }}
          >
            {saving ? '提交中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}

function RequirementComposer({
  mode,
  open,
  draft,
  saving,
  selected,
  onChange,
  onClose,
  onSubmit,
}: Readonly<{
  mode: DrawerMode
  open: boolean
  draft: RequirementDraft
  saving: boolean
  selected: AgentRequirement | null
  onChange: (patch: Partial<RequirementDraft>) => void
  onClose: () => void
  onSubmit: () => Promise<void>
}>) {
  const editing = mode === 'edit'
  const Container = editing ? OverlayDrawer : OverlayModal

  return (
    <Container open={open} title={editing ? '编辑需求' : '新建需求'} eyebrow={editing ? `Requirement #${selected?.id ?? '-'}` : 'New Requirement'} onClose={onClose}>
      <RequirementForm draft={draft} saving={saving} onChange={onChange} onClose={onClose} onSubmit={onSubmit} />
    </Container>
  )
}

export default function RequirementPool() {
  const navigate = useNavigate()
  const [requirements, setRequirements] = useState<AgentRequirement[]>([])
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [submittingId, setSubmittingId] = useState<number | null>(null)
  const [selectedRequirementId, setSelectedRequirementId] = useState<number | null>(null)
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('closed')
  const [draft, setDraft] = useState<RequirementDraft>({ ...EMPTY_DRAFT })

  const load = async () => {
    setLoading(true)
    try {
      setRequirements(await api.getRequirements(status || undefined, undefined, search || undefined))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [status])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return requirements
    return requirements.filter((item) =>
      [item.title, item.source_ref || '', item.target_project_path || '', String(item.id)].join('\n').toLowerCase().includes(needle),
    )
  }, [requirements, search])

  useEffect(() => {
    if (selectedRequirementId && filtered.some((item) => item.id === selectedRequirementId)) return
    setSelectedRequirementId(filtered[0]?.id ?? null)
  }, [filtered, selectedRequirementId])

  const selectedRequirement = filtered.find((item) => item.id === selectedRequirementId) ?? null

  const openCreate = () => {
    setDraft({ ...EMPTY_DRAFT })
    setDrawerMode('create')
  }

  const openEdit = (requirement: AgentRequirement) => {
    setSelectedRequirementId(requirement.id)
    setDraft(buildDraft(requirement))
    setDrawerMode('edit')
  }

  const closeComposer = () => {
    setDrawerMode('closed')
    setDraft({ ...EMPTY_DRAFT })
  }

  const handleSubmit = async () => {
    setSaving(true)
    try {
      if (drawerMode === 'create') {
        await api.createRequirement(draft)
      } else if (drawerMode === 'edit' && selectedRequirement) {
        await api.updateRequirement(selectedRequirement.id, draft)
      }
      await load()
      closeComposer()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5" data-testid="agent-first-requirements-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Requirements</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">需求列表</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">全部状态</option>
              <option value="draft">草稿</option>
              <option value="ready">待执行</option>
              <option value="running">执行中</option>
              <option value="blocked">阻塞</option>
              <option value="needs_revision">需修订</option>
              <option value="delivery_ready">待发布</option>
              <option value="done">已完成</option>
            </select>
            <input
              className="w-72 rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm"
              placeholder="搜索标题 / 项目 / ID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
              刷新
            </button>
            <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2.5 text-sm font-medium text-white" onClick={openCreate}>
              新建需求
            </button>
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse">
            <thead className="bg-slate-50/90">
              <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                <th className="px-5 py-4 font-medium">标题</th>
                <th className="px-4 py-4 font-medium">状态</th>
                <th className="px-4 py-4 font-medium">优先级</th>
                <th className="px-4 py-4 font-medium">审批</th>
                <th className="px-4 py-4 font-medium">执行 / 发布</th>
                <th className="px-4 py-4 font-medium">更新时间</th>
                <th className="px-5 py-4 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => {
                const selected = item.id === selectedRequirementId
                return (
                  <tr
                    key={item.id}
                    className={[
                      'border-t border-[color:var(--ops-stroke-soft)] transition',
                      selected ? 'bg-[color:var(--ops-accent-soft)]/40' : 'hover:bg-slate-50/80',
                    ].join(' ')}
                    onClick={() => setSelectedRequirementId(item.id)}
                  >
                    <td className="px-5 py-4">
                      <button type="button" className="text-left" onClick={() => navigate(`/requirements/${item.id}`)}>
                        <div className="text-base font-semibold text-[color:var(--ops-text-title)]">{item.title}</div>
                        <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">#{item.id}</div>
                      </button>
                    </td>
                    <td className="px-4 py-4">
                      <StateBadge tone={statusTone(item.status)}>{STATUS_LABEL[item.status] || item.status}</StateBadge>
                    </td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-body)]">{item.priority}</td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.approval_required ? item.approval_status : 'waived'}</td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                      execution {item.active_execution_run_id ?? item.latest_execution_run_id ?? '-'} · {item.latest_release_status ?? '-'}
                    </td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(item.updated_at)}</td>
                    <td className="px-5 py-4">
                      <div className="flex flex-wrap justify-end gap-2">
                        <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => openEdit(item)}>
                          编辑
                        </button>
                        <button
                          type="button"
                          className="rounded-lg border border-[color:var(--ops-state-blocked-border)] px-3 py-2 text-sm text-[color:var(--ops-state-blocked-text)] disabled:opacity-50"
                          disabled={deletingId === item.id}
                          onClick={async () => {
                            if (!window.confirm(`确认删除需求 #${item.id} 吗？`)) return
                            setDeletingId(item.id)
                            try {
                              await api.deleteRequirement(item.id)
                              await load()
                            } finally {
                              setDeletingId(null)
                            }
                          }}
                        >
                          {deletingId === item.id ? '删除中…' : '删除'}
                        </button>
                        <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/requirements/${item.id}`)}>
                          查看
                        </button>
                        <button
                          type="button"
                          className="rounded-lg bg-[color:var(--ops-text-title)] px-3 py-2 text-sm text-white disabled:opacity-50"
                          disabled={submittingId === item.id || (item.status !== 'draft' && item.status !== 'needs_revision')}
                          onClick={async () => {
                            setSubmittingId(item.id)
                            try {
                              const detail = await api.submitRequirement(item.id)
                              if (detail.approval.execution_run_id && detail.approval.auto_started) {
                                navigate(`/executions/${detail.approval.execution_run_id}`)
                                return
                              }
                              navigate(`/requirements/${item.id}`)
                            } finally {
                              await load()
                              setSubmittingId(null)
                            }
                          }}
                        >
                          {submittingId === item.id ? '提交中…' : '提交'}
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {!loading && filtered.length === 0 && (
          <div className="p-6">
            <EmptyPane>
              <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-medium text-white" onClick={openCreate}>
                新建需求
              </button>
            </EmptyPane>
          </div>
        )}
      </section>

      <RequirementComposer
        mode={drawerMode}
        open={drawerMode !== 'closed'}
        draft={draft}
        saving={saving}
        selected={selectedRequirement}
        onChange={(patch) => setDraft((current) => ({ ...current, ...patch }))}
        onClose={closeComposer}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
