import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { ReleaseBranchOption } from '../api'
import type { ScheduledCloudRunJobRecord, ScheduledCloudRunJobStatus } from '../apiReleaseScheduledJobs'
import { EmptyPane, FieldLabel, OverlayModal, StateBadge, useToast } from '../components/workbench'

type JobFamilyFilter = '' | 'gateway' | 'gateway-admin'
type JobKindFilter = '' | 'periodic' | 'migration'
type PublishDraft = {
  jobName: string
  environment: 'staging' | 'production'
  sourceRef: string
  runSmokeJobs: boolean
  runMigrations: boolean
}

const PAGE_SIZE = 10

function statusTone(status: string): 'ready' | 'running' | 'blocked' | 'muted' {
  const normalized = status.toLowerCase()
  if (['published', 'succeeded', 'passed', 'completed'].includes(normalized)) return 'ready'
  if (['publishing', 'requested', 'running', 'pending', 'checking', 'deploying'].includes(normalized)) return 'running'
  if (['failed', 'blocked', 'cancelled', 'canceled'].includes(normalized)) return 'blocked'
  return 'muted'
}

function labelForStatus(status: string) {
  const labels: Record<string, string> = {
    published: '已发布',
    succeeded: '成功',
    completed: '已完成',
    deploying: '发布中',
    publishing: '发布中',
    requested: '待执行',
    running: '运行中',
    pending: '等待中',
    failed: '失败',
    cancelled: '已取消',
    canceled: '已取消',
    unknown: '未知',
    passed: '通过',
    checking: '检查中',
    configured_from_docs: '文档配置',
    manual_job: '手动任务',
  }
  return labels[status] || status || '未知'
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function imageTail(value: string | null) {
  if (!value) return '-'
  const digest = value.includes('@') ? value.split('@').pop() : value
  if (!digest) return value
  return digest.length > 30 ? `${digest.slice(0, 30)}…` : digest
}

function displayJobs(record: ScheduledCloudRunJobRecord) {
  if (record.job_name) return record.job_name
  return record.jobs.length ? record.jobs.join(', ') : '-'
}

export default function ScheduledJobsPanel() {
  const toast = useToast()
  const [jobs, setJobs] = useState<ScheduledCloudRunJobStatus[]>([])
  const [records, setRecords] = useState<ScheduledCloudRunJobRecord[]>([])
  const [totalRecords, setTotalRecords] = useState(0)
  const [diagnostics, setDiagnostics] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [familyFilter, setFamilyFilter] = useState<JobFamilyFilter>('')
  const [kindFilter, setKindFilter] = useState<JobKindFilter>('')
  const [recordStatusFilter, setRecordStatusFilter] = useState('')
  const [recordJobFilter, setRecordJobFilter] = useState('')
  const [catalogQuery, setCatalogQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [catalogOpen, setCatalogOpen] = useState(false)
  const [jobDetail, setJobDetail] = useState<ScheduledCloudRunJobStatus | null>(null)
  const [recordDetail, setRecordDetail] = useState<ScheduledCloudRunJobRecord | null>(null)
  const [publishDraft, setPublishDraft] = useState<PublishDraft | null>(null)
  const [branchOptions, setBranchOptions] = useState<ReleaseBranchOption[]>([])
  const [branchQuery, setBranchQuery] = useState('')
  const [branchLoading, setBranchLoading] = useState(false)
  const [branchError, setBranchError] = useState<string | null>(null)

  const loadJobs = async () => {
    const response = await api.getScheduledCloudRunJobsStatus()
    setJobs(response.items)
    setDiagnostics(response.diagnostics || [])
  }

  const loadRecords = async (nextOffset = offset) => {
    const response = await api.getScheduledCloudRunJobRecords({
      environment: 'staging',
      family: familyFilter || undefined,
      job_name: recordJobFilter || undefined,
      status: recordStatusFilter || undefined,
      limit: PAGE_SIZE,
      offset: nextOffset,
    })
    setRecords(response.items)
    setTotalRecords(response.total)
    setOffset(response.offset)
  }

  const load = async (nextOffset = offset) => {
    setLoading(true)
    try {
      await Promise.all([loadJobs(), loadRecords(nextOffset)])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(0).catch(() => {})
  }, [familyFilter, recordJobFilter, recordStatusFilter])

  useEffect(() => {
    if (!publishDraft) return
    let cancelled = false
    setBranchLoading(true)
    setBranchError(null)
    api.getReleaseTaskBranchOptions({ project_key: 'synapse-network', service_key: 'gateway' })
      .then((options) => {
        if (cancelled) return
        setBranchOptions(options)
        setPublishDraft((current) => {
          if (!current) return current
          if (current.sourceRef && options.some((option) => option.name === current.sourceRef)) return current
          const defaultBranch = options.find((option) => option.is_default)?.name || options[0]?.name || 'main'
          return { ...current, sourceRef: defaultBranch }
        })
      })
      .catch((error: unknown) => {
        if (!cancelled) setBranchError(error instanceof Error ? error.message : '无法读取 GitHub 分支列表')
      })
      .finally(() => {
        if (!cancelled) setBranchLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [!!publishDraft])

  const filteredCatalogJobs = useMemo(() => {
    const needle = catalogQuery.trim().toLowerCase()
    return jobs.filter((item) => {
      if (familyFilter && item.family !== familyFilter) return false
      if (kindFilter && item.job_type !== kindFilter) return false
      if (needle && !`${item.job_name} ${item.command} ${item.purpose}`.toLowerCase().includes(needle)) return false
      return true
    })
  }, [catalogQuery, familyFilter, jobs, kindFilter])

  const filteredBranchOptions = useMemo(() => {
    const needle = branchQuery.trim().toLowerCase()
    return needle
      ? branchOptions.filter((branch) => branch.name.toLowerCase().includes(needle) || (branch.commit_sha || '').toLowerCase().includes(needle))
      : branchOptions
  }, [branchOptions, branchQuery])

  const selectedPublishJob = useMemo(
    () => jobs.find((item) => item.job_name === publishDraft?.jobName) || null,
    [jobs, publishDraft?.jobName],
  )

  const openSinglePublish = (job?: ScheduledCloudRunJobStatus) => {
    setBranchQuery('')
    setPublishDraft({
      jobName: job?.job_name || '',
      environment: 'staging',
      sourceRef: 'main',
      runSmokeJobs: false,
      runMigrations: false,
    })
  }

  const createTask = async () => {
    if (!publishDraft || busy) return
    if (!publishDraft.jobName) {
      toast.error('请选择要发布的定时任务名称')
      return
    }
    if (selectedPublishJob?.migration_execution_required && !publishDraft.runMigrations) {
      toast.error('迁移任务需要确认执行 migration job')
      return
    }
    setBusy(`create:${publishDraft.jobName}`)
    try {
      await api.createScheduledCloudRunJobTask({
        job_name: publishDraft.jobName,
        environment: publishDraft.environment,
        source_ref_type: 'branch',
        source_ref: publishDraft.sourceRef,
        actor: 'operator',
        run_smoke_jobs: publishDraft.runSmokeJobs,
        run_migrations: publishDraft.runMigrations,
      })
      toast.success('已创建，点击发布到 staging 执行。')
      setPublishDraft(null)
      setCatalogOpen(false)
      await loadRecords(0)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '触发定时任务发布失败')
    } finally {
      setBusy(null)
    }
  }

  const publishRecord = async (record: ScheduledCloudRunJobRecord) => {
    if (busy) return
    setBusy(`publish-record:${record.id}`)
    try {
      await api.publishScheduledCloudRunJobTask(record.id, { actor: 'operator' })
      toast.success('已创建本地 runner 发布记录。')
      await loadRecords(offset)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '触发定时任务发布失败')
    } finally {
      setBusy(null)
    }
  }

  const cancelRecord = async (record: ScheduledCloudRunJobRecord) => {
    if (busy) return
    setBusy(`cancel-record:${record.id}`)
    try {
      await api.cancelScheduledCloudRunJobTask(record.id)
      toast.success('已取消定时任务发布。')
      await loadRecords(offset)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '取消定时任务发布失败')
    } finally {
      setBusy(null)
    }
  }

  const sync = async () => {
    if (busy) return
    setBusy('sync')
    try {
      const result = await api.syncScheduledCloudRunJobs()
      toast.success(`定时任务状态同步完成：处理 ${result.processed_count} 条，成功 ${result.succeeded_ids.length}，失败 ${result.failed_ids.length}`)
      await load(0)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '同步定时任务发布状态失败')
    } finally {
      setBusy(null)
    }
  }

  const hasNextPage = offset + PAGE_SIZE < totalRecords

  return (
    <div className="space-y-5">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Scheduled Job Releases</div>
            <h3 className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">定时任务发布记录</h3>
            <p className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">
              页面只展示定时任务发布记录。可发布任务列表通过弹窗查看；Google 写操作由本地 runner 使用 gcloud 和受控凭据执行。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load(offset).catch(() => {})}>刷新</button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-state-running-border)] px-4 py-2.5 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50" disabled={busy === 'sync'} onClick={sync}>{busy === 'sync' ? '同步中…' : '同步状态'}</button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => setCatalogOpen(true)}>查看定时任务列表</button>
            <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white" onClick={() => openSinglePublish()}>创建定时任务发布</button>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={familyFilter} onChange={(event) => setFamilyFilter(event.target.value as JobFamilyFilter)}>
            <option value="">全部 family</option>
            <option value="gateway">gateway</option>
            <option value="gateway-admin">gateway-admin</option>
          </select>
          <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={recordJobFilter} onChange={(event) => setRecordJobFilter(event.target.value)}>
            <option value="">全部任务</option>
            {jobs.map((item) => <option key={item.job_name} value={item.job_name}>{item.job_name}</option>)}
          </select>
          <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={recordStatusFilter} onChange={(event) => setRecordStatusFilter(event.target.value)}>
            <option value="">全部状态</option>
            <option value="requested">待执行</option>
            <option value="deploying">发布中</option>
            <option value="completed">已完成</option>
            <option value="failed">失败</option>
            <option value="cancelled">已取消</option>
          </select>
        </div>
        {diagnostics.length ? <div className="mt-4 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-sm text-[color:var(--ops-text-muted)]">{diagnostics.join(' · ')}</div> : null}
      </section>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
        <div className="grid grid-cols-[1.2fr_0.55fr_0.65fr_0.75fr_0.75fr_0.9fr_0.45fr] gap-4 bg-[color:var(--ops-panel-strong)] px-5 py-4 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
          <div>任务名称</div><div>Family</div><div>环境</div><div>状态</div><div>Branch</div><div>Runner / 更新时间</div><div className="text-right">操作</div>
        </div>
        {loading ? (
          <div className="px-5 py-10 text-sm text-[color:var(--ops-text-muted)]">正在读取定时任务发布记录…</div>
        ) : records.length === 0 ? (
          <EmptyPane>
            <div className="font-semibold">暂无定时任务发布记录</div>
            <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">点击“创建定时任务发布”创建第一条待执行记录。</div>
          </EmptyPane>
        ) : records.map((record) => (
          <div key={record.id} className="grid grid-cols-[1.2fr_0.55fr_0.65fr_0.75fr_0.75fr_0.9fr_0.45fr] gap-4 border-t border-[color:var(--ops-stroke-soft)] px-5 py-5 text-sm">
            <div><div className="font-semibold text-[color:var(--ops-text-title)]">{displayJobs(record)}</div><div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">record #{record.id} · {record.publish_mode}</div></div>
            <div><StateBadge tone="muted">{record.family}</StateBadge></div>
            <div><StateBadge tone="ready">{record.environment}</StateBadge></div>
            <div className="space-y-2"><StateBadge tone={statusTone(record.status)}>{labelForStatus(record.status)}</StateBadge><div className="text-xs text-[color:var(--ops-text-muted)]">Health: {labelForStatus(record.health_status)}</div>{record.failure_summary ? <div className="line-clamp-2 text-xs text-[color:var(--ops-state-blocked-text)]">{record.failure_summary}</div> : null}</div>
            <div className="font-mono text-xs text-[color:var(--ops-text-body)]">{record.source_ref || '-'}</div>
            <div><div className="text-xs text-[color:var(--ops-text-body)]">{record.external_url ? 'Local runner 已关联' : '等待本地 runner'}</div><div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">{formatTime(record.updated_at)}</div></div>
            <div className="flex flex-col items-end gap-2">
              <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => setRecordDetail(record)}>详情</button>
              {record.status === 'requested' ? (
                <button type="button" className="rounded-xl border border-[color:var(--ops-state-running-border)] px-4 py-2 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50" disabled={!!busy} onClick={() => publishRecord(record)}>发布到 staging</button>
              ) : null}
              {record.status === 'failed' ? (
                <button type="button" className="rounded-xl border border-[color:var(--ops-state-running-border)] px-4 py-2 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50" disabled={!!busy} onClick={() => publishRecord(record)}>重新发布</button>
              ) : null}
              {record.status === 'deploying' ? (
                <button type="button" className="rounded-xl border border-[color:var(--ops-state-running-border)] px-4 py-2 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50" disabled={busy === 'sync'} onClick={sync}>同步状态</button>
              ) : null}
              {record.status === 'requested' ? (
                <button type="button" className="rounded-xl border border-[color:var(--ops-state-blocked-border)] px-4 py-2 text-sm text-[color:var(--ops-state-blocked-text)] disabled:opacity-50" disabled={!!busy} onClick={() => cancelRecord(record)}>取消</button>
              ) : null}
            </div>
          </div>
        ))}
        <div className="flex items-center justify-between border-t border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]">
          <div>第 {Math.floor(offset / PAGE_SIZE) + 1} 页 · 共 {totalRecords} 条发布记录</div>
          <div className="flex gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-2 disabled:opacity-40" disabled={offset === 0 || loading} onClick={() => loadRecords(Math.max(0, offset - PAGE_SIZE))}>上一页</button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-2 disabled:opacity-40" disabled={!hasNextPage || loading} onClick={() => loadRecords(offset + PAGE_SIZE)}>下一页</button>
          </div>
        </div>
      </section>

      <CatalogModal open={catalogOpen} jobs={filteredCatalogJobs} familyFilter={familyFilter} kindFilter={kindFilter} catalogQuery={catalogQuery} onFamilyFilter={setFamilyFilter} onKindFilter={setKindFilter} onQuery={setCatalogQuery} onClose={() => setCatalogOpen(false)} onDetail={setJobDetail} onPublish={openSinglePublish} />
      <JobDetailModal detail={jobDetail} onClose={() => setJobDetail(null)} />
      <RecordDetailModal detail={recordDetail} onClose={() => setRecordDetail(null)} />
      <PublishModal publishDraft={publishDraft} branchError={branchError} branchLoading={branchLoading} branchOptions={filteredBranchOptions} branchQuery={branchQuery} busy={busy} jobs={jobs} selectedPublishJob={selectedPublishJob} onBranchQuery={setBranchQuery} onChange={setPublishDraft} onClose={() => setPublishDraft(null)} onPublish={createTask} />
    </div>
  )
}

