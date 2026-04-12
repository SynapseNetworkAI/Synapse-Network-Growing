import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { api, Task, TaskLog, TaskHistoryItem, FileChange, TaskFileChanges, AgentsMemoryResult, agentsMemoryApi } from '../api'

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-700',
  pending_approval: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  failed: 'bg-red-100 text-red-700',
  deleted: 'bg-zinc-200 text-zinc-700',
}

const STATUS_LABEL: Record<string, string> = {
  pending: '待执行',
  running: '执行中',
  pending_approval: '待审批',
  completed: '已完成',
  rejected: '已拒绝',
  failed: '失败',
  deleted: '已删除',
}

const STEP_TYPE_LABEL: Record<string, string> = {
  research: 'Research',
  synthesis: 'Synthesis',
  implementation: 'Implementation',
  review: 'Review',
  test: 'Validation',
  closeout: 'Closeout',
  bugfix: 'Bugfix',
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

// ── Diff viewer ─────────────────────────────────────────────────────────────

function DiffLine({ line }: Readonly<{ line: string }>) {
  if (line.startsWith('+') && !line.startsWith('+++'))
    return <div className="px-2 font-mono text-xs leading-5 text-green-800 whitespace-pre bg-green-50">{line}</div>
  if (line.startsWith('-') && !line.startsWith('---'))
    return <div className="px-2 font-mono text-xs leading-5 text-red-800 whitespace-pre bg-red-50">{line}</div>
  if (line.startsWith('@@'))
    return <div className="px-2 font-mono text-xs leading-5 text-blue-600 whitespace-pre bg-blue-50">{line}</div>
  return <div className="px-2 font-mono text-xs leading-5 text-gray-700 whitespace-pre">{line}</div>
}

function DiffModal({ file, onClose }: Readonly<{ file: FileChange; onClose: () => void }>) {
  return (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
      <dialog
        open
        className="relative w-[90vw] max-w-4xl max-h-[85vh] flex flex-col rounded-xl bg-white shadow-2xl m-0 p-0 border-0"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b bg-gray-50 rounded-t-xl">
          <div className="min-w-0">
            <span className="block font-mono text-sm font-semibold text-gray-800 truncate">{file.filename}</span>
            <span className="text-xs text-gray-500">
              <span className="text-green-600">+{file.additions}</span>
              {' / '}
              <span className="text-red-500">-{file.deletions}</span>
            </span>
          </div>
          <button
            className="p-1 ml-4 text-gray-400 rounded shrink-0 hover:bg-gray-200 hover:text-gray-700"
            onClick={onClose}
          >
            ✕
          </button>
        </div>
        {/* Diff body */}
        <div className="flex-1 overflow-auto rounded-b-xl">
          {file.patch ? (
            <div className="divide-y divide-gray-100">
              {file.patch.split('\n').map((line, i) => (
                // eslint-disable-next-line react/no-array-index-key
                <DiffLine key={i} line={line} />
              ))}
            </div>
          ) : (
            <p className="p-4 text-sm text-gray-400">无 diff 内容</p>
          )}
        </div>
      </dialog>
    </div>
  )
}

export default function TaskDetail() {
  const { id } = useParams<{ id: string }>()
  const taskId = Number(id)

  const [task, setTask] = useState<Task | null>(null)
  const [logs, setLogs] = useState<TaskLog[]>([])
  const [history, setHistory] = useState<TaskHistoryItem[]>([])
  const [fileChanges, setFileChanges] = useState<TaskFileChanges | null>(null)
  const [selectedDiff, setSelectedDiff] = useState<FileChange | null>(null)
  const [memoryResults, setMemoryResults] = useState<AgentsMemoryResult[]>([])
  const [nowMs, setNowMs] = useState(() => Date.now())
  const logsPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadTask = useCallback(async () => {
    const pageData = await api.getTasks({ page: 1, page_size: 100 })
    const found = pageData.items.find((t) => t.id === taskId) || null
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
    api.getTaskFileChanges(taskId).then(setFileChanges).catch(() => {})
  }, [loadTask, loadLogs, taskId])

  // Agents-Memory: search using task description once task is loaded
  useEffect(() => {
    if (!task?.description) return
    const query = task.description.slice(0, 120)
    agentsMemoryApi.search(query, 5)
      .then((r) => setMemoryResults(r.results))
      .catch(() => {})
  }, [task?.description])

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
        <div className="p-8 text-sm text-gray-500 bg-white border rounded-xl">加载中…</div>
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
      {/* Diff modal */}
      {selectedDiff && <DiffModal file={selectedDiff} onClose={() => setSelectedDiff(null)} />}
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
        <span className="font-medium text-gray-900">Task #{task.id}</span>
      </div>

      {/* Header card */}
      <div className="p-6 bg-white border shadow-sm rounded-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[task.status] || 'bg-gray-100'}`}>
                {STATUS_LABEL[task.status] || task.status}
              </span>
              <span className="font-mono text-xs text-gray-400">#{task.id}</span>
              {task.project_label && <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700">{task.project_label}</span>}
              {task.agent_group && <span className="text-xs px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">{task.agent_group}</span>}
              {task.workflow_step_type && (
                <span className="text-xs px-2 py-0.5 rounded bg-violet-50 text-violet-700">
                  {STEP_TYPE_LABEL[task.workflow_step_type] || task.workflow_step_type}
                </span>
              )}
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
            {task.workflow_step_title && (
              <p className="mt-1 text-sm text-gray-500">
                工作流步骤：{task.workflow_step_title}
                {task.workflow_step_type === 'review' || task.workflow_step_type === 'test'
                  ? '。这是验证阶段任务，主要职责是评审或验证已有实现，不直接承担代码实现。'
                  : null}
              </p>
            )}
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
      <div className="p-5 bg-white border shadow-sm rounded-xl">
        <h3 className="mb-2 text-sm font-bold text-gray-500">任务描述</h3>
        <div className="p-3 border rounded bg-gray-50">
          <Md>{task.description}</Md>
        </div>
      </div>

      {/* Linked requirement */}
      {task.requirement_title && (
        <div className="p-5 bg-white border shadow-sm rounded-xl">
          <h3 className="mb-2 text-sm font-bold text-gray-500">关联需求</h3>
          <Link
            to={`/requirements/${task.requirement_id}`}
            className="block p-3 text-sm text-blue-800 transition border rounded bg-blue-50 hover:bg-blue-100"
          >
            📋 #{task.requirement_id} {task.requirement_title}
          </Link>
        </div>
      )}

      {/* File changes (git diff) */}
      {fileChanges && fileChanges.changed_files.length > 0 && (
        <div className="p-5 bg-white border shadow-sm rounded-xl">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-bold text-gray-500">文件改动</h3>
            <span className="text-xs text-gray-400">
              {fileChanges.source === 'snapshot' ? '📸 快照' : '⚡ 实时'}
              {fileChanges.target_project_path && ` · ${fileChanges.target_project_path.split('/').slice(-2).join('/')}`}
            </span>
          </div>
          <ul className="space-y-1">
            {fileChanges.changed_files.map((f) => (
              <li key={f.filename}>
                <button
                  className="flex items-center w-full gap-2 px-3 py-2 text-left transition border border-transparent rounded-lg hover:bg-gray-50 hover:border-gray-200"
                  onClick={() => setSelectedDiff(f)}
                >
                  <span className="flex-1 font-mono text-xs text-gray-700 truncate">📄 {f.filename}</span>
                  <span className="text-xs text-green-600 shrink-0">+{f.additions}</span>
                  <span className="text-xs text-red-500 shrink-0">-{f.deletions}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Agents-Memory related records */}
      {memoryResults.length > 0 && (
        <div className="p-5 bg-white border shadow-sm rounded-xl" data-testid="memory-section">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-gray-500">🧠 相关工程记忆（Agents-Memory）</h3>
            <a
              href={`http://localhost:10000`}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-indigo-600 hover:underline"
            >
              在 Agents-Memory 中搜索 →
            </a>
          </div>
          <ul className="space-y-1.5">
            {memoryResults.map((r) => (
              <li key={`${r.type}-${r.id}`}>
                <a
                  href={agentsMemoryApi.linkFor(r)}
                  target="_blank"
                  rel="noreferrer"
                  className={`flex items-start gap-3 px-3 py-2.5 rounded-lg border-l-4 bg-gray-50 hover:bg-gray-100 transition ${r.type === 'error' ? 'border-red-400' : 'border-blue-400'}`}
                >
                  <span className={`mt-0.5 shrink-0 text-xs font-bold px-1.5 py-0.5 rounded ${r.type === 'error' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}`}>
                    {r.type === 'error' ? 'ERR' : 'WIKI'}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-800 truncate">{r.title}</span>
                      <span className="font-mono text-xs text-gray-400 shrink-0">{r.id}</span>
                      <span className="text-xs text-gray-300 shrink-0">{(r.score * 100).toFixed(0)}%</span>
                    </div>
                    {r.snippet && <p className="mt-0.5 text-xs text-gray-500 line-clamp-2">{r.snippet}</p>}
                  </div>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Output files */}
      {task.output_files && task.output_files.length > 0 && (
        <div className="p-5 bg-white border shadow-sm rounded-xl">
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
        <div className="p-5 bg-white border border-red-200 shadow-sm rounded-xl">
          <h3 className="mb-2 text-sm font-bold text-gray-500">失败原因</h3>
          <div className="p-3 text-sm text-red-600 border border-red-100 rounded bg-red-50">{errorSummary}</div>
        </div>
      )}

      {/* Execution output */}
      {shouldShowOutputContent && task.output_content && (
        <div className="p-5 bg-white border shadow-sm rounded-xl">
          <h3 className="mb-2 text-sm font-bold text-gray-500">执行产出</h3>
          <div className="p-3 border rounded bg-gray-50">
            <Md>{task.output_content}</Md>
          </div>
        </div>
      )}

      {/* Copilot output */}
      <div className="p-5 bg-white border shadow-sm rounded-xl" data-testid={`runtime-events-${task.id}`}>
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
      <div className="p-5 bg-white border shadow-sm rounded-xl" data-testid={`history-${task.id}`}>
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
