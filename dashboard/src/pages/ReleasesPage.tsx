import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { OnlineReleaseRecord, ProjectPolicy, ReleaseBranchOption, ReleaseCandidate, ReleaseTask, api } from '../api'
import { EmptyPane, FieldLabel, OverlayDrawer, StateBadge, useToast } from '../components/workbench'

type ReleaseTab = 'candidates' | 'tasks' | 'online'

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
  succeeded: '上线成功',
  deploy: 'deploy',
  promote: 'promote',
  rollback: 'rollback',
}

const SOURCE_LABEL: Record<string, string> = {
  manual: '人工创建',
  requirement_flow: '需求流转',
}

const TASK_STATUS_OPTIONS = ['', 'requested', 'completed', 'failed', 'cancelled']
const DEFAULT_RELEASE_TARGETS = [
  { project_key: 'synapse-network', project_display_name: 'Synapse-Network', service_key: 'gateway', service_label: 'Gateway API' },
  { project_key: 'synapse-network', project_display_name: 'Synapse-Network', service_key: 'gateway-admin', service_label: 'Gateway Admin API' },
  { project_key: 'synapse-network', project_display_name: 'Synapse-Network', service_key: 'admin-front', service_label: 'Admin Front' },
  { project_key: 'synapse-network', project_display_name: 'Synapse-Network', service_key: 'user-front', service_label: 'User Front' },
]

function releaseTone(state: string | null | undefined) {
  if (state === 'merged' || state === 'completed' || state === 'succeeded' || state === 'passed') return 'delivered'
  if (state === 'pr_open' || state === 'pr_opened' || state === 'ready_for_merge' || state === 'requested') return 'ready'
  if (state === 'repairing' || state === 'pushing' || state === 'opening_pr' || state === 'preparing_branch') return 'running'
  if (state === 'blocked' || state === 'pr_closed' || state === 'abandoned' || state === 'failed') return 'blocked'
  if (state === 'pending') return 'ready'
  return 'muted'
}

function shortSha(value: string | null | undefined) {
  if (!value) return '-'
  return value.length > 10 ? value.slice(0, 10) : value
}

function compactJson(value: unknown) {
  if (value == null) return '-'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
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
  const fallback = DEFAULT_RELEASE_TARGETS[0]
  const policy = policies.find((item) => item.project_key === fallback.project_key)
  return {
    project_key: fallback.project_key,
    project_display_name: policy?.display_name || fallback.project_display_name,
    service_key: fallback.service_key,
    branch_name: '',
    environment: 'staging' as 'staging' | 'production',
    note: '',
  }
}

function releaseTargets(policies: ProjectPolicy[]) {
  return DEFAULT_RELEASE_TARGETS.map((target) => {
    const policy = policies.find((item) => item.project_key === target.project_key)
    return { ...target, project_display_name: policy?.display_name || target.project_display_name }
  })
}

