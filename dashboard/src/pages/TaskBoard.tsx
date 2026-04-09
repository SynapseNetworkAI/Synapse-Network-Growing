import { useEffect, useState, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import { api, Task, Agent, TaskLog, TaskHistoryItem, TaskExecutionSuggestion, ApiError } from '../api'

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

const STATUS_ORDER: Record<string, number> = {
  running: 0,
  failed: 1,
  pending_approval: 2,
  pending: 3,
  completed: 4,
  rejected: 5,
}

function Md({ children }: { children: string }) {
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

function inferProjectFromAgent(agent: Agent | undefined) {
  if (!agent?.group) return 'Synapse-Network-Growing'
  return 'Synapse-Network-Growing'
}

function formatTime(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

export default function TaskBoard() {
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
  const [drawerTaskId, setDrawerTaskId] = useState<number | null>(null)
  const [runningSkill, setRunningSkill] = useState<Record<number, string>>({})
  const [taskHistory, setTaskHistory] = useState<Record<number, TaskHistoryItem[]>>({})
  const [selectedTaskIds, setSelectedTaskIds] = useState<number[]>([])
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
    if (drawerTaskId == null || taskHistory[drawerTaskId]) return
    api.getTaskHistory(drawerTaskId)
      .then((history) => {
        setTaskHistory((prev) => ({ ...prev, [drawerTaskId]: history }))
      })
      .catch(() => {})
  }, [drawerTaskId, taskHistory])

  useEffect(() => {
    setSelectedTaskIds((prev) => prev.filter((id) => tasks.some((task) => task.id === id && RETRYABLE_STATUSES.has(task.status))))
    if (drawerTaskId != null && !tasks.some((task) => task.id === drawerTaskId)) {
      setDrawerTaskId(null)
    }
  }, [tasks, drawerTaskId])

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
  const drawerTask = drawerTaskId != null ? tasks.find((task) => task.id === drawerTaskId) || null : null
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
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h2 className="text-xl font-bold">任务看板</h2>
        <div className="flex gap-2 flex-wrap items-center">
          <select
            data-testid="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="text-sm border rounded px-3 py-2"
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
            className="text-sm border rounded px-3 py-2"
          >
            <option value="">全部项目</option>
            {projectKeys.map((project) => (
              <option key={project} value={project}>{project}</option>
            ))}
          </select>
          <button
            data-testid="advanced-filters-toggle"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-sm border rounded px-3 py-2 hover:bg-gray-50"
          >
            {showAdvanced ? '收起高级筛选' : '高级筛选'}
          </button>
          <button
            data-testid="create-btn"
            onClick={() => setShowCreate(!showCreate)}
            className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
          >
            + 新建任务
          </button>
        </div>
      </div>

      {showAdvanced && (
        <div className="bg-white border rounded-lg p-3 mb-4 grid grid-cols-1 md:grid-cols-4 gap-3" data-testid="advanced-filters">
          <select
            data-testid="group-filter"
            value={agentGroupFilter}
            onChange={(e) => setAgentGroupFilter(e.target.value)}
            className="text-sm border rounded px-3 py-2"
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
            className="text-sm border rounded px-3 py-2"
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
            className="text-sm border rounded px-3 py-2"
          />
          <label className="flex items-center gap-2 text-sm border rounded px-3 py-2">
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

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4" data-testid="task-summary-bar">
        <div className="bg-white border rounded-lg p-3"><div className="text-xs text-gray-500">执行中</div><div className="text-lg font-semibold">{tasks.filter(t => t.status === 'running').length}</div></div>
        <div className="bg-white border rounded-lg p-3"><div className="text-xs text-gray-500">失败</div><div className="text-lg font-semibold">{tasks.filter(t => t.status === 'failed').length}</div></div>
        <div className="bg-white border rounded-lg p-3"><div className="text-xs text-gray-500">待审批</div><div className="text-lg font-semibold">{tasks.filter(t => t.status === 'pending_approval').length}</div></div>
        <div className="bg-white border rounded-lg p-3"><div className="text-xs text-gray-500">已完成</div><div className="text-lg font-semibold">{tasks.filter(t => t.status === 'completed').length}</div></div>
      </div>

      {selectedRetryableTaskIds.length > 0 && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3" data-testid="bulk-retry-bar">
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
        <div data-testid="create-form" className="bg-white border rounded-lg p-4 mb-4 shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
            <select
              data-testid="agent-select"
              value={form.agent_id}
              onChange={(e) => {
                setSuggestionMessage('')
                setForm({ ...form, agent_id: e.target.value, skill_name: '' })
              }}
              className="border rounded px-3 py-2 text-sm"
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
              className="border rounded px-3 py-2 text-sm"
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
              className="border rounded px-3 py-2 text-sm"
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
            <div className="mb-3 rounded border bg-gray-50 px-3 py-2 text-xs text-gray-600" data-testid="agent-meta-hint">
              <span className="mr-4">项目: {inferProjectFromAgent(selectedAgent)}</span>
              <span className="mr-4">组别: {selectedAgent.group || '-'}</span>
              <span>技能数: {selectedAgentSkills.length}</span>
            </div>
          )}

          {suggestion && (
            <div
              data-testid="auto-suggestion-card"
              className={`mb-3 rounded border px-3 py-3 text-sm ${suggestion.requires_confirmation ? 'border-amber-300 bg-amber-50' : 'border-emerald-300 bg-emerald-50'}`}
            >
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <div className="font-medium text-gray-900">
                    {suggestion.requires_confirmation ? '系统推荐需要人工确认' : '系统已自动匹配执行方案'}
                  </div>
                  <div className="text-xs text-gray-600 mt-1" data-testid="auto-suggestion-summary">
                    推荐 Agent: {suggestion.agent_id || '-'} · 推荐 Skill: {suggestion.skill_name || '-'} · 置信度 {Math.round(suggestion.confidence * 100)}%
                  </div>
                  <div className="text-xs text-gray-500 mt-1">{suggestionMessage || suggestion.reason}</div>
                </div>
                {!suggestion.requires_confirmation && suggestion.agent_id && suggestion.skill_name && (
                  <button
                    data-testid="apply-suggestion"
                    type="button"
                    onClick={() => applySuggestion(suggestion.agent_id || '', suggestion.skill_name || '')}
                    className="text-xs bg-emerald-600 text-white px-3 py-2 rounded hover:bg-emerald-700"
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
                      className="w-full rounded border bg-white px-3 py-2 text-left hover:border-amber-400"
                    >
                      <div className="text-sm font-medium text-gray-900">{candidate.display_name} · {candidate.skill_name}</div>
                      <div className="text-xs text-gray-500 mt-1">{candidate.reason} · 置信度 {Math.round(candidate.confidence * 100)}%</div>
                    </button>
                  ))}
                </div>
              )}
              {suggestionLoading && <div className="mt-2 text-xs text-gray-500">正在分析任务并匹配 Agent / Skill...</div>}
            </div>
          )}

          <div className="flex items-center gap-1 mb-1 border-b pb-1">
            <span className="text-xs text-gray-400 mr-2">Markdown</span>
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
                className="text-xs px-2 py-1 rounded hover:bg-gray-100 text-gray-600 font-mono border border-transparent hover:border-gray-200"
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
              {form.description ? <Md>{form.description}</Md> : <p className="text-gray-400 text-sm">暂无内容</p>}
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
                className="text-sm text-gray-500 px-4 py-2"
              >
                取消
              </button>
              <button
                data-testid="submit-btn"
                onClick={handleCreate}
                disabled={!form.description.trim()}
                className="text-sm bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                提交任务
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-4">
        {Object.keys(groupedTasks).length === 0 && <p data-testid="empty-tasks" className="text-gray-500 text-sm">暂无任务</p>}
        {Object.entries(groupedTasks)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([project, projectTasks]) => (
            <section key={project} data-testid={`project-section-${project}`}>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-gray-700">项目: {project}</h3>
                <span className="text-xs text-gray-400">{projectTasks.length} 个任务</span>
              </div>
              <div className="space-y-2">
                {projectTasks
                  .slice()
                  .sort((a, b) => {
                    const statusDiff = (STATUS_ORDER[a.status] ?? 99) - (STATUS_ORDER[b.status] ?? 99)
                    if (statusDiff !== 0) return statusDiff
                    return b.id - a.id
                  })
                  .map((task) => {
                    const errorSummary = getTaskErrorSummary(task)
                    const isSelected = selectedTaskIds.includes(task.id)
                    const isRetryable = RETRYABLE_STATUSES.has(task.status)
                    return (
                      <div key={task.id} data-testid={`task-${task.id}`} className="bg-white border rounded-lg shadow-sm">
                        <div
                          className="p-4 flex items-start justify-between cursor-pointer hover:bg-gray-50"
                          onClick={() => setDrawerTaskId(task.id)}
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1 flex-wrap">
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
                              <span className="text-xs text-gray-400 font-mono">#{task.id}</span>
                              {task.project_label && <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700">{task.project_label}</span>}
                              <span className="text-xs text-gray-500">@{task.agent_id}</span>
                              {task.agent_group && <span className="text-xs px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">{task.agent_group}</span>}
                              {task.skill_name && <span className="text-xs px-2 py-0.5 rounded bg-purple-100 text-purple-700">🛠 {task.skill_name}</span>}
                              {task.priority !== 'normal' && (
                                <span className={`text-xs px-2 py-0.5 rounded ${task.priority === 'high' ? 'bg-red-50 text-red-600' : 'bg-gray-50 text-gray-500'}`}>
                                  {task.priority === 'high' ? '⚡ 高' : '低'}
                                </span>
                              )}
                              {task.attempt_no > 1 && <span className="text-xs px-2 py-0.5 rounded bg-amber-50 text-amber-700">第 {task.attempt_no} 次</span>}
                              <span className="text-xs text-gray-300">▶</span>
                            </div>
                            <p className="text-sm truncate font-medium">{task.description.split('\n')[0]}</p>
                            {task.status === 'failed' && errorSummary && (
                              <p className="text-xs text-red-600 mt-1 truncate" data-testid={`error-summary-${task.id}`}>{errorSummary}</p>
                            )}
                          </div>
                          <div className="flex gap-2 ml-4 items-center flex-wrap justify-end" onClick={(e) => e.stopPropagation()}>
                            {task.status === 'running' && (
                              <span data-testid={`spinner-${task.id}`} className="text-blue-500 animate-spin text-sm">⏳</span>
                            )}
                            {task.status === 'pending' && (
                              <>
                                {!task.skill_name && (
                                  <select
                                    data-testid={`run-skill-${task.id}`}
                                    value={runningSkill[task.id] || ''}
                                    onChange={(e) => setRunningSkill({ ...runningSkill, [task.id]: e.target.value })}
                                    className="text-xs border rounded px-2 py-1"
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

      {drawerTask && (
        <div className="fixed inset-0 z-40 flex justify-end" data-testid="task-drawer-shell">
          <button className="absolute inset-0 bg-black/20" aria-label="关闭任务详情" onClick={() => setDrawerTaskId(null)} />
          <aside className="relative h-full w-full max-w-2xl overflow-y-auto bg-white shadow-2xl" data-testid="task-drawer">
            <div className="sticky top-0 z-10 border-b bg-white px-6 py-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[drawerTask.status] || 'bg-gray-100'}`}>
                      {STATUS_LABEL[drawerTask.status] || drawerTask.status}
                    </span>
                    <span className="text-xs text-gray-400 font-mono">#{drawerTask.id}</span>
                    {drawerTask.project_label && <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700">{drawerTask.project_label}</span>}
                    {drawerTask.agent_group && <span className="text-xs px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">{drawerTask.agent_group}</span>}
                    {drawerTask.skill_name && (
                      <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded" data-testid={`skill-badge-${drawerTask.id}`}>
                        🛠 {drawerTask.skill_name}
                      </span>
                    )}
                  </div>
                  <h3 className="mt-2 text-lg font-semibold" data-testid={`task-detail-${drawerTask.id}`}>{drawerTask.description.split('\n')[0]}</h3>
                  <p className="mt-1 text-sm text-gray-500">Agent: @{drawerTask.agent_id}</p>
                </div>
                <button
                  data-testid="task-drawer-close"
                  onClick={() => setDrawerTaskId(null)}
                  className="text-sm border rounded px-3 py-1.5 hover:bg-gray-50"
                >
                  关闭
                </button>
              </div>
            </div>

            <div className="px-6 py-5">
              <div className="mb-4 flex gap-3 flex-wrap items-center text-xs text-gray-500">
                {drawerTask.retry_of_task_id != null && <span>重试来源: #{drawerTask.retry_of_task_id}</span>}
                {drawerTask.execution_time_ms != null && <span>⏱ {(drawerTask.execution_time_ms / 1000).toFixed(1)}s</span>}
                <span>创建: {formatTime(drawerTask.created_at)}</span>
                <span>开始: {formatTime(drawerTask.started_at)}</span>
                <span>完成: {formatTime(drawerTask.completed_at)}</span>
              </div>

              <div className="mb-4">
                <h4 className="text-xs font-bold text-gray-500 mb-1">任务描述</h4>
                <div className="bg-gray-50 border rounded p-3">
                  <Md>{drawerTask.description}</Md>
                </div>
              </div>

              {getTaskErrorSummary(drawerTask) && (
                <div className="mb-4">
                  <h4 className="text-xs font-bold text-gray-500 mb-1">失败原因</h4>
                  <div className="bg-red-50 border border-red-100 rounded p-3 text-sm text-red-600">{getTaskErrorSummary(drawerTask)}</div>
                </div>
              )}

              {drawerTask.output_content && (
                <div className="mb-4">
                  <h4 className="text-xs font-bold text-gray-500 mb-1">执行产出</h4>
                  <div className="bg-gray-50 border rounded p-3">
                    <Md>{drawerTask.output_content}</Md>
                  </div>
                </div>
              )}

              <div className="mb-3" data-testid={`history-${drawerTask.id}`}>
                <h4 className="text-xs font-bold text-gray-500 mb-2">重试历史时间线</h4>
                <div className="bg-gray-50 border rounded p-3">
                  {(taskHistory[drawerTask.id] || []).length === 0 ? (
                    <p className="text-sm text-gray-400">暂无重试历史</p>
                  ) : (
                    <div className="space-y-3">
                      {(taskHistory[drawerTask.id] || []).map((item) => (
                        <div key={item.task_id} className="flex gap-3 items-start" data-testid={`history-item-${drawerTask.id}-${item.task_id}`}>
                          <div className={`mt-1 h-2.5 w-2.5 rounded-full ${STATUS_COLORS[item.status]?.split(' ')[0] || 'bg-gray-300'}`} />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-xs font-medium text-gray-700">尝试 #{item.attempt_no}</span>
                              <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[item.status] || 'bg-gray-100 text-gray-700'}`}>
                                {STATUS_LABEL[item.status] || item.status}
                              </span>
                              <span className="text-xs text-gray-400 font-mono">Task #{item.task_id}</span>
                              {item.retry_of_task_id != null && <span className="text-xs text-gray-400">来自 #{item.retry_of_task_id}</span>}
                            </div>
                            <div className="mt-1 text-xs text-gray-500 flex gap-3 flex-wrap">
                              <span>创建: {formatTime(item.created_at)}</span>
                              <span>完成: {formatTime(item.completed_at)}</span>
                            </div>
                            {item.last_error_message && <p className="mt-1 text-xs text-red-600">{item.last_error_message}</p>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </aside>
        </div>
      )}

      {selectedLogs && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setSelectedLogs(null)}>
          <div className="bg-white rounded-lg p-6 max-w-lg w-full max-h-[70vh] overflow-auto shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-bold mb-3">Task #{selectedLogs.taskId} 日志</h3>
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
