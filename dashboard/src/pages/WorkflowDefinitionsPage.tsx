import { useEffect, useMemo, useState } from 'react'
import { api, DeclarativeWorkflowDefinition } from '../api'
import { ActionButton, CockpitPanel, EmptyCockpitState, MetricTile } from '../components/controlPlane'
import { StateBadge } from '../components/workbench'

export default function WorkflowDefinitionsPage() {
  const [definitions, setDefinitions] = useState<DeclarativeWorkflowDefinition[]>([])
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    api.getWorkflowDefinitions()
      .then((data) => {
        setDefinitions(data)
        setSelectedKey((current) => current || data[0]?.workflow_key || null)
      })
      .catch((err) => setError(err.message || String(err)))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const selected = useMemo(() => definitions.find((item) => item.workflow_key === selectedKey) || definitions[0] || null, [definitions, selectedKey])
  const agentStates = selected?.states.filter((state) => state.atom_type === 'agent') || []
  const deterministicStates = selected?.states.filter((state) => state.atom_type === 'deterministic') || []

  return (
    <div className="space-y-6">
      <CockpitPanel
        eyebrow="Workflow Factory"
        title="状态机定义"
        description="v1 只读展示 workflow 轨道、状态、atom 和风险策略。不要在 UI 里直接编辑 YAML，直到 spec versioning 与校验发布链路稳定。"
        actions={<ActionButton onClick={load}>刷新</ActionButton>}
      >
        <div className="grid gap-4 md:grid-cols-4">
          <MetricTile label="Definitions" value={definitions.length} detail="已注册 declarative workflows" tone="info" />
          <MetricTile label="Agent States" value={agentStates.length} detail="当前选中 workflow 的 agent atoms" tone="warning" />
          <MetricTile label="Deterministic States" value={deterministicStates.length} detail="当前选中 workflow 的 deterministic atoms" tone="success" />
          <MetricTile label="Edit Mode" value="Read-only" detail="Factory 编辑能力留给 v2" tone="muted" />
        </div>
      </CockpitPanel>

      {error ? <div className="rounded-2xl border border-rose-400/25 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">{error}</div> : null}

      {loading ? (
        <div className="text-sm text-[color:var(--ops-text-muted)]">Loading workflow definitions...</div>
      ) : definitions.length ? (
        <div className="grid gap-5 xl:grid-cols-[380px_1fr]">
          <CockpitPanel eyebrow="Registry" title="Workflow Specs">
            <div className="space-y-2">
              {definitions.map((definition) => (
                <button
                  key={definition.workflow_key}
                  type="button"
                  className={[
                    'w-full rounded-2xl border px-4 py-4 text-left transition',
                    selected?.workflow_key === definition.workflow_key
                      ? 'border-cyan-300/35 bg-cyan-300/10'
                      : 'border-white/8 bg-white/[0.03] hover:border-white/18 hover:bg-white/[0.055]',
                  ].join(' ')}
                  onClick={() => setSelectedKey(definition.workflow_key)}
                >
                  <div className="font-mono text-sm font-semibold text-[color:var(--ops-text-title)]">{definition.workflow_key}</div>
                  <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">{definition.description || definition.title}</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <StateBadge tone={definition.status === 'active' ? 'ready' : 'muted'}>{definition.status}</StateBadge>
                    <StateBadge tone="muted">{definition.states.length} states</StateBadge>
                  </div>
                </button>
              ))}
            </div>
          </CockpitPanel>

          {selected ? (
            <CockpitPanel
              eyebrow="State Machine"
              title={selected.workflow_key}
              description={selected.description || selected.title}
              actions={<ActionButton onClick={() => navigator.clipboard?.writeText(JSON.stringify(selected.spec, null, 2))}>Copy Spec</ActionButton>}
            >
              <div className="grid gap-4 md:grid-cols-3">
                <MetricTile label="Initial State" value={<span className="text-xl">{selected.initial_state}</span>} detail="Runner 进入 workflow 的第一站" tone="info" />
                <MetricTile label="Limits" value={<span className="text-xl">{Object.keys(selected.limits || {}).length}</span>} detail="Retry / budget / loop guard" tone="warning" />
                <MetricTile label="Risk Policy" value={<span className="text-xl">{Object.keys(selected.risk_policy || {}).length}</span>} detail="Human gate and safety policy" tone="danger" />
              </div>

              <div className="mt-6 grid gap-3">
                {selected.states.map((state) => (
                  <div key={state.key} className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-mono text-sm font-semibold text-cyan-100">{state.key}</div>
                        <div className="mt-2 text-xs text-[color:var(--ops-text-muted)]">
                          {state.atom_type} · {state.atom_key || 'terminal'} · output {state.output_key || '-'}
                        </div>
                      </div>
                      <StateBadge tone={state.terminal ? 'delivered' : state.atom_type === 'agent' ? 'running' : 'ready'}>
                        {state.terminal ? 'terminal' : state.atom_type}
                      </StateBadge>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-[color:var(--ops-text-muted)]">
                      {state.transitions.map((transition) => (
                        <span key={`${state.key}-${transition.goto}-${transition.condition}`} className="rounded-full border border-white/8 bg-white/[0.035] px-3 py-1">
                          {transition.condition || 'always'} {'->'} {transition.goto}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </CockpitPanel>
          ) : null}
        </div>
      ) : (
        <EmptyCockpitState title="No workflow definitions" description="当前后端没有返回 workflow definitions。请检查 declarative workflow registry 是否初始化。" />
      )}
    </div>
  )
}
