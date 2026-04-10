import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { api, Task, TaskLog, TaskHistoryItem } from '../api'

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

function toUtcDate(value: string): Date {
  return new Date(value.endsWith('Z') ? value : value + 'Z')
}

function formatTime(value: string | null) {
  return value ? toUtcDate(value).toLocaleString('zh-CN') : '-'
}

function parseTime(value: string | null) {
  if (!value) return null
  const parsed = toUtcDate(value).getTime()
  return Number.isNaN(parsed) ? null : parsed
}

function getExecutionTimeMs(task: Task, nowMs: number) {
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
  if (totalSeconds < 60) return `${totalSeconds.toFixed(1)}s`
  const totalWholeSeconds = Math.floor(totalSeconds)
  const hours = Math.floor(totalWholeSeconds / 3600)
  const minutes = Math.floor((totalWholeSeconds % 3600) / 60)
  const seconds = totalWholeSeconds % 60
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, '0')}m ${String(seconds).padStart(2, '0')}s`
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

function normalizeComparableContent(value: string | null | undefined) {
  return (value || '').replace(/\r\n/g, '\n').replace(/\s+/g, ' ').trim()
}

function isDuplicateOutput(outputContent: string | null | undefined, assistantMessages: string[]) {
  const normalizedOutput = normalizeComparableContent(outputContent)
  if (!normalizedOutput) return false
  const combinedTranscript = normalizeComparableContent(assistantMessages.join('\n\n'))
  if (combinedTranscript && normalizedOutput === combinedTranscript) return true
  return assistantMessages.some((msg) => normalizeComparableContent(msg) === normalizedOutput)
}

function getTaskErrorSummary(task: Task) {
  if (task.last_error_message) return task.last_error_message
  if (task.output_content?.startsWith('[ERROR] ')) return task.output_content.replace('[ERROR] ', '').trim()
  return ''
}

export default function TaskDetail() {
  const { id } = useParams<{ id: string }>()
  const taskId = Number(id)

  const [task, setTask] = useState<Task | null>(null)
  const [logs, setLogs] = useState<TaskLog[]>([])
  const [history, setHistory] = useState<TaskHistoryItem[]>([])
  const [nowMs, setNowMs] = useState(() => Date.now())
  const logsPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadTask = useCallback(async () => {
    const tasks = await api.getTasks({})
    const found = tasks.find((t) => t.id === taskId) || null
    setTask(found)
  }, [taskId])

  const loadLogs = useCallback(async () => {
    const data = await api.getTaskLogs(taskId)
    setLogs(data)
  }, [taskId])

  useEffect(() => {
    loadTask().catch(() => {})
    loadLogs().catch(() => {})
    api.getTaskHistory(taskId).then(setHistory).catch(() => {})
  }, [loadTask, loadLogs, taskId])

  // Poll task + logs while running
  useEffect(() => {
    if (!task || task.status !== 'running') return
    const timer = setInterval(() => {
      loadTask().catch(() => {})
      loadLogs().catch(() => {})
    }, 3000)
    return () => clearInterval(timer)
  }, [task, loadTask, loadLogs])

  // Tick timer for live duration
  useEffect(() => {
    if (!task || task.status !== 'running') return
    const timer = setInterval(() => setNowMs(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [task])

  // Cleanup poll ref
  useEffect(() => {
    return () => {
      if (logsPollRef.current) clearInterval(logsPollRef.current)
    }
  }, [])

  if (!task) {
    return (
      <div className="space-y-4">
        <Link to="/tasks" className="text-sm text-blue-600 hover:underline">← 返回任务看板</Link>
        <div className="rounded-xl border bg-white p-8 text-sm text-gray-500">加载中…</div>
      </div>
    )
  }

  const executionTimeLabel = formatDuration(getExecutionTimeMs(task, nowMs))
  const assistantOutputs = logs
    .filter((log) => log.event_type === 'assistant_output' && Boolean(log.detail?.trim()))
    .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))
  const assistantMessages = assistantOutputs.map((log) => log.detail?.trim() || '').filter(Boolean)
  const shouldShowOutputContent = !isDuplicateOutput(task.output_content, assistantMessages)
  const errorSummary = getTaskErrorSummary(task)

  return (
    <div data-testid="task-detail-page" className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Link to="/tasks" className="text-blue-600 hover:underline">任务看板</Link>
        <span>/</span>
        {task.requirement_id && (
          <>
            <Link to={`/requirements/${task.requirement_id}`} className="text-blue-600 hover:underline">
              需求 #{task.requirement_id}
            </Link>
            <span>/</span>
          </>
        )}
        <span className="text-gray-900 font-medium">Task #{task.id}</span>
      </div>

      {/* Header card */}
      <div className="rounded-2xl border bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[task.status] || 'bg-gray-100'}`}>
                {STATUS_LABEL[task.status] || task.status}
              </span>
              <span className="font-mono text-xs text-gray-400">#{task.id}</span>
              {task.project_label && <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700">{task.project_label}</span>}
              {task.agent_group && <span className="text-xs px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">{task.agent_group}</span>}
              {task.skill_name && (
                <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded" data-testid={`skill-badge-${task.id}`}>
                  🛠 {task.skill_name}
                </span>
              )}
              {task.runtime_backend && (
                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded" data-testid={`runtime-backend-${task.id}`}>
                  ⚙ {task.runtime_backend}
                </span>
              )}
              {task.runtime_selected_agent && (
                <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded" data-testid={`runtime-agent-${task.id}`}>
                  🤖 {task.runtime_selected_agent}
                </span>
              )}
            </div>
            <h2 className="mt-2 text-lg font-semibold" data-testid={`task-detail-${task.id}`}>{task.description.split('\n')[0]}</h2>
            <p className="mt-1 text-sm text-gray-500">Agent: @{task.agent_id}</p>
            {task.runtime_session_id && (
              <p className="mt-1 font-mono text-xs text-gray-400" data-testid={`runtime-session-${task.id}`}>
                Session: {task.runtime_session_id}
              </p>
            )}
          </div>
        </div>

        {/* Metadata */}
        <div className="flex flex-wrap items-center gap-3 mt-4 text-xs text-gray-500">
          {task.retry_of_task_id != null && <span>重试来源: #{task.retry_of_task_id}</span>}
          {executionTimeLabel && (
            <span data-testid={`execution-time-${task.id}`}>
              ⏱ {task.status === 'running' ? `已运行 ${executionTimeLabel}` : `耗时 ${executionTimeLabel}`}
            </span>
          )}
          <span>创建: {formatTime(task.created_at)}</span>
          <span>开始: {formatTime(task.started_at)}</span>
          <span>完成: {formatTime(task.completed_at)}</span>
        </div>
      </div>

      {/* Task description */}
      <div className="rounded-xl border bg-white p-5 shadow-sm">
        <h3 className="mb-2 text-sm font-bold text-gray-500">任务描述</h3>
        <div className="p-3 border rounded bg-gray-50">
          <Md>{task.description}</Md>
        </div>
      </div>

      {/* Linked requirement */}
      {task.requirement_title && (
        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <h3 className="mb-2 text-sm font-bold text-gray-500">关联需求</h3>
          <Link
            to={`/requirements/${task.requirement_id}`}
            className="block p-3 text-sm text-blue-800 border rounded bg-blue-50 hover:bg-blue-100 transition"
          >
            📋 #{task.requirement_id} {task.requirement_title}
          </Link>
        </div>
      )}

      {/* Output files */}
      {task.output_files && task.output_files.length > 0 && (
        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <h3 className="mb-2 text-sm font-bold text-gray-500">产出文件</h3>
          <ul className="p-3 space-y-1 text-sm border rounded bg-gray-50">
            {task.output_files.map((file) => (
              <li key={file} className="font-mono text-xs text-gray-700 truncate">📄 {file}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Error */}
      {errorSummary && (
        <div className="rounded-xl border border-red-200 bg-white p-5 shadow-sm">
          <h3 className="mb-2 text-sm font-bold text-gray-500">失败原因</h3>
          <div className="p-3 text-sm text-red-600 border border-red-100 rounded bg-red-50">{errorSummary}</div>
        </div>
      )}

      {/* Execution output */}
      {shouldShowOutputContent && task.output_content && (
        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <h3 className="mb-2 text-sm font-bold text-gray-500">执行产出</h3>
          <div className="p-3 border rounded bg-gray-50">
            <Md>{task.output_content}</Md>
          </div>
        </div>
      )}

      {/* Copilot output */}
      <div className="rounded-xl border bg-white p-5 shadow-sm" data-testid={`runtime-events-${task.id}`}>
        <h3 className="mb-2 text-sm font-bold text-gray-500">Copilot 输出</h3>
        <div className="p-3 border rounded bg-gray-50">
          {assistantOutputs.length === 0 ? (
            <p className="text-sm text-gray-400">
              {task.status === 'running' ? 'Copilot 正在执行，等待 assistant_output...' : '暂无 assistant_output'}
            </p>
          ) : (
            <div className="space-y-2">
              {assistantOutputs.map((log, index) => (
                <div key={log.id} className="p-3 bg-white border rounded border-slate-200" data-testid={`runtime-event-${task.id}-${index}`}>
                  <div className="flex flex-wrap items-center gap-2 mb-2 text-xs text-gray-400">
                    <span>assistant</span>
                    <span className="font-mono">{log.created_at}</span>
                  </div>
                  {log.detail && (
                    <div className="text-sm text-gray-700">
                      <Md>{log.detail}</Md>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Retry history */}
      <div className="rounded-xl border bg-white p-5 shadow-sm" data-testid={`history-${task.id}`}>
        <h3 className="mb-2 text-sm font-bold text-gray-500">重试历史时间线</h3>
        <div className="p-3 border rounded bg-gray-50">
          {history.length === 0 ? (
            <p className="text-sm text-gray-400">暂无重试历史</p>
          ) : (
            <div className="space-y-3">
              {history.map((item) => (
                <div key={item.task_id} className="flex items-start gap-3" data-testid={`history-item-${task.id}-${item.task_id}`}>
                  <div className={`mt-1 h-2.5 w-2.5 rounded-full ${STATUS_COLORS[item.status]?.split(' ')[0] || 'bg-gray-300'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-medium text-gray-700">尝试 #{item.attempt_no}</span>
                      <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[item.status] || 'bg-gray-100 text-gray-700'}`}>
                        {STATUS_LABEL[item.status] || item.status}
                      </span>
                      <span className="font-mono text-xs text-gray-400">Task #{item.task_id}</span>
                      {item.retry_of_task_id != null && <span className="text-xs text-gray-400">来自 #{item.retry_of_task_id}</span>}
                    </div>
                    <div className="flex flex-wrap gap-3 mt-1 text-xs text-gray-500">
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
  )
}
