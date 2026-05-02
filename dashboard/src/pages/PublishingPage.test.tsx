// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PublishingPage from './PublishingPage'

const apiMock = vi.hoisted(() => ({
  getSocialDistributionTasks: vi.fn(),
  getSocialContentAssets: vi.fn(),
  getSocialContentAsset: vi.fn(),
  createSocialContentAsset: vi.fn(),
  generateSocialDistributionTasks: vi.fn(),
  getDistributionAccounts: vi.fn(),
  updateDistributionAccount: vi.fn(),
  getSocialTrends: vi.fn(),
  getSocialPostMetricSummary: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

function account(overrides: Record<string, unknown> = {}) {
  return {
    id: 11,
    platform: 'devto',
    channel_key: 'dev.to',
    display_name: 'DEV Community',
    signup_url: 'https://dev.to/enter',
    profile_url: null,
    account_type: 'official_author',
    priority: 'P1',
    status: 'active',
    email_hint: null,
    two_factor_status: 'enabled',
    read_automation_mode: 'manual_only',
    human_publish_required: true,
    notes: 'Long-form developer tutorials.',
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
    ...overrides,
  }
}

function task(overrides: Record<string, unknown> = {}) {
  return {
    id: 21,
    asset_id: 31,
    account_id: 11,
    platform: 'devto',
    channel_key: 'dev.to',
    action: 'post',
    account_display_name: 'DEV Community',
    signup_url: 'https://dev.to/enter',
    status: 'draft_ready',
    platform_title: 'How AI agents should pay for APIs',
    platform_body: 'A practical developer guide to agent-native payment rails.',
    operator_checklist: 'Human Gate required.',
    submission_url: 'https://dev.to/enter',
    published_url: null,
    external_post_id: null,
    failure_summary: null,
    manual_result_note: null,
    metadata: {},
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
    ...overrides,
  }
}

function asset(overrides: Record<string, unknown> = {}) {
  return {
    id: 31,
    asset_type: 'article',
    source_type: 'manual',
    title: 'How AI agents should pay for APIs',
    body: 'Long-form article body.',
    summary: 'A practical developer guide to agent-native payment rails.',
    canonical_url: 'https://docs.synapse-network.ai/agent-payments',
    source_signal_id: null,
    goal_key: 'growth_social_conversion_loop',
    policy_check: {},
    agent_metadata: {},
    status: 'ready',
    created_by: 'operator',
    task_count: 1,
    status_counts: { draft_ready: 1 },
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
    ...overrides,
  }
}

describe('PublishingPage v2 distribution workbench', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getSocialDistributionTasks.mockResolvedValue({
      groups: [{ asset: asset(), tasks: [task()] }],
      flat: [task()],
      total_assets: 1,
      total_tasks: 1,
    })
    apiMock.getSocialContentAssets.mockResolvedValue([asset()])
    apiMock.getSocialContentAsset.mockResolvedValue({ ...asset(), tasks: [task()], events: [] })
    apiMock.createSocialContentAsset.mockResolvedValue({ ...asset(), tasks: [], events: [] })
    apiMock.generateSocialDistributionTasks.mockResolvedValue({
      asset: { ...asset(), tasks: [task()], events: [] },
      results: [{ account_id: 11, platform: 'devto', channel_key: 'dev.to', status: 'generated', task_id: 21, error: null }],
      generated_task_ids: [21],
      failed_task_ids: [],
    })
    apiMock.getDistributionAccounts.mockResolvedValue([account()])
    apiMock.updateDistributionAccount.mockResolvedValue(account())
    apiMock.getSocialTrends.mockResolvedValue([])
    apiMock.getSocialPostMetricSummary.mockResolvedValue({
      observed_post_count: 0,
      total_impressions: 0,
      total_likes: 0,
      total_replies: 0,
      total_reposts: 0,
      total_link_clicks: 0,
      last_observed_at: null,
      diagnostic: 'No metrics yet.',
    })
  })

  it('renders only the four v2 tabs and grouped tasks by asset', async () => {
    render(<PublishingPage />)

    expect(await screen.findByText('多渠道分发中心')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tasks' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Signals & Metrics' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Assets' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '今日队列' })).not.toBeInTheDocument()
    expect(await screen.findByText('How AI agents should pay for APIs')).toBeInTheDocument()
    expect(screen.getByText(/1 tasks/)).toBeInTheDocument()
  })

  it('switches to assets and creates the source asset before task generation', async () => {
    const user = userEvent.setup()
    render(<PublishingPage />)

    await user.click(screen.getByRole('button', { name: 'Assets' }))
    expect(await screen.findByRole('button', { name: '创建内容资产' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '创建内容资产' }))
    await user.type(screen.getByLabelText('标题'), 'Agent payment rails launch note')
    await user.click(screen.getByRole('button', { name: '创建' }))

    expect(apiMock.createSocialContentAsset).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Agent payment rails launch note', source_type: 'manual' }),
    )
  })
})
