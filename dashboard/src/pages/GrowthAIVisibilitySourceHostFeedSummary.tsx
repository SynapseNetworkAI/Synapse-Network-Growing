import { StateBadge } from '../components/workbench'
import type { GrowthAIVisibilityPresencePlan, GrowthAIVisibilitySourceHostExecutionChecklist, GrowthAIVisibilitySourceHostFeedPackage } from '../apiGrowthAiVisibilityPlanTypes'

export function PresencePlanSummary({ plan }: Readonly<{ plan: GrowthAIVisibilityPresencePlan | null }>) {
  if (!plan) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-presence-plan">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Source-host presence plan</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{plan.feed_key}</div>
        </div>
        <StateBadge tone={plan.actions.length ? 'running' : 'blocked'}>{plan.status}</StateBadge>
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        Source hosts: {plan.source_hosts.slice(0, 8).join(', ') || '-'}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {plan.actions.slice(0, 6).map((action) => (
          <div key={`${action.host}-${action.action_type}`} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="font-semibold text-[color:var(--ops-text-title)]">{action.host}</div>
              <StateBadge tone={action.ownership === 'not_directly_editable' ? 'muted' : 'running'}>{action.action_type}</StateBadge>
            </div>
            <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">{action.ownership} · priority {action.priority}</div>
            <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{action.rationale}</div>
            <div className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">Asset: {action.asset}</div>
            {action.submit_url && (
              <a className="mt-3 block text-sm font-semibold text-[color:var(--ops-accent)]" href={action.submit_url} target="_blank" rel="noreferrer">
                Submit: {action.submit_url}
              </a>
            )}
            {Object.keys(action.submission_payload || {}).length > 0 && (
              <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">
                Payload: {Object.keys(action.submission_payload).slice(0, 6).join(', ')}
              </div>
            )}
            {action.operator_notes[0] && (
              <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">{action.operator_notes[0]}</div>
            )}
            <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">
              {action.validation_command}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">
        Probe: {plan.next_probe_command}
      </div>
    </div>
  )
}

export function SourceHostFeedPackageSummary({ packagePayload }: Readonly<{ packagePayload: GrowthAIVisibilitySourceHostFeedPackage | null }>) {
  if (!packagePayload) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-source-host-feed-package">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Source-host feed package</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{packagePayload.feed_key}</div>
        </div>
        <StateBadge tone={packagePayload.drafts.length ? 'running' : 'blocked'}>{packagePayload.status}</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {packagePayload.drafts.slice(0, 6).map((draft) => (
          <div key={`${draft.host}-${draft.draft_type}`} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="font-semibold text-[color:var(--ops-text-title)]">{draft.host}</div>
              <StateBadge tone={draft.status === 'ready_to_submit' ? 'delivered' : draft.status === 'needs_operator_review' ? 'muted' : 'running'}>{draft.draft_type}</StateBadge>
            </div>
            <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">{draft.status} · priority {draft.priority}</div>
            <div className="mt-2 text-sm font-semibold text-[color:var(--ops-text-title)]">{draft.title}</div>
            <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{draft.summary}</div>
            <div className="mt-3 text-xs leading-5 text-[color:var(--ops-text-caption)]">Target: {draft.submit_url || draft.target_url}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">
        Probe: {packagePayload.commands.after_feed_probe || '-'}
      </div>
    </div>
  )
}

export function SourceHostExecutionChecklistSummary({ checklist }: Readonly<{ checklist: GrowthAIVisibilitySourceHostExecutionChecklist | null }>) {
  if (!checklist) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-source-host-execution-checklist">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Source-host execution checklist</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{checklist.feed_key}</div>
        </div>
        <StateBadge tone={checklist.items.length ? 'running' : 'blocked'}>{checklist.status}</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {checklist.items.slice(0, 6).map((item) => (
          <div key={item.key} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="font-semibold text-[color:var(--ops-text-title)]">{item.host}</div>
              <StateBadge tone={item.execution_status === 'pending_owned_publish' ? 'running' : 'muted'}>{item.execution_status}</StateBadge>
            </div>
            <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">{item.draft_type} · priority {item.priority}</div>
            <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{item.action_required}</div>
            {item.design_handoff_frame ? (
              <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">Design frame: {item.design_handoff_frame}</div>
            ) : null}
            <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">Evidence: {item.required_evidence.slice(0, 3).join(', ')}</div>
            {item.submission_confirmation_command ? (
              <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">Record: {item.submission_confirmation_command.slice(0, 160)}...</div>
            ) : null}
          </div>
        ))}
      </div>
      <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">
        Gate: {checklist.items[0]?.completion_gate || '-'}
      </div>
    </div>
  )
}
