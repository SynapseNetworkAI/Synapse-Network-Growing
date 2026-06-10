import { StateBadge } from '../components/workbench'
import type { GrowthAIVisibilityExternalProbeGate, GrowthAIVisibilityFeedCycle, GrowthAIVisibilityFeedScorecard, GrowthAIVisibilityGoalAudit, GrowthAIVisibilityLiveReadiness, GrowthAIVisibilityNextCycle, GrowthAIVisibilityOptimizationBrief, GrowthAIVisibilityWeeklyReport } from '../api'
import { CommandBlock, EvidenceList, Info, SourceHostActionList, signed } from './GrowthAIVisibilityPanelParts'

export function LiveReadinessSummary({ readiness }: Readonly<{ readiness: GrowthAIVisibilityLiveReadiness | null }>) {
  if (!readiness) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-live-readiness">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Live feed readiness</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">External probe gate</div>
        </div>
        <StateBadge tone={readiness.status === 'blocked' ? 'blocked' : 'delivered'}>{readiness.status}</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-4">
        <Info label="Homepage" value={readiness.canonical_homepage} />
        <Info label="Run group" value={readiness.run_group} />
        <Info label="Ready feeds" value={`${readiness.ready_count}/${readiness.total}`} />
        <Info label="Blocked feeds" value={`${readiness.blocked_count}`} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {readiness.items.map((item) => (
          <div key={item.feed_key} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-[color:var(--ops-text-title)]">{item.feed_key}</div>
                <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{item.platform}</div>
              </div>
              <StateBadge tone={item.feed_ready ? 'delivered' : 'blocked'}>{item.status}</StateBadge>
            </div>
            <div className="mt-3 space-y-2">
              {item.checks.slice(0, 5).map((check) => (
                <div key={`${item.feed_key}-${check.label}`} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-[color:var(--ops-text-title)]">{check.label}</span>
                    <StateBadge tone={check.ok ? 'delivered' : 'blocked'}>{check.status || 'error'}</StateBadge>
                  </div>
                  <div className="mt-1 break-all text-xs leading-5 text-[color:var(--ops-text-muted)]">{check.url}</div>
                </div>
              ))}
            </div>
            <EvidenceList title="Readiness blockers" empty="Feed ready." items={item.missing_facts} />
            <div className="mt-3 text-sm leading-5 text-[color:var(--ops-text-muted)]">{item.next_action || '-'}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <CommandBlock label="Run live validation" value={readiness.validation_command} />
        <CommandBlock label="Record readiness rows" value={readiness.apply_command} />
      </div>
    </div>
  )
}

export function ExternalProbeGateSummary({ gate }: Readonly<{ gate: GrowthAIVisibilityExternalProbeGate | null }>) {
  if (!gate) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-external-probe-gate">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">External probe gate</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{gate.feed_key}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StateBadge tone={gate.ready_to_execute ? 'delivered' : 'blocked'}>{gate.status}</StateBadge>
          <StateBadge tone={gate.manual_ready_to_execute ? 'delivered' : 'blocked'}>
            {gate.manual_ready_to_execute ? 'manual ready' : 'manual blocked'}
          </StateBadge>
        </div>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-5">
        <Info label="Run group" value={gate.run_group} />
        <Info label="Feed ready" value={gate.feed_ready ? 'yes' : 'no'} />
        <Info label="Manual UI ready" value={gate.manual_ready_to_execute ? 'yes' : 'no'} />
        <Info label="API keys ready" value={gate.api_keys_ready ? 'yes' : 'no'} />
        <Info label="Partial ready" value={gate.partial_ready_to_execute ? 'yes' : 'no'} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <Info label="Target platforms" value={gate.target_platforms.join(', ')} />
        <Info label="Ready platforms" value={gate.ready_platforms.join(', ') || '-'} />
        <Info label="Missing platforms" value={gate.missing_platforms.join(', ') || '-'} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {gate.provider_readiness.map((provider) => (
          <div key={provider.platform} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-[color:var(--ops-text-title)]">{provider.platform}</span>
              <StateBadge tone={provider.configured ? 'delivered' : 'blocked'}>{provider.configured ? 'configured' : 'missing'}</StateBadge>
            </div>
            <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-muted)]">{provider.env_key}</div>
          </div>
        ))}
      </div>
      <EvidenceList title="Probe blockers" empty="Ready to execute external probes." items={gate.blockers} />
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <CommandBlock label="Validate feed" value={gate.feed_validation_command} />
        <CommandBlock label="Manual template" value={gate.manual_probe_template_command || '-'} />
        <CommandBlock label="Record evidence" value={gate.record_probe_command} />
        <CommandBlock label="API readiness" value={gate.api_readiness_command} />
        <CommandBlock label="Execute probes" value={gate.api_execute_command} />
        <CommandBlock label="Configured-platform readiness" value={gate.partial_api_readiness_command || '-'} />
        <CommandBlock label="Configured-platform execute" value={gate.partial_api_execute_command || '-'} />
        <CommandBlock label="Compare evidence" value={gate.compare_command} />
      </div>
    </div>
  )
}

