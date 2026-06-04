import { EmptyPane, StateBadge } from '../components/workbench'
import type { GrowthAIVisibilityCheck, GrowthAIVisibilityComparison, GrowthAIVisibilityOptimizationPlan } from '../api'

function tone(value: boolean) {
  return value ? 'delivered' : 'muted'
}

export function GrowthAIVisibilityPanel({
  items,
  comparisons,
  plan,
  onCreate,
}: Readonly<{
  items: GrowthAIVisibilityCheck[]
  comparisons: GrowthAIVisibilityComparison[]
  plan: GrowthAIVisibilityOptimizationPlan | null
  onCreate: () => void
}>) {
  return (
    <section
      className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5"
      data-testid="ai-visibility-optimization-panel"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xl font-semibold text-[color:var(--ops-text-title)]">AI Visibility Optimization</h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
            {plan?.objective || 'Answer-engine citation checks and feed experiments for Synapse discovery.'}
          </p>
        </div>
        <button className="rounded-xl border border-cyan-300/35 px-4 py-2.5 text-sm text-cyan-100" onClick={onCreate}>
          新增 Check
        </button>
      </div>

      {plan && (
        <>
          <div className="mt-5 grid gap-3 lg:grid-cols-3">
            <Info label="Canonical" value={plan.canonical_domain} />
            <Info label="Docs category" value={plan.product_docs.docs_category} />
            <Info label="Workflow" value={plan.growing_workflows[1] || plan.growing_workflows[0] || '-'} />
          </div>
          <ComparisonList items={comparisons} />
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <PlanList title="P0 feed experiments" items={plan.feed_experiments.map((item) => item.feed_key)} />
            <PlanList title="Baseline queries" items={plan.baseline_queries.slice(0, 5).map((item) => item.query)} />
          </div>
        </>
      )}

      <div className="mt-5 overflow-hidden rounded-2xl border border-[color:var(--ops-stroke-soft)]">
        {items.length ? (
          items.map((item) => (
            <div key={item.id} className="flex items-center justify-between gap-4 border-b border-[color:var(--ops-stroke-soft)] px-5 py-4 last:border-b-0">
              <span>
                <strong>{item.query}</strong>
                <span className="mt-1 block text-sm text-[color:var(--ops-text-muted)]">
                  {item.platform} · cited {item.synapse_cited ? 'yes' : 'no'} · {item.next_action || '-'}
                </span>
              </span>
              <StateBadge tone={tone(item.synapse_cited)}>{item.synapse_cited ? 'cited' : 'not_cited'}</StateBadge>
            </div>
          ))
        ) : (
          <div className="p-6">
            <EmptyPane>No records yet.</EmptyPane>
          </div>
        )}
      </div>
    </section>
  )
}

function ComparisonList({ items }: Readonly<{ items: GrowthAIVisibilityComparison[] }>) {
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Search comparison</div>
        <StateBadge tone={items.length ? 'running' : 'muted'}>{items.length ? `${items.length} runs` : 'no_runs'}</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {items.length ? (
          items.slice(0, 2).map((item) => (
            <ComparisonCard key={`${item.feed_key}:${item.run_group}`} item={item} />
          ))
        ) : (
          <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] p-4 text-sm text-[color:var(--ops-text-muted)]">
            Record GPT, Claude, and Grok checks with the same feed key and run group to compare impact.
          </div>
        )}
      </div>
    </div>
  )
}

function ComparisonCard({ item }: Readonly<{ item: GrowthAIVisibilityComparison }>) {
  const externalPlatforms = item.external_platforms || []
  const externalChecks = item.external_checks_count ?? item.total_checks
  const localValidationCount = item.local_validation_count ?? 0

  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
      <div className="font-semibold text-[color:var(--ops-text-title)]">{item.feed_key}</div>
      <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">
        {item.run_group} · external {externalPlatforms.join(', ') || '-'} · cited {item.cited_count}/{externalChecks} · mentioned {item.mentioned_count}/{externalChecks}
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        Local feed evidence: {localValidationCount} · all records: {item.total_checks}
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        Missing: {item.missing_platforms.join(', ') || '-'}
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        Next: {item.next_actions[0] || '-'}
      </div>
    </div>
  )
}

function PlanList({ title, items }: Readonly<{ title: string; items: string[] }>) {
  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{title}</div>
      <div className="mt-3 space-y-2">
        {items.map((item) => (
          <div key={item} className="text-sm text-[color:var(--ops-text-title)]">
            {item}
          </div>
        ))}
      </div>
    </div>
  )
}

function Info({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-title)]">{value}</div>
    </div>
  )
}
