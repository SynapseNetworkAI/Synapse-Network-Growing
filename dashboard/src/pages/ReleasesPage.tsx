import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ProjectPolicy, ReleaseCandidate, ReleaseTask, api } from '../api'
import { EmptyPane, FieldLabel, OverlayDrawer, StateBadge, useToast } from '../components/workbench'

type ReleaseTab = 'candidates' | 'tasks'

const STATUS_LABEL: Record<string, string> = {
  pending: '待交付',
  preparing_branch: '准备分支',
  pushing: '推送中',
  opening_pr: '打开 PR',
  repairing: '交付修复中',
  blocked: '阻塞',
  pr_open: 'PR 已打开',
  pr_opened: 'PR 已打开',
  pr_closed: 'PR 已关闭',
  ready_for_merge: '等待合并',
  merged: '已合并',
  abandoned: '已废弃',
  no_deploy: '无需部署',
  requested: '待执行',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

const SOURCE_LABEL: Record<string, string> = {
  manual: '人工创建',
  requirement_flow: '需求流转',
}

const TASK_STATUS_OPTIONS = ['', 'requested', 'completed', 'failed', 'cancelled']

function releaseTone(state: string | null | undefined) {
  if (state === 'merged' || state === 'completed') return 'delivered'
  if (state === 'pr_open' || state === 'pr_opened' || state === 'ready_for_merge' || state === 'requested') return 'ready'
  if (state === 'repairing' || state === 'pushing' || state === 'opening_pr' || state === 'preparing_branch') return 'running'
  if (state === 'blocked' || state === 'pr_closed' || state === 'abandoned' || state === 'failed') return 'blocked'
  if (state === 'pending') return 'ready'
  return 'muted'
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function releaseAction(item: ReleaseCandidate): { key: 'prepare' | 'open-pr' | 'repair-gate' | null; label: string } {
  const release = item.release
  if (!release) return { key: 'prepare', label: '准备分支' }
  if (release.status === 'release_blocked' && release.next_action === 'restart_current') return { key: 'prepare', label: '重新准备' }
  if (release.status === 'release_blocked' && release.next_action === 'repair_delivery' && release.repairable) return { key: 'repair-gate', label: '修复门禁' }
  if (release.status === 'branch_prepared' || release.status === 'ready') return { key: 'open-pr', label: '打开 PR' }
  if (release.state === 'pending') return { key: 'prepare', label: '准备分支' }
  return { key: null, label: '查看' }
}

function workflowRunIdFor(item: ReleaseCandidate) {
  return item.requirement.active_workflow_run_id ?? item.requirement.active_workflow_run_summary?.id ?? null
}

function defaultTaskDraft(policies: ProjectPolicy[]) {
  const first = policies[0]
  return {
    project_key: first?.project_key || '',
    branch_name: '',
    environment: 'staging' as 'staging' | 'production',
    note: '',
  }
}

export default function ReleasesPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [activeTab, setActiveTab] = useState<ReleaseTab>('candidates')
  const [candidates, setCandidates] = useState<ReleaseCandidate[]>([])
  const [tasks, setTasks] = useState<ReleaseTask[]>([])
  const [policies, setPolicies] = useState<ProjectPolicy[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [taskStatusFilter, setTaskStatusFilter] = useState('')
  const [taskEnvironmentFilter, setTaskEnvironmentFilter] = useState('')
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [syncBusy, setSyncBusy] = useState(false)
  const [taskDrawerOpen, setTaskDrawerOpen] = useState(false)
  const [taskDraft, setTaskDraft] = useState(defaultTaskDraft([]))
  const [taskBusy, setTaskBusy] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [nextCandidates, nextTasks, nextPolicies] = await Promise.all([
        api.getReleaseCandidates(),
        api.getReleaseTasks(),
        api.getProjectPolicies(),
      ])
      setCandidates(nextCandidates)
      setTasks(nextTasks)
      setPolicies(nextPolicies)
      if (!taskDraft.project_key && nextPolicies[0]?.project_key) {
        setTaskDraft((current) => ({ ...current, project_key: nextPolicies[0].project_key }))
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const filteredCandidates = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return candidates
    return candidates.filter((item) =>
      [
        String(item.requirement.id),
        item.requirement.title,
        item.requirement.project_display_name || '',
        item.requirement.project_key || '',
        item.release?.project_display_name || '',
        item.release?.status || '',
      ]
        .join('\n')
        .toLowerCase()
        .includes(needle),
    )
  }, [candidates, search])

  const filteredTasks = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return tasks.filter((task) => {
      if (taskStatusFilter && task.status !== taskStatusFilter) return false
      if (taskEnvironmentFilter && task.environment !== taskEnvironmentFilter) return false
      if (!needle) return true
      return [
        task.project_key,
        task.project_display_name || '',
        task.branch_name,
        task.environment,
        task.status,
        task.actor || '',
        task.operator || '',
        task.note || '',
      ].join('\n').toLowerCase().includes(needle)
    })
  }, [tasks, search, taskStatusFilter, taskEnvironmentFilter])

  const selectedPolicy = policies.find((policy) => policy.project_key === taskDraft.project_key)

  const createTask = async () => {
    if (taskBusy) return
    setTaskBusy(true)
    try {
      await api.createReleaseTask({
        project_key: taskDraft.project_key,
        project_display_name: selectedPolicy?.display_name || null,
        branch_name: taskDraft.branch_name,
        environment: taskDraft.environment,
        actor: 'operator',
        note: taskDraft.note || null,
      })
      toast.success('发布任务已创建')
      setTaskDrawerOpen(false)
      setTaskDraft(defaultTaskDraft(policies))
      await load()
      setActiveTab('tasks')
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建发布任务失败'
      toast.error(message)
    } finally {
      setTaskBusy(false)
    }
  }

  const updateTaskStatus = async (task: ReleaseTask, status: 'completed' | 'failed' | 'cancelled') => {
    const busyKey = `release-task-${task.id}-${status}`
    if (busyAction) return
    setBusyAction(busyKey)
    try {
      await api.updateReleaseTask(task.id, {
        status,
        operator: 'operator',
        note: task.note,
      })
      toast.success(`发布任务已标记为${STATUS_LABEL[status]}`)
      await load()
    } catch (error) {
      const message = error instanceof Error ? error.message : '更新发布任务失败'
      toast.error(message)
    } finally {
      setBusyAction(null)
    }
  }

  return (
    <div className="space-y-5" data-testid="releases-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Releases</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">发布列表</h2>
            <p className="mt-2 text-sm text-[color:var(--ops-text-muted)]">需求交付看 PR 链路；发布管理记录人工分支发布任务。</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              className="w-72 rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm"
              placeholder={activeTab === 'tasks' ? '搜索 project / branch / operator' : '搜索 requirement / project'}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
              刷新
            </button>
            {activeTab === 'candidates' ? (
              <button
                type="button"
                className="rounded-xl border border-[color:var(--ops-state-running-border)] px-4 py-2.5 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50"
                disabled={syncBusy}
                onClick={async () => {
                  if (syncBusy) return
                  setSyncBusy(true)
                  try {
                    const response = await api.syncReleasePrStatuses()
                    const result = response.result || {}
                    const processed = Number(result.processed_count || 0)
                    const merged = Array.isArray(result.merged_ids) ? result.merged_ids.length : 0
                    const closed = Array.isArray(result.closed_ids) ? result.closed_ids.length : 0
                    const missing = Array.isArray(result.missing_ids) ? result.missing_ids.length : 0
                    toast.success(`PR 状态同步完成：处理 ${processed} 条，合并 ${merged} 条，关闭 ${closed + missing} 条`)
                    await load()
                  } catch (error) {
                    const message = error instanceof Error ? error.message : '同步 PR 状态失败，请稍后重试'
                    toast.error(message)
                  } finally {
                    setSyncBusy(false)
                  }
                }}
              >
                {syncBusy ? '同步中…' : '同步 PR 状态'}
              </button>
            ) : (
              <button
                type="button"
                className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
                disabled={policies.length === 0}
                onClick={() => {
                  setTaskDraft(defaultTaskDraft(policies))
                  setTaskDrawerOpen(true)
                }}
              >
                新建发布任务
              </button>
            )}
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          <button
            type="button"
            className={`rounded-full border px-4 py-2 text-sm ${activeTab === 'candidates' ? 'border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] text-[color:var(--ops-state-running-text)]' : 'border-[color:var(--ops-stroke-soft)] text-[color:var(--ops-text-muted)]'}`}
            onClick={() => setActiveTab('candidates')}
          >
            需求交付
          </button>
          <button
            type="button"
            className={`rounded-full border px-4 py-2 text-sm ${activeTab === 'tasks' ? 'border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] text-[color:var(--ops-state-running-text)]' : 'border-[color:var(--ops-stroke-soft)] text-[color:var(--ops-text-muted)]'}`}
            onClick={() => setActiveTab('tasks')}
          >
            发布管理
          </button>
          {activeTab === 'tasks' ? (
            <>
              <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={taskEnvironmentFilter} onChange={(event) => setTaskEnvironmentFilter(event.target.value)}>
                <option value="">全部环境</option>
                <option value="staging">staging</option>
                <option value="production">production</option>
              </select>
              <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={taskStatusFilter} onChange={(event) => setTaskStatusFilter(event.target.value)}>
                {TASK_STATUS_OPTIONS.map((status) => (
                  <option key={status || 'all'} value={status}>{status ? STATUS_LABEL[status] : '全部状态'}</option>
                ))}
              </select>
            </>
          ) : null}
        </div>
      </section>

      {activeTab === 'candidates' ? (
        <ReleaseCandidatesTable
          filtered={filteredCandidates}
          loading={loading}
          busyAction={busyAction}
          setBusyAction={setBusyAction}
          load={load}
          navigate={navigate}
          toast={toast}
        />
      ) : (
        <ReleaseTasksTable
          tasks={filteredTasks}
          loading={loading}
          busyAction={busyAction}
          onUpdateStatus={updateTaskStatus}
        />
      )}

      <OverlayDrawer
        open={taskDrawerOpen}
        eyebrow="Release Task"
        title="新建发布任务"
        description="只创建人工发布任务记录，不触发真实部署。"
        onClose={() => setTaskDrawerOpen(false)}
        actions={
          <button
            type="button"
            className="rounded-2xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            disabled={taskBusy || !taskDraft.project_key || !taskDraft.branch_name.trim()}
            onClick={createTask}
          >
            {taskBusy ? '创建中…' : '创建发布任务'}
          </button>
        }
      >
        <div className="space-y-5">
          <label className="block space-y-2">
            <FieldLabel>项目</FieldLabel>
            <select
              className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm"
              value={taskDraft.project_key}
              onChange={(event) => setTaskDraft((current) => ({ ...current, project_key: event.target.value }))}
            >
              {policies.map((policy) => (
                <option key={policy.id} value={policy.project_key}>{policy.display_name} · {policy.project_key}</option>
              ))}
            </select>
          </label>
          <label className="block space-y-2">
            <FieldLabel>分支</FieldLabel>
            <input
              className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm"
              placeholder="codex/branch-based-staging-deploy"
              value={taskDraft.branch_name}
              onChange={(event) => setTaskDraft((current) => ({ ...current, branch_name: event.target.value }))}
            />
          </label>
          <label className="block space-y-2">
            <FieldLabel>发布环境</FieldLabel>
            <select
              className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm"
              value={taskDraft.environment}
              onChange={(event) => setTaskDraft((current) => ({ ...current, environment: event.target.value as 'staging' | 'production' }))}
            >
              <option value="staging">staging</option>
              <option value="production">production</option>
            </select>
          </label>
          {taskDraft.environment === 'production' ? (
            <div className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] px-4 py-3 text-sm font-semibold text-[color:var(--ops-state-blocked-text)]">
              这里只创建发布任务，不会自动部署生产；生产 deploy/rollback 仍必须走 Human Gate。
            </div>
          ) : null}
          <label className="block space-y-2">
            <FieldLabel>备注</FieldLabel>
            <textarea
              className="min-h-32 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm"
              placeholder="记录发布窗口、手动执行位置或回滚注意事项。"
              value={taskDraft.note}
              onChange={(event) => setTaskDraft((current) => ({ ...current, note: event.target.value }))}
            />
          </label>
        </div>
      </OverlayDrawer>
    </div>
  )
}

