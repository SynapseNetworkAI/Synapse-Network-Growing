import { useEffect, useState, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import { useNavigate } from 'react-router-dom'
import { api, Task, Agent, TaskLog, TaskExecutionSuggestion, ApiError } from '../api'

const RETRYABLE_STATUSES = new Set(['failed', 'rejected'])

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-700',
  pending_approval: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  failed: 'bg-red-100 text-red-700',
}

const STATUS_LABEL: Record<string, string> = {
  pending: '待执行',
  running: '执行中',
  pending_approval: '待审批',
  completed: '已完成',
  rejected: '已拒绝',
  failed: '失败',
}

function Md({ children }: Readonly<{ children: string }>) {
  return (
    <div className="prose prose-sm max-w-none prose-headings:text-base prose-p:my-1 prose-ul:my-1 prose-li:my-0.5">
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  )
}

function getTaskErrorSummary(task: Task) {
  if (task.last_error_message) return task.last_error_message
  if (task.output_content?.startsWith('[ERROR] ')) return task.output_content.replace('[ERROR] ', '').trim()
  return ''
}

function toUtcDate(value: string): Date {
  // Backend sends UTC timestamps without 'Z' suffix; append it so Date parses as UTC.
  return new Date(value.endsWith('Z') ? value : value + 'Z')
}

function parseTime(value: string | null) {
  if (!value) return null
  const parsed = toUtcDate(value).getTime()
  return Number.isNaN(parsed) ? null : parsed
}

function getExecutionTimeMs(task: Task, nowMs: number) {
  // For running tasks, always compute from started_at for a live ticking timer.
  // execution_time_ms may have been set prematurely by the monitor.
  if (task.status === 'running') {
    const startedAt = parseTime(task.started_at)
    if (startedAt != null) return Math.max(nowMs - startedAt, 0)
    return null
  }

  if (task.execution_time_ms != null) return task.execution_time_ms

  const startedAt = parseTime(task.started_at)
  if (startedAt == null) return null

  const completedAt = parseTime(task.completed_at)
  if (completedAt == null) return null
  return Math.max(completedAt - startedAt, 0)
}

