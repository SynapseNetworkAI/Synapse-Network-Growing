import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, BugDetail, BugRecord } from '../api'
import { WorkbenchPagination } from '../components/WorkbenchPagination'
import { EmptyPane, StateBadge, useToast } from '../components/workbench'
import { BugDetailModal } from './bugs/BugDetailModal'

const PAGE_SIZE_OPTIONS = [20, 50, 100]

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function severityTone(value: string) {
  if (value === 'critical' || value === 'high') return 'blocked'
  if (value === 'normal') return 'running'
  return 'muted'
}

function statusTone(value: string) {
  if (['closed', 'verified'].includes(value)) return 'delivered'
  if (['fixing', 'fixed_pending_verification'].includes(value)) return 'validating'
  if (['open', 'ready_for_agent', 'reopened', 'triaged'].includes(value)) return 'running'
  if (['wontfix', 'duplicate', 'failed'].includes(value)) return 'blocked'
  return 'muted'
}

function shortSha(value: string | null) {
  return value ? value.slice(0, 10) : '-'
}

function uniqueValues(items: BugRecord[], key: keyof BugRecord) {
  return Array.from(new Set(items.map((item) => String(item[key] || '')).filter(Boolean))).sort()
}

function toPositiveInt(value: string | null, fallback: number, allowed?: number[]) {
  const parsed = Number(value || fallback)
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback
  if (allowed && !allowed.includes(parsed)) return fallback
  return parsed
}

function updateSearchParams(
  current: URLSearchParams,
  values: Record<string, string | number | null | undefined>,
) {
  const next = new URLSearchParams(current)
  Object.entries(values).forEach(([key, value]) => {
    const normalized = value == null ? '' : String(value).trim()
    if (!normalized) next.delete(key)
    else next.set(key, normalized)
  })
  return next
}

function countFromMap(map: Record<string, number>, keys: string[]) {
  return keys.reduce((sum, key) => sum + Number(map[key] || 0), 0)
}

