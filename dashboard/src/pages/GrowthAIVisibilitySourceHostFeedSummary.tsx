import { StateBadge } from '../components/workbench'
import type { GrowthAIVisibilityPresencePlan, GrowthAIVisibilitySourceHostExecutionChecklist, GrowthAIVisibilitySourceHostFeedPackage, GrowthAIVisibilitySourceHostLiveSpotCheck } from '../apiGrowthAiVisibilityPlanTypes'

function spotCheckTone(status: string) {
  if (status === 'candidate_found' || status === 'all_candidates_found') return 'delivered'
  if (status === 'candidate_incomplete' || status === 'candidate_incomplete_needs_metadata_refresh') return 'blocked'
  if (status === 'ready_to_execute' || status === 'pending_execute') return 'running'
  if (status.includes('failed') || status.includes('blocked') || status === 'not_found') return 'blocked'
  return 'muted'
}

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
            {(item.submission_fields ?? []).length > 0 ? (
              <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-3">
                <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Fields</div>
                <div className="mt-2 space-y-2">
                  {(item.submission_fields ?? []).slice(0, 4).map((field) => (
                    <div key={`${item.key}-${field.label}`} className="text-xs leading-5">
                      <div className="font-semibold text-[color:var(--ops-text-title)]">{field.label}</div>
                      <div className="break-words text-[color:var(--ops-text-caption)]">{field.value || '-'}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {(item.submission_steps ?? [])[0] ? (
              <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">Step: {(item.submission_steps ?? [])[0]}</div>
            ) : null}
            {(item.evidence_recording_steps ?? [])[0] ? (
              <div className="mt-1 text-xs leading-5 text-[color:var(--ops-text-caption)]">Record: {(item.evidence_recording_steps ?? [])[0]}</div>
            ) : null}
            {(item.live_listing_search_urls ?? [])[0] ? (
              <a
                className="mt-2 block break-words text-xs font-semibold leading-5 text-[color:var(--ops-accent)]"
                href={(item.live_listing_search_urls ?? [])[0]}
                target="_blank"
                rel="noreferrer"
              >
                Live search: {(item.live_listing_search_urls ?? [])[0]}
              </a>
            ) : null}
            {(item.live_listing_validation_steps ?? [])[0] ? (
              <div className="mt-1 text-xs leading-5 text-[color:var(--ops-text-caption)]">Live gate: {(item.live_listing_validation_steps ?? [])[0]}</div>
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

export function SourceHostLiveSpotCheckSummary({ spotCheck }: Readonly<{ spotCheck: GrowthAIVisibilitySourceHostLiveSpotCheck | null }>) {
  if (!spotCheck) return null
  const items = spotCheck.items ?? []
  const blockers = spotCheck.blockers ?? []
  const commands = spotCheck.commands ?? {}
  const incompleteCount = items.filter((item) => item.status === 'candidate_incomplete').length
  const foundCount = items.filter((item) => item.status === 'candidate_found').length
  const notFoundCount = items.filter((item) => item.status === 'not_found').length
  const statusSummary = incompleteCount
    ? `${incompleteCount} metadata refresh`
    : foundCount
      ? `${foundCount} candidates`
      : `${notFoundCount} missing`

  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-source-host-live-spot-check">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Source-host live spot-check</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{spotCheck.feed_key}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StateBadge tone={spotCheck.execute ? 'running' : 'muted'}>{spotCheck.execute ? 'executed' : 'not_executed'}</StateBadge>
          <StateBadge tone={spotCheckTone(spotCheck.status || 'unknown')}>{spotCheck.status || 'unknown'}</StateBadge>
        </div>
      </div>
      <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">
        {statusSummary}. This is read-only directory visibility evidence; incomplete candidates still need directory metadata refresh before GPT/Claude probes can treat the source-host as ready.
      </div>
      {blockers.length ? (
        <div className="mt-3 rounded-xl border border-amber-300/20 bg-amber-500/10 px-3 py-2 text-sm leading-6 text-amber-100">
          {blockers[0]}
        </div>
      ) : null}
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {items.slice(0, 6).map((item) => (
          <div key={`${item.host}-${item.search_url}`} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="font-semibold text-[color:var(--ops-text-title)]">{item.host}</div>
              <StateBadge tone={spotCheckTone(item.status)}>{item.status}</StateBadge>
            </div>
            <a className="mt-2 block break-words text-xs font-semibold leading-5 text-[color:var(--ops-accent)]" href={item.search_url} target="_blank" rel="noreferrer">
              {item.search_url}
            </a>
            <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">HTTP {item.http_status || '-'}</div>
            <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{item.next_action || '-'}</div>
            {(item.matched_terms ?? []).length ? (
              <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">Matched: {item.matched_terms.slice(0, 5).join(', ')}</div>
            ) : null}
            {(item.missing_terms ?? []).length ? (
              <div className="mt-1 text-xs leading-5 text-[color:var(--ops-text-caption)]">Missing: {item.missing_terms.slice(0, 5).join(', ')}</div>
            ) : null}
          </div>
        ))}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">
          Execute: {commands.execute || '-'}
        </div>
        <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">
          Record: {commands.record_live_listing || '-'}
        </div>
      </div>
    </div>
  )
}
