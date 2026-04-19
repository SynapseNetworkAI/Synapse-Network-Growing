import { useEffect, useMemo, useState } from 'react'
import { api, DeclarativeWorkflowDefinition } from '../api'
import { CockpitPanel, EmptyCockpitState, MetricTile } from '../components/controlPlane'
import { StateBadge } from '../components/workbench'

type AtomEntry = {
  atom_key: string
  atom_type: string
  states: string[]
  workflows: string[]
  terminal: boolean
}

export default function AtomRegistryPage() {
  const [definitions, setDefinitions] = useState<DeclarativeWorkflowDefinition[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'agent' | 'deterministic' | 'terminal'>('all')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getWorkflowDefinitions()
      .then(setDefinitions)
      .catch((err) => setError(err.message || String(err)))
      .finally(() => setLoading(false))
  }, [])

  const atoms = useMemo(() => {
    const map = new Map<string, AtomEntry>()
    definitions.forEach((definition) => {
      definition.states.forEach((state) => {
        const key = state.atom_key || `terminal:${state.key}`
        const existing = map.get(key) || {
          atom_key: key,
          atom_type: state.terminal ? 'terminal' : state.atom_type,
          states: [],
          workflows: [],
          terminal: state.terminal,
        }
        existing.states.push(state.key)
        if (!existing.workflows.includes(definition.workflow_key)) existing.workflows.push(definition.workflow_key)
        map.set(key, existing)
      })
    })
    return Array.from(map.values()).sort((a, b) => a.atom_key.localeCompare(b.atom_key))
  }, [definitions])

  const visibleAtoms = atoms.filter((atom) => filter === 'all' || atom.atom_type === filter)

  return (
    <div className="space-y-6">
      <CockpitPanel
        eyebrow="Atom Registry"
        title="原子能力库"
        description="Atom 是 Agent-First 工厂的武器库。这里从 workflow definitions 反推出当前已注册的 agent / deterministic / terminal 能力，v1 只读。"
      >
        <div className="grid gap-4 md:grid-cols-4">
          <MetricTile label="Total Atoms" value={atoms.length} detail="从所有 workflow states 聚合" tone="info" />
          <MetricTile label="Agent Atoms" value={atoms.filter((atom) => atom.atom_type === 'agent').length} detail="LLM 认知与生成节点" tone="warning" />
          <MetricTile label="Deterministic" value={atoms.filter((atom) => atom.atom_type === 'deterministic').length} detail="可信代码执行节点" tone="success" />
          <MetricTile label="Terminal" value={atoms.filter((atom) => atom.atom_type === 'terminal').length} detail="状态机终态" tone="muted" />
        </div>
      </CockpitPanel>

      {error ? <div className="rounded-2xl border border-rose-400/25 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">{error}</div> : null}

      <CockpitPanel
        eyebrow="Registry View"
        title="Atoms"
        actions={
          <div className="flex flex-wrap gap-2">
            {(['all', 'agent', 'deterministic', 'terminal'] as const).map((key) => (
              <button
                key={key}
                type="button"
                className={[
                  'rounded-xl border px-3 py-2 text-sm transition',
                  filter === key ? 'border-cyan-300/35 bg-cyan-300/15 text-cyan-100' : 'border-white/10 bg-white/[0.035] text-[color:var(--ops-text-muted)] hover:bg-white/[0.07]',
                ].join(' ')}
                onClick={() => setFilter(key)}
              >
                {key}
              </button>
            ))}
          </div>
        }
      >
        {loading ? (
          <div className="text-sm text-[color:var(--ops-text-muted)]">Loading atom registry...</div>
        ) : visibleAtoms.length ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {visibleAtoms.map((atom) => (
              <div key={atom.atom_key} className="rounded-3xl border border-white/8 bg-white/[0.03] px-5 py-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-mono text-sm font-semibold text-[color:var(--ops-text-title)]">{atom.atom_key}</div>
                    <div className="mt-2 text-xs text-[color:var(--ops-text-muted)]">{atom.workflows.length} workflow(s) · {atom.states.length} state binding(s)</div>
                  </div>
                  <StateBadge tone={atom.atom_type === 'agent' ? 'running' : atom.atom_type === 'deterministic' ? 'ready' : 'muted'}>
                    {atom.atom_type}
                  </StateBadge>
                </div>
                <div className="mt-4">
                  <div className="machine-label text-[color:var(--ops-text-caption)]">Workflows</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {atom.workflows.map((workflow) => (
                      <span key={workflow} className="rounded-full border border-white/8 bg-white/[0.04] px-3 py-1 font-mono text-xs text-cyan-100">
                        {workflow}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="mt-4">
                  <div className="machine-label text-[color:var(--ops-text-caption)]">State Bindings</div>
                  <div className="mt-2 text-xs leading-6 text-[color:var(--ops-text-muted)]">{atom.states.join(', ')}</div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyCockpitState title="No atoms found" description="没有可展示的 atom。请确认 workflow definitions API 已返回 states。" />
        )}
      </CockpitPanel>
    </div>
  )
}
