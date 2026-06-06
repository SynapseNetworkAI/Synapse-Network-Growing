import { EmptyPane, StateBadge } from '../components/workbench'
import type { GrowthAIVisibilityCheck, GrowthAIVisibilityComparison, GrowthAIVisibilityDesignHandoff, GrowthAIVisibilityDocsBlueprint, GrowthAIVisibilityExternalProbeGate, GrowthAIVisibilityFeedPackage, GrowthAIVisibilityFeedScorecard, GrowthAIVisibilityFeedCycle, GrowthAIVisibilityGoalAudit, GrowthAIVisibilityHandoffBundle, GrowthAIVisibilityLiveReadiness, GrowthAIVisibilityNextCycle, GrowthAIVisibilityOptimizationBrief, GrowthAIVisibilityOfficialSourceList, GrowthAIVisibilityOptimizationPlan, GrowthAIVisibilityPresencePlan, GrowthAIVisibilityProbeMatrix, GrowthAIVisibilityReleaseSnapshot, GrowthAIVisibilityReleaseUnblockPlan, GrowthAIVisibilityWeeklyReport } from '../api'
import type { GrowthAIVisibilitySourceHostFeedPackage } from '../apiGrowthAiVisibilityPlanTypes'
import type { GrowthAIVisibilitySourceHostExecutionChecklist } from '../apiGrowthAiVisibilityPlanTypes'
import { ExternalProbeGateSummary, FeedCycleMatrix, FeedScorecardSummary, GoalAuditSummary, LiveReadinessSummary, NextCycleSummary, OptimizationBriefSummary, WeeklyReportSummary } from './GrowthAIVisibilityGateSummaries'
import { HandoffBundleSummary, ReleaseSnapshotSummary, ReleaseUnblockSummary } from './GrowthAIVisibilityReleaseSummaries'
import { Info, signed } from './GrowthAIVisibilityPanelParts'
import { PresencePlanSummary, SourceHostExecutionChecklistSummary, SourceHostFeedPackageSummary } from './GrowthAIVisibilitySourceHostFeedSummary'

function tone(value: boolean) {
  return value ? 'delivered' : 'muted'
}