function ReleaseCandidatesTable({
  filtered,
  loading,
  busyAction,
  setBusyAction,
  load,
  navigate,
  toast,
}: Readonly<{
  filtered: ReleaseCandidate[]
  loading: boolean
  busyAction: string | null
  setBusyAction: (value: string | null) => void
  load: () => Promise<void>
  navigate: (path: string) => void
  toast: ReturnType<typeof useToast>
}>) {
  return (
    <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse">
          <thead className="bg-[color:var(--ops-panel-subtle)]">
            <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
              <th className="px-5 py-4 font-medium">Requirement</th>
              <th className="px-4 py-4 font-medium">验证</th>
              <th className="px-4 py-4 font-medium">发布状态</th>
              <th className="px-4 py-4 font-medium">分支 / PR</th>
              <th className="px-4 py-4 font-medium">工作流</th>
              <th className="px-4 py-4 font-medium">更新时间</th>
              <th className="px-5 py-4 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item) => (
              <tr key={item.requirement.id} className="border-t border-[color:var(--ops-stroke-soft)] hover:bg-[color:var(--ops-panel-subtle)]">
                <td className="px-5 py-4">
                  <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">
                    #{item.requirement.id} {item.requirement.title}
                  </div>
                  <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">
                    {item.release?.project_display_name || item.requirement.project_display_name || item.requirement.project_key || '-'}
                  </div>
                </td>
                <td className="px-4 py-4">
                  <StateBadge tone={item.validation.status === 'passed' ? 'delivered' : 'validating'}>{item.validation.status}</StateBadge>
                </td>
                <td className="px-4 py-4">
                  <StateBadge tone={releaseTone(item.release?.status || item.release?.state)}>
                    {STATUS_LABEL[item.release?.status || item.release?.state || 'pending'] || item.release?.status || item.release?.state || 'pending'}
                  </StateBadge>
                </td>
                <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                  <div>{item.release?.branch_name || '-'} · PR {item.release?.pr_number || '-'}</div>
                  {item.release?.pr_status || item.release?.last_pr_status_synced_at ? (
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">
                      GitHub: {item.release?.pr_status || '-'} · synced {formatTime(item.release?.last_pr_status_synced_at || null)}
                    </div>
                  ) : null}
                  {item.release?.pr_sync_failure_summary ? (
                    <div className="mt-1 line-clamp-1 text-xs text-[color:var(--ops-state-blocked-text)]">{item.release.pr_sync_failure_summary}</div>
                  ) : null}
                </td>
                <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                  {item.requirement.active_workflow_run_summary
                    ? `${item.requirement.active_workflow_run_summary.workflow_key} · ${item.requirement.active_workflow_run_summary.current_state}`
                    : '-'}
                </td>
                <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(item.release?.updated_at || item.validation.updated_at)}</td>
                <td className="px-5 py-4">
                  <div className="flex flex-wrap justify-end gap-2">
                    <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/requirements/${item.requirement.id}`)}>
                      需求
                    </button>
                    <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/workflows/${workflowRunIdFor(item)}`)} disabled={!workflowRunIdFor(item)}>
                      工作流
                    </button>
                    {(() => {
                      const action = releaseAction(item)
                      const busyKey = `${action.key}-${item.requirement.id}`
                      if (!action.key) return null
                      return (
                        <button
                          type="button"
                          className="rounded-lg border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50"
                          disabled={busyAction === busyKey}
                          onClick={async () => {
                            if (action.key === 'repair-gate') {
                              navigate(`/releases/${item.requirement.id}`)
                              return
                            }
                            setBusyAction(busyKey)
                            try {
                              if (action.key === 'prepare') {
                                await api.prepareRelease(item.requirement.id, { actor: 'operator', note: 'Release list branch preparation' })
                                toast.success('已准备交付分支')
                              } else if (action.key === 'open-pr') {
                                await api.openReleasePr(item.requirement.id, { actor: 'operator', note: 'Release list open PR' })
                                toast.success('已触发 PR 交付')
                              }
                            } catch (error) {
                              const message = error instanceof Error ? error.message : '发布动作失败，请重试'
                              toast.error(message)
                            } finally {
                              await load()
                              setBusyAction(null)
                            }
                          }}
                        >
                          {busyAction === busyKey ? '处理中…' : action.label}
                        </button>
                      )
                    })()}
                    <button type="button" className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white" onClick={() => navigate(`/releases/${item.requirement.id}`)}>
                      查看
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!loading && filtered.length === 0 && (
        <div className="p-6">
          <EmptyPane>暂无发布候选。</EmptyPane>
        </div>
      )}
    </section>
  )
}

