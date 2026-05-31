// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PublishingPage from './PublishingPage'

const apiMock = vi.hoisted(() => ({
  getSocialDistributionBoard: vi.fn(),
  getSocialDistributionTasks: vi.fn(),
  getSocialContentAssets: vi.fn(),
  getSocialContentAsset: vi.fn(),
  createSocialContentTask: vi.fn(),
  createSocialContentAsset: vi.fn(),
  generateSocialDistributionContentPlan: vi.fn(),
  generateSocialDistributionTasks: vi.fn(),
  approveAndGenerateSocialDistributionTasks: vi.fn(),
  generateSocialXReplyBlock: vi.fn(),
  publishSocialDistributionTaskToX: vi.fn(),
  updateSocialReply: vi.fn(),
  publishSocialReplyToX: vi.fn(),
  generateSocialReplyForRepostCandidate: vi.fn(),
  getSocialDistributionTaskXAuthStatus: vi.fn(),
  startSocialXOAuth: vi.fn(),
  markSocialDistributionTaskLive: vi.fn(),
  markSocialDistributionTaskRemoved: vi.fn(),
  updateSocialDistributionTask: vi.fn(),
  getDistributionAccounts: vi.fn(),
  updateDistributionAccount: vi.fn(),
  getSocialTrends: vi.fn(),
  getSocialPostMetricSummary: vi.fn(),
  createManualSocialPostMetric: vi.fn(),
  createXBrandWeekCampaignTemplate: vi.fn(),
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
    documents: [],
    tasks: [],
    events: [],
    reply_items: [],
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
    ...overrides,
  }
}

describe('PublishingPage v2 distribution workbench', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getSocialDistributionBoard.mockResolvedValue({
      columns: [
        { key: 'backlog', title: '待计划', description: 'Needs plan.', count: 0, cards: [] },
        { key: 'needs_review', title: '待审核', description: 'Plan ready.', count: 0, cards: [] },
        {
          key: 'ready_to_publish',
          title: '待发布',
          description: 'Ready.',
          count: 1,
          cards: [{
            id: 'asset:31',
            asset: asset(),
            column_key: 'ready_to_publish',
            task_count: 1,
            task_kind_code: 'content_distribution',
            task_kind_label: '通用内容发布',
            task_kind_action: 'approve_and_generate_platform_docs',
            document_count: 2,
            platform_count: 1,
            failed_count: 0,
            ready_to_publish_count: 1,
            live_count: 0,
            status_counts: { draft_ready: 1 },
            document_status_counts: { generated: 2 },
            next_action: 'Publish manually.',
            updated_at: '2026-05-01T00:00:00Z',
          }],
        },
        { key: 'live', title: '已发布', description: 'Live.', count: 0, cards: [] },
        { key: 'blocked', title: '异常', description: 'Blocked.', count: 0, cards: [] },
      ],
      summary: { total_assets: 1, total_tasks: 1, total_documents: 2 },
      generated_at: '2026-05-01T00:00:00Z',
    })
    apiMock.getSocialDistributionTasks.mockResolvedValue({
      groups: [{ asset: asset(), tasks: [task()] }],
      flat: [task()],
      total_assets: 1,
      total_tasks: 1,
    })
    apiMock.getSocialContentAssets.mockResolvedValue([asset()])
    apiMock.getSocialContentAsset.mockResolvedValue({ ...asset(), tasks: [task()], events: [], documents: [] })
    apiMock.createSocialContentTask.mockResolvedValue({ ...asset(), source_type: 'manual_task', tasks: [], events: [], documents: [] })
    apiMock.createSocialContentAsset.mockResolvedValue({ ...asset(), tasks: [], events: [], documents: [] })
    apiMock.generateSocialDistributionContentPlan.mockResolvedValue({ ...asset(), tasks: [], events: [], documents: [] })
    apiMock.generateSocialDistributionTasks.mockResolvedValue({
      asset: { ...asset(), tasks: [task()], events: [], documents: [] },
      results: [{ account_id: 11, platform: 'devto', channel_key: 'dev.to', status: 'generated', task_id: 21, error: null }],
      generated_task_ids: [21],
      failed_task_ids: [],
    })
    apiMock.getDistributionAccounts.mockResolvedValue([account()])
    apiMock.updateDistributionAccount.mockResolvedValue(account())
    apiMock.getSocialTrends.mockResolvedValue([])
    apiMock.getSocialPostMetricSummary.mockResolvedValue({
      observed_post_count: 0,
      metric_row_count: 0,
      total_impressions: 0,
      total_likes: 0,
      total_replies: 0,
      total_reposts: 0,
      total_link_clicks: 0,
      total_profile_visits: 0,
      total_bookmarks: 0,
      average_engagement: 0,
      top_posts: [],
      last_observed_at: null,
      diagnostic: 'No metrics yet.',
    })
  })

  it('renders only the v2 operator tabs and task board by asset', async () => {
    render(<PublishingPage />)

    expect(await screen.findByText('多渠道分发中心')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tasks' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Signals & Metrics' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Assets' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '今日队列' })).not.toBeInTheDocument()
    expect(await screen.findByText('How AI agents should pay for APIs')).toBeInTheDocument()
    expect(screen.getByTestId('distribution-board-column-ready_to_publish')).toBeInTheDocument()
  })

  it('opens the dedicated X reply task detail without long-form publishing sections', async () => {
    const replyDetail = {
      ...asset({
        id: 44,
        asset_type: 'reply',
        title: 'X Week 1 Reply Block Day 5',
        agent_metadata: {
          post_intent: 'engagement_reply',
          target_platforms: ['x'],
          reply_block: {
            reply_ids: [91],
            source_candidate_ids: [81],
            publish_mode: 'agent_approved_needs_manual_publish',
            approval_ref_configured: false,
            auto_publish: false,
            reply_source_strategy: 'agent_economy_monetization',
          },
        },
      }),
      tasks: [],
      documents: [{
        id: 71,
        asset_id: 44,
        task_id: null,
        document_kind: 'source_plan',
        platform: null,
        channel_key: null,
        title: 'Reply plan',
        body_markdown: 'Paste 5 real X URLs and generate value-add replies.',
        status: 'generated',
        version: 1,
        metadata: {},
        created_at: '2026-05-01T00:00:00Z',
        updated_at: '2026-05-01T00:00:00Z',
      }],
      reply_items: [{
        id: 91,
        platform: 'x',
        external_reply_id: 'target:123',
        source_candidate_id: 81,
        source_post_id: '123',
        source_author_handle: 'OpenAI',
        source_text: 'Tool-using agents need safer ways to call external APIs.',
        author_handle: 'SynapseNetworkAI',
        incoming_text: 'Tool-using agents need safer ways to call external APIs.',
        intent: 'engagement_reply',
        suggested_reply: 'One concrete control I like here: give agents credential scopes, budgets, and receipts before they touch paid APIs.',
        generation_reason: 'Specific and non-promotional.',
        risk_level: 'normal',
        status: 'agent_approved_needs_manual_publish',
        source_url: 'https://x.com/OpenAI/status/123',
        published_external_post_id: null,
        reviewed_by: 'agent',
        failure_summary: null,
        metadata: {
          agent_quality_review: { status: 'passed' },
          x_reply_compliance: { approval_ref_configured: false },
          x_reply_source_strategy: {
            strategy: 'agent_economy_monetization',
            source_bucket: 'direct_pain',
            reply_angle: 'budget_cap',
            matched_keywords: ['agent', 'payment'],
          },
          model: 'test-reply-model',
        },
        created_at: '2026-05-01T00:00:00Z',
        updated_at: '2026-05-01T00:00:00Z',
      }],
    }
    apiMock.getSocialDistributionBoard.mockResolvedValue({
      columns: [
        { key: 'backlog', title: '待计划', description: 'Needs plan.', count: 0, cards: [] },
        {
          key: 'needs_review',
          title: '待审核',
          description: 'Plan ready.',
          count: 1,
          cards: [{
            id: 'asset:44',
            asset: replyDetail,
            column_key: 'needs_review',
            task_kind_code: 'x_reply_block',
            task_kind_label: 'X 回复',
            task_kind_action: 'generate_x_reply_candidates',
            task_count: 0,
            document_count: 1,
            platform_count: 0,
            failed_count: 0,
            ready_to_publish_count: 0,
            live_count: 0,
            status_counts: {},
            document_status_counts: { generated: 1 },
            next_action: '生成 5 条 X 回复候选。',
            updated_at: '2026-05-01T00:00:00Z',
          }],
        },
        { key: 'ready_to_publish', title: '待发布', description: 'Ready.', count: 0, cards: [] },
        { key: 'live', title: '已发布', description: 'Live.', count: 0, cards: [] },
        { key: 'blocked', title: '异常', description: 'Blocked.', count: 0, cards: [] },
      ],
      summary: { total_assets: 1, total_tasks: 0, total_documents: 1 },
      generated_at: '2026-05-01T00:00:00Z',
    })
    apiMock.getSocialContentAsset.mockResolvedValue(replyDetail)

    render(<PublishingPage />)
    expect(await screen.findByText('任务类型是互斥过滤；每张卡只属于一个类型。看板列表示生命周期状态，不是分类。')).toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: /通用内容发布/ }))
    expect(screen.queryByText('X Week 1 Reply Block Day 5')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /X 回复/ }))
    expect(await screen.findByText('X Week 1 Reply Block Day 5')).toBeInTheDocument()
    await userEvent.click(await screen.findByText('X Week 1 Reply Block Day 5'))

    expect(await screen.findByText('Reply Candidates')).toBeInTheDocument()
    expect(screen.getByText('123')).toBeInTheDocument()
    expect(screen.getByText(/credential scopes, budgets, and receipts/)).toBeInTheDocument()
    expect(screen.getByText('manual publish required')).toBeInTheDocument()
    expect(screen.getAllByText('bucket: direct_pain')).toHaveLength(2)
    expect(screen.getAllByText('angle: budget_cap')).toHaveLength(2)
    expect(screen.getByText('matched: agent, payment')).toBeInTheDocument()
    expect(screen.getByText('source strategy: agent_economy_monetization')).toBeInTheDocument()
    expect(screen.queryByText('Canonical Article')).not.toBeInTheDocument()
    expect(screen.queryByText('Platform Docs')).not.toBeInTheDocument()
    expect(screen.queryByText('Channel Selection')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '通过 X API 发布' })).not.toBeInTheDocument()
  })
})