function formatDuration(ms: number | null) {
  if (ms == null) return null

  const totalSeconds = Math.max(ms / 1000, 0)
  if (totalSeconds < 60) {
    return `${totalSeconds.toFixed(1)}s`
  }

  const totalWholeSeconds = Math.floor(totalSeconds)
  const hours = Math.floor(totalWholeSeconds / 3600)
  const minutes = Math.floor((totalWholeSeconds % 3600) / 60)
  const seconds = totalWholeSeconds % 60
  if (hours > 0) {
    return `${hours}h ${String(minutes).padStart(2, '0')}m ${String(seconds).padStart(2, '0')}s`
  }
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

function taskCreatedAtValue(task: Task) {
  if (!task.created_at) return 0
  const parsed = Date.parse(task.created_at)
  return Number.isNaN(parsed) ? 0 : parsed
}

function compareTasksByNewestFirst(left: Task, right: Task) {
  const createdDiff = taskCreatedAtValue(right) - taskCreatedAtValue(left)
  if (createdDiff !== 0) return createdDiff
  return right.id - left.id
}

export default function TaskBoard() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<Task[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [skills, setSkills] = useState<string[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [projectFilter, setProjectFilter] = useState('')
  const [agentGroupFilter, setAgentGroupFilter] = useState('')
  const [agentFilter, setAgentFilter] = useState('')
  const [search, setSearch] = useState('')
  const [onlyAnomalies, setOnlyAnomalies] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ description: '', agent_id: '', requires_approval: false, priority: 'normal', skill_name: '' })
  const [preview, setPreview] = useState(false)
  const [suggestion, setSuggestion] = useState<TaskExecutionSuggestion | null>(null)
  const [suggestionLoading, setSuggestionLoading] = useState(false)
  const [suggestionMessage, setSuggestionMessage] = useState('')
  const [selectedLogs, setSelectedLogs] = useState<{ taskId: number; logs: TaskLog[] } | null>(null)
  const [runningSkill, setRunningSkill] = useState<Record<number, string>>({})
  const [selectedTaskIds, setSelectedTaskIds] = useState<number[]>([])
  const [nowMs, setNowMs] = useState(() => Date.now())
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const suggestionRequestRef = useRef(0)

  const load = useCallback(async () => {
    const [t, a] = await Promise.all([
      api.getTasks({
        status: statusFilter || undefined,
        project_id: projectFilter || undefined,
        agent_group: agentGroupFilter || undefined,
        agent_id: agentFilter || undefined,
        only_anomalies: onlyAnomalies || undefined,
      }),
      api.getAgents(),
    ])
    setTasks(t)
    setAgents(a)
  }, [statusFilter, projectFilter, agentGroupFilter, agentFilter, onlyAnomalies])

  useEffect(() => {
    api.getSkills().then(setSkills).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const hasRunning = tasks.some(t => t.status === 'running')
    if (hasRunning) {
      pollRef.current = setInterval(load, 3000)
    } else if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [tasks, load])

  useEffect(() => {
    if (!tasks.some((task) => task.status === 'running')) return
    const timer = setInterval(() => {
      setNowMs(Date.now())
    }, 1000)
    return () => clearInterval(timer)
  }, [tasks])

  useEffect(() => {
    setSelectedTaskIds((prev) => prev.filter((id) => tasks.some((task) => task.id === id && RETRYABLE_STATUSES.has(task.status))))
  }, [tasks])

  const selectedAgent = agents.find(a => a.id === form.agent_id)
  const selectedAgentSkills: string[] = (() => {
    if (!selectedAgent) return []
    try { return JSON.parse(selectedAgent.skills) } catch { return [] }
  })()

  const visibleTasks = tasks.filter((task) => {
    if (!search.trim()) return true
    const q = search.trim().toLowerCase()
    return [
      task.description,
      task.agent_id,
      task.skill_name || '',
      task.project_label || '',
      task.agent_group || '',
      task.requirement_title || '',
      getTaskErrorSummary(task),
    ].some((value) => value.toLowerCase().includes(q))
  })

  const groupedTasks = visibleTasks.reduce<Record<string, Task[]>>((acc, task) => {
    const key = task.project_label || task.project_id || '未分类'
    acc[key] ||= []
    acc[key].push(task)
    return acc
  }, {})

  const projectKeys = Array.from(new Set(tasks.map(t => t.project_id).filter(Boolean))) as string[]
  const groupKeys = Array.from(new Set(agents.map(a => a.group).filter(Boolean)))
  const selectedRetryableTaskIds = selectedTaskIds.filter((id) => {
    const task = tasks.find((candidate) => candidate.id === id)
    return task ? RETRYABLE_STATUSES.has(task.status) : false
  })
  const retryableTaskIds = visibleTasks.filter((task) => RETRYABLE_STATUSES.has(task.status)).map((task) => task.id)
  const allRetryableSelected = retryableTaskIds.length > 0 && retryableTaskIds.every((id) => selectedRetryableTaskIds.includes(id))

  const resolveSuggestion = useCallback(async (nextForm: typeof form) => {
    const description = nextForm.description.trim()
    if (!description) {
      setSuggestion(null)
      return null
    }
    const requestId = ++suggestionRequestRef.current
    setSuggestionLoading(true)
    try {
      const data = await api.suggestTaskExecution({
        description,
        agent_id: nextForm.agent_id || undefined,
        skill_name: nextForm.skill_name || undefined,
        limit: 3,
      })
      if (requestId !== suggestionRequestRef.current) return null
      setSuggestion(data)
      return data
    } catch {
      if (requestId === suggestionRequestRef.current) setSuggestion(null)
      return null
    } finally {
      if (requestId === suggestionRequestRef.current) setSuggestionLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!showCreate) return
    if (!form.description.trim()) {
      setSuggestion(null)
      setSuggestionMessage('')
      return
    }
    if (form.agent_id && form.skill_name) {
      setSuggestion(null)
      return
    }

    const timer = setTimeout(() => {
      resolveSuggestion(form)
    }, 250)
    return () => clearTimeout(timer)
  }, [showCreate, form, resolveSuggestion])

  const applySuggestion = (agentId: string, skillName: string) => {
    setForm((prev) => ({ ...prev, agent_id: agentId, skill_name: skillName }))
    setSuggestionMessage('')
  }

  const handleCreate = async () => {
    if (!form.description.trim()) return

    let taskAgentId = form.agent_id || undefined
    let taskSkillName = form.skill_name || undefined

    if (!taskAgentId || !taskSkillName) {
      const recommended = suggestion || await resolveSuggestion(form)
      if (!recommended?.agent_id) {
        alert('系统未能推断合适的 Agent / Skill，请手动选择后再提交')
        return
      }
      if (!taskAgentId && recommended.requires_confirmation) {
        setSuggestion(recommended)
        setSuggestionMessage('系统推荐置信度不足，请确认 Agent / Skill 后再提交')
        return
      }
      taskAgentId = taskAgentId || recommended.agent_id
      if (!taskSkillName && recommended.skill_name && (!recommended.requires_confirmation || recommended.agent_id === taskAgentId)) {
        taskSkillName = recommended.skill_name
      }
    }

    try {
      await api.createTask({
        description: form.description,
        agent_id: taskAgentId,
        requires_approval: form.requires_approval,
        priority: form.priority,
        skill_name: taskSkillName,
        confirm_auto_selection: true,
      })
      setForm({ description: '', agent_id: '', requires_approval: false, priority: 'normal', skill_name: '' })
      setSuggestion(null)
      setSuggestionMessage('')
      setShowCreate(false)
      setPreview(false)
      await load()
    } catch (error) {
      const detail = (error as ApiError).detail as { message?: string; suggestion?: TaskExecutionSuggestion } | undefined
      if (detail?.suggestion) {
        setSuggestion(detail.suggestion)
        setSuggestionMessage(detail.message || '请确认系统推荐的 Agent / Skill')
        return
      }
      alert(error instanceof Error ? error.message : '任务创建失败')
    }
  }

  const handleRun = async (id: number) => {
    const task = tasks.find(t => t.id === id)
    const skill = runningSkill[id] || task?.skill_name
    try {
      await api.runTask(id, skill || undefined)
      await load()
    } catch (error) {
      const detail = (error as ApiError).detail as { message?: string; suggestion?: TaskExecutionSuggestion } | undefined
      if (detail?.suggestion?.skill_name) {
        setRunningSkill((prev) => ({ ...prev, [id]: detail.suggestion?.skill_name || '' }))
        alert(detail.message || '系统已推荐 Skill，请确认后重新执行')
        return
      }
      if (!skill) {
        alert('请先选择一个 Skill 再执行')
        return
      }
      alert(error instanceof Error ? error.message : '任务执行失败')
    }
  }

  const handleRetry = async (taskId: number) => {
    await api.retryTask(taskId, 'run_now')
    await load()
  }

  const handleBulkRetry = async (mode: 'run_now' | 'edit_first') => {
    if (selectedRetryableTaskIds.length === 0) return
    try {
      await api.bulkRetryTasks({ task_ids: selectedRetryableTaskIds, mode })
      setSelectedTaskIds([])
      await load()
    } catch (error) {
      alert(error instanceof Error ? error.message : '批量重试失败')
    }
  }

  const handleEditRetry = (task: Task) => {
    setForm({
      description: task.description,
      agent_id: task.agent_id,
      requires_approval: task.requires_approval,
      priority: task.priority,
      skill_name: task.skill_name || '',
    })
    setShowCreate(true)
    setPreview(false)
  }

  const handleViewLogs = async (taskId: number) => {
    const logs = await api.getTaskLogs(taskId)
    setSelectedLogs({ taskId, logs })
  }

  const toggleTaskSelection = (taskId: number) => {
    setSelectedTaskIds((prev) => (
      prev.includes(taskId) ? prev.filter((id) => id !== taskId) : [...prev, taskId]
    ))
  }

  const insertMarkdown = (syntax: string) => {
    const ta = document.getElementById('task-desc') as HTMLTextAreaElement | null
    if (!ta) return
    const start = ta.selectionStart
    const end = ta.selectionEnd
    const text = form.description
    const selected = text.substring(start, end)
    let replacement = ''
    switch (syntax) {
      case 'bold': replacement = `**${selected || '粗体'}**`; break
      case 'heading': replacement = `\n## ${selected || '标题'}\n`; break
      case 'list': replacement = `\n- ${selected || '列表项'}\n`; break
      case 'checklist': replacement = `\n- [ ] ${selected || '待办项'}\n`; break
      case 'code': replacement = selected.includes('\n') ? `\n\`\`\`\n${selected || '代码'}\n\`\`\`\n` : `\`${selected || '代码'}\``; break
      case 'link': replacement = `[${selected || '链接文本'}](url)`; break
      default: replacement = selected
    }
    const newText = text.substring(0, start) + replacement + text.substring(end)
    setForm({ ...form, description: newText })
    setTimeout(() => {
      ta.focus()
      ta.selectionStart = ta.selectionEnd = start + replacement.length
    }, 0)
  }

  return (
    <div data-testid="taskboard-page">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h2 className="text-xl font-bold">任务看板</h2>
        <div className="flex flex-wrap items-center gap-2">
          <select
            data-testid="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 text-sm border rounded"
          >
            <option value="">全部状态</option>
            <option value="pending">待执行</option>
            <option value="running">执行中</option>
            <option value="pending_approval">待审批</option>
            <option value="completed">已完成</option>
            <option value="rejected">已拒绝</option>
            <option value="failed">失败</option>
          </select>
          <select
            data-testid="project-filter"
            value={projectFilter}
            onChange={(e) => setProjectFilter(e.target.value)}
            className="px-3 py-2 text-sm border rounded"
          >
            <option value="">全部项目</option>
            {projectKeys.map((project) => (
              <option key={project} value={project}>{project}</option>
            ))}
          </select>
          <button
            data-testid="advanced-filters-toggle"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="px-3 py-2 text-sm border rounded hover:bg-gray-50"
          >
            {showAdvanced ? '收起高级筛选' : '高级筛选'}
          </button>
          <button
            data-testid="create-btn"
            onClick={() => setShowCreate(!showCreate)}
            className="px-4 py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700"
          >
            + 新建任务
          </button>
        </div>
      </div>

      {showAdvanced && (
        <div className="grid grid-cols-1 gap-3 p-3 mb-4 bg-white border rounded-lg md:grid-cols-4" data-testid="advanced-filters">
          <select
            data-testid="group-filter"
            value={agentGroupFilter}
            onChange={(e) => setAgentGroupFilter(e.target.value)}
            className="px-3 py-2 text-sm border rounded"
          >
            <option value="">全部 Agent 组</option>
            {groupKeys.map((group) => (
              <option key={group} value={group}>{group}</option>
            ))}
          </select>
          <select
            data-testid="agent-filter"
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="px-3 py-2 text-sm border rounded"
          >
            <option value="">全部 Agent</option>
            {agents
              .filter((agent) => !agentGroupFilter || agent.group === agentGroupFilter)
              .map((agent) => (
                <option key={agent.id} value={agent.id}>{agent.display_name} ({agent.id})</option>
              ))}
          </select>
          <input
            data-testid="task-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索任务 / Agent / Skill / 错误"
            className="px-3 py-2 text-sm border rounded"
          />
          <label className="flex items-center gap-2 px-3 py-2 text-sm border rounded">
            <input
              data-testid="only-anomalies"
              type="checkbox"
              checked={onlyAnomalies}
              onChange={(e) => setOnlyAnomalies(e.target.checked)}
            />
            仅看异常
          </label>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 mb-4 md:grid-cols-4" data-testid="task-summary-bar">
        <div className="p-3 bg-white border rounded-lg"><div className="text-xs text-gray-500">执行中</div><div className="text-lg font-semibold">{tasks.filter(t => t.status === 'running').length}</div></div>
        <div className="p-3 bg-white border rounded-lg"><div className="text-xs text-gray-500">失败</div><div className="text-lg font-semibold">{tasks.filter(t => t.status === 'failed').length}</div></div>
        <div className="p-3 bg-white border rounded-lg"><div className="text-xs text-gray-500">待审批</div><div className="text-lg font-semibold">{tasks.filter(t => t.status === 'pending_approval').length}</div></div>
        <div className="p-3 bg-white border rounded-lg"><div className="text-xs text-gray-500">已完成</div><div className="text-lg font-semibold">{tasks.filter(t => t.status === 'completed').length}</div></div>
      </div>

      {selectedRetryableTaskIds.length > 0 && (
        <div className="p-3 mb-4 border border-red-200 rounded-lg bg-red-50" data-testid="bulk-retry-bar">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="text-sm text-red-900">已选择 {selectedRetryableTaskIds.length} 个失败/拒绝任务</div>
            <div className="flex flex-wrap gap-2">
              <button
                data-testid="select-all-retryable"
                onClick={() => setSelectedTaskIds(allRetryableSelected ? [] : retryableTaskIds)}
                className="text-xs border border-red-300 px-3 py-1.5 rounded hover:bg-white"
              >
                {allRetryableSelected ? '取消全选' : '全选当前页失败任务'}
              </button>
              <button
                data-testid="clear-selection"
                onClick={() => setSelectedTaskIds([])}
                className="text-xs border border-red-300 px-3 py-1.5 rounded hover:bg-white"
              >
                清空选择
              </button>
              <button
                data-testid="bulk-retry"
                onClick={() => handleBulkRetry('run_now')}
                className="text-xs bg-red-600 text-white px-4 py-1.5 rounded hover:bg-red-700"
              >
                批量重试
              </button>
              <button
                data-testid="bulk-edit-retry"
                onClick={() => handleBulkRetry('edit_first')}
                className="text-xs border border-red-300 px-4 py-1.5 rounded hover:bg-white"
              >
                批量创建重试任务
              </button>
            </div>
          </div>
        </div>
      )}

      {showCreate && (
        <div data-testid="create-form" className="p-4 mb-4 bg-white border rounded-lg shadow-sm">
          <div className="grid grid-cols-1 gap-3 mb-3 md:grid-cols-4">
            <select
              data-testid="agent-select"
              value={form.agent_id}
              onChange={(e) => {
                setSuggestionMessage('')
                setForm({ ...form, agent_id: e.target.value, skill_name: '' })
              }}
              className="px-3 py-2 text-sm border rounded"
            >
              <option value="">自动选择 Agent</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>{a.display_name} ({a.id})</option>
              ))}
            </select>
            <select
              data-testid="skill-select"
              value={form.skill_name}
              onChange={(e) => {
                setSuggestionMessage('')
                setForm({ ...form, skill_name: e.target.value })
              }}
              className="px-3 py-2 text-sm border rounded"
            >
              <option value="">自动选择 Skill</option>
              {(selectedAgentSkills.length > 0 ? selectedAgentSkills : skills).map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <select
              data-testid="priority-select"
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
              className="px-3 py-2 text-sm border rounded"
            >
              <option value="low">低优先级</option>
              <option value="normal">普通</option>
              <option value="high">⚡ 高优先级</option>
            </select>
            <label className="flex items-center gap-2 text-sm">
              <input
                data-testid="approval-checkbox"
                type="checkbox"
                checked={form.requires_approval}
                onChange={(e) => setForm({ ...form, requires_approval: e.target.checked })}
              />
              需要审批
            </label>
          </div>

          {selectedAgent && (
            <div className="px-3 py-2 mb-3 text-xs text-gray-600 border rounded bg-gray-50" data-testid="agent-meta-hint">
              <span className="mr-4">项目: Synapse-Network-Growing</span>
              <span className="mr-4">组别: {selectedAgent.group || '-'}</span>
              <span>技能数: {selectedAgentSkills.length}</span>
            </div>
          )}

          {suggestion && (
            <div
              data-testid="auto-suggestion-card"
              className={`mb-3 rounded border px-3 py-3 text-sm ${suggestion.requires_confirmation ? 'border-amber-300 bg-amber-50' : 'border-emerald-300 bg-emerald-50'}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-medium text-gray-900">
                    {suggestion.requires_confirmation ? '系统推荐需要人工确认' : '系统已自动匹配执行方案'}
                  </div>
                  <div className="mt-1 text-xs text-gray-600" data-testid="auto-suggestion-summary">
                    推荐 Agent: {suggestion.agent_id || '-'} · 推荐 Skill: {suggestion.skill_name || '-'} · 置信度 {Math.round(suggestion.confidence * 100)}%
                  </div>
                  <div className="mt-1 text-xs text-gray-500">{suggestionMessage || suggestion.reason}</div>
                </div>
                {!suggestion.requires_confirmation && suggestion.agent_id && suggestion.skill_name && (
                  <button
                    data-testid="apply-suggestion"
                    type="button"
                    onClick={() => applySuggestion(suggestion.agent_id || '', suggestion.skill_name || '')}
                    className="px-3 py-2 text-xs text-white rounded bg-emerald-600 hover:bg-emerald-700"
                  >
                    采用推荐
                  </button>
                )}
              </div>
              {suggestion.requires_confirmation && suggestion.candidates.length > 0 && (
                <div className="mt-3 space-y-2" data-testid="suggestion-candidates">
                  {suggestion.candidates.map((candidate, index) => (
                    <button
                      key={`${candidate.agent_id}-${candidate.skill_name}`}
                      data-testid={`suggestion-candidate-${index}`}
                      type="button"
                      onClick={() => applySuggestion(candidate.agent_id, candidate.skill_name)}
                      className="w-full px-3 py-2 text-left bg-white border rounded hover:border-amber-400"
                    >
                      <div className="text-sm font-medium text-gray-900">{candidate.display_name} · {candidate.skill_name}</div>
                      <div className="mt-1 text-xs text-gray-500">{candidate.reason} · 置信度 {Math.round(candidate.confidence * 100)}%</div>
                    </button>
                  ))}
                </div>
              )}
              {suggestionLoading && <div className="mt-2 text-xs text-gray-500">正在分析任务并匹配 Agent / Skill...</div>}
            </div>
          )}

          <div className="flex items-center gap-1 pb-1 mb-1 border-b">
            <span className="mr-2 text-xs text-gray-400">Markdown</span>
            {[
              { key: 'heading', icon: 'H', title: '标题' },
              { key: 'bold', icon: 'B', title: '粗体' },
              { key: 'list', icon: '•', title: '列表' },
              { key: 'checklist', icon: '☑', title: '待办' },
              { key: 'code', icon: '</>', title: '代码' },
              { key: 'link', icon: '🔗', title: '链接' },
            ].map((btn) => (
              <button
                key={btn.key}
                data-testid={`md-${btn.key}`}
                type="button"
                title={btn.title}
                onClick={() => insertMarkdown(btn.key)}
                className="px-2 py-1 font-mono text-xs text-gray-600 border border-transparent rounded hover:bg-gray-100 hover:border-gray-200"
              >
                {btn.icon}
              </button>
            ))}
            <div className="flex-1" />
            <button
              data-testid="preview-toggle"
              type="button"
              onClick={() => setPreview(!preview)}
              className={`text-xs px-2 py-1 rounded ${preview ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:bg-gray-100'}`}
            >
              {preview ? '编辑' : '预览'}
            </button>
          </div>

          {preview ? (
            <div data-testid="md-preview" className="border rounded p-3 min-h-[200px] bg-gray-50">
              {form.description ? <Md>{form.description}</Md> : <p className="text-sm text-gray-400">暂无内容</p>}
            </div>
          ) : (
            <textarea
              id="task-desc"
              data-testid="task-description"
              placeholder="任务描述（支持 Markdown）&#10;&#10;例如：&#10;## 目标&#10;为 Synapse 首页做 SEO 审计&#10;&#10;## 要求&#10;- 分析关键词覆盖率&#10;- 输出优化建议清单&#10;- **格式**: Markdown 文档"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              rows={10}
              className="w-full border rounded p-3 text-sm font-mono resize-y min-h-[200px] focus:ring-2 focus:ring-blue-300 focus:border-blue-400 outline-none"
            />
          )}

          <div className="flex items-center justify-between mt-2">
            <span className="text-xs text-gray-400">{form.description.length} 字符</span>
            <div className="flex gap-2">
              <button
                data-testid="cancel-btn"
                onClick={() => { setShowCreate(false); setPreview(false) }}
                className="px-4 py-2 text-sm text-gray-500"
              >
                取消
              </button>
              <button
                data-testid="submit-btn"
                onClick={handleCreate}
                disabled={!form.description.trim()}
                className="px-4 py-2 text-sm text-white bg-green-600 rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                提交任务
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-4">
        {Object.keys(groupedTasks).length === 0 && <p data-testid="empty-tasks" className="text-sm text-gray-500">暂无任务</p>}
        {Object.entries(groupedTasks)
          .sort(([, leftTasks], [, rightTasks]) => {
            const leftNewest = leftTasks.reduce((max, task) => Math.max(max, taskCreatedAtValue(task)), 0)
            const rightNewest = rightTasks.reduce((max, task) => Math.max(max, taskCreatedAtValue(task)), 0)
            if (rightNewest !== leftNewest) return rightNewest - leftNewest
            const leftLabel = leftTasks[0]?.project_label || leftTasks[0]?.project_id || ''
            const rightLabel = rightTasks[0]?.project_label || rightTasks[0]?.project_id || ''
            return leftLabel.localeCompare(rightLabel)
          })
          .map(([project, projectTasks]) => (
            <section key={project} data-testid={`project-section-${project}`}>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-gray-700">项目: {project}</h3>
                <span className="text-xs text-gray-400">{projectTasks.length} 个任务</span>
              </div>
              <div className="space-y-2">
                {projectTasks
                  .slice()
                  .sort(compareTasksByNewestFirst)
                  .map((task) => {
                    const errorSummary = getTaskErrorSummary(task)
                    const isSelected = selectedTaskIds.includes(task.id)
                    const isRetryable = RETRYABLE_STATUSES.has(task.status)
                    const executionTimeLabel = formatDuration(getExecutionTimeMs(task, nowMs))
                    return (
                      <div key={task.id} data-testid={`task-${task.id}`} className="bg-white border rounded-lg shadow-sm">
                        <div
                          className="flex items-start justify-between p-4 cursor-pointer hover:bg-gray-50"
                          onClick={() => navigate(`/tasks/${task.id}`)}
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex flex-wrap items-center gap-2 mb-1">
                              {isRetryable && (
                                <input
                                  data-testid={`select-task-${task.id}`}
                                  type="checkbox"
                                  checked={isSelected}
                                  onClick={(e) => e.stopPropagation()}
                                  onChange={() => toggleTaskSelection(task.id)}
                                />
                              )}
                              <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[task.status] || 'bg-gray-100'}`}>
                                {STATUS_LABEL[task.status] || task.status}
                              </span>
                              <span className="font-mono text-xs text-gray-400">#{task.id}</span>
                              {task.project_label && <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700">{task.project_label}</span>}
                              <span className="text-xs text-gray-500">@{task.agent_id}</span>
                              {task.agent_group && <span className="text-xs px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">{task.agent_group}</span>}
                              {task.skill_name && <span className="text-xs px-2 py-0.5 rounded bg-purple-100 text-purple-700">🛠 {task.skill_name}</span>}
                              {task.requirement_title && <span className="text-xs px-2 py-0.5 rounded bg-blue-50 text-blue-700" title={`需求 #${task.requirement_id}`}>📋 {task.requirement_title.length > 20 ? task.requirement_title.slice(0, 20) + '…' : task.requirement_title}</span>}
                              {task.priority !== 'normal' && (
                                <span className={`text-xs px-2 py-0.5 rounded ${task.priority === 'high' ? 'bg-red-50 text-red-600' : 'bg-gray-50 text-gray-500'}`}>
                                  {task.priority === 'high' ? '⚡ 高' : '低'}
                                </span>
                              )}
                              {task.attempt_no > 1 && <span className="text-xs px-2 py-0.5 rounded bg-amber-50 text-amber-700">第 {task.attempt_no} 次</span>}
                              {executionTimeLabel && (
                                <span className="text-xs px-2 py-0.5 rounded bg-sky-50 text-sky-700" data-testid={`execution-time-${task.id}`}>
                                  ⏱ {task.status === 'running' ? `已运行 ${executionTimeLabel}` : executionTimeLabel}
                                </span>
                              )}
                              <span className="text-xs text-gray-300">▶</span>
                            </div>
                            <p className="text-sm font-medium truncate">{task.description.split('\n')[0]}</p>
                            {task.status === 'failed' && errorSummary && (
                              <p className="mt-1 text-xs text-red-600 truncate" data-testid={`error-summary-${task.id}`}>{errorSummary}</p>
                            )}
                          </div>
                          <div className="flex flex-wrap items-center justify-end gap-2 ml-4" onClick={(e) => e.stopPropagation()}>
                            {task.status === 'running' && (
                              <span data-testid={`spinner-${task.id}`} className="text-sm text-blue-500 animate-spin">⏳</span>
                            )}
                            {task.status === 'pending' && (
                              <>
                                {!task.skill_name && (
                                  <select
                                    data-testid={`run-skill-${task.id}`}
                                    value={runningSkill[task.id] || ''}
                                    onChange={(e) => setRunningSkill({ ...runningSkill, [task.id]: e.target.value })}
                                    className="px-2 py-1 text-xs border rounded"
                                  >
                                    <option value="">Skill...</option>
                                    {skills.map((s) => <option key={s} value={s}>{s}</option>)}
                                  </select>
                                )}
                                <button
                                  data-testid={`run-${task.id}`}
                                  onClick={() => handleRun(task.id)}
                                  className="text-xs bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700"
                                >
                                  执行
                                </button>
                              </>
                            )}
                            {task.status === 'failed' && (
                              <>
                                <button
                                  data-testid={`retry-${task.id}`}
                                  onClick={() => handleRetry(task.id)}
                                  className="text-xs bg-red-600 text-white px-3 py-1.5 rounded hover:bg-red-700"
                                >
                                  重试
                                </button>
                                <button
                                  data-testid={`edit-retry-${task.id}`}
                                  onClick={() => handleEditRetry(task)}
                                  className="text-xs border px-3 py-1.5 rounded hover:bg-gray-50"
                                >
                                  编辑后重试
                                </button>
                              </>
                            )}
                            <button
                              data-testid={`logs-${task.id}`}
                              onClick={() => handleViewLogs(task.id)}
                              className="text-xs border px-3 py-1.5 rounded hover:bg-gray-50"
                            >
                              日志
                            </button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
              </div>
            </section>
          ))}
      </div>

      {selectedLogs && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setSelectedLogs(null)}>
          <div className="bg-white rounded-lg p-6 max-w-lg w-full max-h-[70vh] overflow-auto shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-3 font-bold">Task #{selectedLogs.taskId} 日志</h3>
            {selectedLogs.logs.length === 0 && <p className="text-sm text-gray-500">暂无日志</p>}
            <div className="space-y-2">
              {selectedLogs.logs
                .slice()
                .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
                .map((log) => (
                  <div key={log.id} className={`text-sm border-l-2 pl-3 ${log.event_type === 'failed' ? 'border-red-400' : log.event_type === 'completed' ? 'border-green-400' : 'border-gray-300'}`}>
                    <span className="font-mono text-xs text-gray-400">{log.created_at}</span>
                    <span className="ml-2 font-semibold">{log.event_type}</span>
                    {log.detail && <p className="text-gray-600 text-xs mt-0.5">{log.detail}</p>}
                  </div>
                ))}
            </div>
            <button onClick={() => setSelectedLogs(null)} className="mt-4 text-sm text-gray-500 hover:text-gray-700">
              关闭
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
