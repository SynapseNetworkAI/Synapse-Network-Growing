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
  name: 'MCP Weather API',
  organization: 'Weather Tools',
  status: 'new',
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
    if (url.includes('/growth/leads/1') && !url.includes('draft-message')) {
      return json({
        lead: investor,
        messages: [{ id: 10, lead_id: 1, campaign_id: null, channel: 'email', subject: 'Hello', body: 'Draft body', personalization_evidence: [], status: 'needs_review', approved_by: null, sent_at: null, failure_reason: null, metadata: {}, created_at: null, updated_at: null }],
        events: [{ id: 1, lead_id: 1, message_id: 10, event_type: 'message_drafted', actor: 'agent', from_status: null, to_status: 'needs_review', summary: '', metadata: {}, created_at: null }],
      })
    }
    if (url.includes('/growth/leads') && init?.method === 'POST') return json({ ...investor, id: 3 }, 201)
    if (url.includes('/growth/leads?') && url.includes('provider')) return json(listPayload([provider]))
    if (url.includes('/growth/leads')) return json(listPayload([investor]))
    if (url.includes('/growth/messages/10/approve')) return json({ id: 10, lead_id: 1, status: 'approved', subject: 'Hello', body: 'Draft body', personalization_evidence: [], channel: 'email', campaign_id: null, approved_by: 'operator', sent_at: null, failure_reason: null, metadata: {}, created_at: null, updated_at: null })
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

    await screen.findByText('Ada Seed')
    expect(screen.getByText('Growth')).toBeInTheDocument()
    expect(screen.getByText('AI cited')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('investor name'), { target: { value: 'New Investor' } })
    fireEvent.click(screen.getByRole('button', { name: '创建 Lead' }))
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
    await screen.findByText('MCP Weather API')

    fireEvent.click(screen.getByRole('button', { name: 'AI Visibility' }))
    await screen.findByText('MCP monetization platform')
    fireEvent.change(screen.getByPlaceholderText('query'), { target: { value: 'agent API marketplace' } })
    fireEvent.click(screen.getByRole('button', { name: '记录' }))
    await waitFor(() => expect(calls.some((call) => call === 'POST /api/growth/ai-visibility/checks')).toBe(true))

    fireEvent.click(screen.getByRole('button', { name: 'MCP Discovery' }))
    await screen.findByText('official_mcp_registry')
    fireEvent.change(screen.getByPlaceholderText('surface'), { target: { value: 'glama' } })
    fireEvent.click(screen.getByRole('button', { name: '记录' }))
    await waitFor(() => expect(calls.some((call) => call === 'POST /api/growth/discovery-listings')).toBe(true))
  })
})