function ReleaseTasksTable({
  tasks,
  loading,
  busyAction,
  onUpdateStatus,
}: Readonly<{
  tasks: ReleaseTask[]
  loading: boolean
  busyAction: string | null
  onUpdateStatus: (task: ReleaseTask, status: 'completed' | 'failed' | 'cancelled') => void
}>) {
  return (
    <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse">
          <thead className="bg-[color:var(--ops-panel-subtle)]">
            <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
              <th className="px-5 py-4 font-medium">来源</th>
              <th className="px-4 py-4 font-medium">项目 / 分支</th>
              <th className="px-4 py-4 font-medium">环境</th>
              <th className="px-4 py-4 font-medium">状态</th>
              <th className="px-4 py-4 font-medium">创建 / 执行</th>
              <th className="px-4 py-4 font-medium">备注</th>
              <th className="px-4 py-4 font-medium">更新时间</th>
              <th className="px-5 py-4 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => (
              <tr key={task.id} className="border-t border-[color:var(--ops-stroke-soft)] hover:bg-[color:var(--ops-panel-subtle)]">
                <td className="px-5 py-4">
                  <StateBadge tone={task.source_type === 'requirement_flow' ? 'running' : 'muted'}>
                    {SOURCE_LABEL[task.source_type] || task.source_type}
                  </StateBadge>
                  {task.requirement_id ? <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">Requirement #{task.requirement_id}</div> : null}
                </td>
                <td className="px-4 py-4">
                  <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{task.project_display_name || task.project_key}</div>
                  <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-muted)]">{task.branch_name}</div>
                </td>
                <td className="px-4 py-4">
                  <StateBadge tone={task.environment === 'production' ? 'blocked' : 'ready'}>{task.environment}</StateBadge>
                </td>
                <td className="px-4 py-4">
                  <StateBadge tone={releaseTone(task.status)}>{STATUS_LABEL[task.status] || task.status}</StateBadge>
                </td>
                <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                  <div>创建：{task.actor || '-'}</div>
                  <div className="mt-1">执行：{task.operator || '-'}</div>
                </td>
                <td className="max-w-xs px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                  <div className="line-clamp-2">{task.note || '-'}</div>
                </td>
                <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(task.updated_at || task.created_at)}</td>
                <td className="px-5 py-4">
                  {task.status === 'requested' ? (
                    <div className="flex flex-wrap justify-end gap-2">
                      <button
                        type="button"
                        className="rounded-lg border border-[color:var(--ops-state-ready-border)] px-3 py-2 text-sm text-[color:var(--ops-state-ready-text)] disabled:opacity-50"
                        disabled={busyAction === `release-task-${task.id}-completed`}
                        onClick={() => onUpdateStatus(task, 'completed')}
                      >
                        标记为已完成
                      </button>
                      <button
                        type="button"
                        className="rounded-lg border border-[color:var(--ops-state-blocked-border)] px-3 py-2 text-sm text-[color:var(--ops-state-blocked-text)] disabled:opacity-50"
                        disabled={busyAction === `release-task-${task.id}-failed`}
                        onClick={() => onUpdateStatus(task, 'failed')}
                      >
                        标记为失败
                      </button>
                      <button
                        type="button"
                        className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-50"
                        disabled={busyAction === `release-task-${task.id}-cancelled`}
                        onClick={() => onUpdateStatus(task, 'cancelled')}
                      >
                        取消
                      </button>
                    </div>
                  ) : (
                    <div className="text-right text-sm text-[color:var(--ops-text-caption)]">已归档</div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!loading && tasks.length === 0 && (
        <div className="p-6">
          <EmptyPane>暂无发布任务。点击“新建发布任务”记录一次人工分支发布。</EmptyPane>
        </div>
      )}
    </section>
  )
}
