import type { GrowthProviderProfile } from '../api'
import { EmptyPane, StateBadge } from '../components/workbench'

function tone(value: string) {
  if (['sent', 'historical_lead', 'active'].includes(value)) return 'delivered'
  if (['queued', 'approved', 'enriched'].includes(value)) return 'running'
  if (['failed', 'do_not_contact', 'invalid'].includes(value)) return 'blocked'
  return 'muted'
}

function time(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

export function GrowthProviderProfilesPanel({ items }: Readonly<{ items: GrowthProviderProfile[] }>) {
  const contacted = items.filter((item) => item.latest_message_status === 'sent').length
  const withWebsite = items.filter((item) => Boolean(item.website_url)).length
  const withEmail = items.filter((item) => Boolean(item.contact_email)).length

  return (
    <section
      className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5"
      data-testid="provider-customer-profiles"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--ops-text-caption)]">Provider Customer Database</div>
          <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">Provider Customer Profiles</h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
            Sent outreach history enriched with website, company description, contact, and latest message evidence.
          </p>
        </div>
        <div className="grid min-w-[260px] grid-cols-3 gap-2 text-center">
          <MiniMetric label="Profiles" value={items.length} />
          <MiniMetric label="Websites" value={withWebsite} />
          <MiniMetric label="Emails" value={withEmail} />
        </div>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="overflow-hidden rounded-2xl border border-[color:var(--ops-stroke-soft)]">
          {items.length ? (
            items.map((item) => (
              <article key={item.id} className="border-b border-[color:var(--ops-stroke-soft)] px-5 py-4 last:border-b-0">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h4 className="text-base font-semibold text-[color:var(--ops-text-title)]">{item.organization}</h4>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm text-[color:var(--ops-text-muted)]">
                      {item.website_url ? (
                        <a className="text-cyan-100 hover:underline" href={item.website_url} target="_blank" rel="noreferrer">
                          {item.website_url}
                        </a>
                      ) : (
                        <span>No website captured</span>
                      )}
                      <span>{item.contact_email || 'No email captured'}</span>
                    </div>
                  </div>
                  <StateBadge tone={tone(item.latest_message_status || item.profile_status)}>
                    {item.latest_message_status || item.profile_status}
                  </StateBadge>
                </div>
                <p className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">{item.company_description || 'No company description captured.'}</p>
                <div className="mt-3 grid gap-2 text-xs text-[color:var(--ops-text-caption)] md:grid-cols-3">
                  <span>Last contact: {time(item.last_contacted_at)}</span>
                  <span>Subject: {item.latest_message_subject || '-'}</span>
                  <span>Evidence: {item.evidence.length}</span>
                </div>
              </article>
            ))
          ) : (
            <div className="p-6">
              <EmptyPane>No provider customer profiles yet.</EmptyPane>
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Profile Coverage</div>
          <div className="mt-3 text-sm font-semibold text-[color:var(--ops-text-title)]">Providers</div>
          <div className="mt-4 rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Sent history</div>
            <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{contacted}</div>
          </div>
        </div>
      </div>
    </section>
  )
}

function MiniMetric({ label, value }: Readonly<{ label: string; value: number }>) {
  return (
    <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{value}</div>
    </div>
  )
}
