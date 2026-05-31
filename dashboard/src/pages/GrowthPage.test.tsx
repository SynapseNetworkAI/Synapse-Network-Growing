// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import GrowthPage from './GrowthPage'

const investor = {
  id: 1,
  lead_type: 'investor',
  project_key: 'growing',
  name: 'Ada Seed',
  organization: 'Agent Infra Capital',
  role_title: 'Partner',
  public_profile_urls: ['https://example.com/ada'],
  contact_channels: [],
  source_kind: 'manual',
  source_url: 'https://example.com/ada',
  status: 'drafted',
  fit_score: 88,
  confidence_score: 75,
  risk_flags: [],
  evidence: [],
  metadata: {},
  next_action: 'Review draft',
  last_contacted_at: null,
  created_at: '2026-05-30T10:00:00',
  updated_at: '2026-05-30T10:00:00',
}

const provider = {
  ...investor,
  id: 2,
  lead_type: 'provider',
  name: 'Firecrawl',
  organization: 'Firecrawl',
  status: 'approved',
  contact_channels: [{ kind: 'email', value: 'partnerships@firecrawl.dev', confidence: 'high' }],
  metadata: {
    why_this_provider: 'Official MCP server for web search and scrape APIs.',
    contact_provenance: [{ source_url: 'https://docs.firecrawl.dev/partner-integration' }],
  },
}

function json(data: unknown, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(data) } as Response)
}

function listPayload(items: unknown[]) {
  return { items, total: items.length, limit: 100, offset: 0, status_counts: {}, lead_type_counts: {} }
}