function CatalogModal({ open, jobs, familyFilter, kindFilter, catalogQuery, onFamilyFilter, onKindFilter, onQuery, onClose, onDetail, onPublish }: Readonly<{ open: boolean; jobs: ScheduledCloudRunJobStatus[]; familyFilter: JobFamilyFilter; kindFilter: JobKindFilter; catalogQuery: string; onFamilyFilter: (value: JobFamilyFilter) => void; onKindFilter: (value: JobKindFilter) => void; onQuery: (value: string) => void; onClose: () => void; onDetail: (job: ScheduledCloudRunJobStatus) => void; onPublish: (job: ScheduledCloudRunJobStatus) => void }>) {
  return (
    <OverlayModal open={open} eyebrow="Job Catalog" title="定时任务列表" description="这里只展示可发布任务 catalog；发布历史在页面主列表中查看。" onClose={onClose}>
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <input className="min-w-[260px] rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm" placeholder="搜索任务名称 / command / 用途" value={catalogQuery} onChange={(event) => onQuery(event.target.value)} />
          <select className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm" value={familyFilter} onChange={(event) => onFamilyFilter(event.target.value as JobFamilyFilter)}><option value="">全部 family</option><option value="gateway">gateway</option><option value="gateway-admin">gateway-admin</option></select>
          <select className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm" value={kindFilter} onChange={(event) => onKindFilter(event.target.value as JobKindFilter)}><option value="">全部类型</option><option value="periodic">周期任务</option><option value="migration">迁移任务</option></select>
        </div>
        <div className="max-h-[56vh] overflow-auto rounded-2xl border border-[color:var(--ops-stroke-soft)]">
          {jobs.map((item) => (
            <div key={item.job_name} className="grid grid-cols-[1fr_0.55fr_0.8fr_0.45fr] gap-4 border-t border-[color:var(--ops-stroke-soft)] px-4 py-4 first:border-t-0">
              <div><div className="font-semibold text-[color:var(--ops-text-title)]">{item.job_name}</div><div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{item.purpose}</div><div className="mt-2 font-mono text-xs text-[color:var(--ops-text-caption)]">{item.command}</div></div>
              <div className="space-y-2"><StateBadge tone="muted">{item.family}</StateBadge><div className="text-xs text-[color:var(--ops-text-caption)]">{item.job_type} · {item.cadence}</div></div>
              <div className="space-y-2"><StateBadge tone={statusTone(item.publish_status)}>{labelForStatus(item.publish_status)}</StateBadge><div className="font-mono text-xs text-[color:var(--ops-text-body)]">{imageTail(item.effective_image || item.image_digest)}</div></div>
              <div className="flex flex-col items-end gap-2"><button type="button" className="rounded-xl border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)]" onClick={() => onPublish(item)}>创建发布任务</button><button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => onDetail(item)}>详情</button></div>
            </div>
          ))}
        </div>
      </div>
    </OverlayModal>
  )
}

