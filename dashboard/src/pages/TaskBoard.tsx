import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { api, Task, Agent, TaskLog } from '../api'

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

/* ── Markdown 渲染 wrapper ──────────────────────────────────── */
function Md({ children }: { children: string }) {
  return (
    <div className="prose prose-sm max-w-none prose-headings:text-base prose-p:my-1 prose-ul:my-1 prose-li:my-0.5">
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  )
}

export default function TaskBoard() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [filter, setFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ description: '', agent_id: '', requires_approval: false, priority: 'normal' })
  const [preview, setPreview] = useState(false)
  const [selectedLogs, setSelectedLogs] = useState<{ taskId: number; logs: TaskLog[] } | null>(null)
  const [expandedTask, setExpandedTask] = useState<number | null>(null)

  const load = async () => {
    const [t, a] = await Promise.all([
      api.getTasks(filter ? { status: filter } : undefined),
      api.getAgents(),
    ])
    setTasks(t)
    setAgents(a)
  }

  useEffect(() => { load() }, [filter])

  const handleCreate = async () => {
    if (!form.description || !form.agent_id) return
    await api.createTask(form)
    setForm({ description: '', agent_id: '', requires_approval: false, priority: 'normal' })
    setShowCreate(false)
    setPreview(false)
    await load()
  }

  const handleRun = async (id: number) => {
    await api.runTask(id)
    await load()
  }

  const handleViewLogs = async (taskId: number) => {
    const logs = await api.getTaskLogs(taskId)
    setSelectedLogs({ taskId, logs })
  }

  /* ── Markdown 快捷插入工具栏 ─────────────────────────────── */
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
      case 'code': replacement = selected.includes('\n')
        ? `\n\`\`\`\n${selected || '代码'}\n\`\`\`\n`
        : `\`${selected || '代码'}\``; break
      case 'link': replacement = `[${selected || '链接文本'}](url)`; break
      default: replacement = selected
    }
    const newText = text.substring(0, start) + replacement + text.substring(end)
    setForm({ ...form, description: newText })
    // Restore cursor
    setTimeout(() => {
      ta.focus()
      ta.selectionStart = ta.selectionEnd = start + replacement.length
    }, 0)
  }

  return (
    <div data-testid="taskboard-page">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold">任务看板</h2>
        <div className="flex gap-2">
          <select
            data-testid="status-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="text-sm border rounded px-3 py-2"
          >
            <option value="">全部状态</option>
            <option value="pending">待执行</option>
            <option value="running">执行中</option>
            <option value="pending_approval">待审批</option>
            <option value="completed">已完成</option>
            <option value="rejected">已拒绝</option>
          </select>
          <button
            data-testid="create-btn"
            onClick={() => setShowCreate(!showCreate)}
            className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
          >
            + 新建任务
          </button>
        </div>
      </div>

      {/* ── Create form ──────────────────────────────────────── */}
      {showCreate && (
        <div data-testid="create-form" className="bg-white border rounded-lg p-4 mb-4 shadow-sm">
          {/* Agent + Priority + Approval row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
            <select
              data-testid="agent-select"
              value={form.agent_id}
              onChange={(e) => setForm({ ...form, agent_id: e.target.value })}
              className="border rounded px-3 py-2 text-sm"
            >
              <option value="">选择 Agent</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>{a.display_name} ({a.id})</option>
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

          {/* Markdown toolbar */}
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

          {/* Textarea / Preview */}
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

          {/* Character count + actions */}
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
                disabled={!form.description || !form.agent_id}
                className="text-sm bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                提交任务
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Task list ────────────────────────────────────────── */}
      <div className="space-y-2">
        {tasks.length === 0 && <p data-testid="empty-tasks" className="text-gray-500 text-sm">暂无任务</p>}
        {tasks.map((task) => {
          const isExpanded = expandedTask === task.id
          return (
            <div key={task.id} data-testid={`task-${task.id}`} className="bg-white border rounded-lg shadow-sm">
              {/* Task header row */}
              <div
                className="p-4 flex items-center justify-between cursor-pointer hover:bg-gray-50"
                onClick={() => setExpandedTask(isExpanded ? null : task.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[task.status] || 'bg-gray-100'}`}>
                      {STATUS_LABEL[task.status] || task.status}
                    </span>
                    <span className="text-xs text-gray-400 font-mono">#{task.id}</span>
                    <span className="text-xs text-gray-400">@{task.agent_id}</span>
                    {task.priority !== 'normal' && (
                      <span className={`text-xs px-2 py-0.5 rounded ${task.priority === 'high' ? 'bg-red-50 text-red-600' : 'bg-gray-50 text-gray-500'}`}>
                        {task.priority === 'high' ? '⚡ 高' : '低'}
                      </span>
                    )}
                    <span className="text-xs text-gray-300">{isExpanded ? '▼' : '▶'}</span>
                  </div>
                  <p className="text-sm truncate">{task.description.split('\n')[0]}</p>
                </div>
                <div className="flex gap-2 ml-4" onClick={(e) => e.stopPropagation()}>
                  {task.status === 'pending' && (
                    <button
                      data-testid={`run-${task.id}`}
                      onClick={() => handleRun(task.id)}
                      className="text-xs bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700"
                    >
                      执行
                    </button>
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

              {/* Expanded detail */}
              {isExpanded && (
                <div data-testid={`task-detail-${task.id}`} className="border-t px-4 py-3 bg-gray-50">
                  <div className="mb-3">
                    <h4 className="text-xs font-bold text-gray-500 mb-1">任务描述</h4>
                    <div className="bg-white border rounded p-3">
                      <Md>{task.description}</Md>
                    </div>
                  </div>
                  {task.output_content && (
                    <div className="mb-3">
                      <h4 className="text-xs font-bold text-gray-500 mb-1">执行产出</h4>
                      <div className="bg-white border rounded p-3">
                        <Md>{task.output_content}</Md>
                      </div>
                    </div>
                  )}
                  <div className="grid grid-cols-3 gap-4 text-xs text-gray-500">
                    <div>创建: {task.created_at ? new Date(task.created_at).toLocaleString('zh-CN') : '-'}</div>
                    <div>开始: {task.started_at ? new Date(task.started_at).toLocaleString('zh-CN') : '-'}</div>
                    <div>完成: {task.completed_at ? new Date(task.completed_at).toLocaleString('zh-CN') : '-'}</div>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* ── Logs modal ───────────────────────────────────────── */}
      {selectedLogs && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setSelectedLogs(null)}>
          <div className="bg-white rounded-lg p-6 max-w-lg w-full max-h-[70vh] overflow-auto shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-bold mb-3">Task #{selectedLogs.taskId} 日志</h3>
            {selectedLogs.logs.length === 0 && <p className="text-sm text-gray-500">暂无日志</p>}
            <div className="space-y-2">
              {selectedLogs.logs.map((log) => (
                <div key={log.id} className="text-sm border-l-2 border-gray-300 pl-3">
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
