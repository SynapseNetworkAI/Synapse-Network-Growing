import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ExecutionRun, api } from '../api'
import { EmptyPane, FieldLabel, InspectorRail, SectionFrame, StateBadge } from '../components/workbench'

const STATUS_LABEL: Record<string, string> = {
  queued: '排队中',
  running: '执行中',
  paused: '已暂停',
  blocked: '阻塞',
  validating: '验证中',
  failed: '失败',
  succeeded: '成功',
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function statusTone(status: string) {
  if (status === 'succeeded') return 'delivered'
  if (status === 'running') return 'running'
  if (status === 'blocked' || status === 'failed') return 'blocked'
  if (status === 'validating') return 'validating'
  if (status === 'queued') return 'ready'
  return 'muted'
}

export default function ExecutionsPage() {
  const navigate = useNavigate()
  const [executions, setExecutions] = useState<ExecutionRun[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      setExecutions(await api.getExecutions())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return executions
    return executions.filter((item) =>
      [String(item.id), String(item.requirement_id), item.execution_mode, item.complexity, item.planner_summary || '', item.target_projects.join('\n')]
        .join('\n')
        .toLowerCase()
        .includes(needle),
    )
  }, [executions, search])

  return (
    <div className="space-y-[var(--ops-section-gap)]" data-testid="executions-page">
      <SectionFrame
        eyebrow="Execution Console"
        title="执行面"
        description="执行面聚焦 agent 的实际工作面：执行模式、运行时、验证结果和恢复信号。"
        actions={
          <div className="flex items-center gap-3">
            <input
              className="w-72 rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm"
              placeholder="搜索 execution / requirement / target"
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
            <FieldLabel>默认流</FieldLabel>
            <div className="mt-2">{'intake -> execute -> validate -> deliver'}</div>
          </div>
          <div>
            <FieldLabel>主工作区</FieldLabel>
            <div className="mt-2">Execution graph、evidence、checks 和 incidents。</div>
          </div>
          <div>
            <FieldLabel>治理边界</FieldLabel>
            <div className="mt-2">submit 放行后 execution 默认自动启动；这里主要负责观察、恢复和 validate。</div>
          </div>
        </div>
      </SectionFrame>

      <SectionFrame eyebrow="Runs" title="执行队列" description={loading ? '正在拉取 execution run…' : `${filtered.length} 个 execution run`}>
        <div className="mt-4 grid gap-4">
          {filtered.map((item) => (
            <article key={item.id} className="border-b border-[color:var(--ops-stroke-soft)] pb-5 last:border-b-0 last:pb-0">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr),320px]">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-lg font-semibold text-[color:var(--ops-text-title)]">Execution #{item.id}</h4>
                    <StateBadge tone={statusTone(item.status)}>{STATUS_LABEL[item.status] || item.status}</StateBadge>
                    <StateBadge tone="muted">{item.execution_mode}</StateBadge>
                    <StateBadge tone="muted">{item.complexity}</StateBadge>
                  </div>
                  <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">{item.planner_summary || 'No planner summary'}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${item.requirement_id}`)}>
                      查看需求
                    </button>
                    <button className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2 text-sm text-white" onClick={() => navigate(`/executions/${item.id}`)}>
                      打开执行面
                    </button>
                    {(item.status === 'queued' || item.status === 'paused' || item.status === 'blocked') && (
                      <button
                        className="rounded-2xl border border-[color:var(--ops-state-running-border)] px-4 py-2 text-sm text-[color:var(--ops-state-running-text)]"
                        onClick={async () => {
                          await api.startExecution(item.id)
                          await load()
                        }}
                      >
                        {item.status === 'paused' ? '恢复执行' : '恢复/重启执行'}
                      </button>
                    )}
                  </div>
                </div>
                <InspectorRail eyebrow={`Requirement #${item.requirement_id}`} title="Run Summary" className="bg-transparent shadow-none">
                  <div>
                    <FieldLabel>Targets</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{item.target_projects.join(', ') || '-'}</div>
                  </div>
                  <div>
                    <FieldLabel>Validation / Delivery</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{item.validation_profile} · {item.delivery_intent}</div>
                  </div>
                  <div>
                    <FieldLabel>Approval</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{item.approval_required ? 'required' : 'waived'}</div>
                  </div>
                  <div>
                    <FieldLabel>Updated</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{formatTime(item.updated_at)}</div>
                  </div>
                </InspectorRail>
              </div>
            </article>
          ))}

          {!loading && filtered.length === 0 && <EmptyPane>当前没有 execution run。</EmptyPane>}
        </div>
      </SectionFrame>
    </div>
  )
}