function JobDetailModal({ detail, onClose }: Readonly<{ detail: ScheduledCloudRunJobStatus | null; onClose: () => void }>) {
  return (
    <OverlayModal open={!!detail} eyebrow="Cloud Run Job" title={detail?.job_name || 'Job 详情'} description="定时任务详情只读展示；发布、迁移执行和健康检查均由本地 scheduled-job runner 负责。" onClose={onClose}>
      {detail ? <div className="space-y-5"><div className="grid gap-3 md:grid-cols-3"><InfoCard label="Family / Type" value={`${detail.family} / ${detail.job_type}`} /><InfoCard label="Cadence" value={detail.cadence} /><InfoCard label="Publish" value={labelForStatus(detail.publish_status)} /></div><InfoBlock label="Command" value={detail.command} mono /><InfoBlock label="Purpose" value={detail.purpose} /><InfoBlock label="Scheduler" value={detail.scheduler_job || 'deploy/manual job'} mono /><InfoBlock label="Image" value={detail.effective_image || detail.image_digest || '-'} mono />{detail.failure_summary ? <InfoBlock label="Failure" value={detail.failure_summary} /> : null}</div> : null}
    </OverlayModal>
  )
}

function RecordDetailModal({ detail, onClose }: Readonly<{ detail: ScheduledCloudRunJobRecord | null; onClose: () => void }>) {
  const manifest = detail?.metadata?.jobsManifest || detail?.metadata?.jobs_manifest || null
  return (
    <OverlayModal open={!!detail} eyebrow="Publish Record" title={detail ? `定时任务发布记录 #${detail.id}` : '发布记录'} description="记录由本地 runner 回写；成功/失败以 DeploymentRecord、runner 日志和 manifest 为准。" onClose={onClose}>
      {detail ? <div className="space-y-5"><div className="grid gap-3 md:grid-cols-3"><InfoCard label="Job" value={displayJobs(detail)} /><InfoCard label="Family" value={detail.family} /><InfoCard label="Status" value={`${labelForStatus(detail.status)} / ${labelForStatus(detail.health_status)}`} /></div><InfoBlock label="Branch" value={detail.source_ref || '-'} mono /><InfoBlock label="Runner" value={detail.workflow_file || 'local_scheduled_job_runner'} mono />{detail.notes ? <InfoBlock label="Notes" value={detail.notes} /> : null}{manifest ? <InfoBlock label="jobs.json / manifest" value={JSON.stringify(manifest, null, 2)} mono /> : null}<div className="flex flex-wrap gap-2"><button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onClose}>关闭</button></div></div> : null}
    </OverlayModal>
  )
}

