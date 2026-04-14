import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AgentRequirement, api } from '../api'
import {
  EmptyPane,
  FieldLabel,
  OverlayDrawer,
  SectionFrame,
  SelectionInspector,
  StateBadge,
  WorkbenchToolbar,
} from '../components/workbench'

type DrawerMode = 'closed' | 'create' | 'edit'

type RequirementDraft = {
  title: string
  description_markdown: string
  acceptance_criteria_markdown: string
  priority: string
  target_project_path: string
}

const EMPTY_DRAFT: RequirementDraft = {
  title: '',
  description_markdown: '',
  acceptance_criteria_markdown: '',
  priority: 'normal',
  target_project_path: '',
}

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

function buildDraft(requirement?: AgentRequirement | null): RequirementDraft {
  if (!requirement) return { ...EMPTY_DRAFT }
  return {
    title: requirement.title,
    description_markdown: requirement.description_markdown,
    acceptance_criteria_markdown: requirement.acceptance_criteria_markdown,
    priority: requirement.priority,
    target_project_path: requirement.target_project_path || '',
  }
}

function RequirementDrawer({
  mode,
  open,
  draft,
  saving,
  selected,
  onChange,
  onClear,
  onClose,
  onSubmit,
}: Readonly<{
  mode: DrawerMode
  open: boolean
  draft: RequirementDraft
  saving: boolean
  selected: AgentRequirement | null
  onChange: (patch: Partial<RequirementDraft>) => void
  onClear: () => void
  onClose: () => void
  onSubmit: () => Promise<void>
}>) {
  const editing = mode === 'edit'
  const draftHealth: Array<{ label: string; tone: 'ready' | 'blocked' | 'validating' }> = [
    { label: draft.title.trim() ? '标题已填写' : '缺少标题', tone: draft.title.trim() ? 'ready' : 'blocked' },
    {
      label: draft.description_markdown.trim() ? '描述已填写' : '缺少描述',
      tone: draft.description_markdown.trim() ? 'ready' : 'blocked',
    },
    {
      label: draft.acceptance_criteria_markdown.trim() ? '验收已填写' : '待补充验收',
      tone: draft.acceptance_criteria_markdown.trim() ? 'ready' : 'validating',
    },
  ]

  return (
    <OverlayDrawer
      open={open}
      eyebrow={editing ? `Requirement #${selected?.id ?? '-'}` : 'Requirement Intake'}
      title={editing ? '编辑需求' : '新建需求'}
      description={editing ? '仅编辑 requirement 面字段，执行与发布动作仍留在各自独立页面。' : '新建需求通过右侧工作台完成，列表页只负责浏览、筛选和选择。'}
      onClose={onClose}
      actions={
        <button
          type="button"
          className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm text-[color:var(--ops-text-body)]"
          onClick={onClear}
        >
          清空
        </button>
      }
    >
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr),280px]">
        <section className="space-y-5">
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <FieldLabel>标题</FieldLabel>
              <input
                className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                placeholder="用结果描述 requirement"
                value={draft.title}
                onChange={(event) => onChange({ title: event.target.value })}
              />
            </div>
            <div>
              <FieldLabel>目标项目</FieldLabel>
              <input
                className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                placeholder="目标项目路径，可换行写多个"
                value={draft.target_project_path}
                onChange={(event) => onChange({ target_project_path: event.target.value })}
              />
            </div>
          </div>

          <div>
            <FieldLabel>需求描述</FieldLabel>
            <textarea
              className="mt-2 min-h-[220px] w-full rounded-3xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
              placeholder="为什么做、要做到什么、主要约束是什么"
              value={draft.description_markdown}
              onChange={(event) => onChange({ description_markdown: event.target.value })}
            />
          </div>

          <div>
            <FieldLabel>验收标准</FieldLabel>
            <textarea
              className="mt-2 min-h-[150px] w-full rounded-3xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
              placeholder="如何判断 validate 成功"
              value={draft.acceptance_criteria_markdown}
              onChange={(event) => onChange({ acceptance_criteria_markdown: event.target.value })}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-[220px,1fr]">
            <div>
              <FieldLabel>优先级</FieldLabel>
              <select
                className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                value={draft.priority}
                onChange={(event) => onChange({ priority: event.target.value })}
              >
                <option value="low">low</option>
                <option value="normal">normal</option>
                <option value="high">high</option>
              </select>
            </div>
            <div className="flex items-end justify-end gap-3">
              <button
                type="button"
                className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm text-[color:var(--ops-text-body)]"
                onClick={onClose}
              >
                取消
              </button>
              <button
                type="button"
                className="rounded-2xl bg-[color:var(--ops-state-running-text)] px-5 py-3 text-sm font-medium text-white disabled:opacity-60"
                disabled={saving || !draft.title.trim() || !draft.description_markdown.trim()}
                onClick={() => {
                  onSubmit().catch(() => {})
                }}
              >
                {saving ? (editing ? '保存中…' : '创建中…') : editing ? '保存更新' : '创建需求'}
              </button>
            </div>
          </div>
        </section>

        <aside className="space-y-4 rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-5">
          <div>
            <FieldLabel>Requirement Health</FieldLabel>
            <div className="mt-3 flex flex-wrap gap-2">
              {draftHealth.map((item) => (
                <StateBadge key={item.label} tone={item.tone}>
                  {item.label}
                </StateBadge>
              ))}
            </div>
          </div>
          <div>
            <FieldLabel>下一步</FieldLabel>
            <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">
              {editing
                ? '保存后会刷新列表和右侧摘要。真正执行仍从 submit 进入 execution bridge。'
                : '创建后先进入 requirement 队列，再由 submit 桥接到 execution。'}
            </div>
          </div>
          {editing && selected ? (
            <div>
              <FieldLabel>当前治理状态</FieldLabel>
              <div className="mt-3 space-y-2 text-sm text-[color:var(--ops-text-muted)]">
                <div>状态：{STATUS_LABEL[selected.status] || selected.status}</div>
                <div>审批：{selected.approval_required ? selected.approval_status : 'waived'}</div>
                <div>执行：{selected.latest_execution_run_id ?? '-'}</div>
              </div>
            </div>
          ) : null}
        </aside>
      </div>
    </OverlayDrawer>
  )
}

