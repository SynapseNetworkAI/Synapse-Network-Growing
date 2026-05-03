export type WorkflowTab = 'overview' | 'timeline' | 'evidence' | 'gates' | 'debug'

export const WORKFLOW_TABS: Array<{ key: WorkflowTab; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'timeline', label: 'Timeline' },
  { key: 'evidence', label: 'Evidence' },
  { key: 'gates', label: 'Gates & Delivery' },
  { key: 'debug', label: 'Debug' },
]

export function WorkflowRunTabs({ activeTab, onChange }: Readonly<{ activeTab: WorkflowTab; onChange: (tab: WorkflowTab) => void }>) {
  return (
    <div className="flex flex-wrap gap-2 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-2" data-testid="workflow-run-tabs">
      {WORKFLOW_TABS.map((tab) => (
        <button
          key={tab.key}
          type="button"
          className={[
            'rounded-xl px-4 py-2 text-sm font-medium transition',
            activeTab === tab.key
              ? 'bg-cyan-300/15 text-cyan-100 shadow-[0_0_0_1px_rgba(103,232,249,0.32)]'
              : 'text-[color:var(--ops-text-muted)] hover:bg-[color:var(--ops-panel-subtle)] hover:text-[color:var(--ops-text-title)]',
          ].join(' ')}
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
