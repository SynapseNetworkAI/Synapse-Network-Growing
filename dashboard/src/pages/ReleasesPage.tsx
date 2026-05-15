import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { OnlineReleaseRecord, ProjectPolicy, ReleaseBranchOption, ReleaseCandidate, ReleaseTask, api } from '../api'
import { attachReleaseTaskPrebuiltImage, deployReleaseTask, getReleaseTaskGateStatus, getReleaseTasksPage } from '../apiReleaseTasks'
import { EmptyPane, FieldLabel, OverlayModal, StateBadge, useToast } from '../components/workbench'
import { ReleaseTaskDetailModal } from './ReleaseTaskDetailPanel'
import { ReleaseTasksTable, type GateRequestState } from './ReleaseTasksTable'
import { STATUS_LABEL, releaseTone } from './releaseListUi'
import SdkPackagesPanel from './SdkPackagesPanel'
import ScheduledJobsPanel from './ScheduledJobsPanel'
import ProductionDeployModal from './ProductionDeployModal'

type ReleaseTab = 'candidates' | 'tasks' | 'scheduled-jobs' | 'sdk-packages' | 'online'
const RELEASE_TABS: ReleaseTab[] = ['candidates', 'tasks', 'scheduled-jobs', 'sdk-packages', 'online']
const RELEASE_TASK_PAGE_SIZE = 10

const TASK_STATUS_OPTIONS = ['', 'requested', 'deploying', 'completed', 'failed', 'cancelled']
const DEFAULT_RELEASE_TARGETS = [
  { project_key: 'synapse-network', project_display_name: 'Synapse-Network', service_key: 'gateway', service_label: 'Gateway API' },
  { project_key: 'synapse-network', project_display_name: 'Synapse-Network', service_key: 'gateway-admin', service_label: 'Gateway Admin API' },
  { project_key: 'synapse-network', project_display_name: 'Synapse-Network', service_key: 'admin-front', service_label: 'Admin Front' },
  { project_key: 'synapse-network', project_display_name: 'Synapse-Network', service_key: 'user-front', service_label: 'User Front' },
  { project_key: 'synapse-network', project_display_name: 'Synapse-Network', service_key: 'docs-front', service_label: 'Docs Front' },
  { project_key: 'synapse-network-provider', project_display_name: 'Synapse-Network-Provider', service_key: 'provider-service', service_label: 'Provider Service' },
]

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