function installFetch() {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push(`${init?.method || 'GET'} ${url}`)
    if (url.includes('/growth/overview')) {
      return json({ lead_counts: { investor: 1, provider: 1 }, message_counts: { needs_review: 1 }, ai_visibility: { cited: 1 }, discovery_counts: { listed: 1 } })
    }
    if (url.includes('/growth/source-configs/default-provider')) {
      return json({ id: 1, config_key: 'agent_api_mcp_provider_discovery', name: 'Provider Discovery: MCP + API Services', config_type: 'github_mcp_repos', status: 'enabled', description: 'Find providers', query: {}, cadence: {}, thresholds: {}, last_run_at: null, last_result: {}, created_at: null, updated_at: null })
    }
    if (url.includes('/growth/source-configs/1/run')) {
      return json({ id: 5, source_config_id: 1, status: 'succeeded', dry_run: init?.body && String(init.body).includes('"dry_run":true'), params: {}, candidate_count: 1, created_count: 1, reused_count: 0, drafted_count: 1, error_summary: '', result: { candidates: [{ name: 'Firecrawl' }] }, started_at: null, completed_at: null, created_at: null, updated_at: null })
    }
    if (url.includes('/growth/source-configs/1/runs')) {
      return json({ items: [{ id: 5, source_config_id: 1, status: 'succeeded', dry_run: false, params: {}, candidate_count: 1, created_count: 1, reused_count: 0, drafted_count: 1, error_summary: '', result: {}, started_at: null, completed_at: null, created_at: null, updated_at: null }], total: 1, limit: 50, offset: 0 })
    }
    if (url.includes('/growth/source-configs') && init?.method === 'POST') {
      return json({ id: 2, config_key: 'agent_api_mcp_provider_discovery', name: 'Provider Discovery: MCP + API Services', config_type: 'github_mcp_repos', status: 'enabled', description: 'Find providers', query: {}, cadence: {}, thresholds: {}, last_run_at: null, last_result: {}, created_at: null, updated_at: null }, 201)
    }
    if (url.includes('/growth/source-configs')) {
      return json({ items: [{ id: 1, config_key: 'agent_api_mcp_provider_discovery', name: 'Provider Discovery: MCP + API Services', config_type: 'github_mcp_repos', status: 'enabled', description: 'Find providers', query: {}, cadence: {}, thresholds: {}, last_run_at: null, last_result: { candidate_count: 1, created_count: 1, drafted_count: 1 }, created_at: null, updated_at: null }], total: 1 })
    }
    if (url.includes('/growth/leads/1') && !url.includes('draft-message')) {
      return json({
        lead: investor,
        messages: [{ id: 10, lead_id: 1, campaign_id: null, channel: 'email', subject: 'Hello', body: 'Draft body', personalization_evidence: [], status: 'needs_review', approved_by: null, sent_at: null, failure_reason: null, metadata: {}, created_at: null, updated_at: null }],
        events: [{ id: 1, lead_id: 1, message_id: 10, event_type: 'message_drafted', actor: 'agent', from_status: null, to_status: 'needs_review', summary: '', metadata: {}, created_at: null }],
      })
    }
    if (url.includes('/growth/leads/2') && !url.includes('draft-message')) {
      return json({
        lead: provider,
        messages: [{
          id: 20,
          lead_id: 2,
          campaign_id: null,
          channel: 'email',
          subject: 'Synapse provider fit for Firecrawl',
          body: 'Firecrawl could expose metered agent web-data calls through Synapse.',
          personalization_evidence: [],
          status: 'approved',
          approved_by: 'operator',
          sent_at: null,
          failure_reason: null,
          metadata: {
            contact_email: 'partnerships@firecrawl.dev',
            contact_provenance: [{ source_url: 'https://docs.firecrawl.dev/partner-integration' }],
            gmail_status: 'not_created',
          },
          created_at: null,
          updated_at: null,
        }],
        events: [],
      })
    }
    if (url.includes('/growth/leads') && init?.method === 'POST') return json({ ...investor, id: 3 }, 201)
    if (url.includes('/growth/leads?') && url.includes('provider')) return json(listPayload([provider]))
    if (url.includes('/growth/leads')) return json(listPayload([investor]))
    if (url.includes('/growth/messages/10/approve')) return json({ id: 10, lead_id: 1, status: 'approved', subject: 'Hello', body: 'Draft body', personalization_evidence: [], channel: 'email', campaign_id: null, approved_by: 'operator', sent_at: null, failure_reason: null, metadata: {}, created_at: null, updated_at: null })
    if (url.includes('/growth/messages/20/create-gmail-draft')) return json({ id: 20, lead_id: 2, status: 'queued', subject: 'Synapse provider fit for Firecrawl', body: 'Draft body', personalization_evidence: [], channel: 'email', campaign_id: null, approved_by: 'operator', sent_at: null, failure_reason: null, metadata: { gmail_status: 'draft_created', gmail_draft_id: 'draft-123', draft_url: 'https://mail.google.com/mail/u/0/#drafts?compose=draft-123', contact_email: 'partnerships@firecrawl.dev' }, created_at: null, updated_at: null })
    if (url.includes('/growth/ai-visibility/checks') && init?.method === 'POST') return json({ id: 2, query: 'agent API marketplace', platform: 'chatgpt', answer_summary: '', synapse_mentioned: false, synapse_cited: false, cited_urls: [], competitor_mentions: [], missing_facts: [], next_action: '', run_at: null, created_at: null, updated_at: null }, 201)
    if (url.includes('/growth/ai-visibility/checks')) return json({ items: [{ id: 1, query: 'MCP monetization platform', platform: 'perplexity', answer_summary: 'No citation', synapse_mentioned: false, synapse_cited: false, cited_urls: [], competitor_mentions: ['RapidAPI'], missing_facts: [], next_action: 'Create answer block', run_at: null, created_at: null, updated_at: null }], total: 1, limit: 100, offset: 0 })
    if (url.includes('/growth/discovery-listings') && init?.method === 'POST') return json({ id: 2, surface: 'glama', target_repo: '', package_name: '', listing_url: '', status: 'candidate', submission_evidence: {}, verification_evidence: {}, failure_reason: '', last_checked_at: null, created_at: null, updated_at: null }, 201)
    if (url.includes('/growth/discovery-listings')) return json({ items: [{ id: 1, surface: 'official_mcp_registry', target_repo: 'SynapseNetworkAI/Synapse-MCP', package_name: 'synapse-network-mcp', listing_url: 'https://registry.example/synapse', status: 'listed', submission_evidence: {}, verification_evidence: {}, failure_reason: '', last_checked_at: null, created_at: null, updated_at: null }], total: 1, limit: 100, offset: 0 })
    return json({})
  }))
  return calls
}