function PublishModal({ publishDraft, branchError, branchLoading, branchOptions, branchQuery, busy, jobs, selectedPublishJob, onBranchQuery, onChange, onClose, onPublish }: Readonly<{ publishDraft: PublishDraft | null; branchError: string | null; branchLoading: boolean; branchOptions: ReleaseBranchOption[]; branchQuery: string; busy: string | null; jobs: ScheduledCloudRunJobStatus[]; selectedPublishJob: ScheduledCloudRunJobStatus | null; onBranchQuery: (value: string) => void; onChange: (value: PublishDraft | null | ((current: PublishDraft | null) => PublishDraft | null)) => void; onClose: () => void; onPublish: () => void }>) {
  return (
    <OverlayModal open={!!publishDraft} eyebrow="Human Gate" title="创建定时任务发布" description="这里只创建待执行记录，不直接执行。创建后在列表点击“发布到 staging”，再由本地 runner 抢占执行。" onClose={onClose}>
      {publishDraft ? <div className="space-y-5"><div className="rounded-2xl border border-[color:var(--ops-state-ready-border)] bg-[color:var(--ops-state-ready-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-ready-text)]">周期任务发布只更新 image，Cloud Scheduler 继续负责触发。Migration 任务发布会执行 migration job，必须单独确认。</div><div className="grid gap-4 md:grid-cols-3"><label><FieldLabel>环境</FieldLabel><select className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm" value={publishDraft.environment} onChange={(event) => onChange((current) => current ? { ...current, environment: event.target.value as 'staging' | 'production' } : current)}><option value="staging">staging</option><option value="production" disabled>production · 暂未开放</option></select></label><label className="md:col-span-2"><FieldLabel>GitHub 分支</FieldLabel><input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm" placeholder={branchLoading ? '正在读取 GitHub 分支…' : '输入关键词筛选分支'} value={branchQuery} disabled={branchLoading || !!branchError} onChange={(event) => onBranchQuery(event.target.value)} /><select className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm" value={publishDraft.sourceRef} disabled={branchLoading || !!branchError || branchOptions.length === 0} onChange={(event) => onChange((current) => current ? { ...current, sourceRef: event.target.value } : current)}><option value="">{branchLoading ? '正在读取 GitHub 分支…' : '选择 GitHub 分支'}</option>{branchOptions.map((branch) => <option key={branch.name} value={branch.name}>{branch.name}{branch.is_default ? ' · default' : ''}{branch.protected ? ' · protected' : ''}</option>)}</select>{branchError ? <div className="mt-2 text-xs text-[color:var(--ops-state-blocked-text)]">无法读取 GitHub 分支：{branchError}</div> : null}</label></div><label><FieldLabel>任务名称</FieldLabel><select className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm" value={publishDraft.jobName} onChange={(event) => onChange((current) => current ? { ...current, jobName: event.target.value, runMigrations: false } : current)}><option value="">选择要发布的 Cloud Run Job</option>{jobs.map((item) => <option key={item.job_name} value={item.job_name}>{item.job_name} · {item.family} · {item.cadence}</option>)}</select></label>{selectedPublishJob ? <div className="grid gap-3 md:grid-cols-2"><InfoCard label="Family / Type" value={`${selectedPublishJob.family} / ${selectedPublishJob.job_type}`} /><InfoCard label="Cadence" value={selectedPublishJob.cadence} /><InfoBlock label="Command" value={selectedPublishJob.command} mono /><InfoBlock label="Purpose" value={selectedPublishJob.purpose} /></div> : null}<label className="flex items-center gap-3 text-sm text-[color:var(--ops-text-body)]"><input type="checkbox" checked={publishDraft.runSmokeJobs} onChange={(event) => onChange((current) => current ? { ...current, runSmokeJobs: event.target.checked } : current)} />发布后执行 smoke jobs（只建议在需要验证时开启）</label><label className="flex items-center gap-3 text-sm text-[color:var(--ops-text-body)]"><input type="checkbox" checked={publishDraft.runMigrations} onChange={(event) => onChange((current) => current ? { ...current, runMigrations: event.target.checked } : current)} />确认执行这个 migration job</label>{selectedPublishJob?.migration_execution_required ? <div className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-blocked-text)]">该任务是 migration job。发布流程会执行它，必须确认后才能继续。</div> : null}<div className="flex justify-end gap-2"><button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onClose}>取消</button><button type="button" className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={!!busy || branchLoading || !!branchError || !publishDraft.sourceRef || !publishDraft.jobName || !!(selectedPublishJob?.migration_execution_required && !publishDraft.runMigrations)} onClick={onPublish}>{busy?.startsWith('create:') ? '创建中…' : '确认创建'}</button></div></div> : null}
    </OverlayModal>
  )
}

function InfoCard({ label, value }: Readonly<{ label: string; value: string }>) {
  return <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3"><div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div><div className="mt-2 text-sm font-semibold text-[color:var(--ops-text-title)]">{value}</div></div>
}

function InfoBlock({ label, value, mono }: Readonly<{ label: string; value: string; mono?: boolean }>) {
  return <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3"><div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div><div className={`mt-2 whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-body)] ${mono ? 'font-mono' : ''}`}>{value}</div></div>
}
