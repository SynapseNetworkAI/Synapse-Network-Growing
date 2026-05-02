import { useEffect, useMemo, useState } from 'react'
import {
  DistributionAssetsPanel,
  DistributionSettingsPanel,
  DistributionSignalsMetricsPanel,
  DistributionTasksPanel,
} from '../components/SocialDistributionPanels'
import { ToastProvider } from '../components/workbench'

const tabs = [
  { key: 'tasks', label: 'Tasks' },
  { key: 'signals', label: 'Signals & Metrics' },
  { key: 'assets', label: 'Assets' },
  { key: 'settings', label: 'Settings' },
] as const

type PublishingTab = (typeof tabs)[number]['key']

function normalizeTab(value: string | null): PublishingTab {
  if (value === 'signals' || value === 'metrics' || value === 'trends') return 'signals'
  if (value === 'assets') return 'assets'
  if (value === 'settings' || value === 'distribution_accounts' || value === 'rules') return 'settings'
  return 'tasks'
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export default function PublishingPage() {
  const initialTab = useMemo(() => normalizeTab(new URLSearchParams(window.location.search).get('tab')), [])
  const [activeTab, setActiveTab] = useState<PublishingTab>(initialTab)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    params.set('tab', activeTab)
    window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}`)
  }, [activeTab])

  return (
    <ToastProvider>
      <main className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 py-6 md:px-6">
        <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-5 md:px-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-[11px] uppercase tracking-[0.24em] text-[color:var(--ops-text-caption)]">Social Ops + Developer Distribution</div>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">多渠道分发中心</h1>
              <p className="mt-3 max-w-4xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
                `/publishing` v2.1 只使用 Content Assets 和 Distribution Tasks。X 可在审核后走官方 API；HN、Reddit、V2EX、DEV、Hashnode 只生成平台适配稿、复制辅助和人工回填状态。
              </p>
            </div>
            <div className="rounded-2xl border border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-running-text)]">
              Human Gate: 系统不会自动登录、评论、投票、删除或绕过 CAPTCHA。
            </div>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                className={`rounded-2xl border px-4 py-2 text-sm transition ${
                  activeTab === tab.key
                    ? 'border-cyan-300/50 bg-cyan-300/10 text-cyan-50'
                    : 'border-[color:var(--ops-stroke-soft)] text-[color:var(--ops-text-muted)] hover:text-[color:var(--ops-text-title)]'
                }`}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </section>

        {activeTab === 'tasks' ? <DistributionTasksPanel formatDateTime={formatDateTime} /> : null}
        {activeTab === 'signals' ? <DistributionSignalsMetricsPanel formatDateTime={formatDateTime} /> : null}
        {activeTab === 'assets' ? <DistributionAssetsPanel formatDateTime={formatDateTime} /> : null}
        {activeTab === 'settings' ? <DistributionSettingsPanel formatDateTime={formatDateTime} /> : null}
      </main>
    </ToastProvider>
  )
}