export default function ReleasesPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [activeTab, setActiveTab] = useState<ReleaseTab>('candidates')
  const [candidates, setCandidates] = useState<ReleaseCandidate[]>([])
  const [tasks, setTasks] = useState<ReleaseTask[]>([])
  const [onlineRecords, setOnlineRecords] = useState<OnlineReleaseRecord[]>([])
  const [policies, setPolicies] = useState<ProjectPolicy[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [taskStatusFilter, setTaskStatusFilter] = useState('')
  const [taskEnvironmentFilter, setTaskEnvironmentFilter] = useState('')
  const [onlineEnvironmentFilter, setOnlineEnvironmentFilter] = useState('')
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [syncBusy, setSyncBusy] = useState(false)
  const [taskDrawerOpen, setTaskDrawerOpen] = useState(false)
  const [taskDetail, setTaskDetail] = useState<ReleaseTask | null>(null)
  const [onlineDetail, setOnlineDetail] = useState<OnlineReleaseRecord | null>(null)
  const [taskDraft, setTaskDraft] = useState(defaultTaskDraft([]))
  const [taskBusy, setTaskBusy] = useState(false)
  const [branchOptions, setBranchOptions] = useState<ReleaseBranchOption[]>([])
  const [branchQuery, setBranchQuery] = useState('')
  const [branchLoading, setBranchLoading] = useState(false)
  const [branchError, setBranchError] = useState<string | null>(null)
  const taskTargets = useMemo(() => releaseTargets(policies), [policies])

  const load = async () => {
    setLoading(true)
    try {
      const [nextCandidates, nextTasks, nextPolicies] = await Promise.all([
        api.getReleaseCandidates(),
        api.getReleaseTasks(),
        api.getProjectPolicies(),
      ])
      const nextOnlineRecords = await api.getOnlineReleaseRecords({ limit: 100 }).catch(() => [])
      setCandidates(nextCandidates)
      setTasks(nextTasks)
      setOnlineRecords(nextOnlineRecords)
      setPolicies(nextPolicies)
      if (!taskDraft.project_key) {
        setTaskDraft(defaultTaskDraft(nextPolicies))
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
        task.service_key || '',
        task.branch_name,
        task.environment,
        task.status,
        task.actor || '',
        task.operator || '',
        task.note || '',
      ].join('\n').toLowerCase().includes(needle)
    })
  }, [tasks, search, taskStatusFilter, taskEnvironmentFilter])

  const filteredOnlineRecords = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return onlineRecords.filter((record) => {
      if (onlineEnvironmentFilter && record.environment !== onlineEnvironmentFilter) return false
      if (!needle) return true
      return [
        record.project_key,
        record.project_display_name || '',
        record.service_key || '',
        record.branch_name || '',
        record.commit_sha || '',
        record.environment,
        record.action,
        record.actor || '',
        record.health_status || '',
        record.notes || '',
      ].join('\n').toLowerCase().includes(needle)
    })
  }, [onlineRecords, onlineEnvironmentFilter, search])

  const selectedTarget = taskTargets.find((target) => target.project_key === taskDraft.project_key && target.service_key === taskDraft.service_key) || taskTargets[0]
  const filteredBranchOptions = useMemo(() => {
    const needle = branchQuery.trim().toLowerCase()
    const nextOptions = needle
      ? branchOptions.filter((branch) => branch.name.toLowerCase().includes(needle) || (branch.commit_sha || '').toLowerCase().includes(needle))
      : branchOptions
    if (!taskDraft.branch_name || nextOptions.some((branch) => branch.name === taskDraft.branch_name)) {
      return nextOptions
    }
    const selected = branchOptions.find((branch) => branch.name === taskDraft.branch_name)
    return selected ? [selected, ...nextOptions] : nextOptions
  }, [branchOptions, branchQuery, taskDraft.branch_name])

  useEffect(() => {
    if (!taskDrawerOpen || !taskDraft.project_key) return
    let cancelled = false
    setBranchOptions([])
    setBranchError(null)
    setBranchLoading(true)
    api.getReleaseTaskBranchOptions({
      project_key: taskDraft.project_key,
      service_key: taskDraft.service_key || null,
    })
      .then((options) => {
        if (cancelled) return
        setBranchOptions(options)
        setTaskDraft((current) => {
          if (options.some((option) => option.name === current.branch_name)) return current
          return { ...current, branch_name: '' }
        })
      })
      .catch((error) => {
        if (cancelled) return
        const message = error instanceof Error ? error.message : '读取 GitHub 分支失败'
        setBranchError(message)
        setTaskDraft((current) => ({ ...current, branch_name: '' }))
      })
      .finally(() => {
        if (!cancelled) setBranchLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [taskDrawerOpen, taskDraft.project_key, taskDraft.service_key])

  const createTask = async () => {
    if (taskBusy) return
    setTaskBusy(true)
    try {
      await api.createReleaseTask({
        project_key: taskDraft.project_key,
        project_display_name: selectedTarget?.project_display_name || taskDraft.project_display_name || null,
        service_key: taskDraft.service_key,
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
    if (busyAction) {
      toast.info('已有发布任务操作正在处理，请稍候。')
      return
    }
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

  const deployTaskToStaging = async (task: ReleaseTask) => {
    const busyKey = `release-task-${task.id}-deploy-staging`
    if (busyAction) return
    setBusyAction(busyKey)
    try {
      await api.deployReleaseTaskToStaging(task.id, {
        actor: 'operator',
        note: task.note,
      })
      toast.success('Staging 发布已触发')
      await load()
    } catch (error) {
      const message = error instanceof Error ? error.message : '触发 staging 发布失败'
      toast.error(message)
    } finally {
      setBusyAction(null)
    }
  }

  const createTaskPr = async (task: ReleaseTask) => {
    const busyKey = `release-task-${task.id}-create-pr`
    if (busyAction) return
    setBusyAction(busyKey)
    try {
      await api.createReleaseTaskPr(task.id, {
        actor: 'operator',
        note: task.note,
      })
      toast.success('PR 已提交，等待 checks 通过后可发布到 staging')
      await load()
    } catch (error) {
      const message = error instanceof Error ? error.message : '提交 PR 失败'
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
            <p className="mt-2 text-sm text-[color:var(--ops-text-muted)]">需求交付看 PR；发布管理记录任务；上线记录只显示真实成功部署。</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              className="w-72 rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm"
              placeholder={activeTab === 'tasks' ? '搜索 project / branch / operator' : activeTab === 'online' ? '搜索 project / branch / commit' : '搜索 requirement / project'}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
              刷新
            </button>
            <button
              type="button"
              className="rounded-xl border border-[color:var(--ops-state-running-border)] px-4 py-2.5 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50"
              disabled={syncBusy}
              onClick={async () => {
                if (syncBusy) return
                setSyncBusy(true)
                try {
                  const [prResponse, deploymentResponse] = await Promise.all([
                    api.syncReleasePrStatuses(),
                    api.syncReleaseTaskDeploymentStatuses(),
                  ])
                  const prResult = prResponse.result || {}
                  const prProcessed = Number(prResult.processed_count || 0)
                  const deployments = Number(deploymentResponse.processed_count || 0)
                  const succeeded = Array.isArray(deploymentResponse.succeeded_ids) ? deploymentResponse.succeeded_ids.length : 0
                  const failed = Array.isArray(deploymentResponse.failed_ids) ? deploymentResponse.failed_ids.length : 0
                  toast.success(`状态同步完成：PR ${prProcessed} 条，发布 ${deployments} 条，成功 ${succeeded}，失败 ${failed}`)
                  await load()
                } catch (error) {
                  const message = error instanceof Error ? error.message : '同步状态失败，请稍后重试'
                  toast.error(message)
                } finally {
                  setSyncBusy(false)
                }
              }}
            >
              {syncBusy ? '同步中…' : '同步状态'}
            </button>
            {activeTab === 'tasks' ? (
              <button
                type="button"
                className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
                onClick={() => {
                  setTaskDraft(defaultTaskDraft(policies))
                  setBranchQuery('')
                  setTaskDrawerOpen(true)
                }}
              >
                新建发布任务
              </button>
            ) : null}
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
          <button
            type="button"
            className={`rounded-full border px-4 py-2 text-sm ${activeTab === 'online' ? 'border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] text-[color:var(--ops-state-running-text)]' : 'border-[color:var(--ops-stroke-soft)] text-[color:var(--ops-text-muted)]'}`}
            onClick={() => setActiveTab('online')}
          >
            上线记录
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
          ) : activeTab === 'online' ? (
            <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={onlineEnvironmentFilter} onChange={(event) => setOnlineEnvironmentFilter(event.target.value)}>
              <option value="">全部环境</option>
              <option value="staging">staging</option>
              <option value="production">production</option>
            </select>
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
      ) : activeTab === 'tasks' ? (
        <ReleaseTasksTable
          tasks={filteredTasks}
          loading={loading}
          busyAction={busyAction}
          onUpdateStatus={updateTaskStatus}
          onCreatePr={createTaskPr}
          onDeployStaging={deployTaskToStaging}
          onRefresh={() => load().catch(() => {})}
          onOpenDetails={(task) => {
            setTaskDrawerOpen(false)
            setTaskDetail(task)
          }}
        />
      ) : (
        <OnlineRecordsTable
          records={filteredOnlineRecords}
          loading={loading}
          onOpenDetails={setOnlineDetail}
        />
      )}

      <OverlayDrawer
        open={taskDrawerOpen}
        eyebrow="Release Task"
        title="新建发布任务"
        description="只创建人工发布任务记录，不触发真实部署。"
        onClose={() => setTaskDrawerOpen(false)}
      >
        <div className="space-y-5">
          <label className="block space-y-2">
            <FieldLabel>项目 / 服务</FieldLabel>
            <select
              className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm"
              value={`${taskDraft.project_key}::${taskDraft.service_key}`}
              onChange={(event) => {
                const [project_key, service_key] = event.target.value.split('::')
                const target = taskTargets.find((item) => item.project_key === project_key && item.service_key === service_key) || taskTargets[0]
                setTaskDraft((current) => ({
                  ...current,
                  project_key: target.project_key,
                  project_display_name: target.project_display_name,
                  service_key: target.service_key,
                  branch_name: '',
                }))
                setBranchQuery('')
              }}
            >
              {taskTargets.map((target) => (
                <option key={`${target.project_key}-${target.service_key}`} value={`${target.project_key}::${target.service_key}`}>
                  {target.project_display_name} · {target.service_label}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-2">
            <FieldLabel>分支</FieldLabel>
            <input
              className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm"
              aria-label="筛选分支"
              placeholder={branchLoading ? '正在读取 GitHub 分支…' : '输入关键词筛选 GitHub 分支'}
              value={branchQuery}
              disabled={branchLoading || !!branchError}
              onChange={(event) => setBranchQuery(event.target.value)}
            />
            <select
              className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm"
              aria-label="分支"
              value={taskDraft.branch_name}
              disabled={branchLoading || branchOptions.length === 0}
              onChange={(event) => setTaskDraft((current) => ({ ...current, branch_name: event.target.value }))}
            >
              <option value="">
                {branchLoading ? '正在读取 GitHub 分支…' : filteredBranchOptions.length === 0 && branchQuery ? '没有匹配的 GitHub 分支' : '选择 GitHub 分支'}
              </option>
              {filteredBranchOptions.map((branch) => (
                <option key={branch.name} value={branch.name}>
                  {branch.name}{branch.is_default ? ' · default' : ''}{branch.protected ? ' · protected' : ''}
                </option>
              ))}
            </select>
            {branchError ? (
              <div className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-blocked-text)]">
                无法读取 GitHub 分支列表：{branchError}
              </div>
            ) : (
              <p className="text-xs text-[color:var(--ops-text-caption)]">
                分支从发布仓库的 GitHub branch list 读取，避免手输错分支。
              </p>
            )}
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
          ) : (
            <div className="rounded-2xl border border-[color:var(--ops-state-ready-border)] bg-[color:var(--ops-state-ready-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-ready-text)]">
              创建任务不会自动上线。只有在列表中点击“发布到 staging”后，才会触发受控的 Google staging 发布工作流。
            </div>
          )}
          <label className="block space-y-2">
            <FieldLabel>备注</FieldLabel>
            <textarea
              className="min-h-32 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm"
              placeholder="记录发布窗口、手动执行位置或回滚注意事项。"
              value={taskDraft.note}
              onChange={(event) => setTaskDraft((current) => ({ ...current, note: event.target.value }))}
            />
          </label>
          <button
            type="button"
            className="fixed bottom-6 right-6 z-50 rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white shadow-[0_18px_40px_rgba(37,99,235,0.35)] disabled:opacity-50"
            disabled={taskBusy || branchLoading || !!branchError || !taskDraft.project_key || !taskDraft.branch_name.trim()}
            onClick={createTask}
          >
            {taskBusy ? '创建中…' : '创建发布任务'}
          </button>
        </div>
      </OverlayDrawer>
      <ReleaseTaskDetailDrawer task={taskDetail} onClose={() => setTaskDetail(null)} onRefresh={() => load().catch(() => {})} />
      <OnlineRecordDetailDrawer record={onlineDetail} onClose={() => setOnlineDetail(null)} />
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
  onCreatePr,
  onDeployStaging,
  onRefresh,
  onOpenDetails,
}: Readonly<{
  tasks: ReleaseTask[]
  loading: boolean
  busyAction: string | null
  onUpdateStatus: (task: ReleaseTask, status: 'completed' | 'failed' | 'cancelled') => void
  onCreatePr: (task: ReleaseTask) => void
  onDeployStaging: (task: ReleaseTask) => void
  onRefresh: () => void
  onOpenDetails: (task: ReleaseTask) => void
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
                  {task.service_key ? <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">Service: {task.service_key}</div> : null}
                  <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-muted)]">{task.branch_name}</div>
                </td>
                <td className="px-4 py-4">
                  <StateBadge tone={task.environment === 'production' ? 'blocked' : 'ready'}>{task.environment}</StateBadge>
                </td>
                <td className="px-4 py-4">
                  <StateBadge tone={releaseTone(task.status)}>{STATUS_LABEL[task.status] || task.status}</StateBadge>
                  {task.deployment_status ? (
                    <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">
                      Deploy: {STATUS_LABEL[task.deployment_status] || task.deployment_status}
                    </div>
                  ) : null}
                  {task.deployment_failure_summary ? (
                    <div className="mt-2 max-w-xs text-xs text-[color:var(--ops-state-blocked-text)]">{task.deployment_failure_summary}</div>
                  ) : null}
                  {task.environment === 'staging' ? <ReleaseTaskPrGate task={task} /> : null}
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
                  {busyAction?.startsWith(`release-task-${task.id}-`) ? (
                    <div className="mb-2 rounded-lg border border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] px-3 py-2 text-xs font-semibold text-[color:var(--ops-state-running-text)]">
                      正在更新发布任务…
                    </div>
                  ) : null}
                  {task.status === 'requested' ? (
                    <div className="flex flex-wrap justify-end gap-2">
                      <button
                        type="button"
                        className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
                        onClick={() => onOpenDetails(task)}
                      >
                        详情
                      </button>
                      {task.environment === 'staging' && task.pr_gate?.can_create_pr ? (
                        <button
                          type="button"
                          className="rounded-lg border border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] px-3 py-2 text-sm font-semibold text-[color:var(--ops-state-running-text)] disabled:opacity-50"
                          disabled={Boolean(busyAction)}
                          onClick={() => onCreatePr(task)}
                        >
                          {busyAction === `release-task-${task.id}-create-pr` ? '提交中…' : '提交 PR'}
                        </button>
                      ) : null}
                      {task.environment === 'staging' && task.pr_gate?.pr_url ? (
                        <a
                          className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
                          href={task.pr_gate.pr_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          查看 PR
                        </a>
                      ) : null}
                      {task.environment === 'staging' && task.pr_gate?.checks_status === 'unknown' ? (
                        <button
                          type="button"
                          className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
                          disabled={Boolean(busyAction)}
                          onClick={onRefresh}
                        >
                          同步 PR 状态
                        </button>
                      ) : null}
                      {task.environment === 'staging' && !task.deployment_record_id && task.pr_gate?.can_deploy_staging ? (
                        <button
                          type="button"
                          className="rounded-lg border border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] px-3 py-2 text-sm font-semibold text-[color:var(--ops-state-running-text)] disabled:opacity-50"
                          disabled={Boolean(busyAction)}
                          onClick={() => onDeployStaging(task)}
                        >
                          {busyAction === `release-task-${task.id}-deploy-staging` ? '发布中…' : '发布到 staging'}
                        </button>
                      ) : null}
                      {task.environment === 'staging' && task.pr_gate?.pr_exists && task.pr_gate?.checks_status === 'success' && !task.pr_gate?.can_deploy_staging ? (
                        <button
                          type="button"
                          className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm text-[color:var(--ops-text-caption)] opacity-70"
                          disabled
                          title={task.pr_gate.blocked_reason || 'PR gate 尚未允许 staging 发布'}
                        >
                          发布到 staging
                        </button>
                      ) : null}
                      {task.environment === 'production' ? (
                        <span className="rounded-lg border border-[color:var(--ops-state-blocked-border)] px-3 py-2 text-sm text-[color:var(--ops-state-blocked-text)]">
                          Production 需 Human Gate
                        </span>
                      ) : null}
                      <button
                        type="button"
                        className="rounded-lg border border-[color:var(--ops-state-ready-border)] px-3 py-2 text-sm text-[color:var(--ops-state-ready-text)] disabled:opacity-50"
                        disabled={Boolean(busyAction)}
                        onClick={() => onUpdateStatus(task, 'completed')}
                      >
                        {busyAction === `release-task-${task.id}-completed` ? '处理中…' : '标记为已完成'}
                      </button>
                      <button
                        type="button"
                        className="rounded-lg border border-[color:var(--ops-state-blocked-border)] px-3 py-2 text-sm text-[color:var(--ops-state-blocked-text)] disabled:opacity-50"
                        disabled={Boolean(busyAction)}
                        onClick={() => onUpdateStatus(task, 'failed')}
                      >
                        {busyAction === `release-task-${task.id}-failed` ? '处理中…' : '标记为失败'}
                      </button>
                      <button
                        type="button"
                        className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-50"
                        disabled={Boolean(busyAction)}
                        onClick={() => onUpdateStatus(task, 'cancelled')}
                      >
                        {busyAction === `release-task-${task.id}-cancelled` ? '处理中…' : '取消'}
                      </button>
                    </div>
                  ) : (
                    <div className="flex justify-end">
                      <button
                        type="button"
                        className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
                        onClick={() => onOpenDetails(task)}
                      >
                        详情
                      </button>
                    </div>
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

function OnlineRecordsTable({
  records,
  loading,
  onOpenDetails,
}: Readonly<{
  records: OnlineReleaseRecord[]
  loading: boolean
  onOpenDetails: (record: OnlineReleaseRecord) => void
}>) {
  return (
    <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
      <div className="border-b border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4">
        <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Online Records</div>
        <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
          这里只展示成功上线账本。真实部署成功或人工标记已完成时生成的成功 DeploymentRecord 会进入这里；待执行、失败、取消不会进入。
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse">
          <thead className="bg-[color:var(--ops-panel-subtle)]">
            <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
              <th className="px-5 py-4 font-medium">项目 / 服务</th>
              <th className="px-4 py-4 font-medium">环境</th>
              <th className="px-4 py-4 font-medium">分支 / Commit</th>
              <th className="px-4 py-4 font-medium">操作 / 健康</th>
              <th className="px-4 py-4 font-medium">GitHub Actions</th>
              <th className="px-4 py-4 font-medium">上线时间</th>
              <th className="px-5 py-4 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.id} className="border-t border-[color:var(--ops-stroke-soft)] hover:bg-[color:var(--ops-panel-subtle)]">
                <td className="px-5 py-4">
                  <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{record.project_display_name || record.project_key}</div>
                  <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">Service: {record.service_key || '-'}</div>
                  {record.release_task_id ? <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">Release Task #{record.release_task_id}</div> : null}
                </td>
                <td className="px-4 py-4">
                  <StateBadge tone={record.environment === 'production' ? 'blocked' : 'ready'}>{record.environment}</StateBadge>
                </td>
                <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                  <div className="font-mono text-xs">{record.branch_name || '-'}</div>
                  <div className="mt-1 font-mono text-xs">{shortSha(record.commit_sha)}</div>
                </td>
                <td className="px-4 py-4">
                  <div className="flex flex-wrap gap-2">
                    <StateBadge tone="delivered">{STATUS_LABEL[record.action] || record.action}</StateBadge>
                    <StateBadge tone={record.health_status === 'passed' || record.health_status === 'healthy' ? 'delivered' : 'muted'}>
                      Health: {record.health_status || '-'}
                    </StateBadge>
                  </div>
                </td>
                <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                  {record.external_url ? (
                    <a className="text-[color:var(--ops-state-running-text)] underline-offset-4 hover:underline" href={record.external_url} target="_blank" rel="noreferrer">
                      Run {record.external_run_id || record.id}
                    </a>
                  ) : (
                    '-'
                  )}
                </td>
                <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(record.finished_at || record.updated_at || record.created_at)}</td>
                <td className="px-5 py-4 text-right">
                  <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => onOpenDetails(record)}>
                    详情
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!loading && records.length === 0 && (
        <div className="p-6">
          <EmptyPane>暂无成功上线记录。成功的 staging / production DeploymentRecord 会出现在这里。</EmptyPane>
        </div>
      )}
    </section>
  )
}

function ReleaseTaskDetailDrawer({
  task,
  onClose,
  onRefresh,
}: Readonly<{
  task: ReleaseTask | null
  onClose: () => void
  onRefresh: () => void
}>) {
  if (!task) return null
  const hasDeployment = Boolean(task.deployment_record_id)
  return (
    <OverlayDrawer
      open={Boolean(task)}
      eyebrow="Release Task Detail"
      title={`发布任务 #${task.id}`}
      description="查看 PR gate、DeploymentRecord、GitHub Actions 链接、健康检查和失败摘要。"
      onClose={onClose}
    >
      <div className="space-y-5">
        <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">
                {task.project_display_name || task.project_key} · {task.service_key || 'service'}
              </div>
              <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-muted)]">{task.branch_name}</div>
            </div>
            <div className="flex flex-wrap gap-2">
              <StateBadge tone={task.environment === 'production' ? 'blocked' : 'ready'}>{task.environment}</StateBadge>
              <StateBadge tone={releaseTone(task.status)}>{STATUS_LABEL[task.status] || task.status}</StateBadge>
            </div>
          </div>
          <div className="mt-4 grid gap-3 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-2">
            <div>来源：{SOURCE_LABEL[task.source_type] || task.source_type}</div>
            <div>创建人：{task.actor || '-'}</div>
            <div>执行人：{task.operator || '-'}</div>
            <div>更新时间：{formatTime(task.updated_at || task.created_at)}</div>
          </div>
          {task.note ? <div className="mt-4 rounded-xl bg-[color:var(--ops-panel)] p-3 text-sm text-[color:var(--ops-text-muted)]">{task.note}</div> : null}
        </section>

        <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">PR Gate</h3>
            <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-1.5 text-xs" onClick={onRefresh}>
              刷新状态
            </button>
          </div>
          <ReleaseTaskPrGate task={task} />
          {task.pr_gate?.pr_url ? (
            <a className="mt-3 inline-flex rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" href={task.pr_gate.pr_url} target="_blank" rel="noreferrer">
              打开 PR #{task.pr_gate.pr_number || ''}
            </a>
          ) : null}
        </section>

        <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Deployment Record</h3>
          {hasDeployment ? (
            <div className="mt-3 space-y-3 text-sm text-[color:var(--ops-text-muted)]">
              <div className="flex flex-wrap gap-2">
                <StateBadge tone={releaseTone(task.deployment_status || task.status)}>
                  Deploy: {STATUS_LABEL[task.deployment_status || ''] || task.deployment_status || '-'}
                </StateBadge>
                {task.deployment_health_status ? <StateBadge tone={task.deployment_health_status === 'passed' ? 'delivered' : 'blocked'}>Health: {task.deployment_health_status}</StateBadge> : null}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div>Record ID：{task.deployment_record_id}</div>
                <div>Workflow：{task.deployment_workflow_file || '-'}</div>
                <div>Run ID：{task.deployment_external_run_id || '-'}</div>
                <div>Commit：{task.deployment_commit_sha || '-'}</div>
                <div>Started：{formatTime(task.deployment_started_at)}</div>
                <div>Finished：{formatTime(task.deployment_finished_at)}</div>
              </div>
              {task.deployment_external_url ? (
                <a className="inline-flex rounded-lg border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)]" href={task.deployment_external_url} target="_blank" rel="noreferrer">
                  打开 GitHub Actions 日志
                </a>
              ) : null}
              {task.deployment_failure_summary ? (
                <div className="rounded-xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] p-3 text-[color:var(--ops-state-blocked-text)]">
                  {task.deployment_failure_summary}
                </div>
              ) : null}
              <details className="rounded-xl bg-[color:var(--ops-panel)] p-3">
                <summary className="cursor-pointer text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Deployment metadata</summary>
                <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap text-xs text-[color:var(--ops-text-muted)]">
                  {JSON.stringify(task.deployment_metadata || {}, null, 2)}
                </pre>
              </details>
            </div>
          ) : (
            <div className="mt-3 rounded-xl bg-[color:var(--ops-panel)] p-3 text-sm text-[color:var(--ops-text-muted)]">
              还没有 DeploymentRecord。只有点击“发布到 staging”并通过 PR gate 后，系统才会创建部署记录并写入 GitHub Actions 链接、健康检查和结果。
            </div>
          )}
        </section>
      </div>
    </OverlayDrawer>
  )
}

function OnlineRecordDetailDrawer({
  record,
  onClose,
}: Readonly<{
  record: OnlineReleaseRecord | null
  onClose: () => void
}>) {
  if (!record) return null
  const metadataEntries = Object.entries(record.metadata_summary || {}).filter(([, value]) => value !== null && value !== undefined && value !== '')
  return (
    <OverlayDrawer
      open={Boolean(record)}
      eyebrow="Online Record"
      title={`上线记录 #${record.id}`}
      description="成功部署账本：用于确认 GitHub Actions、Cloud Run revision、镜像 / manifest 和健康检查结果。"
      onClose={onClose}
    >
      <div className="space-y-5">
        <section className="rounded-2xl border border-[color:var(--ops-state-ready-border)] bg-[color:var(--ops-state-ready-bg)] p-4 text-sm text-[color:var(--ops-state-ready-text)]">
          这是只读上线记录，只来自成功的 DeploymentRecord。它不是 Release Task，也不会触发新的 deploy 或 rollback。
        </section>

        <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">
                {record.project_display_name || record.project_key} · {record.service_key || 'service'}
              </div>
              <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-muted)]">{record.branch_name || '-'}</div>
            </div>
            <div className="flex flex-wrap gap-2">
              <StateBadge tone={record.environment === 'production' ? 'blocked' : 'ready'}>{record.environment}</StateBadge>
              <StateBadge tone="delivered">{STATUS_LABEL[record.action] || record.action}</StateBadge>
              <StateBadge tone="delivered">上线成功</StateBadge>
            </div>
          </div>
          <div className="mt-4 grid gap-3 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-2">
            <div>Commit：<span className="font-mono">{record.commit_sha || '-'}</span></div>
            <div>健康检查：{record.health_status || '-'}</div>
            <div>Operator：{record.actor || '-'}</div>
            <div>Trigger：{record.trigger_source || '-'}</div>
            <div>Started：{formatTime(record.started_at)}</div>
            <div>Finished：{formatTime(record.finished_at)}</div>
          </div>
          {record.external_url ? (
            <a className="mt-4 inline-flex rounded-lg border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)]" href={record.external_url} target="_blank" rel="noreferrer">
              打开 GitHub Actions 日志
            </a>
          ) : null}
        </section>

        <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Deployment Evidence</h3>
          <div className="mt-3 grid gap-3 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-2">
            <div>Workflow：{record.workflow_file || '-'}</div>
            <div>Run ID：{record.external_run_id || '-'}</div>
            <div>Release Task：{record.release_task_id ? `#${record.release_task_id}` : '-'}</div>
            <div>Rollback target：{record.rollback_target_sha || '-'}</div>
          </div>
          {metadataEntries.length > 0 ? (
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {metadataEntries.map(([key, value]) => (
                <div key={key} className="rounded-xl bg-[color:var(--ops-panel)] p-3">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{key}</div>
                  <div className="mt-2 break-words text-xs text-[color:var(--ops-text-muted)]">{compactJson(value)}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-3 rounded-xl bg-[color:var(--ops-panel)] p-3 text-sm text-[color:var(--ops-text-muted)]">没有额外 deployment metadata summary。</div>
          )}
        </section>

        <section className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] p-4 text-sm text-[color:var(--ops-state-blocked-text)]">
          <div className="font-semibold">回滚说明</div>
          <p className="mt-2">
            Runtime rollback 应选择这里的历史成功上线记录作为 rollback target，并进入 Human Gate。代码级回滚则新建 revert 分支、提交 PR、checks 通过并合并到 main 后，再按正常发布流程上线。
          </p>
        </section>

        <details className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <summary className="cursor-pointer text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Raw deployment metadata</summary>
          <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-xs text-[color:var(--ops-text-muted)]">
            {JSON.stringify(record.metadata || {}, null, 2)}
          </pre>
        </details>
      </div>
    </OverlayDrawer>
  )
}

function ReleaseTaskPrGate({ task }: Readonly<{ task: ReleaseTask }>) {
  const gate = task.pr_gate
  if (!gate) return null
  let label = gate.blocked_reason || 'PR gate 待同步'
  let tone: 'ready' | 'running' | 'blocked' | 'muted' | 'delivered' = 'muted'
  if (!gate.branch_exists) {
    label = '分支不存在'
    tone = 'blocked'
  } else if (!gate.pr_exists) {
    label = '未提交 PR'
    tone = 'running'
  } else if (gate.pr_state === 'draft') {
    label = 'PR 是 Draft'
    tone = 'blocked'
  } else if (gate.pr_state === 'merged' && gate.checks_status === 'success') {
    label = 'PR 已合并 / Checks 通过'
    tone = 'delivered'
  } else if (gate.checks_status === 'success') {
    label = 'Checks 通过'
    tone = 'delivered'
  } else if (gate.checks_status === 'failed') {
    label = 'Checks 失败'
    tone = 'blocked'
  } else if (gate.checks_status === 'pending') {
    label = 'Checks 运行中'
    tone = 'running'
  }
  return (
    <div className="mt-2 space-y-1">
      <StateBadge tone={tone}>PR Gate: {label}</StateBadge>
      {gate.checks_summary ? <div className="max-w-xs text-xs text-[color:var(--ops-text-caption)]">{gate.checks_summary}</div> : null}
      {gate.blocked_reason && label !== gate.blocked_reason ? (
        <div className="max-w-xs text-xs text-[color:var(--ops-state-blocked-text)]">{gate.blocked_reason}</div>
      ) : null}
    </div>
  )
}