export default function BugsPage() {
  const toast = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const [items, setItems] = useState<BugRecord[]>([])
  const [total, setTotal] = useState(0)
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({})
  const [severityCounts, setSeverityCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [detail, setDetail] = useState<BugDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [searchDraft, setSearchDraft] = useState(searchParams.get('q') || '')
  const [projectDraft, setProjectDraft] = useState(searchParams.get('project_key') || '')
  const [statusDraft, setStatusDraft] = useState(searchParams.get('status') || '')
  const [severityDraft, setSeverityDraft] = useState(searchParams.get('severity') || '')
  const [linkDraft, setLinkDraft] = useState({ branch_name: '', commit_sha: '', pr_url: '' })
  const [verificationSummary, setVerificationSummary] = useState('')

  const page = toPositiveInt(searchParams.get('page'), 1)
  const pageSize = toPositiveInt(searchParams.get('page_size'), 20, PAGE_SIZE_OPTIONS)
  const search = searchParams.get('q') || ''
  const project = searchParams.get('project_key') || ''
  const status = searchParams.get('status') || ''
  const severity = searchParams.get('severity') || ''

  useEffect(() => {
    setSearchDraft(search)
    setProjectDraft(project)
    setStatusDraft(status)
    setSeverityDraft(severity)
  }, [search, project, status, severity])

  const load = async () => {
    setLoading(true)
    try {
      const payload = await api.getBugs({
        q: search || undefined,
        project_key: project || undefined,
        status: status || undefined,
        severity: severity || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      })
      setItems(payload.items)
      setTotal(payload.total)
      setStatusCounts(payload.status_counts || {})
      setSeverityCounts(payload.severity_counts || {})
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [search, project, status, severity, page, pageSize])

  const projectOptions = useMemo(() => uniqueValues(items, 'project_key'), [items])
  const statusOptions = useMemo(() => uniqueValues(items, 'status'), [items])
  const severityOptions = useMemo(() => uniqueValues(items, 'severity'), [items])
  const pageCount = Math.max(1, Math.ceil(total / pageSize))

  const openDetail = async (id: number) => {
    setBusy(true)
    try {
      const payload = await api.getBugDetail(id)
      setDetail(payload)
      setLinkDraft({
        branch_name: payload.latest_fix_attempt?.branch_name || '',
        commit_sha: payload.latest_fix_attempt?.commit_sha || '',
        pr_url: payload.latest_fix_attempt?.pr_url || '',
      })
      setVerificationSummary(payload.latest_fix_attempt?.verification_summary || '')
    } finally {
      setBusy(false)
    }
  }

  const refreshDetail = async () => {
    if (!detail) return
    const payload = await api.getBugDetail(detail.bug.id)
    setDetail(payload)
    await load()
  }

  const runAction = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true)
    try {
      await action()
      toast.success(message)
      await refreshDetail()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  const applyFilters = () => {
    setSearchParams(
      updateSearchParams(searchParams, {
        q: searchDraft,
        project_key: projectDraft,
        status: statusDraft,
        severity: severityDraft,
        page: 1,
        page_size: pageSize,
      }),
    )
  }

  const resetFilters = () => {
    setSearchDraft('')
    setProjectDraft('')
    setStatusDraft('')
    setSeverityDraft('')
    setSearchParams(updateSearchParams(searchParams, { q: '', project_key: '', status: '', severity: '', page: 1, page_size: pageSize }))
  }

  const goToPage = (nextPage: number) => {
    setSearchParams(updateSearchParams(searchParams, { page: Math.max(1, Math.min(pageCount, nextPage)), page_size: pageSize }))
  }

  const changePageSize = (nextPageSize: number) => {
    setSearchParams(updateSearchParams(searchParams, { page: 1, page_size: nextPageSize }))
  }

  useEffect(() => {
    if (!loading && page > pageCount) goToPage(pageCount)
  }, [loading, page, pageCount])

  return (
    <div className="space-y-5" data-testid="bugs-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Agent Fix Queue</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">Bug List</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
              Agent 原生 bug backlog：分页查看 bug、领取并启动修复、回填 PR / 验证证据，再按门禁关闭。
            </p>
          </div>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
            刷新
          </button>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          {[
            ['Open bugs', countFromMap(statusCounts, ['open', 'ready_for_agent', 'triaged', 'reopened'])],
            ['Ready for agent', countFromMap(statusCounts, ['open', 'ready_for_agent', 'reopened'])],
            ['Fixing', countFromMap(statusCounts, ['fixing'])],
            ['Pending verification', countFromMap(statusCounts, ['fixed_pending_verification'])],
            ['Verified', countFromMap(statusCounts, ['verified', 'closed'])],
            ['Critical / High', countFromMap(severityCounts, ['critical', 'high'])],
          ].map(([label, value]) => (
            <div key={label} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
              <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{value}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
        <div className="grid gap-3 md:grid-cols-5">
          <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm md:col-span-2" placeholder="搜索 title / fingerprint / summary" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} />
          <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" value={projectDraft} onChange={(event) => setProjectDraft(event.target.value)}>
            <option value="">全部项目</option>
            {projectOptions.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" value={statusDraft} onChange={(event) => setStatusDraft(event.target.value)}>
            <option value="">全部状态</option>
            {statusOptions.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <div className="flex gap-2">
            <select className="min-w-0 flex-1 rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" value={severityDraft} onChange={(event) => setSeverityDraft(event.target.value)}>
              <option value="">全部级别</option>
              {severityOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm text-white" onClick={applyFilters}>查询</button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-end gap-3 text-sm text-[color:var(--ops-text-muted)]">
          <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={resetFilters}>重置筛选</button>
        </div>
      </section>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
        <div className="border-b border-[color:var(--ops-stroke-soft)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]">共 {total} 个 bug</div>
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse">
            <thead className="bg-[color:var(--ops-panel-subtle)]">
              <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                <th className="px-5 py-4 font-medium">Bug</th>
                <th className="px-4 py-4 font-medium">项目</th>
                <th className="px-4 py-4 font-medium">级别</th>
                <th className="px-4 py-4 font-medium">状态</th>
                <th className="px-4 py-4 font-medium">来源 / 次数</th>
                <th className="px-4 py-4 font-medium">修复证据</th>
                <th className="px-4 py-4 font-medium">最后出现</th>
                <th className="px-5 py-4 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const latestFix = item.metadata.latest_fix as Record<string, unknown> | undefined
                return (
                  <tr key={item.id} className="border-t border-[color:var(--ops-stroke-soft)] hover:bg-[color:var(--ops-panel-subtle)]">
                    <td className="max-w-md px-5 py-4">
                      <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{item.title}</div>
                      <div className="mt-1 truncate text-xs text-[color:var(--ops-text-caption)]">{item.fingerprint}</div>
                    </td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.project_key || '-'}</td>
                    <td className="px-4 py-4"><StateBadge tone={severityTone(item.severity)}>{item.severity}</StateBadge></td>
                    <td className="px-4 py-4"><StateBadge tone={statusTone(item.status)}>{item.status}</StateBadge></td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.source_key} · {item.occurrence_count}</td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                      <div>{String(latestFix?.branch_name || '-')}</div>
                      <div className="mt-1 text-xs">commit {shortSha(String(latestFix?.commit_sha || '') || null)}</div>
                    </td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(item.last_seen_at)}</td>
                    <td className="px-5 py-4 text-right">
                      <button type="button" className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white" disabled={busy} onClick={() => openDetail(item.id).catch(() => {})}>详情</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {!loading && items.length === 0 ? <div className="p-6"><EmptyPane>暂无 bug 记录。</EmptyPane></div> : null}
        <WorkbenchPagination
          page={page}
          pageSize={pageSize}
          totalItems={total}
          pageSizeOptions={PAGE_SIZE_OPTIONS}
          itemLabel="个 bug"
          loading={loading}
          onPageChange={goToPage}
          onPageSizeChange={changePageSize}
        />
      </section>

      <BugDetailModal
        detail={detail}
        busy={busy}
        linkDraft={linkDraft}
        verificationSummary={verificationSummary}
        setLinkDraft={setLinkDraft}
        setVerificationSummary={setVerificationSummary}
        onClose={() => setDetail(null)}
        onClaim={() => runAction(() => api.claimBug(detail!.bug.id, { agent_id: 'codex' }), 'Agent 已领取 bug')}
        onClaimAndRun={() => runAction(() => api.claimAndRunBug(detail!.bug.id, { agent_id: 'codex' }), 'Agent 已领取并启动修复')}
        onMaterialize={() => runAction(() => api.materializeBugRequirement(detail!.bug.id), '已创建或绑定修复需求')}
        onLinkFix={() => runAction(() => api.linkBugFix(detail!.bug.id, { agent_id: 'codex', ...linkDraft }), '修复分支和 commit 已记录')}
        onVerify={() => runAction(() => api.addBugVerification(detail!.bug.id, {
          agent_id: 'codex',
          status: 'verified',
          summary: verificationSummary || 'Verified by agent.',
          commands: [{ command: 'manual verification evidence registered', status: 'passed' }],
          screenshots: detail?.latest_fix_attempt?.verification_screenshots || [],
        }), '验证证据已记录')}
        onCloseBug={() => runAction(() => api.closeBug(detail!.bug.id, { actor: 'codex', resolution: 'verified' }), 'Bug 已关闭')}
        onReopen={() => runAction(() => api.reopenBug(detail!.bug.id, { actor: 'codex', reason: 'Regression or verification failed.' }), 'Bug 已重新打开')}
      />
    </div>
  )
}
