import type { GrowthSourceConfig } from '../api'
import { EmptyPane, StateBadge } from '../components/workbench'

function time(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

export function SourcesPanel({ sources, onCreate, onEnsureDefault, onRun, onOpenRuns }: Readonly<{
  sources: GrowthSourceConfig[]
  onCreate: () => void
  onEnsureDefault: () => void
  onRun: (source: GrowthSourceConfig, dryRun: boolean) => void
  onOpenRuns: (source: GrowthSourceConfig) => void
}>) {
  return (
    <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xl font-semibold text-[color:var(--ops-text-title)]">Provider Source Configs</h3>
          <p className="mt-2 text-sm text-[color:var(--ops-text-muted)]">配置采集源，自动发现 provider lead，生成人工审核草稿；不自动外发。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onEnsureDefault}>创建 Firecrawl 默认配置</button>
          <button type="button" className="rounded-xl border border-cyan-300/35 px-4 py-2 text-sm text-cyan-100" onClick={onCreate}>新增配置</button>
        </div>
      </div>
      <div className="mt-5 overflow-hidden rounded-2xl border border-[color:var(--ops-stroke-soft)]">
        {sources.length ? sources.map((source) => {
          const result = source.last_result || {}
          return (
            <div key={source.id} className="grid gap-4 border-b border-[color:var(--ops-stroke-soft)] px-5 py-4 last:border-b-0 lg:grid-cols-[1.4fr_1fr_1fr_auto]">
              <div>
                <div className="font-semibold text-[color:var(--ops-text-title)]">{source.name}</div>
                <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{source.config_type} · {source.description || 'no description'}</div>
              </div>
              <div className="text-sm text-[color:var(--ops-text-muted)]">
                <div>last run: {time(source.last_run_at)}</div>
                <div>found {Number(result.candidate_count || 0)} · created {Number(result.created_count || 0)} · drafted {Number(result.drafted_count || 0)}</div>
              </div>
              <div className="flex items-center"><StateBadge tone={source.status === 'enabled' ? 'ready' : 'muted'}>{source.status}</StateBadge></div>
              <div className="flex flex-wrap justify-end gap-2">
                <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => onRun(source, true)}>Dry Run</button>
                <button className="rounded-xl border border-cyan-300/35 px-3 py-2 text-sm text-cyan-100" onClick={() => onRun(source, false)}>Run Now</button>
                <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => onOpenRuns(source)}>运行历史</button>
              </div>
            </div>
          )
        }) : <div className="p-6"><EmptyPane>No source configs yet. Create the Firecrawl default config to start provider acquisition.</EmptyPane></div>}
      </div>
    </section>
  )
}