export function OptimizationBriefSummary({ brief }: Readonly<{ brief: GrowthAIVisibilityOptimizationBrief | null }>) {
  if (!brief) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-optimization-brief">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Optimization brief</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{brief.title}</div>
        </div>
        <StateBadge tone={brief.status === 'blocked' ? 'blocked' : 'running'}>{brief.status}</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-4">
        <Info label="Homepage" value={brief.official_homepage} />
        <Info label="Recommended feed" value={brief.recommended_feed_key || '-'} />
        <Info label="Platforms" value={brief.target_platforms.join(', ') || '-'} />
        <Info label="Artifact" value={brief.artifact_path} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvidenceList title="Brief blockers" empty="No blockers." items={brief.blockers} />
        <EvidenceList title="Brief next actions" empty="No next actions." items={brief.next_actions} />
      </div>
      <CommandBlock label="Export brief" value={brief.export_command} />
    </div>
  )
}

export function GoalAuditSummary({ audit }: Readonly<{ audit: GrowthAIVisibilityGoalAudit | null }>) {
  if (!audit) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-goal-audit">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Goal completion audit</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">
            {audit.goal_achieved ? 'GPT/Claude/Grok/Gemini visibility proven' : 'Objective still requires external evidence'}
          </div>
        </div>
        <StateBadge tone={audit.goal_achieved ? 'delivered' : 'blocked'}>{audit.status}</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-4">
        <Info label="Homepage" value={audit.official_homepage} />
        <Info label="Platforms" value={audit.target_platforms.join(', ') || '-'} />
        <Info label="Completed" value={`${audit.completed_count}/${audit.total_required}`} />
        <Info label="Export" value={audit.export_command} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvidenceList title="Goal blockers" empty="No blockers." items={audit.blockers} />
        <EvidenceList title="Goal next actions" empty="No next actions." items={audit.next_actions} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {audit.requirements.map((item) => (
          <div key={item.key} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-[color:var(--ops-text-title)]">{item.title}</span>
              <StateBadge tone={item.status === 'completed' ? 'delivered' : 'blocked'}>{item.status}</StateBadge>
            </div>
            <div className="mt-1 text-xs leading-5 text-[color:var(--ops-text-muted)]">
              {item.evidence || item.blocker || item.next_action || '-'}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function FeedCycleMatrix({ items }: Readonly<{ items: GrowthAIVisibilityFeedCycle[] }>) {
  if (!items.length) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-feed-cycle-matrix">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Feed cycle matrix</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">Feed, probe, compare, iterate</div>
        </div>
        <StateBadge tone="running">{items.length} feeds</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {items.map((item) => (
          <div key={item.feed_key} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-[color:var(--ops-text-title)]">{item.feed_key}</div>
                <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{item.latest_run_group || 'no external run'}</div>
              </div>
              <StateBadge tone={item.status.includes('blocked') ? 'blocked' : item.status.includes('observed') ? 'delivered' : 'running'}>{item.status}</StateBadge>
            </div>
            <div className="mt-3 grid gap-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">
              <div>Surfaces: {item.publish_surfaces.join(', ') || '-'}</div>
              <div>External: {item.external_platforms.join(', ') || '-'}</div>
              <div>Missing: {item.missing_platforms.join(', ') || '-'}</div>
              <div>Mention/cite: {item.mentioned_count}/{item.cited_count}</div>
            </div>
            <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2">
              <div className="text-[11px] uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">Next</div>
              <div className="mt-1 text-sm leading-5 text-[color:var(--ops-text-muted)]">{item.next_actions[0] || '-'}</div>
            </div>
            <div className="mt-3 space-y-2">
              <CommandBlock label="Validate feed" value={item.feed_validation_command} />
              <CommandBlock label="API readiness" value={item.api_readiness_command} />
              <CommandBlock label="Compare run" value={item.compare_command} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function NextCycleSummary({ nextCycle }: Readonly<{ nextCycle: GrowthAIVisibilityNextCycle | null }>) {
  if (!nextCycle) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-next-cycle">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Next optimization cycle</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{nextCycle.feed_key}</div>
        </div>
        <StateBadge tone={nextCycle.blockers.length ? 'blocked' : 'running'}>{nextCycle.run_group}</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <Info label="Output" value={nextCycle.output_path} />
        <Info label="Missing platforms" value={nextCycle.missing_platforms.join(', ') || '-'} />
        <Info label="First validation" value={nextCycle.validation_commands[0] || '-'} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvidenceList title="Cycle blockers" empty="No cycle blockers." items={nextCycle.blockers} />
        <EvidenceList title="Cycle next actions" empty="Run the weekly probe and compare answer-engine visibility." items={nextCycle.next_actions} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <CommandBlock label="Feed validation" value={nextCycle.feed_validation_command} />
        <CommandBlock label="Manual template" value={nextCycle.manual_probe_template_command} />
        <CommandBlock label="External gate" value={nextCycle.external_probe_gate_command} />
        <CommandBlock label="API readiness" value={nextCycle.api_readiness_command} />
        <CommandBlock label="API execute" value={nextCycle.api_execute_command} />
        <CommandBlock label="Public search import" value={nextCycle.public_web_search_import_command || '-'} />
        <CommandBlock label="Probe matrix" value={nextCycle.probe_matrix_command} />
        <CommandBlock label="Apply evidence" value={nextCycle.apply_command} />
        <CommandBlock label="Validate matrix" value={nextCycle.validate_matrix_command} />
        <CommandBlock label="Cycle summary" value={nextCycle.cycle_summary_command} />
        <CommandBlock label="Operator brief" value={nextCycle.operator_brief_command} />
        <CommandBlock label="Compare" value={nextCycle.compare_command} />
        <CommandBlock label="Weekly report" value={nextCycle.weekly_report_command} />
      </div>
    </div>
  )
}

export function FeedScorecardSummary({ scorecard }: Readonly<{ scorecard: GrowthAIVisibilityFeedScorecard | null }>) {
  if (!scorecard) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-feed-scorecard">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Feed experiment scorecard</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">Compare feed impact</div>
        </div>
        <StateBadge tone="running">recommended {scorecard.recommended_feed_key || '-'}</StateBadge>
      </div>
      <div className="mt-2 text-sm leading-5 text-[color:var(--ops-text-muted)]">{scorecard.ranking_basis}</div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {scorecard.items.map((item) => (
          <div key={item.feed_key} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">Rank #{item.rank}</div>
                <div className="mt-1 font-semibold text-[color:var(--ops-text-title)]">{item.feed_key}</div>
              </div>
              <StateBadge tone={item.feed_effective ? 'delivered' : item.status.includes('blocked') ? 'blocked' : 'running'}>{item.impact_score}</StateBadge>
            </div>
            <div className="mt-3 grid gap-1 text-xs leading-5 text-[color:var(--ops-text-muted)]">
              <div>Status: {item.status} · {item.comparison_status}</div>
              <div>Citation quality: {item.citation_quality_status || 'unknown'}</div>
              <div>Covered: {item.covered_platforms.join(', ') || '-'}</div>
              <div>Missing: {item.missing_platforms.join(', ') || '-'}</div>
              <div>Mention/cite: {item.mentioned_count}/{item.cited_count}</div>
              <div>Official/collision: {(item.official_cited_urls || []).length}/{(item.known_collision_competitors || []).length}</div>
              <div>Delta: mention {signed(item.mentioned_delta)} · cite {signed(item.cited_delta)}</div>
              <div>External/local: {item.external_checks_count}/{item.local_validation_count}</div>
            </div>
            <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm leading-5 text-[color:var(--ops-text-muted)]">
              {item.recommended_action}
            </div>
            <SourceHostActionList actions={item.source_host_actions || []} />
          </div>
        ))}
      </div>
    </div>
  )
}

export function WeeklyReportSummary({ report }: Readonly<{ report: GrowthAIVisibilityWeeklyReport | null }>) {
  if (!report) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-weekly-report">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Weekly visibility gate</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">
            {report.goal_achieved ? 'Achieved' : 'Still optimizing'}
          </div>
        </div>
        <StateBadge tone={report.goal_achieved ? 'delivered' : 'blocked'}>{report.goal_status}</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-4">
        <Info label="Stable runs" value={`${report.stable_positive_runs}/${report.required_stable_runs}`} />
        <Info label="Covered" value={report.covered_platforms.join(', ') || '-'} />
        <Info label="Missing" value={report.missing_platforms.join(', ') || '-'} />
        <Info label="Recommended feed" value={report.recommended_feed_key || '-'} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvidenceList title="Gate blockers" empty="No blockers." items={report.blockers} />
        <EvidenceList title="Gate next actions" empty="No next actions." items={report.next_actions} />
      </div>
      <div className="mt-2 break-words text-xs leading-5 text-[color:var(--ops-text-caption)]">
        {report.recommended_probe_template_command}
      </div>
    </div>
  )
}