describe('GrowthPage', () => {
  beforeEach(() => {
    installFetch()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders lead tabs, metrics, creates a lead, and opens lead detail actions', async () => {
    const calls = installFetch()
    render(<GrowthPage />)

    await screen.findByText('Provider Source Configs')
    expect(screen.getByText('Growth')).toBeInTheDocument()
    expect(screen.getByText('AI cited')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Investors' }))
    await screen.findByText('Ada Seed')
    fireEvent.click(screen.getByRole('button', { name: '新增 Lead' }))
    const createDialog = await screen.findByRole('dialog', { name: /新增 investor lead/i })
    fireEvent.change(within(createDialog).getByPlaceholderText('investor name'), { target: { value: 'New Investor' } })
    fireEvent.click(within(createDialog).getByRole('button', { name: '创建 Lead' }))
    await waitFor(() => expect(calls.some((call) => call === 'POST /api/growth/leads')).toBe(true))

    fireEvent.click(screen.getByText('Ada Seed'))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Draft body')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: '批准' }))
    await waitFor(() => expect(calls.some((call) => call.includes('/api/growth/messages/10/approve'))).toBe(true))
  })

  it('renders provider, AI visibility, and MCP discovery workflows', async () => {
    const calls = installFetch()
    render(<GrowthPage />)

    fireEvent.click(screen.getByRole('button', { name: 'Providers' }))
    await screen.findByText('Firecrawl')
    fireEvent.click(screen.getByText('Firecrawl'))
    const providerDialog = await screen.findByRole('dialog')
    expect(within(providerDialog).getByText('partnerships@firecrawl.dev')).toBeInTheDocument()
    expect(within(providerDialog).getByText(/partner-integration/)).toBeInTheDocument()
    fireEvent.click(within(providerDialog).getByRole('button', { name: '创建 Gmail Draft' }))
    await waitFor(() => expect(calls.some((call) => call.includes('/api/growth/messages/20/create-gmail-draft'))).toBe(true))
    fireEvent.click(within(providerDialog).getByRole('button', { name: /关闭/i }))

    fireEvent.click(screen.getByRole('button', { name: 'AI Visibility' }))
    await screen.findByText('MCP monetization platform')
    fireEvent.click(screen.getByRole('button', { name: '新增 Check' }))
    const aiDialog = await screen.findByRole('dialog', { name: '新增 AI Visibility Check' })
    fireEvent.change(within(aiDialog).getByPlaceholderText('query'), { target: { value: 'agent API marketplace' } })
    fireEvent.click(within(aiDialog).getByRole('button', { name: '记录 Check' }))
    await waitFor(() => expect(calls.some((call) => call === 'POST /api/growth/ai-visibility/checks')).toBe(true))

    fireEvent.click(screen.getByRole('button', { name: 'MCP Discovery' }))
    await screen.findByText('official_mcp_registry')
    fireEvent.click(screen.getByRole('button', { name: '新增 Listing' }))
    const mcpDialog = await screen.findByRole('dialog', { name: '新增 MCP Discovery Listing' })
    fireEvent.change(within(mcpDialog).getByPlaceholderText('surface'), { target: { value: 'glama' } })
    fireEvent.click(within(mcpDialog).getByRole('button', { name: '记录 Listing' }))
    await waitFor(() => expect(calls.some((call) => call === 'POST /api/growth/discovery-listings')).toBe(true))
  })

  it('renders source configs and can run provider acquisition', async () => {
    const calls = installFetch()
    render(<GrowthPage />)

    await screen.findByText('Provider Source Configs')
    expect(screen.getByText('Provider Discovery: MCP + API Services')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Dry Run' }))
    await waitFor(() => expect(calls.some((call) => call.includes('/api/growth/source-configs/1/run'))).toBe(true))
    await screen.findByRole('dialog', { name: 'Provider Discovery: MCP + API Services' })
  })
})
