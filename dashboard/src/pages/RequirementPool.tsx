import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, Requirement } from '../api'

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  ready: '已规划',
  paused: '已暂停',
  in_progress: '执行中',
  done: '已完成',
  needs_revision: '需修订',
  blocked: '阻塞',
  deleted: '已删除',
}

const STATUS_CLASS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  ready: 'bg-sky-100 text-sky-700',
  paused: 'bg-slate-200 text-slate-700',
  in_progress: 'bg-blue-100 text-blue-700',
  done: 'bg-green-100 text-green-700',
  needs_revision: 'bg-amber-100 text-amber-700',
  blocked: 'bg-red-100 text-red-700',
  deleted: 'bg-zinc-200 text-zinc-700',
}

function formatTime(value: string | null) {
  if (!value) return '-'
  const d = new Date(value.endsWith('Z') ? value : value + 'Z')
  return d.toLocaleString('zh-CN')
}

function getTargetProjectPaths(value: string | null) {
  if (!value) return []
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

function getRequirementSortRank(requirement: Requirement) {
  if (requirement.status === 'in_progress') return 0
  if (requirement.status === 'deleted') return 2
  return 1
}

function getRequirementSortTimestamp(requirement: Requirement) {
  const timestamp = Date.parse(requirement.updated_at ?? requirement.created_at ?? '')
  return Number.isNaN(timestamp) ? 0 : timestamp
}

function sortRequirements(requirements: Requirement[], sortMode: string) {
  return [...requirements].sort((a, b) => {
    const rankDiff = getRequirementSortRank(a) - getRequirementSortRank(b)
    if (rankDiff !== 0) return rankDiff

    if (sortMode === 'score') {
      const scoreDiff = (b.score_breakdown?.total ?? 0) - (a.score_breakdown?.total ?? 0)
      if (scoreDiff !== 0) return scoreDiff
    }

    const timeDiff = getRequirementSortTimestamp(b) - getRequirementSortTimestamp(a)
    if (timeDiff !== 0) return timeDiff

    return b.id - a.id
  })
}

export default function RequirementPool() {
  const navigate = useNavigate()
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [sortMode, setSortMode] = useState('score')
  const [actioningRequirementId, setActioningRequirementId] = useState<number | null>(null)
  const [editingRequirement, setEditingRequirement] = useState<{
    id: number
    title: string
    description_markdown: string
    priority: string
    target_project_path: string
  } | null>(null)
  const [editRequirementSaving, setEditRequirementSaving] = useState(false)
  const [deleteRequirementSavingId, setDeleteRequirementSavingId] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 10
  const [showCreate, setShowCreate] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [titleError, setTitleError] = useState(false)
  const [depQuery, setDepQuery] = useState('')
  const [depOpen, setDepOpen] = useState(false)
  const [form, setForm] = useState({
    title: '',
    description_markdown: '',
    priority: 'normal',
    target_project_path: '',
    depends_on_requirement_ids: [] as number[],
    auto_start: true,
  })

  const loadRequirements = useCallback(async () => {
    const data = await api.getRequirements(statusFilter || undefined, sortMode === 'score' ? 'score' : undefined)
    setRequirements(sortRequirements(data, sortMode))
    setPage(1)
  }, [sortMode, statusFilter])

  useEffect(() => {
    loadRequirements().catch(() => {})
  }, [loadRequirements])

  // Auto-advance queue on first load if nothing in_progress
  useEffect(() => {
    api.advanceQueue().then(() => loadRequirements().catch(() => {})).catch(() => {})
  }, [])

  // Poll while any in_progress or ready (plan may be generating)
  useEffect(() => {
    const needsPoll = requirements.some((r) => r.status === 'in_progress' || (r.status === 'ready' && r.current_plan_version === 0))
    if (!needsPoll) return
    const timer = setInterval(() => { loadRequirements().catch(() => {}) }, 3000)
    return () => clearInterval(timer)
  }, [requirements, loadRequirements])

  const handleCreate = async () => {
    if (!form.title.trim()) {
      setTitleError(true)
      return
    }
    if (!form.description_markdown.trim()) return
    setTitleError(false)
    setSubmitting(true)
    try {
      const created = await api.createRequirement({
        title: form.title.trim(),
        description_markdown: form.description_markdown.trim(),
        priority: form.priority,
        target_project_path: form.target_project_path.trim() || undefined,
        depends_on_requirement_ids: form.depends_on_requirement_ids,
        auto_start: form.auto_start,
      })
      setShowCreate(false)
      setTitleError(false)
      setDepQuery('')
      setDepOpen(false)
      setForm({ title: '', description_markdown: '', priority: 'normal', target_project_path: '', depends_on_requirement_ids: [], auto_start: true })
      setPage(1)
      await loadRequirements()
      navigate(`/requirements/${created.requirement.id}`)
    } finally {
      setSubmitting(false)
    }
  }

  const toggleDependency = (values: number[], requirementId: number) => {
    if (values.includes(requirementId)) return values.filter((v) => v !== requirementId)
    return [...values, requirementId]
  }

  const handleExecutionToggle = async (requirement: Requirement) => {
    setActioningRequirementId(requirement.id)
    try {
      if (requirement.status === 'in_progress') {
        await api.pauseRequirement(requirement.id)
      } else {
        await api.startRequirement(requirement.id)
      }
      await loadRequirements()
    } finally {
      setActioningRequirementId(null)
    }
  }

  const handleOpenEditRequirement = (requirement: Requirement) => {
    setEditingRequirement({
      id: requirement.id,
      title: requirement.title,
      description_markdown: requirement.description_markdown,
      priority: requirement.priority,
      target_project_path: requirement.target_project_path || '',
    })
  }

  const handleSaveRequirement = async () => {
    if (!editingRequirement) return
    setEditRequirementSaving(true)
    try {
      await api.updateRequirement(editingRequirement.id, {
        title: editingRequirement.title,
        description_markdown: editingRequirement.description_markdown,
        priority: editingRequirement.priority,
        target_project_path: editingRequirement.target_project_path || undefined,
      })
      setEditingRequirement(null)
      await loadRequirements()
    } catch (error) {
      alert(error instanceof Error ? error.message : '保存失败')
    } finally {
      setEditRequirementSaving(false)
    }
  }

  const handleDeleteRequirement = async (requirement: Requirement) => {
    const confirmed = window.confirm(`确认逻辑删除需求「${requirement.title}」吗？这会把关联 workflow 和下游依赖需求一起标记为已删除。`)
    if (!confirmed) return
    setDeleteRequirementSavingId(requirement.id)
    try {
      await api.deleteRequirement(requirement.id)
      if (editingRequirement?.id === requirement.id) {
        setEditingRequirement(null)
      }
      await loadRequirements()
    } catch (error) {
      alert(error instanceof Error ? error.message : '删除失败')
    } finally {
      setDeleteRequirementSavingId(null)
    }
  }

  const hasRunningRequirement = requirements.some((requirement) => requirement.status === 'in_progress')

  return (
    <>
    <div data-testid="requirements-page" className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">需求池</h2>
          <p className="text-sm text-gray-500">Requirement-first workflow orchestration with validation and bugfix loop.</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            data-testid="requirement-status-filter"
            className="px-3 py-2 text-sm border rounded"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">全部状态</option>
            <option value="draft">草稿</option>
            <option value="ready">已规划</option>
            <option value="paused">已暂停</option>
            <option value="in_progress">执行中</option>
            <option value="done">已完成</option>
            <option value="blocked">阻塞</option>
            <option value="needs_revision">需修订</option>
            <option value="deleted">已删除</option>
          </select>
          <select
            data-testid="requirement-sort-mode"
            className="px-3 py-2 text-sm border rounded"
            value={sortMode}
            onChange={(e) => setSortMode(e.target.value)}
          >
            <option value="score">智能排序</option>
            <option value="updated">最近更新</option>
          </select>
          <button
            data-testid="create-requirement-btn"
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700"
            onClick={() => setShowCreate((v) => !v)}
          >
            新建需求
          </button>
        </div>
      </div>

      {showCreate && (
        <div data-testid="requirement-create-form" className="p-5 space-y-3 bg-white border shadow-sm rounded-xl">
          <div>
            <input
              data-testid="requirement-title"
              className={`w-full rounded border px-3 py-2 ${titleError ? 'border-red-500 ring-1 ring-red-500' : ''}`}
              placeholder="需求标题"
              value={form.title}
              onChange={(e) => {
                setTitleError(false)
                setForm((prev) => ({ ...prev, title: e.target.value }))
              }}
            />
            {titleError && (
              <p className="mt-1 text-xs text-red-500">请填写需求标题</p>
            )}
          </div>
          <textarea
            data-testid="requirement-description"
            className="w-full px-3 py-2 border rounded min-h-32"
            placeholder="用 Markdown 描述需求、目标和约束"
            value={form.description_markdown}
            onChange={(e) => setForm((prev) => ({ ...prev, description_markdown: e.target.value }))}
          />
          <div className="space-y-1">
            <div className="text-xs text-gray-500">目标项目路径（可选，每行一个路径；留空时会按项目 readiness 和语义自动路由）</div>
            <textarea
              data-testid="requirement-target-project"
              className="w-full px-3 py-2 font-mono text-sm leading-relaxed border rounded"
              rows={3}
              placeholder={`/Users/cliff/workspace/agent/Synapse-Network\n/Users/cliff/workspace/agent/Synapse-Network-Growing`}
              value={form.target_project_path}
              onChange={(e) => setForm((prev) => ({ ...prev, target_project_path: e.target.value }))}
            />
          </div>
          <div className="flex items-end gap-2">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-500">优先级</label>
              <select
                data-testid="requirement-priority"
                className="px-3 py-2 text-sm border rounded"
                value={form.priority}
                onChange={(e) => setForm((prev) => ({ ...prev, priority: e.target.value }))}
              >
                <option value="low">low</option>
                <option value="normal">normal</option>
                <option value="high">high</option>
              </select>
            </div>
            <div className="flex flex-col flex-1 gap-1">
              <div className="text-xs text-gray-500">前置依赖（选后等依赖完成才启动）</div>
              <div data-testid="create-dependencies" className="relative">
                {/* Selected chips */}
                {form.depends_on_requirement_ids.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-1">
                    {form.depends_on_requirement_ids.map((rid) => {
                      const r = requirements.find((x) => x.id === rid)
                      return (
                        <span key={rid} className="flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-800">
                          <span className="max-w-[140px] truncate">{r?.title ?? `#${rid}`}</span>
                          <button
                            type="button"
                            className="ml-0.5 text-blue-400 hover:text-blue-700 leading-none"
                            onMouseDown={() => setForm((prev) => ({
                              ...prev,
                              depends_on_requirement_ids: prev.depends_on_requirement_ids.filter((v) => v !== rid),
                            }))}
                          >×</button>
                        </span>
                      )
                    })}
                  </div>
                )}
                {/* Search input */}
                <input
                  data-testid="create-dependency-search"
                  className="w-full px-3 py-2 text-sm border rounded"
                  placeholder="搜索需求名称…"
                  value={depQuery}
                  onFocus={() => setDepOpen(true)}
                  onChange={(e) => { setDepQuery(e.target.value); setDepOpen(true) }}
                  onBlur={() => setTimeout(() => setDepOpen(false), 150)}
                />
                {/* Dropdown list */}
                {depOpen && (() => {
                  const q = depQuery.toLowerCase()
                  const filtered = requirements.filter((r) =>
                    r.status !== 'deleted' && (
                    !q || r.title.toLowerCase().includes(q) || String(r.id).includes(q)
                    )
                  )
                  return (
                    <div className="absolute z-20 w-full mt-1 overflow-auto bg-white border rounded-lg shadow-lg max-h-48">
                      {filtered.length === 0 ? (
                        <div className="px-3 py-2 text-xs text-gray-400">无匹配需求</div>
                      ) : filtered.map((r) => {
                        const selected = form.depends_on_requirement_ids.includes(r.id)
                        return (
                          <button
                            key={r.id}
                            type="button"
                            data-testid={`create-dependency-${r.id}`}
                            className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm transition hover:bg-blue-50 ${
                              selected ? 'bg-blue-50' : ''
                            }`}
                            onMouseDown={() => setForm((prev) => ({
                              ...prev,
                              depends_on_requirement_ids: toggleDependency(prev.depends_on_requirement_ids, r.id),
                            }))}
                          >
                            <span className="flex-1 truncate">{r.title}</span>
                            <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_CLASS[r.status] || ''}`}>
                              {STATUS_LABEL[r.status] || r.status}
                            </span>
                            {selected && <span className="text-xs text-blue-600 shrink-0">✓</span>}
                          </button>
                        )
                      })}
                    </div>
                  )
                })()}
              </div>
            </div>
            <label className="flex items-center gap-2 py-2">
              <input
                data-testid="auto-start-checkbox"
                type="checkbox"
                checked={form.auto_start}
                onChange={() => setForm((prev) => ({ ...prev, auto_start: !prev.auto_start }))}
              />
              <span className="text-sm">创建后自动生成计划并启动执行</span>
            </label>
            <button
              data-testid="submit-requirement-btn"
              className="px-4 py-2 text-sm font-medium text-white bg-gray-900 rounded hover:bg-black disabled:opacity-50"
              disabled={submitting}
              onClick={() => { handleCreate().catch(() => {}) }}
            >
              {form.auto_start ? '创建并启动' : '创建并保存'}
            </button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {/* Queue status banner */}
        {!showCreate && (() => {
          const inProgress = requirements.filter((r) => r.status === 'in_progress')
          const readyCount = requirements.filter((r) => r.status === 'ready' && r.current_plan_version === 0).length
          const plannedCount = requirements.filter((r) => r.status === 'ready' && r.current_plan_version > 0).length
          if (inProgress.length > 0) return (
            <div className="flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-2.5 text-xs text-blue-700">
              <span className="inline-block h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
              <span>正在执行：<span className="font-medium">{inProgress[0].title}</span></span>
              {readyCount + plannedCount > 0 && <span className="ml-auto text-blue-400">队列中还有 {readyCount + plannedCount} 个需求</span>}
            </div>
          )
          if (readyCount + plannedCount > 0) return (
            <div className="flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-700">
              <span>队列中有 <span className="font-medium">{readyCount + plannedCount}</span> 个待执行需求</span>
              <button
                className="ml-3 rounded bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700"
                onClick={() => api.advanceQueue().then(() => loadRequirements().catch(() => {})).catch(() => {})}
              >启动下一个</button>
            </div>
          )
          return null
        })()}
        {requirements.length === 0 && (
          <div data-testid="requirements-empty" className="p-6 text-sm text-gray-500 bg-white border border-dashed rounded-xl">
            还没有 requirement。先创建一条需求，再规划和启动 workflow。
          </div>
        )}
        {requirements.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((requirement) => {
          const showToggle = requirement.status === 'in_progress' || ((requirement.status === 'ready' || requirement.status === 'paused') && requirement.current_plan_version > 0)
          const isRunning = requirement.status === 'in_progress'
          const isDeleted = requirement.status === 'deleted'
          const targetProjectPaths = getTargetProjectPaths(requirement.target_project_path)
          const routingContext = requirement.routing_context
          const projectScorecards = routingContext?.project_scorecards || []
          let toggleLabel = '启动'
          if (actioningRequirementId === requirement.id) {
            toggleLabel = '处理中…'
          } else if (isRunning) {
            toggleLabel = '暂停'
          }

          return (
            <div
              key={requirement.id}
              data-testid={`requirement-card-${requirement.id}`}
              className="w-full p-4 text-left transition bg-white border shadow-sm rounded-xl hover:border-blue-300 hover:shadow-md"
            >
              <div className="flex items-start gap-3">
                <button
                  type="button"
                  className="flex-1 text-left"
                  onClick={() => navigate(`/requirements/${requirement.id}`)}
                >
                  <div className="mb-2">
                    <div className="text-sm font-semibold text-gray-900">{requirement.title}</div>
                    <div className="mt-1 text-xs text-gray-500">Plan v{requirement.current_plan_version || 0}</div>
                  </div>
                  {targetProjectPaths.length > 0 && (
                    <div className="mb-2 rounded-md bg-blue-50 px-3 py-2 text-xs text-blue-800">
                      <div className="mb-1 font-medium">目标项目:</div>
                      <div className="space-y-1 font-mono">
                        {targetProjectPaths.map((projectPath) => (
                          <div key={projectPath} className="break-all">{projectPath}</div>
                        ))}
                      </div>
                    </div>
                  )}
                  {routingContext?.summary && (
                    <div
                      className={`mb-2 rounded-md px-3 py-2 text-xs ${
                        routingContext.automation_ready
                          ? 'bg-emerald-50 text-emerald-800'
                          : 'bg-amber-50 text-amber-800'
                      }`}
                    >
                      <div className="font-medium">
                        路由: {routingContext.routing_mode} / readiness: {routingContext.readiness_status}
                      </div>
                      <div className="mt-1">{routingContext.summary}</div>
                    </div>
                  )}
                  {projectScorecards.length > 0 && (
                    <div className="mb-2 grid gap-2 md:grid-cols-2">
                      {projectScorecards.map((project) => (
                        <div
                          key={`${requirement.id}-${project.project_key}`}
                          className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-700"
                        >
                          <div className="font-medium">{project.display_name}</div>
                          <div>readiness: {project.readiness_status} ({project.readiness_score})</div>
                          <div>bug pressure: {project.bug_report_count}</div>
                          <div>blocked publish: {project.blocked_publish_count}</div>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="text-xs text-gray-600 line-clamp-3">{requirement.description_markdown}</div>
                  <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
                    <span>优先级: {requirement.priority}</span>
                    <span>阻塞: {requirement.blocked_by_count}</span>
                    <span>Score: {requirement.score_breakdown?.total ?? 0}</span>
                    <span>{formatTime(requirement.updated_at)}</span>
                  </div>
                </button>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    data-testid={`requirement-edit-${requirement.id}`}
                    className="rounded-lg px-3 py-1.5 text-xs font-medium border border-gray-200 text-gray-600 hover:bg-gray-50 transition"
                    disabled={isDeleted}
                    onClick={(event) => {
                      event.stopPropagation()
                      handleOpenEditRequirement(requirement)
                    }}
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    data-testid={`requirement-delete-${requirement.id}`}
                    className="rounded-lg px-3 py-1.5 text-xs font-medium border border-red-200 text-red-600 hover:bg-red-50 transition disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={isDeleted || deleteRequirementSavingId === requirement.id}
                    onClick={(event) => {
                      event.stopPropagation()
                      handleDeleteRequirement(requirement).catch(() => {})
                    }}
                  >
                    {deleteRequirementSavingId === requirement.id ? '删除中…' : '删除'}
                  </button>
                  {showToggle && (
                    <button
                      type="button"
                      data-testid={`requirement-toggle-${requirement.id}`}
                      className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                        isRunning
                          ? 'border border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100'
                          : 'bg-blue-600 text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50'
                      }`}
                      disabled={isDeleted || actioningRequirementId === requirement.id || (!isRunning && hasRunningRequirement)}
                      onClick={(event) => {
                        event.stopPropagation()
                        handleExecutionToggle(requirement).catch(() => {})
                      }}
                    >
                      {toggleLabel}
                    </button>
                  )}
                  <span className={`rounded-full px-2 py-1 text-xs font-medium ${STATUS_CLASS[requirement.status] || STATUS_CLASS.draft}`}>
                    {STATUS_LABEL[requirement.status] || requirement.status}
                  </span>
                </div>
              </div>
            </div>
          )
        })}

        {/* Pagination */}
        {requirements.length > PAGE_SIZE && (() => {
          const totalPages = Math.ceil(requirements.length / PAGE_SIZE)
          const start = (page - 1) * PAGE_SIZE + 1
          const end = Math.min(page * PAGE_SIZE, requirements.length)
          return (
            <div className="flex items-center justify-between pt-1 text-xs text-gray-500">
              <span>{start}–{end} / {requirements.length} 条需求</span>
              <div className="flex items-center gap-1">
                <button
                  className="rounded border px-2 py-1 hover:bg-gray-50 disabled:opacity-40"
                  disabled={page === 1}
                  onClick={() => setPage((p) => p - 1)}
                >‹ 上一页</button>
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                  <button
                    key={p}
                    className={`rounded border px-2.5 py-1 ${
                      p === page ? 'bg-blue-600 text-white border-blue-600' : 'hover:bg-gray-50'
                    }`}
                    onClick={() => setPage(p)}
                  >{p}</button>
                ))}
                <button
                  className="rounded border px-2 py-1 hover:bg-gray-50 disabled:opacity-40"
                  disabled={page === totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >下一页 ›</button>
              </div>
            </div>
          )
        })()}
      </div>
    </div>

    {editingRequirement && (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setEditingRequirement(null)}>
        <div className="bg-white rounded-xl p-6 max-w-xl w-full max-h-[80vh] overflow-auto shadow-xl space-y-4" onClick={(e) => e.stopPropagation()} data-testid="edit-requirement-modal">
          <h3 className="font-bold text-base">编辑需求 #{editingRequirement.id}</h3>
          <div className="space-y-1">
            <label className="text-xs text-gray-500">标题</label>
            <input
              data-testid="edit-requirement-title"
              className="w-full border rounded px-3 py-2 text-sm"
              value={editingRequirement.title}
              onChange={(e) => setEditingRequirement({ ...editingRequirement, title: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-gray-500">需求描述 (Markdown)</label>
            <textarea
              data-testid="edit-requirement-description"
              className="w-full border rounded px-3 py-2 text-sm min-h-[120px] font-mono resize-y"
              value={editingRequirement.description_markdown}
              onChange={(e) => setEditingRequirement({ ...editingRequirement, description_markdown: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-gray-500">优先级</label>
            <select
              data-testid="edit-requirement-priority"
              className="w-full border rounded px-3 py-2 text-sm"
              value={editingRequirement.priority}
              onChange={(e) => setEditingRequirement({ ...editingRequirement, priority: e.target.value })}
            >
              <option value="low">低</option>
              <option value="normal">普通</option>
              <option value="high">⚡ 高</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-gray-500">目标项目路径（每行一个）</label>
            <textarea
              data-testid="edit-requirement-target"
              className="w-full border rounded px-3 py-2 text-sm font-mono min-h-[64px] resize-y"
              value={editingRequirement.target_project_path}
              onChange={(e) => setEditingRequirement({ ...editingRequirement, target_project_path: e.target.value })}
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setEditingRequirement(null)}
              className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700"
            >
              取消
            </button>
            <button
              data-testid="save-requirement-btn"
              disabled={editRequirementSaving || !editingRequirement.title.trim() || !editingRequirement.description_markdown.trim()}
              onClick={() => { handleSaveRequirement().catch(() => {}) }}
              className="px-4 py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {editRequirementSaving ? '保存中…' : '保存'}
            </button>
          </div>
        </div>
      </div>
    )}
  </>
  )
}
