import { StateBadge } from '../components/workbench'
import type {
  GrowthAIVisibilityHandoffBundle,
  GrowthAIVisibilityPendingPublicationGap,
  GrowthAIVisibilityPendingSourcePr,
  GrowthAIVisibilityReleaseSnapshot,
  GrowthAIVisibilityReleaseUnblockPlan,
} from '../api'
import { CommandBlock, CommandList, EvidenceList, Info } from './GrowthAIVisibilityPanelParts'

export function ReleaseUnblockSummary({ releasePlan }: Readonly<{ releasePlan: GrowthAIVisibilityReleaseUnblockPlan | null }>) {
  if (!releasePlan) return null
  const preflight = releasePlan.command_groups.find((group) => group.key.includes('preflight'))
  const productionValidation = releasePlan.command_groups.find((group) => group.key === 'production_validation')
  const productionGroups = releasePlan.command_groups.filter((group) => group.environment === 'production')
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-release-unblock-plan">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Release unblock plan</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{releasePlan.feed_key}</div>
        </div>
        <StateBadge tone={releasePlan.status.includes('blocked') ? 'blocked' : 'running'}>{releasePlan.status}</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-4">
        <Info label="Homepage" value={releasePlan.official_homepage} />
        <Info label="Services" value={releasePlan.services.join(', ')} />
        <Info label="Branch" value={releasePlan.branch_name} />
        <Info label="Target commit" value={releasePlan.target_commit_sha.slice(0, 12)} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-4">
        <Info label="Deploy readiness" value={releasePlan.deploy_readiness_status || '-'} />
        <Info label="Source PR" value={releaseInfo(releasePlan.source_pr, 'url')} />
        <Info label="PR state" value={releaseInfo(releasePlan.source_pr, 'state')} />
        <Info label="Evidence" value={releaseInfo(releasePlan.predeploy_evidence, 'status')} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvidenceList title="Predeploy validations" empty="No predeploy validation evidence." items={releaseValidationLines(releasePlan.predeploy_evidence)} />
        <EvidenceList title="Predeploy screenshots" empty="No screenshots." items={releaseStringList(releasePlan.predeploy_evidence, 'screenshots').slice(0, 4)} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvidenceList title="Merged source PRs" empty="No merged source PRs." items={releasePrLines(releasePlan.source_prs || [])} />
        <EvidenceList title="Deployment gaps" empty="No deployment gaps." items={deploymentGapLines(releasePlan.deployment_gaps || [])} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvidenceList title="Pending source PRs" empty="No pending source PRs." items={pendingSourcePrLines(releasePlan.pending_source_prs || [])} />
        <EvidenceList title="Pending publication gaps" empty="No pending publication gaps." items={publicationGapLines(releasePlan.pending_publication_gaps || [])} />
      </div>
      <EvidenceList className="mt-3" title="Confirmed facts" empty="No confirmed facts." items={releasePlan.confirmed_facts || []} />
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvidenceList title="Release blockers" empty="No release blockers." items={releasePlan.known_blockers} />
        <EvidenceList title="Release boundaries" empty="No release boundaries." items={releasePlan.hard_boundaries} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <CommandList label={preflight?.key || 'preflight'} commands={preflight?.commands || []} />
        <CommandList label="production promotion" commands={productionGroups.flatMap((group) => group.commands).slice(0, 6)} />
        <CommandList label={productionValidation?.key || 'production validation'} commands={productionValidation?.commands || []} />
        <EvidenceList title="Success criteria" empty="No success criteria." items={releasePlan.success_criteria} />
      </div>
    </div>
  )
}

export function ReleaseSnapshotSummary({ snapshot }: Readonly<{ snapshot: GrowthAIVisibilityReleaseSnapshot | null }>) {
  if (!snapshot) return null
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-release-snapshot">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Release blocker snapshot</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{snapshot.feed_key}</div>
        </div>
        <StateBadge tone={snapshot.status === 'blocked' ? 'blocked' : 'delivered'}>{snapshot.status}</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-4">
        <Info label="Homepage" value={snapshot.official_homepage} />
        <Info label="Release plan" value={snapshot.release_plan_status} />
        <Info label="Deploy readiness" value={snapshot.deploy_readiness_status} />
        <Info label="Run group" value={snapshot.run_group} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-4">
        <EvidenceList title="GCloud checks" empty="No GCloud checks." items={snapshotCheckLines(snapshot.gcloud)} />
        <EvidenceList title="External probe keys" empty="No key checks." items={snapshotCheckLines(snapshot.external_probe_keys)} />
        <EvidenceList title="Snapshot next actions" empty="No next actions." items={snapshot.next_actions} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvidenceList title="Snapshot confirmed facts" empty="No confirmed facts." items={snapshot.confirmed_facts} />
        <EvidenceList title="Snapshot blockers" empty="No blockers." items={snapshot.blockers} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvidenceList title="Snapshot pending PRs" empty="No pending PRs." items={pendingSourcePrLines(snapshot.pending_source_prs || [])} />
        <EvidenceList title="Snapshot publication gaps" empty="No publication gaps." items={publicationGapLines(snapshot.pending_publication_gaps || [])} />
      </div>
    </div>
  )
}

