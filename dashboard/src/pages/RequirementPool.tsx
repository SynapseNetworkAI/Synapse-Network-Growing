import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, Requirement } from '../api'

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  ready: '已规划',
  in_progress: '执行中',
  done: '已完成',
  needs_revision: '需修订',
  blocked: '阻塞',
}

const STATUS_CLASS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  ready: 'bg-sky-100 text-sky-700',
  in_progress: 'bg-blue-100 text-blue-700',
  done: 'bg-green-100 text-green-700',
  needs_revision: 'bg-amber-100 text-amber-700',
  blocked: 'bg-red-100 text-red-700',
}

function formatTime(value: string | null) {
  if (!value) return '-'
  const d = new Date(value.endsWith('Z') ? value : value + 'Z')
  return d.toLocaleString('zh-CN')
}

export default function RequirementPool() {
  const navigate = useNavigate()
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [statusFilter, setStatusFilter] = useState('')
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
    const data = await api.getRequirements(statusFilter || undefined)
    // Sort: in_progress first, then by created_at desc
    data.sort((a, b) => {
      if (a.status === 'in_progress' && b.status !== 'in_progress') return -1
      if (b.status === 'in_progress' && a.status !== 'in_progress') return 1
      return 0
    })
    setRequirements(data)
  }, [statusFilter])

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

  return (
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
            <option value="in_progress">执行中</option>
            <option value="done">已完成</option>
            <option value="blocked">阻塞</option>
            <option value="needs_revision">需修订</option>
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
            <div className="text-xs text-gray-500">目标项目路径（可选，每行一个路径）</div>
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
                    !q || r.title.toLowerCase().includes(q) || String(r.id).includes(q)
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
        {requirements.map((requirement) => (
          <button
            key={requirement.id}
            data-testid={`requirement-card-${requirement.id}`}
            className="w-full p-4 text-left transition bg-white border shadow-sm rounded-xl hover:border-blue-300 hover:shadow-md"
            onClick={() => navigate(`/requirements/${requirement.id}`)}
          >
            <div className="flex items-start justify-between gap-3 mb-2">
              <div>
                <div className="text-sm font-semibold text-gray-900">{requirement.title}</div>
                <div className="mt-1 text-xs text-gray-500">Plan v{requirement.current_plan_version || 0}</div>
              </div>
              <span className={`rounded-full px-2 py-1 text-xs font-medium ${STATUS_CLASS[requirement.status] || STATUS_CLASS.draft}`}>
                {STATUS_LABEL[requirement.status] || requirement.status}
              </span>
            </div>
            {requirement.target_project_path && (
              <div className="mb-2 text-xs text-blue-700 truncate">{requirement.target_project_path}</div>
            )}
            <div className="text-xs text-gray-600 line-clamp-3">{requirement.description_markdown}</div>
            <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
              <span>优先级: {requirement.priority}</span>
              <span>阻塞: {requirement.blocked_by_count}</span>
              <span>{formatTime(requirement.updated_at)}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}