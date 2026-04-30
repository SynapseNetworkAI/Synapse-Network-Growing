// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../components/workbench'
import PublishingPage from './PublishingPage'

const apiMock = vi.hoisted(() => ({
  getSocialAccounts: vi.fn(),
  getSocialOpsOverview: vi.fn(),
  getSocialCampaignGoals: vi.fn(),
  createSocialCampaignGoal: vi.fn(),
  getSocialTrends: vi.fn(),
  getSocialWatchlist: vi.fn(),
  getSocialReplies: vi.fn(),
  updateSocialReply: vi.fn(),
  publishSocialReplyToX: vi.fn(),
  getSocialRepostCandidates: vi.fn(),
  generateSocialReplyForRepostCandidate: vi.fn(),
  publishSocialRepostCandidateToX: vi.fn(),
  getSocialPostMetrics: vi.fn(),
  getSocialPostMetricSummary: vi.fn(),
  getSocialPosts: vi.fn(),
  getSocialPost: vi.fn(),
  startSocialXOAuth: vi.fn(),
  createSocialPost: vi.fn(),
  generateSocialPostDraft: vi.fn(),
  updateSocialPost: vi.fn(),
  publishSocialPostToX: vi.fn(),
  regenerateSocialPostImage: vi.fn(),
  removeSocialPostMedia: vi.fn(),
  uploadSocialPostImage: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

function draft(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    platform: 'x',
    account_id: 1,
    source_type: 'manual_prompt',
    account_handle: 'SynapseNetworkA',
    account_display_name: 'Synapse Network',
    title: 'Build note',
    body_text: 'Synapse Agent Ops now has a human-gated X publishing surface.',
    status: 'approved',
    generated_by: 'social_content_agent_v1',
    reviewed_by: 'operator',
    review_note: null,
    target_audience: 'legacy builders',
    cta: 'legacy follow',
    agent_rationale: 'legacy rationale',
    policy_check: { status: 'passed', character_count: 67, warnings: [], blocked_reasons: [] },
    raw_agent_output: { source: 'test', prompt_excerpt: 'Write a concise launch note about staging governance.', style_type: 'marketing' },
    published_at: null,
    external_post_id: null,
    external_url: null,
    failure_summary: null,
    media_assets: [],
    events: [],
    created_at: '2026-04-25T00:00:00Z',
    updated_at: '2026-04-25T00:00:00Z',
    ...overrides,
  }
}

function reply(overrides: Record<string, unknown> = {}) {
  return {
    id: 41,
    platform: 'x',
    external_reply_id: 'target:777',
    source_candidate_id: 31,
    source_post_id: '777',
    source_author_handle: 'OpenAI',
    source_text: 'AI agents increasingly need reliable tool access and payment primitives.',
    author_handle: 'OpenAI',
    incoming_text: 'AI agents increasingly need reliable tool access and payment primitives.',
    intent: 'growth_reply',
    suggested_reply: 'Agentic products also need governed access, budgets, and settlement rails when tools become paid services.',
    generation_reason: 'Generated from a real X repost candidate with a payment-rails angle.',
    risk_level: 'normal',
    status: 'needs_review',
    source_url: 'https://x.com/OpenAI/status/777',
    published_external_post_id: null,
    reviewed_by: null,
    failure_summary: null,
    metadata: { generated_by: 'social_reply_agent_v1', model: 'test-reply-model', human_gate_required: true, auto_publish: false },
    created_at: '2026-04-25T00:00:00Z',
    updated_at: '2026-04-25T00:00:00Z',
    ...overrides,
  }
}

function renderPage() {
  return render(
    <ToastProvider>
      <PublishingPage />
    </ToastProvider>,
  )
}

describe('PublishingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getSocialAccounts.mockResolvedValue([
      {
        id: 1,
        platform: 'x',
        handle: 'SynapseNetworkA',
        display_name: 'Synapse Network',
        secret_ref: 'x-official-oauth2-user-token',
        status: 'active',
        auth_status: 'authorized',
        auth_message: 'OAuth refresh token is configured.',
        created_at: '2026-04-25T00:00:00Z',
        updated_at: '2026-04-25T00:00:00Z',
      },
    ])
    apiMock.getSocialOpsOverview.mockResolvedValue({
      active_goal_count: 1,
      draft_queue_count: 1,
      needs_review_count: 0,
      trend_count: 1,
      reply_needs_review_count: 0,
      repost_candidate_count: 0,
      published_count: 0,
      daily_planner_target_count: 3,
      daily_planner_active_count: 1,
      daily_planner_local_date: '2026-04-25',
      daily_planner_active_post_ids: [7],
      human_gate_required: true,
      safety_summary: 'Agent drafts; humans publish.',
    })
    apiMock.getSocialCampaignGoals.mockResolvedValue([
      {
        id: 1,
        platform: 'x',
        title: 'Build trust for Synapse Network official X',
        objective: 'Explain Synapse Network to AI agent builders.',
        status: 'active',
        cadence: 'daily',
        content_pillars: ['Product education'],
        success_metrics: ['engagement rate'],
        created_by: 'system_seed',
        created_at: '2026-04-25T00:00:00Z',
        updated_at: '2026-04-25T00:00:00Z',
      },
    ])
    apiMock.createSocialCampaignGoal.mockResolvedValue({})
    apiMock.getSocialTrends.mockResolvedValue([
      {
        id: 1,
        source_platform: 'x',
        source_url: null,
        author_handle: null,
        topic: 'AI agents need payment rails',
        summary: 'Agent builders increasingly need budgeted API access.',
        relevance_score: 0.82,
        status: 'new',
        collected_at: '2026-04-25T00:00:00Z',
        updated_at: '2026-04-25T00:00:00Z',
      },
    ])
    apiMock.getSocialWatchlist.mockResolvedValue([
      {
        id: 1,
        platform: 'x',
        handle: 'LangChainAI',
        display_name: 'LangChain',
        category: 'agent_framework',
        rationale: 'Agent framework builders are a primary Synapse audience.',
        status: 'active',
        last_checked_at: null,
        latest_summary: 'Not synced yet.',
        updated_at: '2026-04-25T00:00:00Z',
      },
    ])
    apiMock.getSocialReplies.mockResolvedValue([])
    apiMock.updateSocialReply.mockResolvedValue(reply({ status: 'approved', reviewed_by: 'operator' }))
    apiMock.publishSocialReplyToX.mockResolvedValue(reply({ status: 'published', published_external_post_id: '1800000000000000777', reviewed_by: 'operator' }))
    apiMock.getSocialRepostCandidates.mockResolvedValue([])
    apiMock.generateSocialReplyForRepostCandidate.mockResolvedValue(reply())
    apiMock.getSocialPostMetrics.mockResolvedValue([])
    apiMock.getSocialPostMetricSummary.mockResolvedValue({
      observed_post_count: 0,
      metric_row_count: 0,
      total_impressions: 0,
      total_likes: 0,
      total_replies: 0,
      total_reposts: 0,
      total_link_clicks: 0,
      average_engagement: 0,
      top_posts: [],
      last_observed_at: null,
      diagnostic: 'No X post metrics recorded yet.',
    })
    apiMock.getSocialPosts.mockResolvedValue([draft()])
    apiMock.getSocialPost.mockResolvedValue(draft({
      events: [
        {
          id: 1,
          post_id: 7,
          event_type: 'draft_generated',
          actor: 'social_content_agent_v1',
          summary: 'Agent generated title and body.',
          payload: { prompt_excerpt: 'Write a concise launch note about staging governance.' },
          created_at: '2026-04-25T00:01:00Z',
        },
        {
          id: 2,
          post_id: 7,
          event_type: 'published',
          actor: 'operator',
          summary: 'Published to X as post 1801.',
          payload: { external_post_id: '1801' },
          created_at: '2026-04-25T00:02:00Z',
        },
      ],
    }))
    apiMock.startSocialXOAuth.mockResolvedValue({ auth_url: 'https://twitter.com/i/oauth2/authorize?state=test', state: 'test', expires_at: '2026-04-25T00:10:00Z' })
    apiMock.createSocialPost.mockResolvedValue(draft({ id: 8 }))
    apiMock.generateSocialPostDraft.mockResolvedValue(draft({ id: 8, status: 'approved', generated_by: 'social_content_agent_v1', reviewed_by: 'operator' }))
    apiMock.updateSocialPost.mockResolvedValue(draft({ status: 'approved' }))
    apiMock.publishSocialPostToX.mockResolvedValue(draft({ status: 'published', external_post_id: '1801', external_url: 'https://x.com/SynapseNetworkA/status/1801' }))
    apiMock.regenerateSocialPostImage.mockResolvedValue(draft())
    apiMock.removeSocialPostMedia.mockResolvedValue(draft())
    apiMock.uploadSocialPostImage.mockResolvedValue(draft({
      media_assets: [{
        id: 4,
        post_id: 7,
        media_type: 'image',
        status: 'ready',
        prompt: 'manual_upload',
        alt_text: 'Operator uploaded launch graphic.',
        preview_url: '/api/social/media/4/preview',
        x_media_id: null,
        failure_summary: null,
        created_at: '2026-04-25T00:00:00Z',
        updated_at: '2026-04-25T00:00:00Z',
      }],
    }))
  })

  it('shows the minimal generated draft surface and hides legacy content metadata', async () => {
    renderPage()

    expect(await screen.findByText('官方账号内容发布')).toBeInTheDocument()
    expect(screen.getByText('Build trust for Synapse Network official X')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '趋势雷达' })).toBeInTheDocument()
    expect(screen.getByText('Synapse Agent Ops now has a human-gated X publishing surface.')).toBeInTheDocument()
    expect(screen.getByText('#7')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '详情' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '发布到 X' })).toBeInTheDocument()
    expect(screen.queryByText('目标受众')).not.toBeInTheDocument()
    expect(screen.queryByText('CTA')).not.toBeInTheDocument()
    expect(screen.queryByText('Agent 生成理由')).not.toBeInTheDocument()
    expect(screen.queryByText('legacy builders')).not.toBeInTheDocument()
    expect(screen.queryByText('legacy follow')).not.toBeInTheDocument()
    expect(screen.queryByText('legacy rationale')).not.toBeInTheDocument()
    expect(screen.getByText('第 1 / 1 页 · 共 1 条草稿 · 今日库存视图')).toBeInTheDocument()
  })

  it('defaults the queue to today active daily planner inventory and keeps history separate', async () => {
    const user = userEvent.setup()
    apiMock.getSocialPosts.mockResolvedValue([
      draft({
        id: 25,
        source_type: 'daily_planner',
        title: 'Today product-change draft',
        status: 'needs_review',
        raw_agent_output: {
          source: 'x_social_daily_content_planner',
          planner_local_date: '2026-04-25',
          planner_slot: 1,
          planner_run_key: 'x_daily:1:2026-04-25:slot-1',
        },
        created_at: '2026-04-25T02:00:00Z',
        updated_at: '2026-04-25T02:00:00Z',
      }),
      draft({
        id: 24,
        source_type: 'daily_planner',
        title: 'Historical backlog draft',
        status: 'needs_review',
        raw_agent_output: {
          source: 'x_social_daily_content_planner',
          planner_local_date: '2026-04-24',
          planner_slot: 3,
          planner_run_key: 'x_daily:1:2026-04-24:slot-3',
        },
        created_at: '2026-04-24T02:00:00Z',
        updated_at: '2026-04-24T02:00:00Z',
      }),
    ])

    renderPage()

    expect(await screen.findByText('Today product-change draft')).toBeInTheDocument()
    expect(screen.getByText('Daily planner · 2026-04-25 · slot 1')).toBeInTheDocument()
    expect(screen.queryByText('Historical backlog draft')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '全部历史' }))

    expect(screen.getByText('Historical backlog draft')).toBeInTheDocument()
    expect(screen.getByText('Daily planner · 2026-04-24 · slot 3')).toBeInTheDocument()
  })

  it('opens a centered detail modal with full process timeline and result data', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '详情' }))

    await waitFor(() => expect(apiMock.getSocialPost).toHaveBeenCalledWith(7))
    expect(screen.getByRole('dialog', { name: '内容草稿 #7' })).toBeInTheDocument()
    expect(screen.getByText('任务过程 Timeline')).toBeInTheDocument()
    expect(screen.getByText('draft_generated')).toBeInTheDocument()
    expect(screen.getByText('published')).toBeInTheDocument()
    expect(screen.getByText('Agent generated title and body.')).toBeInTheDocument()
    expect(screen.getByText('Debug metadata')).toBeInTheDocument()
    expect(screen.queryByText('Drawer')).not.toBeInTheDocument()
  })

  it('shows social ops trend radar and watchlist without publishing actions', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '趋势雷达' }))

    expect(screen.getByText('AI agents need payment rails')).toBeInTheDocument()
    expect(screen.getByText('Agent builders increasingly need budgeted API access.')).toBeInTheDocument()
    expect(screen.getByText('来源：本地趋势种子')).toBeInTheDocument()
    expect(screen.getByText('@LangChainAI')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '查看全部趋势' })).toHaveAttribute('href', '/publishing/trends')
    expect(screen.queryByRole('button', { name: '发布到 X' })).not.toBeInTheDocument()
  })

  it('shows repost candidates as a paginated list and requires confirmation before quote publishing', async () => {
    const user = userEvent.setup()
    apiMock.getSocialRepostCandidates.mockResolvedValue([
      {
        id: 31,
        platform: 'x',
        source_url: 'https://x.com/OpenAI/status/100',
        author_handle: 'OpenAI',
        source_text: 'AI agents increasingly need reliable tool access and payment primitives.',
        suggested_quote: 'This is exactly why agent-native payment rails matter: builders need budgeted API access without manual billing glue.',
        relevance_score: 0.91,
        status: 'candidate',
        updated_at: '2026-04-25T00:00:00Z',
      },
    ])
    apiMock.publishSocialRepostCandidateToX.mockResolvedValue({
      id: 31,
      platform: 'x',
      source_url: 'https://x.com/OpenAI/status/100',
      author_handle: 'OpenAI',
      source_text: 'AI agents increasingly need reliable tool access and payment primitives.',
      suggested_quote: 'This is exactly why agent-native payment rails matter: builders need budgeted API access without manual billing glue.',
      relevance_score: 0.91,
      status: 'published',
      updated_at: '2026-04-25T00:00:00Z',
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: '转发候选' }))
    expect(screen.getByText('第 1 / 1 页 · 共 1 条候选')).toBeInTheDocument()
    expect(screen.getByText('@OpenAI')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '详情' }))

    expect(screen.getByRole('dialog', { name: '转发 / 引用候选 #31' })).toBeInTheDocument()
    expect(screen.getAllByText('AI agents increasingly need reliable tool access and payment primitives.').length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: '引用发布到 X' }))
    expect(screen.getByText(/公开发布 Agent 拟写的引用文案/)).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: '引用发布到 X' }).at(-1)!)

    await waitFor(() => {
      expect(apiMock.publishSocialRepostCandidateToX).toHaveBeenCalledWith(31, { actor: 'operator', action: 'quote' })
    })
  })

  it('allows direct link repost from the repost candidate list after confirmation', async () => {
    const user = userEvent.setup()
    apiMock.getSocialRepostCandidates.mockResolvedValue([
      {
        id: 32,
        platform: 'x',
        source_url: 'https://x.com/NVIDIAAI/status/200',
        author_handle: 'NVIDIAAI',
        source_text: 'Agentic tools need reliable infrastructure.',
        suggested_quote: 'Agent-native infrastructure needs payment and access rails.',
        relevance_score: 0.88,
        status: 'candidate',
        updated_at: '2026-04-25T00:00:00Z',
      },
    ])
    apiMock.publishSocialRepostCandidateToX.mockResolvedValue({
      id: 32,
      platform: 'x',
      source_url: 'https://x.com/NVIDIAAI/status/200',
      author_handle: 'NVIDIAAI',
      source_text: 'Agentic tools need reliable infrastructure.',
      suggested_quote: 'Agent-native infrastructure needs payment and access rails.',
      relevance_score: 0.88,
      status: 'published',
      updated_at: '2026-04-25T00:00:00Z',
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: '转发候选' }))
    await user.click(await screen.findByRole('button', { name: '转发到 X' }))

    expect(screen.getByText(/公开发布原帖链接/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '转发链接到 X' }))

    await waitFor(() => {
      expect(apiMock.publishSocialRepostCandidateToX).toHaveBeenCalledWith(32, { actor: 'operator', action: 'repost' })
    })
  })

  it('generates a human-reviewed reply draft from a repost candidate', async () => {
    const user = userEvent.setup()
    apiMock.getSocialRepostCandidates.mockResolvedValue([
      {
        id: 31,
        platform: 'x',
        source_url: 'https://x.com/OpenAI/status/777',
        author_handle: 'OpenAI',
        source_text: 'AI agents increasingly need reliable tool access and payment primitives.',
        suggested_quote: 'Agent-native infrastructure needs payment and access rails.',
        relevance_score: 0.91,
        status: 'candidate',
        updated_at: '2026-04-25T00:00:00Z',
      },
    ])
    apiMock.generateSocialReplyForRepostCandidate.mockResolvedValue(reply())
    renderPage()

    await user.click(await screen.findByRole('button', { name: '转发候选' }))
    await user.click(await screen.findByRole('button', { name: '生成回帖' }))

    await waitFor(() => {
      expect(apiMock.generateSocialReplyForRepostCandidate).toHaveBeenCalledWith(31, { actor: 'operator' })
    })
    expect(screen.getByRole('dialog', { name: '回帖草稿 #41' })).toBeInTheDocument()
    expect(screen.getByLabelText('Agent 回帖草稿')).toHaveValue('Agentic products also need governed access, budgets, and settlement rails when tools become paid services.')
    expect(screen.getByText('Human Gate：点击“回复到 X”会代表 @SynapseNetworkA 公开评论该原帖。系统不会自动点赞、关注、删除或私信。')).toBeInTheDocument()
  })

  it('publishes an approved reply only after confirmation', async () => {
    const user = userEvent.setup()
    apiMock.getSocialReplies.mockResolvedValue([reply({ status: 'approved', reviewed_by: 'operator' })])
    apiMock.publishSocialReplyToX.mockResolvedValue(reply({ status: 'published', published_external_post_id: '1800000000000000777', reviewed_by: 'operator' }))
    renderPage()

    await user.click(await screen.findByRole('button', { name: '回帖处理' }))
    await user.click(await screen.findByRole('button', { name: '详情' }))
    const reviewDialog = screen.getByRole('dialog', { name: '回帖草稿 #41' })
    await user.click(within(reviewDialog).getByRole('button', { name: '回复到 X' }))

    expect(screen.getByText('确认回复到 X')).toBeInTheDocument()
    expect(screen.getByText(/公开评论该 X 原帖/)).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: '回复到 X' }).at(-1)!)

    await waitFor(() => {
      expect(apiMock.updateSocialReply).toHaveBeenCalledWith(41, {
        suggested_reply: 'Agentic products also need governed access, budgets, and settlement rails when tools become paid services.',
        status: 'approved',
        reviewed_by: 'operator',
      })
      expect(apiMock.publishSocialReplyToX).toHaveBeenCalledWith(41, { actor: 'operator' })
    })
  })

  it('allows retry after reconnecting failed reply authentication', async () => {
    const user = userEvent.setup()
    apiMock.getSocialReplies.mockResolvedValue([
      reply({
        status: 'failed',
        failure_summary: 'X reply authentication failed. Reconnect the X official account and approve the tweet.write scope.',
        metadata: { publish_failure_kind: 'x_reply_auth_failed' },
      }),
    ])
    renderPage()

    await user.click(await screen.findByRole('button', { name: '回帖处理' }))
    expect(await screen.findByRole('button', { name: '重新发送' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重新连接 X 官方账号' })).not.toBeInTheDocument()
  })

  it('shows view reply instead of generating duplicate replies for handled candidates', async () => {
    const user = userEvent.setup()
    apiMock.getSocialRepostCandidates.mockResolvedValue([
      {
        id: 31,
        platform: 'x',
        source_url: 'https://x.com/OpenAI/status/777',
        author_handle: 'OpenAI',
        source_text: 'AI agents increasingly need reliable tool access and payment primitives.',
        suggested_quote: 'Agent-native infrastructure needs payment and access rails.',
        relevance_score: 0.91,
        status: 'candidate',
        updated_at: '2026-04-25T00:00:00Z',
      },
    ])
    apiMock.getSocialReplies.mockResolvedValue([reply()])
    renderPage()

    await user.click(await screen.findByRole('button', { name: '转发候选' }))

    expect(screen.getByRole('button', { name: '查看回帖' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '生成回帖' })).not.toBeInTheDocument()
  })

  it('hides direct repost for local seeds and already published candidates', async () => {
    const user = userEvent.setup()
    apiMock.getSocialRepostCandidates.mockResolvedValue([
      {
        id: 33,
        platform: 'x',
        source_url: null,
        author_handle: 'unknown',
        source_text: 'Local seed inspiration only.',
        suggested_quote: 'Local seed should not be reposted.',
        relevance_score: 0.75,
        status: 'candidate',
        updated_at: '2026-04-25T00:00:00Z',
      },
      {
        id: 34,
        platform: 'x',
        source_url: 'https://x.com/OpenAI/status/300',
        author_handle: 'OpenAI',
        source_text: 'Already published source.',
        suggested_quote: 'Already handled.',
        relevance_score: 0.91,
        status: 'published',
        updated_at: '2026-04-25T00:00:00Z',
      },
    ])
    renderPage()

    await user.click(await screen.findByRole('button', { name: '转发候选' }))

    expect(screen.queryByRole('button', { name: '转发到 X' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '详情' })).toHaveLength(2)
  })

  it('shows generated image thumbnails and includes image count in publish confirmation', async () => {
    const user = userEvent.setup()
    apiMock.getSocialPosts.mockResolvedValue([draft({
      media_assets: [{
        id: 3,
        post_id: 7,
        media_type: 'image',
        status: 'ready',
        prompt: 'A polished AI settlement network visual.',
        alt_text: 'Abstract AI agents connected through a settlement layer.',
        preview_url: '/api/social/media/3/preview',
        x_media_id: null,
        failure_summary: null,
        created_at: '2026-04-25T00:00:00Z',
        updated_at: '2026-04-25T00:00:00Z',
      }],
    })])
    renderPage()

    expect(await screen.findByText('图片已生成')).toBeInTheDocument()
    expect(screen.getByAltText('Abstract AI agents connected through a settlement layer.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '发布到 X' }))
    expect(screen.getByText(/并附带 1 张图片/)).toBeInTheDocument()
  })

  it('does not show a publish action when policy blocks a generated draft', async () => {
    const user = userEvent.setup()
    apiMock.getSocialPosts.mockResolvedValue([draft({
      status: 'needs_review',
      body_text: 'Guaranteed risk-free returns. Send funds now.',
      policy_check: { status: 'blocked', character_count: 45, warnings: [], blocked_reasons: ['guaranteed_return'] },
    })])
    renderPage()

    expect(await screen.findByText(/Blocked: guaranteed_return/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '发布到 X' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '拒绝' }))
    await waitFor(() => expect(apiMock.updateSocialPost).toHaveBeenCalledWith(7, { status: 'rejected', reviewed_by: 'operator' }))
  })

  it('shows an explicit review approval action for needs-review safe drafts', async () => {
    const user = userEvent.setup()
    apiMock.getSocialPosts.mockResolvedValue([draft({ status: 'needs_review', reviewed_by: null })])
    apiMock.updateSocialPost.mockResolvedValue(draft({ status: 'approved', reviewed_by: 'operator' }))
    renderPage()

    await user.click(await screen.findByRole('button', { name: '审核通过' }))

    await waitFor(() => {
      expect(apiMock.updateSocialPost).toHaveBeenCalledWith(7, { status: 'approved', reviewed_by: 'operator' })
    })
  })

  it('requires explicit confirmation before publishing to X', async () => {
    const user = userEvent.setup()
    apiMock.getSocialPosts.mockResolvedValue([draft()])
    renderPage()

    await user.click(await screen.findByRole('button', { name: '发布到 X' }))
    expect(screen.getByText('这会代表 @SynapseNetworkA 公开发布内容到 X。确认后不可由系统自动撤回。')).toBeInTheDocument()
    const publishButtons = screen.getAllByRole('button', { name: '发布到 X' })
    await user.click(publishButtons[publishButtons.length - 1])

    await waitFor(() => {
      expect(apiMock.publishSocialPostToX).toHaveBeenCalledWith(7, { actor: 'operator' })
    })
  })

  it('shows resend for failed publish attempts that are otherwise safe', async () => {
    const user = userEvent.setup()
    apiMock.getSocialPosts.mockResolvedValue([draft({
      status: 'failed',
      failure_summary: 'Google Secret Manager client is unavailable in this runtime.',
      policy_check: { status: 'passed', character_count: 67, warnings: [], blocked_reasons: [] },
    })])
    renderPage()

    expect(await screen.findByRole('button', { name: '重新发送' })).toBeInTheDocument()
    expect(screen.getByText('Google Secret Manager client is unavailable in this runtime.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重新发送' }))
    expect(screen.getByText('这会代表 @SynapseNetworkA 公开发布内容到 X。确认后不可由系统自动撤回。')).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: '重新发送' }).at(-1)!)

    await waitFor(() => {
      expect(apiMock.publishSocialPostToX).toHaveBeenCalledWith(7, { actor: 'operator' })
    })
  })

  it('requires OAuth connection before resending a safe failed post', async () => {
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    apiMock.getSocialAccounts.mockResolvedValue([
      {
        id: 1,
        platform: 'x',
        handle: 'SynapseNetworkA',
        display_name: 'Synapse Network',
        secret_ref: 'x-official',
        status: 'active',
        auth_status: 'needs_authorization',
        auth_message: 'X OAuth refresh token is missing.',
        created_at: '2026-04-25T00:00:00Z',
        updated_at: '2026-04-25T00:00:00Z',
      },
    ])
    apiMock.getSocialPosts.mockResolvedValue([draft({
      status: 'failed',
      failure_summary: 'X media upload authentication failed.',
      policy_check: { status: 'passed', character_count: 67, warnings: [], blocked_reasons: [] },
    })])
    renderPage()

    expect((await screen.findAllByRole('button', { name: '连接 X 官方账号' })).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: '重新发送' })).not.toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: '连接 X 官方账号' })[0])

    await waitFor(() => {
      expect(apiMock.startSocialXOAuth).toHaveBeenCalledWith(1)
      expect(openSpy).toHaveBeenCalledWith('https://twitter.com/i/oauth2/authorize?state=test', '_blank', 'noopener,noreferrer')
    })
    openSpy.mockRestore()
  })

  it('shows a dedicated local GCP ADC expired warning instead of reconnecting X', async () => {
    apiMock.getSocialAccounts.mockResolvedValue([
      {
        id: 1,
        platform: 'x',
        handle: 'SynapseNetworkA',
        display_name: 'Synapse Network',
        secret_ref: 'x-official',
        status: 'active',
        auth_status: 'gcp_adc_expired',
        auth_message: 'Local Google credentials expired. Run `gcloud auth application-default login` and refresh /publishing.',
        created_at: '2026-04-25T00:00:00Z',
        updated_at: '2026-04-25T00:00:00Z',
      },
    ])
    renderPage()

    expect(await screen.findByText('GCP 凭据过期')).toBeInTheDocument()
    expect(screen.getByText('本地 GCP 凭据已过期，暂时无法读取 Secret Manager 里的 X OAuth refresh token。')).toBeInTheDocument()
    expect(screen.getByText('gcloud auth application-default login')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '连接 X 官方账号' })).not.toBeInTheDocument()
  })

  it('shows resend plus reconnect for failed media auth attempts when account status is authorized', async () => {
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    const failedPost = draft({
      status: 'failed',
      failure_summary: 'X media upload authentication failed. Reconnect the X official account and approve the media.write scope.',
      policy_check: { status: 'passed', character_count: 67, warnings: [], blocked_reasons: [] },
    })
    apiMock.getSocialPosts.mockResolvedValue([failedPost])
    renderPage()

    expect(await screen.findByRole('button', { name: '重新发送' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: '重新连接 X 官方账号' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重新连接 X 官方账号' }))

    await waitFor(() => {
      expect(apiMock.startSocialXOAuth).toHaveBeenCalledWith(1)
      expect(openSpy).toHaveBeenCalledWith('https://twitter.com/i/oauth2/authorize?state=test', '_blank', 'noopener,noreferrer')
    })
    openSpy.mockRestore()
  })

  it('sorts reviewable drafts above failed history, published, and rejected records', async () => {
    const user = userEvent.setup()
    apiMock.getSocialPosts.mockResolvedValue([
      draft({ id: 1, title: 'Rejected record', status: 'rejected', updated_at: '2026-04-25T04:00:00Z' }),
      draft({ id: 2, title: 'Published record', status: 'published', updated_at: '2026-04-25T05:00:00Z' }),
      draft({ id: 3, title: 'Approved record', status: 'approved', updated_at: '2026-04-25T01:00:00Z' }),
      draft({ id: 4, title: 'Failed record', status: 'failed', updated_at: '2026-04-25T02:00:00Z' }),
      draft({ id: 5, title: 'Needs review record', status: 'needs_review', updated_at: '2026-04-25T00:00:00Z' }),
    ])
    renderPage()

    await user.click(await screen.findByRole('button', { name: '全部历史' }))
    await screen.findByText('Approved record')
    const order = screen
      .getAllByRole('row')
      .map((row) => row.textContent ?? '')
      .filter((text) => text.includes(' record'))

    expect(order[0]).toContain('Approved record')
    expect(order[1]).toContain('Needs review record')
    expect(order[2]).toContain('Failed record')
    expect(order[3]).toContain('Published record')
    expect(order[4]).toContain('Rejected record')
  })

  it('shows the backend failure reason when resend still fails', async () => {
    const user = userEvent.setup()
    const failedPost = draft({
      status: 'failed',
      failure_summary: 'X API returned HTTP 500 while creating the post.',
      policy_check: { status: 'passed', character_count: 67, warnings: [], blocked_reasons: [] },
    })
    apiMock.getSocialPosts.mockResolvedValue([failedPost])
    apiMock.publishSocialPostToX.mockResolvedValue(failedPost)
    renderPage()

    await user.click(await screen.findByRole('button', { name: '重新发送' }))
    await user.click(screen.getAllByRole('button', { name: '重新发送' }).at(-1)!)

    await waitFor(() => {
      expect(apiMock.publishSocialPostToX).toHaveBeenCalledWith(7, { actor: 'operator' })
    })
    expect((await screen.findAllByText('X API returned HTTP 500 while creating the post.')).length).toBeGreaterThan(0)
  })

  it('asks Agent to generate publish-ready text without publishing', async () => {
    const user = userEvent.setup()
    const prompt = 'Write a concise launch note about staging release governance.'
    renderPage()

    await user.click(await screen.findByRole('button', { name: '让 Agent 写草稿' }))
    expect(screen.getByRole('dialog', { name: '让 Agent 写草稿' })).toBeInTheDocument()
    expect(screen.queryByLabelText('标题')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('最终发布正文')).not.toBeInTheDocument()
    expect(screen.getByLabelText('内容风格')).toHaveValue('marketing')
    expect(screen.getByLabelText('媒体策略')).toHaveValue('auto')
    await user.type(screen.getByLabelText('目标 / Prompt'), prompt)
    await user.click(screen.getByRole('button', { name: '生成草稿' }))

    await waitFor(() => {
      expect(apiMock.generateSocialPostDraft).toHaveBeenCalledWith(expect.objectContaining({
        account_id: 1,
        prompt,
        style_type: 'marketing',
        media_mode: 'auto',
        actor: 'operator',
      }))
    })
    expect(apiMock.createSocialPost).not.toHaveBeenCalled()
    expect(apiMock.publishSocialPostToX).not.toHaveBeenCalled()
  })

  it('opens approved draft editing in a centered modal', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '编辑' }))

    expect(screen.getByRole('dialog', { name: '编辑内容草稿' })).toBeInTheDocument()
    expect(screen.getByLabelText('目标 / Prompt')).toHaveValue('Write a concise launch note about staging governance.')
    expect(screen.getByLabelText('最终发布正文')).toHaveValue('Synapse Agent Ops now has a human-gated X publishing surface.')
    expect(screen.getByText('这条草稿当前没有配图。')).toBeInTheDocument()
  })

  it('lets an operator attach a manual image while editing a draft', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '编辑' }))
    const imageFile = new File(['fake-png'], 'launch.png', { type: 'image/png' })
    await user.upload(screen.getByLabelText('选择图片文件'), imageFile)
    await user.clear(screen.getByLabelText('图片 alt text'))
    await user.type(screen.getByLabelText('图片 alt text'), 'Operator uploaded launch graphic.')
    await user.click(screen.getByRole('button', { name: '保存草稿' }))

    await waitFor(() => {
      expect(apiMock.uploadSocialPostImage).toHaveBeenCalledWith(
        7,
        imageFile,
        { actor: 'operator', alt_text: 'Operator uploaded launch graphic.' },
      )
    })
  })

  it('keeps the modal open and restores the generate button after diagnostic generation failure', async () => {
    const user = userEvent.setup()
    let rejectGeneration: (error: Error) => void = () => undefined
    apiMock.generateSocialPostDraft.mockImplementation(
      () =>
        new Promise((_, reject) => {
          rejectGeneration = reject
        }),
    )
    renderPage()

    await user.click(await screen.findByRole('button', { name: '让 Agent 写草稿' }))
    expect(screen.getByRole('dialog', { name: '让 Agent 写草稿' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('目标 / Prompt'), 'Write the first public X post.')
    await user.click(screen.getByRole('button', { name: '生成草稿' }))

    expect(screen.getByRole('button', { name: '生成中...' })).toBeDisabled()
    rejectGeneration(new Error('agent_generation_failed: provider=codex exit_code=1 stderr=quota exceeded'))
    await waitFor(() => {
      expect(screen.getByText(/provider=codex exit_code=1/)).toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { name: '让 Agent 写草稿' })).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: '让 Agent 写草稿' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '生成草稿' })).toBeEnabled()
  })
})
