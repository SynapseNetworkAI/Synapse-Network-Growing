import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AgentRequirement, api } from '../api'
import { EmptyPane, FieldLabel, InspectorRail, SectionFrame, StateBadge } from '../components/workbench'

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  ready: '待执行',
  running: '执行中',
  blocked: '阻塞',
  needs_revision: '需修订',
  delivery_ready: '待发布',
  done: '已完成',
  cancelled: '已取消',
  deleted: '已删除',
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function statusTone(status: string) {
  if (status === 'done' || status === 'delivery_ready') return 'delivered'
  if (status === 'running') return 'running'
  if (status === 'blocked' || status === 'needs_revision' || status === 'cancelled') return 'blocked'
  if (status === 'ready') return 'ready'
  return 'muted'
}

export default function RequirementPool() {
  const navigate = useNavigate()
  const [requirements, setRequirements] = useState<AgentRequirement[]>([])
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [submittingId, setSubmittingId] = useState<number | null>(null)
  const [form, setForm] = useState({
    title: '',
    description_markdown: '',
    acceptance_criteria_markdown: '',
    priority: 'normal',
    target_project_path: '',
  })

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getRequirements(status || undefined, undefined, search || undefined)
      setRequirements(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [status])

  const filtered = useMemo(() => {
    if (!search.trim()) return requirements
    const needle = search.trim().toLowerCase()
    return requirements.filter((item) =>
      [item.title, item.description_markdown, item.source_ref || '', item.target_project_path || '', String(item.id)]
        .join('\n')
        .toLowerCase()
        .includes(needle),
    )
  }, [requirements, search])

  return (
    <div className="space-y-[var(--ops-section-gap)]" data-testid="agent-first-requirements-page">
      <SectionFrame
        eyebrow="Requirement Workspace"
        title="需求面"
        description="需求面只收口意图、约束和验收标准，不直接承载执行日志和发布动作。"
        actions={
          <>
            <select className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">全部状态</option>
              <option value="draft">草稿</option>
              <option value="ready">待执行</option>
              <option value="running">执行中</option>
              <option value="blocked">阻塞</option>
              <option value="needs_revision">需修订</option>
              <option value="delivery_ready">待发布</option>
              <option value="done">已完成</option>
            </select>
            <input
              className="w-72 rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm"
              placeholder="搜索标题 / 项目 / source_ref / ID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button
              className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2.5 text-sm font-medium text-white"
              onClick={() => load().catch(() => {})}
            >
              刷新
            </button>
          </>
        }
      >
        <div className="grid gap-4 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-3">
          <div>
            <FieldLabel>治理原则</FieldLabel>
            <div className="mt-2">Requirement 只定义 why / what / constraints。</div>
          </div>
          <div>
            <FieldLabel>下一跳</FieldLabel>
            <div className="mt-2">submit 会先做审批判定，放行后自动进入 Execution，交付进入 Release。</div>
          </div>
          <div>
            <FieldLabel>当前视图</FieldLabel>
            <div className="mt-2">先定义意图，再 submit 进入 execution bridge。</div>
          </div>
        </div>
      </SectionFrame>

      <div className="grid gap-[var(--ops-section-gap)] xl:grid-cols-[minmax(0,1.65fr),minmax(300px,var(--ops-inspector-width))]">
        <SectionFrame
          eyebrow="Intake"
          title="新建需求"
          description="主工作区只承载 requirement intake 表单，把标题、描述、约束和验收一次写清。"
          actions={
            <button
              className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm text-[color:var(--ops-text-body)]"
              onClick={() => setForm({ title: '', description_markdown: '', acceptance_criteria_markdown: '', priority: 'normal', target_project_path: '' })}
            >
              清空
            </button>
          }
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <FieldLabel>标题</FieldLabel>
              <input
                className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                placeholder="用结果描述 requirement"
                value={form.title}
                onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
              />
            </div>
            <div>
              <FieldLabel>目标项目</FieldLabel>
              <input
                className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                placeholder="目标项目路径，可换行写多个"
                value={form.target_project_path}
                onChange={(event) => setForm((current) => ({ ...current, target_project_path: event.target.value }))}
              />
            </div>
            <div className="lg:col-span-2">
              <FieldLabel>需求描述</FieldLabel>
              <textarea
                className="mt-2 min-h-[180px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                placeholder="为什么做、要做到什么、主要约束是什么"
                value={form.description_markdown}
                onChange={(event) => setForm((current) => ({ ...current, description_markdown: event.target.value }))}
              />
            </div>
            <div className="lg:col-span-2">
              <FieldLabel>验收标准</FieldLabel>
              <textarea
                className="mt-2 min-h-[120px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                placeholder="如何判断 validate 成功"
                value={form.acceptance_criteria_markdown}
                onChange={(event) => setForm((current) => ({ ...current, acceptance_criteria_markdown: event.target.value }))}
              />
            </div>
            <div>
              <FieldLabel>优先级</FieldLabel>
              <select
                className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                value={form.priority}
                onChange={(event) => setForm((current) => ({ ...current, priority: event.target.value }))}
              >
                <option value="low">low</option>
                <option value="normal">normal</option>
                <option value="high">high</option>
              </select>
            </div>
            <div className="flex items-end justify-end">
              <button
                className="rounded-2xl bg-[color:var(--ops-state-running-text)] px-5 py-3 text-sm font-medium text-white disabled:opacity-60"
                disabled={creating || !form.title.trim() || !form.description_markdown.trim()}
                onClick={async () => {
                  setCreating(true)
                  try {
                    const detail = await api.createRequirement(form)
                    await load()
                    navigate(`/requirements/${detail.requirement.id}`)
                  } finally {
                    setCreating(false)
                  }
                }}
              >
                {creating ? '创建中…' : '创建需求'}
              </button>
            </div>
          </div>
        </SectionFrame>

        <InspectorRail eyebrow="Checks" title="Requirement Health">
          <div>
            <FieldLabel>写法建议</FieldLabel>
            <div className="mt-2 leading-6 text-[color:var(--ops-text-muted)]">标题写结果，描述写 why / what / constraints，验收写 validate 如何判定。</div>
          </div>
          <div>
            <FieldLabel>当前草稿</FieldLabel>
            <div className="mt-2 flex flex-wrap gap-2">
              <StateBadge tone={form.title.trim() ? 'ready' : 'blocked'}>{form.title.trim() ? '标题已填写' : '缺少标题'}</StateBadge>
              <StateBadge tone={form.description_markdown.trim() ? 'ready' : 'blocked'}>
                {form.description_markdown.trim() ? '描述已填写' : '缺少描述'}
              </StateBadge>
              <StateBadge tone={form.acceptance_criteria_markdown.trim() ? 'ready' : 'validating'}>
                {form.acceptance_criteria_markdown.trim() ? '验收已填写' : '待补充验收'}
              </StateBadge>
            </div>
          </div>
          <div>
            <FieldLabel>下一步</FieldLabel>
            <div className="mt-2 leading-6 text-[color:var(--ops-text-muted)]">Requirement submit 后会先做自动审批。低风险会直接 auto-start，高风险会回到需求面等待人工批准。</div>
          </div>
        </InspectorRail>
      </div>

      <SectionFrame
        eyebrow="Queue"
        title="需求列表"
        description={loading ? '正在拉取 requirement…' : `当前共 ${filtered.length} 条 requirement。`}
      >
        <div className="grid gap-4">
          {filtered.map((item) => (
            <article key={item.id} className="border-b border-[color:var(--ops-stroke-soft)] pb-5 last:border-b-0 last:pb-0">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.75fr),320px]">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-lg font-semibold text-[color:var(--ops-text-title)]">{item.title}</h4>
                    <StateBadge tone={statusTone(item.status)}>{STATUS_LABEL[item.status] || item.status}</StateBadge>
                    <StateBadge tone="muted">{item.priority}</StateBadge>
                  </div>
                  <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)] line-clamp-3">{item.description_markdown}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${item.id}`)}>
                      查看需求
                    </button>
                    <button
                      className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2 text-sm text-white disabled:opacity-50"
                      disabled={submittingId === item.id || (item.status !== 'draft' && item.status !== 'needs_revision')}
                      onClick={async () => {
                        setSubmittingId(item.id)
                        try {
                          const detail = await api.submitRequirement(item.id)
                          if (detail.approval.execution_run_id && detail.approval.auto_started) {
                            navigate(`/executions/${detail.approval.execution_run_id}`)
                            return
                          }
                          navigate(`/requirements/${item.id}`)
                        } finally {
                          await load()
                          setSubmittingId(null)
                        }
                      }}
                    >
                      {submittingId === item.id ? '提交中…' : '提交到执行'}
                    </button>
                    {item.status === 'blocked' && item.approval_status === 'pending_approval' && (
                      <button
                        className="rounded-2xl border border-[color:var(--ops-state-validating-border)] px-4 py-2 text-sm text-[color:var(--ops-state-validating-text)]"
                        onClick={() => navigate(`/requirements/${item.id}`)}
                      >
                        等待审批
                      </button>
                    )}
                    {item.status === 'ready' && !item.latest_execution_run_id && (
                      <button
                        className="rounded-2xl border border-[color:var(--ops-state-running-border)] px-4 py-2 text-sm text-[color:var(--ops-state-running-text)]"
                        onClick={async () => {
                          const detail = await api.createExecution({ requirement_id: item.id })
                          navigate(`/executions/${detail.execution.id}`)
                        }}
                      >
                        高级: 手动创建执行
                      </button>
                    )}
                    {item.latest_execution_run_id && (
                      <button
                        className="rounded-2xl border border-[color:var(--ops-state-running-border)] px-4 py-2 text-sm text-[color:var(--ops-state-running-text)]"
                        onClick={() => navigate(`/executions/${item.latest_execution_run_id}`)}
                      >
                        查看执行
                      </button>
                    )}
                    {item.latest_release_status && (
                      <button
                        className="rounded-2xl border border-[color:var(--ops-state-ready-border)] px-4 py-2 text-sm text-[color:var(--ops-state-ready-text)]"
                        onClick={() => navigate(`/releases/${item.id}`)}
                      >
                        查看发布
                      </button>
                    )}
                  </div>
                </div>
                <InspectorRail eyebrow={`Requirement #${item.id}`} title="治理摘要" className="bg-transparent shadow-none">
                  <div>
                    <FieldLabel>目标项目</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{item.target_projects.join(', ') || '-'}</div>
                  </div>
                  <div>
                    <FieldLabel>审批</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{item.approval_required ? item.approval_status : 'waived'}</div>
                  </div>
                  <div>
                    <FieldLabel>执行 / 发布</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">
                      execution {item.active_execution_run_id ?? '-'} · release {item.latest_release_status ?? '-'}
                    </div>
                  </div>
                  <div>
                    <FieldLabel>更新时间</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{formatTime(item.updated_at)}</div>
                  </div>
                </InspectorRail>
              </div>
            </article>
          ))}
          {!loading && filtered.length === 0 && <EmptyPane>当前没有符合条件的 requirement。</EmptyPane>}
        </div>
      </SectionFrame>
    </div>
  )
}