export default function RequirementPool() {
  const navigate = useNavigate()
  const [requirements, setRequirements] = useState<AgentRequirement[]>([])
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [submittingId, setSubmittingId] = useState<number | null>(null)
  const [selectedRequirementId, setSelectedRequirementId] = useState<number | null>(null)
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('closed')
  const [draft, setDraft] = useState<RequirementDraft>({ ...EMPTY_DRAFT })

  const load = async (preferredId?: number | null) => {
    setLoading(true)
    try {
      const data = await api.getRequirements(status || undefined, undefined, search || undefined)
      setRequirements(data)
      const nextId =
        preferredId && data.some((item) => item.id === preferredId)
          ? preferredId
          : selectedRequirementId && data.some((item) => item.id === selectedRequirementId)
            ? selectedRequirementId
            : data[0]?.id ?? null
      setSelectedRequirementId(nextId)
      return data
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

  useEffect(() => {
    if (selectedRequirementId && filtered.some((item) => item.id === selectedRequirementId)) return
    setSelectedRequirementId(filtered[0]?.id ?? null)
  }, [filtered, selectedRequirementId])

  const selectedRequirement = filtered.find((item) => item.id === selectedRequirementId) ?? null

  const openCreateDrawer = () => {
    setDraft({ ...EMPTY_DRAFT })
    setDrawerMode('create')
  }

  const openEditDrawer = (requirement: AgentRequirement) => {
    setSelectedRequirementId(requirement.id)
    setDraft(buildDraft(requirement))
    setDrawerMode('edit')
  }

  const closeDrawer = () => {
    setDrawerMode('closed')
    setDraft({ ...EMPTY_DRAFT })
  }

  const handleDrawerSubmit = async () => {
    setSaving(true)
    try {
      if (drawerMode === 'create') {
        const detail = await api.createRequirement(draft)
        await load(detail.requirement.id)
      } else if (drawerMode === 'edit' && selectedRequirement) {
        const detail = await api.updateRequirement(selectedRequirement.id, draft)
        await load(detail.requirement.id)
      }
      closeDrawer()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-[var(--ops-section-gap)]" data-testid="agent-first-requirements-page">
      <SectionFrame
        eyebrow="Requirement Workspace"
        title="需求面"
        description="需求面只负责浏览、筛选和治理摘要；新建与编辑通过右侧工作台进行。"
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
              onClick={() => load(selectedRequirementId).catch(() => {})}
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
            <div className="mt-2">列表页先看队列与治理摘要，create / edit 通过右侧 Drawer 完成。</div>
          </div>
        </div>
      </SectionFrame>

      <SectionFrame eyebrow="Queue" title="需求列表" description={loading ? '正在拉取 requirement…' : `当前共 ${filtered.length} 条 requirement。`}>
        <WorkbenchToolbar>
          <div className="text-sm text-[color:var(--ops-text-muted)]">主焦点是 requirement queue 与选中摘要，不在列表页常驻铺开 intake 表单。</div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="rounded-2xl bg-[color:var(--ops-state-running-text)] px-4 py-2.5 text-sm font-medium text-white"
              onClick={openCreateDrawer}
            >
              新建需求
            </button>
            <button
              type="button"
              className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm text-[color:var(--ops-text-body)] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!selectedRequirement}
              onClick={() => {
                if (selectedRequirement) openEditDrawer(selectedRequirement)
              }}
            >
              编辑需求
            </button>
            <button
              type="button"
              className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm text-[color:var(--ops-text-body)]"
              onClick={() => load(selectedRequirementId).catch(() => {})}
            >
              刷新队列
            </button>
          </div>
        </WorkbenchToolbar>

        <div className="mt-6 grid gap-[var(--ops-section-gap)] xl:grid-cols-[minmax(0,1.7fr),minmax(300px,var(--ops-inspector-width))]">
          <div className="space-y-4">
            {filtered.map((item) => {
              const selected = item.id === selectedRequirementId
              return (
                <article
                  key={item.id}
                  className={[
                    'rounded-[var(--ops-radius-panel)] border px-5 py-5 transition',
                    selected
                      ? 'border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-workspace-bg)] shadow-[0_10px_30px_rgba(15,23,42,0.08)]'
                      : 'border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] hover:border-[color:var(--ops-stroke-strong)]',
                  ].join(' ')}
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <button type="button" className="min-w-0 text-left" onClick={() => setSelectedRequirementId(item.id)}>
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="text-lg font-semibold text-[color:var(--ops-text-title)]">{item.title}</h4>
                        <StateBadge tone={statusTone(item.status)}>{STATUS_LABEL[item.status] || item.status}</StateBadge>
                        <StateBadge tone="muted">{item.priority}</StateBadge>
                      </div>
                      <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)] line-clamp-3">{item.description_markdown}</p>
                    </button>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm"
                        onClick={() => openEditDrawer(item)}
                      >
                        编辑
                      </button>
                      <button type="button" className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${item.id}`)}>
                        查看需求
                      </button>
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-2">
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
                          await load(item.id)
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
                </article>
              )
            })}
            {!loading && filtered.length === 0 && (
              <EmptyPane>
                当前没有符合条件的 requirement。
                <div className="mt-4">
                  <button type="button" className="rounded-2xl bg-[color:var(--ops-state-running-text)] px-4 py-2 text-sm font-medium text-white" onClick={openCreateDrawer}>
                    新建需求
                  </button>
                </div>
              </EmptyPane>
            )}
          </div>

          <SelectionInspector
            eyebrow={selectedRequirement ? `Requirement #${selectedRequirement.id}` : 'Selection'}
            title={selectedRequirement ? '治理摘要' : '选择需求'}
            empty="先在左侧队列选择一条 requirement，再查看 health、审批和下一跳。"
            active={
              selectedRequirement ? (
                <>
                  <div>
                    <FieldLabel>描述摘要</FieldLabel>
                    <div className="mt-2 leading-6 text-[color:var(--ops-text-muted)]">{selectedRequirement.description_markdown}</div>
                  </div>
                  <div>
                    <FieldLabel>目标项目</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{selectedRequirement.target_projects.join(', ') || '-'}</div>
                  </div>
                  <div>
                    <FieldLabel>审批</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{selectedRequirement.approval_required ? selectedRequirement.approval_status : 'waived'}</div>
                  </div>
                  <div>
                    <FieldLabel>执行 / 发布</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">
                      execution {selectedRequirement.active_execution_run_id ?? selectedRequirement.latest_execution_run_id ?? '-'} · release {selectedRequirement.latest_release_status ?? '-'}
                    </div>
                  </div>
                  <div>
                    <FieldLabel>更新时间</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{formatTime(selectedRequirement.updated_at)}</div>
                  </div>
                  <div>
                    <FieldLabel>下一步</FieldLabel>
                    <div className="mt-2 leading-6 text-[color:var(--ops-text-muted)]">
                      {selectedRequirement.status === 'draft' || selectedRequirement.status === 'needs_revision'
                        ? '先确认 why / what / acceptance，再 submit 进入 execution bridge。'
                        : selectedRequirement.status === 'blocked'
                          ? '当前停在治理门口，优先查看审批原因或缺失输入。'
                          : 'Requirement 面只负责定义和治理，执行与发布动作分别跳转到独立页面。'}
                    </div>
                  </div>
                </>
              ) : undefined
            }
          />
        </div>
      </SectionFrame>

      <RequirementDrawer
        mode={drawerMode}
        open={drawerMode !== 'closed'}
        draft={draft}
        saving={saving}
        selected={selectedRequirement}
        onChange={(patch) => setDraft((current) => ({ ...current, ...patch }))}
        onClear={() => setDraft(drawerMode === 'edit' ? buildDraft(selectedRequirement) : { ...EMPTY_DRAFT })}
        onClose={closeDrawer}
        onSubmit={handleDrawerSubmit}
      />
    </div>
  )
}
