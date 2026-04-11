import { useEffect, useState } from 'react'
import { api, ProjectOnboarding, ProjectPolicy } from '../api'

function parseLines(value: string) {
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

const CAPABILITY_OPTIONS = [
  { key: 'shell_access', label: '允许 shell / terminal' },
  { key: 'git_read', label: '允许 git read' },
  { key: 'git_write', label: '允许 git write' },
  { key: 'git_push', label: '允许 git push' },
  { key: 'network_access', label: '允许 network access' },
  { key: 'publish', label: '允许 publish' },
] as const

const INTERRUPT_OPTION_GROUPS = [
  {
    key: 'operator_confirmation_actions',
    title: '需人工确认的动作',
    options: ['shell_access', 'git_write', 'git_push', 'network_access', 'publish'],
  },
  {
    key: 'auto_pause_on_events',
    title: '自动暂停事件',
    options: ['capability_denied', 'policy_violation', 'missing_required_checks', 'session_resume_failure', 'operator_confirmation_required'],
  },
  {
    key: 'auto_abort_on_events',
    title: '自动终止事件',
    options: ['forbidden_write', 'publish_without_gate'],
  },
] as const

export default function ProjectPolicies() {
  const [policies, setPolicies] = useState<ProjectPolicy[]>([])
  const [onboardings, setOnboardings] = useState<ProjectOnboarding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [onboardingSaving, setOnboardingSaving] = useState(false)
  const [drafts, setDrafts] = useState<Record<number, {
    display_name: string
    root_path: string
    status: string
    release_mode: string
    requires_manual_approval: boolean
    autonomy_mode: string
    allow_rebalance: boolean
    allow_preemption: boolean
    capability_matrix: {
      shell_access: boolean
      git_read: boolean
      git_write: boolean
      git_push: boolean
      network_access: boolean
      publish: boolean
    }
    interrupt_policy: {
      operator_confirmation_actions: string[]
      auto_pause_on_events: string[]
      auto_abort_on_events: string[]
    }
    scheduler_weight: string
    max_parallel_requirements: string
    portfolio_budget_points: string
    allowed_write_globs: string
    forbidden_globs: string
    required_checks: string
    notes: string
  }>>({})
  const [onboardingDraft, setOnboardingDraft] = useState({
    project_key: '',
    display_name: '',
    root_path: '',
    docs_entrypoints: '',
    validation_commands: '',
    agents_memory_namespace: '',
    release_mode: 'manual',
    requires_manual_approval: true,
    allowed_write_globs: '**',
    forbidden_globs: '.git/**\nnode_modules/**\n.venv/**',
    notes: '',
  })

  const loadPolicies = async () => {
    setLoading(true)
    setError(null)
    try {
      const [policyData, onboardingData] = await Promise.all([
        api.getProjectPolicies(),
        api.getProjectOnboardings(),
      ])
      setPolicies(policyData)
      setOnboardings(onboardingData)
      setDrafts(
        Object.fromEntries(
          policyData.map((policy) => [
            policy.id,
            {
              display_name: policy.display_name,
              root_path: policy.root_path,
              status: policy.status,
              release_mode: policy.release_mode,
              requires_manual_approval: policy.requires_manual_approval,
              autonomy_mode: policy.autonomy_mode,
              allow_rebalance: policy.allow_rebalance,
              allow_preemption: policy.allow_preemption,
              capability_matrix: policy.capability_matrix,
              interrupt_policy: policy.interrupt_policy,
              scheduler_weight: String(policy.scheduler_weight ?? 1),
              max_parallel_requirements: String(policy.max_parallel_requirements ?? 1),
              portfolio_budget_points: String(policy.portfolio_budget_points ?? 100),
              allowed_write_globs: policy.allowed_write_globs.join('\n'),
              forbidden_globs: policy.forbidden_globs.join('\n'),
              required_checks: policy.required_checks.join('\n'),
              notes: policy.notes || '',
            },
          ]),
        ),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载项目策略失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPolicies().catch(() => {})
  }, [])

  const toggleInterruptValue = (
    policyId: number,
    groupKey: 'operator_confirmation_actions' | 'auto_pause_on_events' | 'auto_abort_on_events',
    value: string,
  ) => {
    setDrafts((prev) => {
      const draft = prev[policyId]
      if (!draft) return prev
      const current = draft.interrupt_policy[groupKey]
      const nextValues = current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value]
      return {
        ...prev,
        [policyId]: {
          ...draft,
          interrupt_policy: {
            ...draft.interrupt_policy,
            [groupKey]: nextValues,
          },
        },
      }
    })
  }

  if (loading) {
    return <div data-testid="project-policies-loading" className="rounded-xl border bg-white p-6 text-sm text-gray-500">正在加载项目策略…</div>
  }

  if (error) {
    return <div data-testid="project-policies-error" className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">{error}</div>
  }

  return (
    <div data-testid="project-policies-page" className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">项目策略</h2>
          <p className="text-sm text-gray-500">先 onboarding 新项目，再为每个受管项目定义可写范围、禁止范围、必跑检查、能力矩阵和发布模式。</p>
          <p className="text-xs text-gray-400">P2 调度器会直接读取每个项目的 `scheduler weight` 和 `max parallel requirements` 进行跨项目编排。</p>
        </div>
        <button
          className="rounded-lg border px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
          onClick={() => loadPolicies().catch(() => {})}
        >
          刷新
        </button>
      </div>

      <section className="rounded-xl border bg-white p-5 shadow-sm" data-testid="project-onboarding-panel">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-gray-900">项目 Onboarding Pack</h3>
          <p className="text-sm text-gray-500">提交项目 manifest，自动生成 policy，并产出 readiness checklist。</p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-gray-500">项目 Key</span>
            <input
              className="w-full rounded border px-3 py-2"
              value={onboardingDraft.project_key}
              onChange={(e) => setOnboardingDraft((prev) => ({ ...prev, project_key: e.target.value }))}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-gray-500">显示名称</span>
            <input
              className="w-full rounded border px-3 py-2"
              value={onboardingDraft.display_name}
              onChange={(e) => setOnboardingDraft((prev) => ({ ...prev, display_name: e.target.value }))}
            />
          </label>
          <label className="space-y-1 text-sm md:col-span-2">
            <span className="text-gray-500">项目根路径</span>
            <input
              className="w-full rounded border px-3 py-2 font-mono text-xs"
              value={onboardingDraft.root_path}
              onChange={(e) => setOnboardingDraft((prev) => ({ ...prev, root_path: e.target.value }))}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-gray-500">Docs Entrypoints</span>
            <textarea
              className="min-h-[100px] w-full rounded border px-3 py-2 font-mono text-xs"
              value={onboardingDraft.docs_entrypoints}
              onChange={(e) => setOnboardingDraft((prev) => ({ ...prev, docs_entrypoints: e.target.value }))}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-gray-500">Validation Commands</span>
            <textarea
              className="min-h-[100px] w-full rounded border px-3 py-2 font-mono text-xs"
              value={onboardingDraft.validation_commands}
              onChange={(e) => setOnboardingDraft((prev) => ({ ...prev, validation_commands: e.target.value }))}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-gray-500">Agents-Memory Namespace</span>
            <input
              className="w-full rounded border px-3 py-2"
              value={onboardingDraft.agents_memory_namespace}
              onChange={(e) => setOnboardingDraft((prev) => ({ ...prev, agents_memory_namespace: e.target.value }))}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-gray-500">发布模式</span>
            <select
              className="w-full rounded border px-3 py-2"
              value={onboardingDraft.release_mode}
              onChange={(e) => setOnboardingDraft((prev) => ({ ...prev, release_mode: e.target.value }))}
            >
              <option value="disabled">disabled</option>
              <option value="manual">manual</option>
              <option value="auto">auto</option>
            </select>
          </label>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-gray-500">允许写入 globs</span>
            <textarea
              className="min-h-[100px] w-full rounded border px-3 py-2 font-mono text-xs"
              value={onboardingDraft.allowed_write_globs}
              onChange={(e) => setOnboardingDraft((prev) => ({ ...prev, allowed_write_globs: e.target.value }))}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-gray-500">禁止写入 globs</span>
            <textarea
              className="min-h-[100px] w-full rounded border px-3 py-2 font-mono text-xs"
              value={onboardingDraft.forbidden_globs}
              onChange={(e) => setOnboardingDraft((prev) => ({ ...prev, forbidden_globs: e.target.value }))}
            />
          </label>
        </div>

        <label className="mt-4 flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={onboardingDraft.requires_manual_approval}
            onChange={(e) => setOnboardingDraft((prev) => ({ ...prev, requires_manual_approval: e.target.checked }))}
          />
          生成的项目策略默认需要人工审批
        </label>

        <label className="mt-4 block space-y-1 text-sm">
          <span className="text-gray-500">备注</span>
          <textarea
            className="min-h-[80px] w-full rounded border px-3 py-2 text-sm"
            value={onboardingDraft.notes}
            onChange={(e) => setOnboardingDraft((prev) => ({ ...prev, notes: e.target.value }))}
          />
        </label>

        <div className="mt-4 flex justify-end">
          <button
            data-testid="project-onboarding-submit"
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            disabled={onboardingSaving}
            onClick={async () => {
              setOnboardingSaving(true)
              try {
                await api.createProjectOnboarding({
                  project_key: onboardingDraft.project_key,
                  display_name: onboardingDraft.display_name,
                  root_path: onboardingDraft.root_path,
                  docs_entrypoints: parseLines(onboardingDraft.docs_entrypoints),
                  validation_commands: parseLines(onboardingDraft.validation_commands),
                  agents_memory_namespace: onboardingDraft.agents_memory_namespace || null,
                  auto_create_policy: true,
                  allowed_write_globs: parseLines(onboardingDraft.allowed_write_globs),
                  forbidden_globs: parseLines(onboardingDraft.forbidden_globs),
                  release_mode: onboardingDraft.release_mode,
                  requires_manual_approval: onboardingDraft.requires_manual_approval,
                  notes: onboardingDraft.notes || null,
                })
                await loadPolicies()
              } catch (err) {
                alert(err instanceof Error ? err.message : '项目 onboarding 失败')
              } finally {
                setOnboardingSaving(false)
              }
            }}
          >
            {onboardingSaving ? '评估中…' : 'Create Onboarding Pack'}
          </button>
        </div>
      </section>

      {onboardings.length > 0 && (
        <section className="space-y-4" data-testid="project-onboarding-results">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Project Readiness</h3>
            <p className="text-sm text-gray-500">最近的 onboarding 结果与缺口项。</p>
          </div>
          <div className="grid gap-4">
            {onboardings.map((onboarding) => (
              <div key={onboarding.id} className="rounded-xl border bg-white p-5 shadow-sm" data-testid={`project-onboarding-card-${onboarding.id}`}>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h4 className="text-base font-semibold text-gray-900">{onboarding.display_name}</h4>
                    <div className="font-mono text-xs text-gray-500">{onboarding.root_path}</div>
                  </div>
                  <div className="text-right text-xs text-gray-500">
                    <div>status: {onboarding.readiness_status}</div>
                    <div>score: {onboarding.readiness_score}</div>
                  </div>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {onboarding.readiness_items.map((item) => (
                    <div key={`${onboarding.id}-${item.key}`} className={`rounded-lg border p-3 text-xs ${item.status === 'ready' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
                      <div className="font-medium">{item.label}</div>
                      <div className="mt-1">{item.message}</div>
                    </div>
                  ))}
                </div>
                {onboarding.missing_items.length > 0 && (
                  <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                    缺口: {onboarding.missing_items.join(' / ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="grid gap-4">
        {policies.map((policy) => {
          const draft = drafts[policy.id]
          if (!draft) return null
          return (
            <div key={policy.id} data-testid={`project-policy-card-${policy.id}`} className="space-y-4 rounded-xl border bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">{policy.display_name}</h3>
                  <p className="font-mono text-xs text-gray-500">{policy.project_key}</p>
                </div>
                <div className="text-right text-xs text-gray-500">
                  <div>更新时间: {formatTime(policy.updated_at)}</div>
                  <div>发布模式: {policy.release_mode}</div>
                  <div>自治: {policy.autonomy_mode}</div>
                  <div>能力: shell {policy.capability_matrix.shell_access ? 'on' : 'off'} / git_write {policy.capability_matrix.git_write ? 'on' : 'off'} / push {policy.capability_matrix.git_push ? 'on' : 'off'} / publish {policy.capability_matrix.publish ? 'on' : 'off'}</div>
                  <div>调度: x{policy.scheduler_weight} / {policy.max_parallel_requirements} 槽位 / budget {policy.portfolio_budget_points}</div>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">显示名称</span>
                  <input
                    className="w-full rounded border px-3 py-2"
                    value={draft.display_name}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, display_name: e.target.value } }))}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">项目根路径</span>
                  <input
                    className="w-full rounded border px-3 py-2 font-mono text-xs"
                    value={draft.root_path}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, root_path: e.target.value } }))}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">状态</span>
                  <select
                    className="w-full rounded border px-3 py-2"
                    value={draft.status}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, status: e.target.value } }))}
                  >
                    <option value="active">active</option>
                    <option value="disabled">disabled</option>
                  </select>
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">发布模式</span>
                  <select
                    className="w-full rounded border px-3 py-2"
                    value={draft.release_mode}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, release_mode: e.target.value } }))}
                  >
                    <option value="disabled">disabled</option>
                    <option value="manual">manual</option>
                    <option value="auto">auto</option>
                  </select>
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">自治模式</span>
                  <select
                    aria-label="自治模式"
                    className="w-full rounded border px-3 py-2"
                    value={draft.autonomy_mode}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, autonomy_mode: e.target.value } }))}
                  >
                    <option value="observe">observe</option>
                    <option value="recommend">recommend</option>
                    <option value="execute_with_approval">execute_with_approval</option>
                    <option value="execute_autonomously">execute_autonomously</option>
                  </select>
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">调度权重</span>
                  <input
                    aria-label="调度权重"
                    className="w-full rounded border px-3 py-2"
                    type="number"
                    min="0.2"
                    max="3"
                    step="0.1"
                    value={draft.scheduler_weight}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, scheduler_weight: e.target.value } }))}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">项目并行槽位</span>
                  <input
                    aria-label="项目并行槽位"
                    className="w-full rounded border px-3 py-2"
                    type="number"
                    min="1"
                    max="5"
                    step="1"
                    value={draft.max_parallel_requirements}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, max_parallel_requirements: e.target.value } }))}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">项目预算</span>
                  <input
                    aria-label="项目预算"
                    className="w-full rounded border px-3 py-2"
                    type="number"
                    min="20"
                    max="300"
                    step="5"
                    value={draft.portfolio_budget_points}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, portfolio_budget_points: e.target.value } }))}
                  />
                </label>
              </div>

              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={draft.requires_manual_approval}
                  onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, requires_manual_approval: e.target.checked } }))}
                />
                需要人工审批
              </label>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={draft.allow_rebalance}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, allow_rebalance: e.target.checked } }))}
                  />
                  允许 scheduler 做 portfolio rebalance
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={draft.allow_preemption}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, allow_preemption: e.target.checked } }))}
                  />
                  允许本项目中的运行中 requirement 被 preempt
                </label>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">允许写入 globs</span>
                  <textarea
                    className="min-h-[120px] w-full rounded border px-3 py-2 font-mono text-xs"
                    value={draft.allowed_write_globs}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, allowed_write_globs: e.target.value } }))}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">禁止写入 globs</span>
                  <textarea
                    className="min-h-[120px] w-full rounded border px-3 py-2 font-mono text-xs"
                    value={draft.forbidden_globs}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, forbidden_globs: e.target.value } }))}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">必跑检查</span>
                  <textarea
                    className="min-h-[120px] w-full rounded border px-3 py-2 font-mono text-xs"
                    value={draft.required_checks}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, required_checks: e.target.value } }))}
                  />
                </label>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <div className="text-sm font-medium text-gray-700">Capability Matrix</div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {CAPABILITY_OPTIONS.map((option) => (
                      <label key={`${policy.id}-${option.key}`} className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm text-gray-700">
                        <input
                          type="checkbox"
                          checked={draft.capability_matrix[option.key]}
                          onChange={(e) => setDrafts((prev) => ({
                            ...prev,
                            [policy.id]: {
                              ...draft,
                              capability_matrix: {
                                ...draft.capability_matrix,
                                [option.key]: e.target.checked,
                              },
                            },
                          }))}
                        />
                        {option.label}
                      </label>
                    ))}
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="text-sm font-medium text-gray-700">Interrupt Policy</div>
                  {INTERRUPT_OPTION_GROUPS.map((group) => (
                    <div key={`${policy.id}-${group.key}`} className="rounded-lg border p-3">
                      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">{group.title}</div>
                      <div className="grid gap-2">
                        {group.options.map((option) => (
                          <label key={`${policy.id}-${group.key}-${option}`} className="flex items-center gap-2 text-sm text-gray-700">
                            <input
                              type="checkbox"
                              checked={draft.interrupt_policy[group.key].includes(option)}
                              onChange={() => toggleInterruptValue(policy.id, group.key, option)}
                            />
                            {option}
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <label className="space-y-1 text-sm">
                <span className="text-gray-500">备注</span>
                <textarea
                  className="min-h-[80px] w-full rounded border px-3 py-2 text-sm"
                  value={draft.notes}
                  onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, notes: e.target.value } }))}
                />
              </label>

              <div className="flex justify-end">
                <button
                  data-testid={`project-policy-save-${policy.id}`}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                  disabled={savingId === policy.id}
                  onClick={async () => {
                    setSavingId(policy.id)
                    try {
                      await api.updateProjectPolicy(policy.id, {
                        display_name: draft.display_name,
                        root_path: draft.root_path,
                        status: draft.status,
                        release_mode: draft.release_mode,
                        requires_manual_approval: draft.requires_manual_approval,
                        autonomy_mode: draft.autonomy_mode,
                        allow_rebalance: draft.allow_rebalance,
                        allow_preemption: draft.allow_preemption,
                        capability_matrix: draft.capability_matrix,
                        interrupt_policy: draft.interrupt_policy,
                        scheduler_weight: Number(draft.scheduler_weight || 1),
                        max_parallel_requirements: Math.max(1, Number(draft.max_parallel_requirements || 1)),
                        portfolio_budget_points: Math.max(20, Number(draft.portfolio_budget_points || 100)),
                        allowed_write_globs: parseLines(draft.allowed_write_globs),
                        forbidden_globs: parseLines(draft.forbidden_globs),
                        required_checks: parseLines(draft.required_checks),
                        notes: draft.notes || null,
                      })
                      await loadPolicies()
                    } catch (err) {
                      alert(err instanceof Error ? err.message : '保存项目策略失败')
                    } finally {
                      setSavingId(null)
                    }
                  }}
                >
                  {savingId === policy.id ? '保存中…' : '保存策略'}
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