function metadataString(source: Record<string, unknown> | null | undefined, ...keys: string[]) {
  for (const key of keys) {
    const value = source?.[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

function releaseTabFromQuery(value: string | null): ReleaseTab {
  return RELEASE_TABS.includes(value as ReleaseTab) ? (value as ReleaseTab) : 'candidates'
}

function onlineRecordActionsUrl(record: OnlineReleaseRecord) {
  return (
    record.external_url ||
    metadataString(record.metadata_summary, 'githubRunUrl', 'github_run_url', 'externalUrl') ||
    metadataString(record.metadata, 'githubRunUrl', 'github_run_url', 'externalUrl', 'external_url') ||
    null
  )
}

function onlineRecordPrUrl(record: OnlineReleaseRecord) {
  const explicit =
    metadataString(record.metadata_summary, 'prUrl', 'pr_url', 'githubPrUrl', 'githubPullRequestUrl') ||
    metadataString(record.metadata, 'prUrl', 'pr_url', 'githubPrUrl', 'githubPullRequestUrl')
  if (explicit) return explicit
  const repo = metadataString(record.metadata, 'deploy_repo_full_name', 'deployRepoFullName', 'repo_full_name')
  const branch = metadataString(record.metadata, 'sourceRef', 'source_ref', 'branch_name') || record.branch_name
  if (!repo || !branch) return null
  const query = new URLSearchParams({ q: `is:pr head:${branch}` })
  return `https://github.com/${repo}/pulls?${query.toString()}`
}

function openExternalUrl(url: string | null | undefined) {
  if (!url) return
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (opened) opened.opener = null
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

function releaseTaskMatchesFilters(task: ReleaseTask, filters: { environment?: string; status?: string; q?: string }) {
  if (filters.environment && task.environment !== filters.environment) return false
  if (filters.status && task.status !== filters.status) return false
  const needle = (filters.q || '').trim().toLowerCase()
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
  const [searchParams, setSearchParams] = useSearchParams()
  const toast = useToast()
  const [activeTab, setActiveTab] = useState<ReleaseTab>(() => releaseTabFromQuery(searchParams.get('tab')))
  const [candidates, setCandidates] = useState<ReleaseCandidate[]>([])
  const [tasks, setTasks] = useState<ReleaseTask[]>([])
  const [taskTotal, setTaskTotal] = useState(0)
  const [taskOffset, setTaskOffset] = useState(0)
  const [gateStatusByTaskId, setGateStatusByTaskId] = useState<Record<number, GateRequestState>>({})
  const [onlineRecords, setOnlineRecords] = useState<OnlineReleaseRecord[]>([])
  const [policies, setPolicies] = useState<ProjectPolicy[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [taskStatusFilter, setTaskStatusFilter] = useState('')
  const [taskEnvironmentFilter, setTaskEnvironmentFilter] = useState('')
  const [onlineEnvironmentFilter, setOnlineEnvironmentFilter] = useState('')
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [syncBusy, setSyncBusy] = useState(false)
  const [taskModalOpen, setTaskModalOpen] = useState(false)
  const [taskDetail, setTaskDetail] = useState<ReleaseTask | null>(null)
  const [onlineDetail, setOnlineDetail] = useState<OnlineReleaseRecord | null>(null)
  const [taskDraft, setTaskDraft] = useState(defaultTaskDraft([]))
  const [taskBusy, setTaskBusy] = useState(false)
  const [productionDeployTask, setProductionDeployTask] = useState<ReleaseTask | null>(null)
  const [productionConfirmPhrase, setProductionConfirmPhrase] = useState('')
  const [branchOptions, setBranchOptions] = useState<ReleaseBranchOption[]>([])
  const [branchQuery, setBranchQuery] = useState('')
  const [branchLoading, setBranchLoading] = useState(false)
  const [branchError, setBranchError] = useState<string | null>(null)
  const taskTargets = useMemo(() => releaseTargets(policies), [policies])

  const selectReleaseTab = (tab: ReleaseTab) => {
    setActiveTab(tab)
    const nextParams = new URLSearchParams(searchParams)
    if (tab === 'candidates') {
      nextParams.delete('tab')
    } else {
      nextParams.set('tab', tab)
    }
    setSearchParams(nextParams, { replace: true })
  }

  const releaseTaskPageFilters = () => ({
    environment: taskEnvironmentFilter || undefined,
    status: taskStatusFilter || undefined,
    q: search.trim() || undefined,
    limit: RELEASE_TASK_PAGE_SIZE,
    offset: taskOffset,
  })

  const fetchReleaseTaskPage = async () => {
    const filters = releaseTaskPageFilters()
    return getReleaseTasksPage(filters)
  }

  const loadReleaseTasksPage = async () => {
    const page = await fetchReleaseTaskPage()
    setTasks(page.items)
    setTaskTotal(page.total)
  }

  const refreshTaskGateStatus = async (task: ReleaseTask) => {
    setGateStatusByTaskId((current) => ({
      ...current,
      [task.id]: { status: 'loading', gate: current[task.id]?.gate },
    }))
    try {
      const gate = await getReleaseTaskGateStatus(task.id)
      setGateStatusByTaskId((current) => ({
        ...current,
        [task.id]: { status: 'ready', gate },
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Gate 检查失败'
      setGateStatusByTaskId((current) => ({
        ...current,
        [task.id]: { status: 'error', gate: current[task.id]?.gate, error: message },
      }))
    }
  }

  const load = async () => {
    setLoading(true)
    try {
      const [nextCandidates, nextTasks, nextPolicies] = await Promise.all([
        api.getReleaseCandidates(),
        fetchReleaseTaskPage(),
        api.getProjectPolicies(),
      ])
      const nextOnlineRecords = await api.getOnlineReleaseRecords({ limit: 100 }).catch(() => [])
      setCandidates(nextCandidates)
      setTasks(nextTasks.items)
      setTaskTotal(nextTasks.total)
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

  useEffect(() => {
    const nextTab = releaseTabFromQuery(searchParams.get('tab'))
    setActiveTab((current) => (current === nextTab ? current : nextTab))
  }, [searchParams])

  useEffect(() => {
    if (activeTab !== 'tasks') return
    loadReleaseTasksPage().catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, search, taskEnvironmentFilter, taskStatusFilter, taskOffset])

  useEffect(() => {
    if (activeTab !== 'tasks') return
    const pendingTasks = tasks
      .filter((task) => task.status === 'requested' && ['staging', 'production'].includes(task.environment))
      .slice(0, 5)
    pendingTasks.forEach((task) => {
      const current = gateStatusByTaskId[task.id]
      if (!current || current.status === 'idle') {
        refreshTaskGateStatus(task).catch(() => {})
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, tasks.map((task) => `${task.id}:${task.status}:${task.environment}`).join('|')])

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

  const filteredTasks = tasks

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
    if (!taskModalOpen || !taskDraft.project_key) return
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
  }, [taskModalOpen, taskDraft.project_key, taskDraft.service_key])

  const createTask = async () => {
    if (taskBusy) return
    setTaskBusy(true)
    try {
      const created = await api.createReleaseTask({
        project_key: taskDraft.project_key,
        project_display_name: selectedTarget?.project_display_name || taskDraft.project_display_name || null,
        service_key: taskDraft.service_key,
        branch_name: taskDraft.branch_name,
        environment: taskDraft.environment,
        actor: 'operator',
        note: taskDraft.note || null,
      })
      toast.success('发布任务已创建')
      setTaskModalOpen(false)
      setTaskDraft(defaultTaskDraft(policies))
      selectReleaseTab('tasks')
      setGateStatusByTaskId((current) => ({
        ...current,
        [created.id]: { status: 'idle' },
      }))
      const filters = releaseTaskPageFilters()
      if (taskOffset === 0 && releaseTaskMatchesFilters(created, filters)) {
        setTasks((current) => [created, ...current].slice(0, RELEASE_TASK_PAGE_SIZE))
        setTaskTotal((current) => current + 1)
      }
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
      const updated = await api.updateReleaseTask(task.id, {
        status,
        operator: 'operator',
        note: task.note,
      })
      toast.success(`发布任务已标记为${STATUS_LABEL[status]}`)
      const filters = releaseTaskPageFilters()
      setTasks((current) => {
        if (!releaseTaskMatchesFilters(updated, filters)) {
          return current.filter((item) => item.id !== updated.id)
        }
        return current.map((item) => (item.id === updated.id ? updated : item))
      })
      if (!releaseTaskMatchesFilters(updated, filters)) {
        setTaskTotal((current) => Math.max(0, current - 1))
      }
      setTaskDetail((current) => (current?.id === updated.id ? updated : current))
      setGateStatusByTaskId((current) => {
        if (!(updated.id in current)) return current
        const next = { ...current }
        delete next[updated.id]
        return next
      })
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
      const updated = await api.deployReleaseTaskToStaging(task.id, {
        actor: 'operator',
        note: task.note,
      })
      toast.success('Staging 发布已触发')
      setTasks((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setTaskDetail((current) => (current?.id === updated.id ? updated : current))
    } catch (error) {
      const message = error instanceof Error ? error.message : '触发 staging 发布失败'
      toast.error(message)
    } finally {
      setBusyAction(null)
    }
  }

  const attachPrebuiltImage = async (
    task: ReleaseTask,
    payload: { image_digest: string; source_commit_sha: string },
  ) => {
    const updated = await attachReleaseTaskPrebuiltImage(task.id, {
      service_key: task.service_key || '',
      image_digest: payload.image_digest,
      source_commit_sha: payload.source_commit_sha,
      image_source: 'ephemeral_worktree_local_build',
      build_evidence: { attached_from: 'ops_console_release_task_detail' },
    })
    setTasks((current) => current.map((item) => (item.id === updated.id ? updated : item)))
    setTaskDetail(updated)
    toast.success('Prebuilt image 已绑定到发布任务')
  }

  const deployTaskToProduction = async () => {
    if (!productionDeployTask || busyAction) return
    const busyKey = `release-task-${productionDeployTask.id}-deploy-production`
    setBusyAction(busyKey)
    try {
      const updated = await deployReleaseTask(productionDeployTask.id, {
        actor: 'operator',
        note: productionDeployTask.note,
        confirm_phrase: productionConfirmPhrase,
      })
      toast.success('Production 发布已触发')
      setTasks((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setTaskDetail((current) => (current?.id === updated.id ? updated : current))
      setGateStatusByTaskId((current) => {
        if (!(updated.id in current)) return current
        const next = { ...current }
        delete next[updated.id]
        return next
      })
      setProductionDeployTask(null)
      setProductionConfirmPhrase('')
    } catch (error) {
      const message = error instanceof Error ? error.message : '触发 production 发布失败'
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
              placeholder={activeTab === 'tasks' ? '搜索 project / branch / operator' : activeTab === 'sdk-packages' ? '搜索 SDK package / version / registry' : activeTab === 'online' ? '搜索 project / branch / commit' : '搜索 requirement / project'}
              value={search}
              onChange={(event) => {
                setSearch(event.target.value)
                setTaskOffset(0)
              }}
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
                  setTaskModalOpen(true)
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
            onClick={() => selectReleaseTab('candidates')}
          >
            需求交付
          </button>
          <button
            type="button"
            className={`rounded-full border px-4 py-2 text-sm ${activeTab === 'tasks' ? 'border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] text-[color:var(--ops-state-running-text)]' : 'border-[color:var(--ops-stroke-soft)] text-[color:var(--ops-text-muted)]'}`}
            onClick={() => selectReleaseTab('tasks')}
          >
            发布管理
          </button>
          <button
            type="button"
            className={`rounded-full border px-4 py-2 text-sm ${activeTab === 'scheduled-jobs' ? 'border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] text-[color:var(--ops-state-running-text)]' : 'border-[color:var(--ops-stroke-soft)] text-[color:var(--ops-text-muted)]'}`}
            onClick={() => selectReleaseTab('scheduled-jobs')}
          >
            定时任务发布
          </button>
          <button
            type="button"
            className={`rounded-full border px-4 py-2 text-sm ${activeTab === 'sdk-packages' ? 'border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] text-[color:var(--ops-state-running-text)]' : 'border-[color:var(--ops-stroke-soft)] text-[color:var(--ops-text-muted)]'}`}
            onClick={() => selectReleaseTab('sdk-packages')}
          >
            SDK Packages
          </button>
          <button
            type="button"
            className={`rounded-full border px-4 py-2 text-sm ${activeTab === 'online' ? 'border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] text-[color:var(--ops-state-running-text)]' : 'border-[color:var(--ops-stroke-soft)] text-[color:var(--ops-text-muted)]'}`}
            onClick={() => selectReleaseTab('online')}
          >
            上线记录
          </button>
          {activeTab === 'tasks' ? (
            <>
              <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={taskEnvironmentFilter} onChange={(event) => {
                setTaskEnvironmentFilter(event.target.value)
                setTaskOffset(0)
              }}>
                <option value="">全部环境</option>
                <option value="staging">staging</option>
                <option value="production">production</option>
              </select>
              <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={taskStatusFilter} onChange={(event) => {
                setTaskStatusFilter(event.target.value)
                setTaskOffset(0)
              }}>
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
          total={taskTotal}
          limit={RELEASE_TASK_PAGE_SIZE}
          offset={taskOffset}
          loading={loading}
          busyAction={busyAction}
          gateStatusByTaskId={gateStatusByTaskId}
          onUpdateStatus={updateTaskStatus}
          onCreatePr={createTaskPr}
          onDeployStaging={deployTaskToStaging}
          onDeployProduction={(task) => {
            setProductionConfirmPhrase('')
            setProductionDeployTask(task)
            refreshTaskGateStatus(task).catch(() => {})
          }}
          onRefreshGate={(task) => refreshTaskGateStatus(task)}
          onRefresh={() => load().catch(() => {})}
          onOpenDetails={(task) => {
            setTaskModalOpen(false)
            setTaskDetail(task)
          }}
          onPage={(nextOffset) => setTaskOffset(Math.max(0, nextOffset))}
        />
      ) : activeTab === 'scheduled-jobs' ? (
        <ScheduledJobsPanel />
      ) : activeTab === 'sdk-packages' ? (
        <SdkPackagesPanel search={search} />
      ) : (
        <OnlineRecordsTable
          records={filteredOnlineRecords}
          loading={loading}
          onOpenDetails={setOnlineDetail}
        />
      )}

      <ProductionDeployModal
        task={productionDeployTask}
        gate={
          productionDeployTask
            ? gateStatusByTaskId[productionDeployTask.id]?.gate || productionDeployTask.pr_gate
            : undefined
        }
        gateStatus={productionDeployTask ? gateStatusByTaskId[productionDeployTask.id]?.status : undefined}
        confirmPhrase={productionConfirmPhrase}
        busyAction={busyAction}
        onConfirmPhraseChange={setProductionConfirmPhrase}
        onClose={() => {
          setProductionDeployTask(null)
          setProductionConfirmPhrase('')
        }}
        onDeploy={deployTaskToProduction}
      />

      <OverlayModal
        open={taskModalOpen}
        eyebrow="Release Task"
        title="新建发布任务"
        description="只创建人工发布任务记录，不触发真实部署。"
        onClose={() => setTaskModalOpen(false)}
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
      </OverlayModal>
      <ReleaseTaskDetailModal
        task={taskDetail}
        onClose={() => setTaskDetail(null)}
        onRefresh={() => load().catch(() => {})}
        onAttachPrebuiltImage={attachPrebuiltImage}
      />
      <OnlineRecordDetailModal record={onlineDetail} onClose={() => setOnlineDetail(null)} />
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
            {records.map((record) => {
              const actionsUrl = onlineRecordActionsUrl(record)
              const prUrl = onlineRecordPrUrl(record)
              return (
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
                  {actionsUrl ? (
                    <a className="text-[color:var(--ops-state-running-text)] underline-offset-4 hover:underline" href={actionsUrl} target="_blank" rel="noreferrer">
                      Run {record.external_run_id || record.id}
                    </a>
                  ) : (
                    '-'
                  )}
                </td>
                <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(record.finished_at || record.updated_at || record.created_at)}</td>
                <td className="px-5 py-4 text-right">
                  <div className="flex flex-wrap justify-end gap-2">
                    {prUrl ? (
                      <button type="button" className="rounded-lg border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)]" onClick={() => openExternalUrl(prUrl)}>
                        打开 PR
                      </button>
                    ) : null}
                    <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => onOpenDetails(record)}>
                      详情
                    </button>
                  </div>
                </td>
              </tr>
              )
            })}
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

function OnlineRecordDetailModal({
  record,
  onClose,
}: Readonly<{
  record: OnlineReleaseRecord | null
  onClose: () => void
}>) {
  if (!record) return null
  const metadataEntries = Object.entries(record.metadata_summary || {}).filter(([, value]) => value !== null && value !== undefined && value !== '')
  const actionsUrl = onlineRecordActionsUrl(record)
  const prUrl = onlineRecordPrUrl(record)
  return (
    <OverlayModal
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
          <div className="mt-4 flex flex-wrap gap-2">
            {actionsUrl ? (
              <button type="button" className="rounded-lg border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)]" onClick={() => openExternalUrl(actionsUrl)}>
                打开 GitHub Actions 日志
              </button>
            ) : (
              <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm text-[color:var(--ops-text-caption)] opacity-70" disabled>
                无 Actions 链接
              </button>
            )}
            {prUrl ? (
              <button type="button" className="rounded-lg border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)]" onClick={() => openExternalUrl(prUrl)}>
                打开 PR
              </button>
            ) : null}
          </div>
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
    </OverlayModal>
  )
}
