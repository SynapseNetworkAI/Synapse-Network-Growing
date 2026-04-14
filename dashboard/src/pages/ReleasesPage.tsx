import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ReleaseCandidate, api } from '../api'
import { EmptyPane, FieldLabel, InspectorRail, SectionFrame, StateBadge } from '../components/workbench'

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

export default function ReleasesPage() {
  const navigate = useNavigate()
  const [candidates, setCandidates] = useState<ReleaseCandidate[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      setCandidates(await api.getReleaseCandidates())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return candidates
    return candidates.filter((item) =>
      [String(item.requirement.id), item.requirement.title, item.requirement.target_projects.join('\n'), item.release?.status || '', item.validation.summary_markdown]
        .join('\n')
        .toLowerCase()
        .includes(needle),
    )
  }, [candidates, search])

  return (
    <div className="space-y-[var(--ops-section-gap)]" data-testid="releases-page">
      <SectionFrame
        eyebrow="Release Center"
        title="发布面"
        description="发布面只接收 validate 成功后的 requirement，统一处理 branch、PR、部署和 rollback。"
        actions={
          <div className="flex items-center gap-3">
            <input
              className="w-72 rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm"
              placeholder="搜索 requirement / project / release status"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2.5 text-sm font-medium text-white" onClick={() => load().catch(() => {})}>
              刷新
            </button>
          </div>
        }
      >
        <div className="grid gap-4 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-3">
          <div>
            <FieldLabel>候选门槛</FieldLabel>
            <div className="mt-2">只有 validate 成功的 requirement 才进入 release candidates。</div>
          </div>
          <div>
            <FieldLabel>主工作区</FieldLabel>
            <div className="mt-2">branch / commit / PR / deployment timeline。</div>
          </div>
          <div>
            <FieldLabel>右侧环境栏</FieldLabel>
            <div className="mt-2">staging / production 状态与 rollback target。</div>
          </div>
        </div>
      </SectionFrame>

      <SectionFrame eyebrow="Candidates" title="发布候选" description={loading ? '正在拉取候选…' : `${filtered.length} 个候选`}>
        <div className="mt-4 grid gap-4">
          {filtered.map((item) => (
            <article key={item.requirement.id} className="border-b border-[color:var(--ops-stroke-soft)] pb-5 last:border-b-0 last:pb-0">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr),320px]">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-lg font-semibold text-[color:var(--ops-text-title)]">#{item.requirement.id} {item.requirement.title}</h4>
                    <StateBadge tone="delivered">{item.requirement.status}</StateBadge>
                    <StateBadge tone={item.release?.status ? 'ready' : 'muted'}>{item.release?.status || 'ready'}</StateBadge>
                  </div>
                  <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">{item.validation.summary_markdown}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${item.requirement.id}`)}>
                      查看需求
                    </button>
                    <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/executions/${item.requirement.latest_execution_run_id}`)} disabled={!item.requirement.latest_execution_run_id}>
                      查看执行
                    </button>
                    <button className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2 text-sm text-white" onClick={() => navigate(`/releases/${item.requirement.id}`)}>
                      打开发布面
                    </button>
                  </div>
                </div>
                <InspectorRail eyebrow={`Requirement #${item.requirement.id}`} title="Release Summary" className="bg-transparent shadow-none">
                  <div>
                    <FieldLabel>Target Projects</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{item.requirement.target_projects.join(', ') || '-'}</div>
                  </div>
                  <div>
                    <FieldLabel>Validation</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{item.validation.status}</div>
                  </div>
                  <div>
                    <FieldLabel>Branch / PR</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">
                      {item.release?.branch_name || '-'} · PR {item.release?.pr_number || '-'}
                    </div>
                  </div>
                  <div>
                    <FieldLabel>Updated</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{formatTime(item.release?.updated_at || item.validation.updated_at)}</div>
                  </div>
                </InspectorRail>
              </div>
            </article>
          ))}

          {!loading && filtered.length === 0 && <EmptyPane>当前没有 validate 成功的 release candidate。</EmptyPane>}
        </div>
      </SectionFrame>
    </div>
  )
}
