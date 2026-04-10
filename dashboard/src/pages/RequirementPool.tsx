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
    setRequirements(data)
  }, [statusFilter])

  useEffect(() => {
    loadRequirements().catch(() => {})
  }, [loadRequirements])

  // Poll while any in_progress
  useEffect(() => {
    if (!requirements.some((r) => r.status === 'in_progress')) return
    const timer = setInterval(() => { loadRequirements().catch(() => {}) }, 2500)
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
            className="rounded border px-3 py-2 text-sm"
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
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            onClick={() => setShowCreate((v) => !v)}
          >
            新建需求
          </button>
        </div>
      </div>

      {showCreate && (
        <div data-testid="requirement-create-form" className="rounded-xl border bg-white p-5 shadow-sm space-y-3">
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
            className="min-h-32 w-full rounded border px-3 py-2"
            placeholder="用 Markdown 描述需求、目标和约束"
            value={form.description_markdown}
            onChange={(e) => setForm((prev) => ({ ...prev, description_markdown: e.target.value }))}
          />
          <input
            data-testid="requirement-target-project"
            className="w-full rounded border px-3 py-2 text-sm"
            placeholder="目标项目路径 (可选, 如 /Users/cliff/workspace/agent/Synapse-Network)"
            value={form.target_project_path}
            onChange={(e) => setForm((prev) => ({ ...prev, target_project_path: e.target.value }))}
          />
          <div className="flex items-end gap-2">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-500">优先级</label>
              <select
                data-testid="requirement-priority"
                className="rounded border px-3 py-2 text-sm"
                value={form.priority}
                onChange={(e) => setForm((prev) => ({ ...prev, priority: e.target.value }))}
              >
                <option value="low">low</option>
                <option value="normal">normal</option>
                <option value="high">high</option>
              </select>
            </div>
            <div className="flex flex-1 flex-col gap-1">
              <label className="text-xs text-gray-500">前置依赖（勾选后等依赖完成才启动）</label>
              <div data-testid="create-dependencies" className="max-h-28 flex-1 overflow-auto rounded border px-3 py-2 text-xs text-gray-600">
              {requirements.length === 0 ? (
                <div>暂无可选依赖</div>
              ) : (
                requirements.map((r) => (
                  <label key={r.id} className="flex items-center gap-2 py-1">
                    <input
                      data-testid={`create-dependency-${r.id}`}
                      type="checkbox"
                      checked={form.depends_on_requirement_ids.includes(r.id)}
                      onChange={() => setForm((prev) => ({
                        ...prev,
                        depends_on_requirement_ids: toggleDependency(prev.depends_on_requirement_ids, r.id),
                      }))}
                    />
                    <span>{r.title}</span>
                    <span className="text-gray-400">{STATUS_LABEL[r.status] || r.status}</span>
                  </label>
                ))
              )}
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
              className="rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-50"
              disabled={submitting}
              onClick={() => { handleCreate().catch(() => {}) }}
            >
              {form.auto_start ? '创建并启动' : '创建并保存'}
            </button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {requirements.length === 0 && (
          <div data-testid="requirements-empty" className="rounded-xl border border-dashed bg-white p-6 text-sm text-gray-500">
            还没有 requirement。先创建一条需求，再规划和启动 workflow。
          </div>
        )}
        {requirements.map((requirement) => (
          <button
            key={requirement.id}
            data-testid={`requirement-card-${requirement.id}`}
            className="w-full rounded-xl border bg-white p-4 text-left shadow-sm transition hover:border-blue-300 hover:shadow-md"
            onClick={() => navigate(`/requirements/${requirement.id}`)}
          >
            <div className="mb-2 flex items-start justify-between gap-3">
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
            <div className="line-clamp-3 text-xs text-gray-600">{requirement.description_markdown}</div>
            <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
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