export function GrowthAIVisibilityPanel({
  items,
  comparisons,
  feedPackages,
  feedCycles,
  feedScorecard,
  docsBlueprint,
  designHandoff,
  weeklyReport,
  nextCycle,
  goalAudit,
  releasePlan,
  releaseSnapshot,
  handoffBundle,
  optimizationBrief,
  liveReadiness,
  externalProbeGate,
  officialSources,
  probeMatrix,
  presencePlan,
  sourceHostFeedPackage,
  sourceHostExecutionChecklist,
  plan,
  onCreate,
}: Readonly<{
  items: GrowthAIVisibilityCheck[]
  comparisons: GrowthAIVisibilityComparison[]
  feedPackages: GrowthAIVisibilityFeedPackage[]
  feedCycles: GrowthAIVisibilityFeedCycle[]
  feedScorecard: GrowthAIVisibilityFeedScorecard | null
  docsBlueprint: GrowthAIVisibilityDocsBlueprint | null
  designHandoff: GrowthAIVisibilityDesignHandoff | null
  weeklyReport: GrowthAIVisibilityWeeklyReport | null
  nextCycle: GrowthAIVisibilityNextCycle | null
  goalAudit: GrowthAIVisibilityGoalAudit | null
  releasePlan: GrowthAIVisibilityReleaseUnblockPlan | null
  releaseSnapshot: GrowthAIVisibilityReleaseSnapshot | null
  handoffBundle: GrowthAIVisibilityHandoffBundle | null
  optimizationBrief: GrowthAIVisibilityOptimizationBrief | null
  liveReadiness: GrowthAIVisibilityLiveReadiness | null
  externalProbeGate: GrowthAIVisibilityExternalProbeGate | null
  officialSources: GrowthAIVisibilityOfficialSourceList | null
  probeMatrix: GrowthAIVisibilityProbeMatrix | null
  presencePlan: GrowthAIVisibilityPresencePlan | null
  sourceHostFeedPackage: GrowthAIVisibilitySourceHostFeedPackage | null
  sourceHostExecutionChecklist: GrowthAIVisibilitySourceHostExecutionChecklist | null
  plan: GrowthAIVisibilityOptimizationPlan | null
  onCreate: () => void
}>) {
  const latest = comparisons[0]
  const externalChecks = latest?.external_checks_count ?? 0
  const citedCount = latest?.cited_count ?? 0
  const mentionedCount = latest?.mentioned_count ?? 0
  const targetPlatforms = ['chatgpt', 'claude', 'grok']
  const coveredPlatforms = new Set(latest?.external_platforms || [])

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
          <div className="mt-5 grid gap-3 lg:grid-cols-4">
            <Info label="Canonical" value={plan.canonical_domain} />
            <Info label="Docs category" value={plan.product_docs.docs_category} />
            <Info label="Mention rate" value={externalChecks ? `${mentionedCount}/${externalChecks}` : 'no external checks'} />
            <Info label="Citation rate" value={externalChecks ? `${citedCount}/${externalChecks}` : 'no external checks'} />
          </div>
          <div className="mt-4 grid gap-3 lg:grid-cols-3">
            {targetPlatforms.map((platform) => (
              <PlatformCoverage key={platform} platform={platform} covered={coveredPlatforms.has(platform)} />
            ))}
          </div>
          <WeeklyReportSummary report={weeklyReport} />
          <GoalAuditSummary audit={goalAudit} />
          <OptimizationBriefSummary brief={optimizationBrief} />
          <OfficialSourceMap sources={officialSources} />
          <ProbeMatrixSummary matrix={probeMatrix} />
          <PresencePlanSummary plan={presencePlan} />
          <SourceHostFeedPackageSummary packagePayload={sourceHostFeedPackage} />
          <SourceHostExecutionChecklistSummary checklist={sourceHostExecutionChecklist} />
          <ExternalProbeGateSummary gate={externalProbeGate} />
          <LiveReadinessSummary readiness={liveReadiness} />
          <NextCycleSummary nextCycle={nextCycle} />
          <FeedScorecardSummary scorecard={feedScorecard} />
          <FeedCycleMatrix items={feedCycles} />
          <ReleaseSnapshotSummary snapshot={releaseSnapshot} />
          <HandoffBundleSummary bundle={handoffBundle} />
          <ReleaseUnblockSummary releasePlan={releasePlan} />
          <ComparisonList items={comparisons} />
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <FeedExperimentList items={plan.feed_experiments} />
            <BaselineQueryList items={plan.baseline_queries.slice(0, 7)} />
          </div>
          <FeedPackageList items={feedPackages} />
          <DocsBlueprintSummary blueprint={docsBlueprint} />
          <DesignHandoffSummary handoff={designHandoff} />
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <PlanList title="Product docs design" items={[plan.product_docs.docs_category, ...plan.product_docs.pages.slice(0, 4), ...plan.product_docs.required_blocks.slice(0, 3)]} />
            <PlanList title="Stitch to Figma handoff" items={[plan.design_plan.stitch_prompt, ...plan.design_plan.figma_handoff]} />
          </div>
          <PlanList className="mt-5" title="Success criteria" items={plan.success_criteria} />
        </>
      )}

      <div className="mt-5 overflow-hidden rounded-2xl border border-[color:var(--ops-stroke-soft)]">
        {items.length ? (
          items.map((item) => (
            <div key={item.id} className="grid gap-4 border-b border-[color:var(--ops-stroke-soft)] px-5 py-4 last:border-b-0 lg:grid-cols-[1.4fr_0.9fr_auto]">
              <span>
                <strong>{item.query}</strong>
                <span className="mt-1 block text-sm text-[color:var(--ops-text-muted)]">
                  {item.platform} · {item.feed_key || 'unassigned'} · {item.run_group || 'manual'}
                </span>
                {item.answer_summary ? <span className="mt-2 block text-sm text-[color:var(--ops-text-muted)]">{item.answer_summary}</span> : null}
              </span>
              <span className="text-sm text-[color:var(--ops-text-muted)]">
                <span className="block">Competitors: {item.competitor_mentions.join(', ') || '-'}</span>
                <span className="mt-1 block">Evidence: {item.evidence_url || item.cited_urls[0] || '-'}</span>
                <span className="mt-1 block">Next: {item.next_action || '-'}</span>
              </span>
              <span className="flex flex-col items-start gap-2 lg:items-end">
                <StateBadge tone={tone(item.synapse_mentioned)}>{item.synapse_mentioned ? 'mentioned' : 'not_mentioned'}</StateBadge>
                <StateBadge tone={tone(item.synapse_cited)}>{item.synapse_cited ? 'cited' : 'not_cited'}</StateBadge>
              </span>
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

function ProbeMatrixSummary({ matrix }: Readonly<{ matrix: GrowthAIVisibilityProbeMatrix | null }>) {
  if (!matrix) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-probe-matrix">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Answer-engine probe matrix</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{matrix.recommended_feed_key || 'no feed'} next</div>
        </div>
        <StateBadge tone={matrix.total ? 'running' : 'muted'}>{matrix.total} probes</StateBadge>
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        Platforms: {matrix.target_platforms.join(', ')}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {matrix.rows.slice(0, 9).map((row) => (
          <div key={`${row.feed_key}-${row.platform}`} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{row.platform}</div>
              <StateBadge tone={row.status === 'covered' ? 'delivered' : row.status === 'ready_to_probe' ? 'running' : 'blocked'}>{row.status}</StateBadge>
            </div>
            <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">{row.feed_key} · {row.run_group}</div>
            <div className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">Query: {row.queries[0] || '-'}</div>
            <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">Official: {row.official_source_urls.slice(0, 3).join(', ') || '-'}</div>
            <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">
              {row.record_probe_command}
            </div>
            <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">Next: {row.next_actions[0] || row.success_decision_rule}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function OfficialSourceMap({ sources }: Readonly<{ sources: GrowthAIVisibilityOfficialSourceList | null }>) {
  if (!sources) return null
  const requiredCount = sources.items.filter((item) => item.required_for_success).length
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-official-sources">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Official source map</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">Citation authority surfaces</div>
        </div>
        <StateBadge tone={requiredCount ? 'running' : 'muted'}>{requiredCount} required</StateBadge>
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        Accepted prefixes: {sources.official_citation_prefixes.join(', ')}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {sources.items.map((source) => (
          <div key={source.surface_key} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-semibold text-[color:var(--ops-text-title)]">{source.surface_key}</div>
              <StateBadge tone={source.required_for_success ? 'running' : 'muted'}>{source.surface}</StateBadge>
            </div>
            <div className="mt-2 break-words text-xs leading-5 text-[color:var(--ops-text-caption)]">{source.canonical_url}</div>
            <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{source.citation_role}</div>
            <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">Feeds: {source.feed_keys.join(', ') || '-'}</div>
            <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">
              {source.validation_command}
            </div>
            <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">Accept: {source.acceptance_signal}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
function DesignHandoffSummary({ handoff }: Readonly<{ handoff: GrowthAIVisibilityDesignHandoff | null }>) {
  if (!handoff) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-design-handoff">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Stitch/Figma handoff</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{handoff.figma_file_name}</div>
        </div>
        <StateBadge tone="running">{handoff.frames.length} frames</StateBadge>
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        {handoff.source_tool} {'->'} {handoff.target_tool} · {handoff.canonical_domain}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {handoff.frames.map((frame) => (
          <div key={frame.name} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="font-semibold text-[color:var(--ops-text-title)]">{frame.name}</div>
            <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{frame.purpose}</div>
            <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">Source: {frame.source_page_slug}</div>
            <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">Components: {frame.figma_components.slice(0, 4).join(', ')}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm text-[color:var(--ops-text-muted)]">
        Import: {handoff.import_steps[0] || '-'}
      </div>
    </div>
  )
}

function DocsBlueprintSummary({ blueprint }: Readonly<{ blueprint: GrowthAIVisibilityDocsBlueprint | null }>) {
  if (!blueprint) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-docs-blueprint">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Docs blueprint</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{blueprint.category}</div>
        </div>
        <StateBadge tone="running">{blueprint.pages.length} pages</StateBadge>
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        {blueprint.target_repo} · {blueprint.implementation_root}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {blueprint.pages.slice(0, 3).map((page) => (
          <div key={page.slug} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="font-semibold text-[color:var(--ops-text-title)]">{page.title}</div>
            <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{page.definition_block}</div>
            <div className="mt-3 break-words text-xs leading-5 text-[color:var(--ops-text-caption)]">{page.canonical_url}</div>
            <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">Components: {page.figma_components.slice(0, 3).join(', ')}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 text-sm text-[color:var(--ops-text-muted)]">
        Shared components: {blueprint.shared_components.join(', ')}
      </div>
    </div>
  )
}

function FeedPackageList({ items }: Readonly<{ items: GrowthAIVisibilityFeedPackage[] }>) {
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-feed-packages">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Feed packages</div>
        <StateBadge tone={items.length ? 'running' : 'muted'}>{items.length ? `${items.length} active` : 'none'}</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {items.map((item) => (
          <div key={item.feed_key} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="font-semibold text-[color:var(--ops-text-title)]">{item.feed_key}</div>
            <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{item.objective}</div>
            <div className="mt-3 text-xs leading-5 text-[color:var(--ops-text-caption)]">Canonical: {item.canonical_domain}</div>
            <div className="mt-3 text-sm text-[color:var(--ops-text-muted)]">Assets: {item.publish_assets.map((asset) => asset.surface).join(', ') || '-'}</div>
            <div className="mt-3 space-y-2">
              {(item.platform_strategies || []).slice(0, 3).map((strategy) => (
                <div key={strategy.platform} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2">
                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">{strategy.platform}</div>
                  <div className="mt-1 text-sm leading-5 text-[color:var(--ops-text-muted)]">{strategy.feed_focus}</div>
                  <div className="mt-1 text-xs leading-5 text-[color:var(--ops-text-caption)]">Surfaces: {strategy.preferred_surfaces.join(', ')}</div>
                </div>
              ))}
            </div>
            <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">Validate: {item.validation_commands[0] || '-'}</div>
            <div className="mt-2 break-words text-xs leading-5 text-[color:var(--ops-text-caption)]">{item.probe_template_command}</div>
            <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm text-[color:var(--ops-text-muted)]">
              Next: {item.next_actions[0] || '-'}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function PlatformCoverage({ platform, covered }: Readonly<{ platform: string; covered: boolean }>) {
  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{platform}</div>
        <StateBadge tone={covered ? 'delivered' : 'blocked'}>{covered ? 'checked' : 'missing'}</StateBadge>
      </div>
      <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">
        {covered ? 'Latest run has answer-engine evidence.' : 'Record a search result for this platform in the latest run group.'}
      </div>
    </div>
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
  const statusTone = item.feed_effective ? 'delivered' : item.comparison_status === 'needs_external_probe' ? 'blocked' : item.comparison_status === 'regressed' ? 'blocked' : 'running'
  const citationQuality = item.citation_quality_status || 'unknown'
  const qualityTone = citationQuality === 'official_citation_verified' ? 'delivered' : citationQuality === 'needs_external_probe' || citationQuality === 'missing_official_citation' || citationQuality === 'brand_collision_present' ? 'blocked' : 'running'
  const officialCitations = item.official_cited_urls || []
  const collisionCompetitors = item.known_collision_competitors || []

  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="font-semibold text-[color:var(--ops-text-title)]">{item.feed_key}</div>
        <div className="flex flex-wrap items-center gap-2">
          <StateBadge tone={qualityTone}>{citationQuality}</StateBadge>
          <StateBadge tone={statusTone}>{item.comparison_status || 'baseline'}</StateBadge>
        </div>
      </div>
      <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">
        {item.run_group} · external {externalPlatforms.join(', ') || '-'} · cited {item.cited_count}/{externalChecks} · mentioned {item.mentioned_count}/{externalChecks}
      </div>
      <div className="mt-2 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm text-[color:var(--ops-text-muted)]">
        Previous: {item.previous_run_group || '-'} · mentioned {item.previous_mentioned_count ?? 0} {'->'} {item.mentioned_count} ({signed(item.mentioned_delta ?? 0)}) · cited {item.previous_cited_count ?? 0} {'->'} {item.cited_count} ({signed(item.cited_delta ?? 0)})
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        Local feed evidence: {localValidationCount} · all records: {item.total_checks}
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        Missing: {item.missing_platforms.join(', ') || '-'}
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        Official citations: {officialCitations.join(', ') || '-'}
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        Brand collisions: {collisionCompetitors.join(', ') || '-'}
      </div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
        Next: {item.next_actions[0] || '-'}
      </div>
    </div>
  )
}

function FeedExperimentList({ items }: Readonly<{ items: Array<{ feed_key: string; surfaces: string[]; content_assets: string[]; target_queries: string[]; measurement_window_days: number }> }>) {
  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Feed experiments</div>
      <div className="mt-3 space-y-3">
        {items.map((item) => (
          <div key={item.feed_key} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-3">
            <div className="font-semibold text-[color:var(--ops-text-title)]">{item.feed_key}</div>
            <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">Surfaces: {item.surfaces.join(', ')}</div>
            <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">Assets: {item.content_assets.slice(0, 3).join(', ')}</div>
            <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">Measure for {item.measurement_window_days} days · {item.target_queries[0]}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function BaselineQueryList({ items }: Readonly<{ items: Array<{ query: string; intent: string; target_platforms: string[]; success_signal: string }> }>) {
  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Baseline queries</div>
      <div className="mt-3 space-y-3">
        {items.map((item) => (
          <div key={item.query} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-3">
            <div className="font-semibold text-[color:var(--ops-text-title)]">{item.query}</div>
            <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{item.intent} · {item.target_platforms.join(', ')}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function PlanList({ title, items, className = '' }: Readonly<{ title: string; items: string[]; className?: string }>) {
  return (
    <div className={`rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4 ${className}`}>
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{title}</div>
      <div className="mt-3 space-y-2">
        {items.map((item) => (
          <div key={item} className="text-sm leading-6 text-[color:var(--ops-text-title)]">
            {item}
          </div>
        ))}
      </div>
    </div>
  )
}