export function HandoffBundleSummary({ bundle }: Readonly<{ bundle: GrowthAIVisibilityHandoffBundle | null }>) {
  if (!bundle) return null
  const commandEntries = Object.entries(bundle.commands || {}).filter(([, value]) => value)
  const fileEntries = Object.entries(bundle.files || {}).map(([key, value]) => `${key}: ${value}`)
  return (
    <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="ai-visibility-handoff-bundle">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Operator handoff bundle</div>
          <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{bundle.feed_key}</div>
        </div>
        <StateBadge tone={bundle.status === 'blocked' ? 'blocked' : 'running'}>{bundle.status}</StateBadge>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-4">
        <Info label="Homepage" value={bundle.official_homepage} />
        <Info label="Run group" value={bundle.run_group} />
        <Info label="Target commit" value={bundle.target_commit_sha.slice(0, 12)} />
        <Info label="Generated" value={bundle.generated_at} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <Info label="Release status" value={bundle.release_status} />
        <Info label="Live readiness" value={bundle.live_readiness_status} />
        <Info label="External probe gate" value={bundle.external_probe_gate_status} />
        <Info label="Goal audit" value={`${bundle.goal_audit_status || 'unknown'} · ${bundle.goal_achieved ? 'achieved' : 'not achieved'}`} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvidenceList title="Ready platforms" empty="No platform ready." items={bundle.ready_platforms} />
        <EvidenceList title="Missing platforms" empty="No platform missing." items={bundle.missing_platforms} />
        <EvidenceList title="Handoff blockers" empty="No blockers." items={bundle.blockers} />
        <EvidenceList title="Handoff next actions" empty="No next actions." items={bundle.next_actions} />
      </div>
      <EvidenceList className="mt-3" title="Evidence files" empty="No files." items={fileEntries} />
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {commandEntries.slice(0, 12).map(([key, value]) => (
          <CommandBlock key={key} label={key} value={value} />
        ))}
      </div>
    </div>
  )
}

function snapshotCheckLines(records: Record<string, Record<string, unknown>>) {
  return Object.entries(records || {}).map(([key, record]) => {
    const status = releaseInfo(record, 'status')
    const configured = record.configured
    const ok = record.ok
    const state = typeof configured === 'boolean' ? (configured ? 'configured' : 'missing') : typeof ok === 'boolean' ? (ok ? 'ok' : 'failed') : status
    const env = releaseInfo(record, 'env_key')
    const summary = releaseInfo(record, 'summary')
    return `${key}: ${state}${env !== '-' ? ` ${env}` : ''}${summary !== '-' ? ` - ${summary}` : ''}`
  })
}

function releaseInfo(source: Record<string, unknown>, key: string) {
  const value = source?.[key]
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '-'
}

function releaseStringList(source: Record<string, unknown>, key: string) {
  const value = source?.[key]
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : []
}

function releasePrLines(records: Record<string, unknown>[]) {
  return records.map((record) => {
    const number = releaseInfo(record, 'number')
    const state = releaseInfo(record, 'state')
    const commit = releaseInfo(record, 'merge_commit').slice(0, 12)
    const purpose = releaseInfo(record, 'purpose')
    return `#${number} ${state} ${commit}${purpose && purpose !== '-' ? ` - ${purpose}` : ''}`
  })
}

function pendingSourcePrLines(records: GrowthAIVisibilityPendingSourcePr[]) {
  return records.map((record) => {
    const commit = record.head_commit ? record.head_commit.slice(0, 12) : '-'
    const purpose = record.purpose ? ` - ${record.purpose}` : ''
    return `#${record.number} ${record.state} ${record.head_ref} ${commit}; ${record.url}${purpose}`
  })
}

function deploymentGapLines(records: Record<string, unknown>[]) {
  return records.map((record) => {
    const service = releaseInfo(record, 'service_key')
    const status = releaseInfo(record, 'status')
    const staging = releaseInfo(record, 'staging_commit').slice(0, 12)
    const prod = releaseInfo(record, 'production_commit').slice(0, 12)
    const target = releaseInfo(record, 'target_commit').slice(0, 12)
    const next = releaseInfo(record, 'next_action')
    return `${service}: ${status}; staging=${staging} prod=${prod} target=${target}${next && next !== '-' ? `; ${next}` : ''}`
  })
}

function publicationGapLines(records: GrowthAIVisibilityPendingPublicationGap[]) {
  return records.map((record) => {
    return `${record.surface}: ${record.current_status}->${record.expected_after_merge} via PR #${record.source_pr}; ${record.url}; ${record.next_action}`
  })
}

function releaseValidationLines(source: Record<string, unknown>) {
  const value = source?.validations
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (!item || typeof item !== 'object') return ''
      const record = item as Record<string, unknown>
      const result = typeof record.result === 'string' ? record.result : 'unknown'
      const command = typeof record.command === 'string' ? record.command : ''
      return command ? `${result}: ${command}` : result
    })
    .filter(Boolean)
}
