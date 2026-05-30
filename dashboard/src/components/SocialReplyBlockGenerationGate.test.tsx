// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DistributionTasksPanel } from './SocialDistributionPanels'
import { ToastProvider } from './workbench'

const apiMock = vi.hoisted(() => ({
  getSocialDistributionBoard: vi.fn(),
  getSocialContentAsset: vi.fn(),
  getDistributionAccountAuthStatuses: vi.fn(),
  generateSocialXReplyBlock: vi.fn(),
  startSocialXOAuth: vi.fn(),
  getSocialDistributionTasks: vi.fn(),
  markSocialDistributionTaskLive: vi.fn(),
  markSocialDistributionTaskRemoved: vi.fn(),
  auditSocialDistributionPublishedPage: vi.fn(),
  updateSocialDistributionTask: vi.fn(),
  getSocialContentAssets: vi.fn(),
  createSocialContentTask: vi.fn(),
  createSocialContentAsset: vi.fn(),
  generateSocialDistributionContentPlan: vi.fn(),
  expandSocialDistributionCanonicalArticle: vi.fn(),
  approveSocialDistributionCanonicalArticle: vi.fn(),
  generateSocialDistributionTasks: vi.fn(),
  approveAndGenerateSocialDistributionTasks: vi.fn(),
  publishSocialDistributionTaskToX: vi.fn(),
  getSocialDistributionTaskXAuthStatus: vi.fn(),
  runSocialAssetPlanner: vi.fn(),
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

const formatDateTime = (value: string | null | undefined) => value ?? '-'

describe('Social reply block generation gate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.startSocialXOAuth.mockResolvedValue({
      auth_url: 'https://twitter.com/i/oauth2/authorize?state=test',
      state: 'test',
      expires_at: '2026-05-01T00:10:00Z',
    })
  })

  it('shows one guarded regenerate action for completed X reply blocks', async () => {
    const user = userEvent.setup()
    const replyAsset = replyBlockAsset({ complete: true })
    apiMock.getSocialContentAsset.mockResolvedValue(replyAsset)
    apiMock.getSocialDistributionBoard.mockResolvedValue(boardWithReplyAsset(replyAsset, 'ready_to_publish'))
    apiMock.getDistributionAccountAuthStatuses.mockResolvedValue(xAuthBlocked())
    apiMock.generateSocialXReplyBlock.mockResolvedValue({
      asset: replyAsset,
      reply_ids: [901, 902, 903, 904, 905],
      failed_reply_ids: [],
      source_candidate_ids: [801, 802, 803, 804, 805],
      processed_source_count: 5,
      auto_publish: false,
      timed_out: false,
      blocked_reason: null,
      agent_review: true,
      publish_mode: 'agent_approved_needs_manual_publish',
      approval_ref_configured: false,
    })

    renderWithToast(<DistributionTasksPanel formatDateTime={formatDateTime} />)
    await user.click(await screen.findByTestId('distribution-board-card-44'))

    expect(await screen.findByText('X Source/Auth Status')).toBeInTheDocument()
    expect(screen.getByText('使用已提供的 source posts，不需要 trend/radar 拉源。')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '重新生成候选' })).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: '重新生成候选' }))
    expect(apiMock.generateSocialXReplyBlock).not.toHaveBeenCalled()
    const confirmDialog = screen.getByRole('dialog', { name: '重新生成 X 回复候选' })
    expect(confirmDialog).toBeInTheDocument()

    await user.click(within(confirmDialog).getByRole('button', { name: '重新生成候选' }))
    await waitFor(() => {
      expect(apiMock.generateSocialXReplyBlock).toHaveBeenCalledWith(44, expect.objectContaining({
        force_regenerate: true,
        target_count: 5,
      }))
    })
  })

  it('shows authorized X state and enables generation without explicit sources', async () => {
    const user = userEvent.setup()
    const replyAsset = replyBlockAsset({ complete: false })
    apiMock.getSocialContentAsset.mockResolvedValue(replyAsset)
    apiMock.getSocialDistributionBoard.mockResolvedValue(boardWithReplyAsset(replyAsset, 'needs_review'))
    apiMock.getDistributionAccountAuthStatuses.mockResolvedValue(xAuthAuthorized())

    renderWithToast(<DistributionTasksPanel formatDateTime={formatDateTime} />)
    await user.click(await screen.findByTestId('distribution-board-card-45'))

    expect(await screen.findByText('X Source/Auth Status')).toBeInTheDocument()
    expect(screen.getByText('已授权')).toBeInTheDocument()
    expect(screen.getByText('X OAuth 已授权，trend/radar 拉源可用。')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '连接 X / 重新授权' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '生成 5 条 X 回复候选' })).toBeEnabled()
  })

  it('blocks new X reply block generation when X auth is invalid and no sources exist', async () => {
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, 'open').mockReturnValue({} as Window)
    const replyAsset = replyBlockAsset({ complete: false })
    apiMock.getSocialContentAsset.mockResolvedValue(replyAsset)
    apiMock.getSocialDistributionBoard.mockResolvedValue(boardWithReplyAsset(replyAsset, 'needs_review'))
    apiMock.getDistributionAccountAuthStatuses.mockResolvedValue(xAuthBlocked())

    renderWithToast(<DistributionTasksPanel formatDateTime={formatDateTime} />)
    await user.click(await screen.findByTestId('distribution-board-card-45'))

    expect(await screen.findByRole('button', { name: '先连接 X 或粘贴来源' })).toBeDisabled()
    expect(screen.getByText('需要重新授权')).toBeInTheDocument()
    expect(screen.getByText('X 授权已失效，请连接 X 重新授权后再同步 trend/radar 来源。')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '连接 X / 重新授权' }))

    await waitFor(() => {
      expect(apiMock.startSocialXOAuth).toHaveBeenCalledWith()
      expect(openSpy).toHaveBeenCalledWith(
        'https://twitter.com/i/oauth2/authorize?state=test',
        '_blank',
        'noopener,noreferrer',
      )
    })
    expect(apiMock.generateSocialXReplyBlock).not.toHaveBeenCalled()
    openSpy.mockRestore()
  })

  it('keeps Publishing open when the X OAuth popup is blocked', async () => {
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined)
    const replyAsset = replyBlockAsset({ complete: false })
    apiMock.getSocialContentAsset.mockResolvedValue(replyAsset)
    apiMock.getSocialDistributionBoard.mockResolvedValue(boardWithReplyAsset(replyAsset, 'needs_review'))
    apiMock.getDistributionAccountAuthStatuses.mockResolvedValue(xAuthBlocked())

    renderWithToast(<DistributionTasksPanel formatDateTime={formatDateTime} />)
    await user.click(await screen.findByTestId('distribution-board-card-45'))
    await user.click(await screen.findByRole('button', { name: '连接 X / 重新授权' }))

    await waitFor(() => {
      expect(apiMock.startSocialXOAuth).toHaveBeenCalledWith()
      expect(openSpy).toHaveBeenCalledWith(
        'https://twitter.com/i/oauth2/authorize?state=test',
        '_blank',
        'noopener,noreferrer',
      )
      expect(clickSpy).toHaveBeenCalled()
    })
    expect(apiMock.generateSocialXReplyBlock).not.toHaveBeenCalled()
    clickSpy.mockRestore()
    openSpy.mockRestore()
  })

  it('shows a bounded error when X OAuth start fails', async () => {
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, 'open').mockReturnValue({} as Window)
    const replyAsset = replyBlockAsset({ complete: false })
    apiMock.getSocialContentAsset.mockResolvedValue(replyAsset)
    apiMock.getSocialDistributionBoard.mockResolvedValue(boardWithReplyAsset(replyAsset, 'needs_review'))
    apiMock.getDistributionAccountAuthStatuses.mockResolvedValue(xAuthBlocked())
    apiMock.startSocialXOAuth.mockRejectedValueOnce(new Error('无法生成 X 授权链接：Local Google credentials expired.'))

    renderWithToast(<DistributionTasksPanel formatDateTime={formatDateTime} />)
    await user.click(await screen.findByTestId('distribution-board-card-45'))
    await user.click(await screen.findByRole('button', { name: '连接 X / 重新授权' }))

    expect(openSpy).not.toHaveBeenCalled()
    expect(await screen.findAllByText(/无法生成 X 授权链接：Local Google credentials expired/)).toHaveLength(2)
    expect(screen.getAllByText(/请配置 X_OAUTH_CLIENT_ID/)).toHaveLength(2)
    openSpy.mockRestore()
  })
})

function renderWithToast(node: ReactNode) {
  return render(<ToastProvider>{node}</ToastProvider>)
}

function replyBlockAsset({ complete }: { complete: boolean }) {
  const id = complete ? 44 : 45
  return {
    id,
    asset_type: 'reply',
    source_type: 'manual',
    title: 'X Week 1 Reply Block Day 4',
    body: complete ? 'https://x.com/builder/status/2001' : 'Generate reply candidates.',
    summary: complete ? 'Use explicit source posts.' : 'No source posts yet.',
    canonical_url: null,
    source_signal_id: null,
    goal_key: 'x_brand_awareness_week_1',
    policy_check: {},
    agent_metadata: {
      post_intent: 'engagement_reply',
      target_platforms: ['x'],
      reply_block: complete
        ? {
          target_count: 5,
          reply_ids: [901, 902, 903, 904, 905],
          source_candidate_ids: [801, 802, 803, 804, 805],
          publish_mode: 'agent_approved_needs_manual_publish',
        }
        : { target_count: 5, reply_ids: [], source_candidate_ids: [] },
    },
    status: complete ? 'ready' : 'draft',
    created_by: 'operator',
    task_count: 0,
    status_counts: complete ? { agent_approved_needs_manual_publish: 5 } : {},
    tasks: [],
    events: [],
    documents: [{
      id: 401,
      asset_id: id,
      task_id: null,
      document_kind: 'source_plan',
      platform: null,
      channel_key: null,
      title: 'Plan',
      body_markdown: 'Reply block plan.',
      status: 'generated',
      version: 1,
      metadata: {},
      created_at: '2026-05-01T00:00:00Z',
      updated_at: '2026-05-01T00:00:00Z',
    }],
    reply_items: complete ? [1, 2, 3, 4, 5].map((index) => replyItem(index)) : [],
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
  }
}

function replyItem(index: number) {
  return {
    id: 900 + index,
    platform: 'x',
    external_reply_id: `target:${index}`,
    source_candidate_id: 800 + index,
    source_post_id: String(2000 + index),
    source_author_handle: `builder${index}`,
    source_text: 'Agents need paid API spend caps and receipts.',
    intent: 'engagement_reply',
    suggested_reply: 'Budget caps should be enforced before every paid tool call.',
    generation_reason: 'source fit',
    risk_level: 'normal',
    status: 'agent_approved_needs_manual_publish',
    source_url: `https://x.com/builder${index}/status/${2000 + index}`,
    published_external_post_id: null,
    reviewed_by: 'agent',
    failure_summary: null,
    metadata: { x_reply_source_strategy: { strategy: 'agent_economy_monetization' } },
  }
}

function boardWithReplyAsset(replyAsset: ReturnType<typeof replyBlockAsset>, columnKey: string) {
  const ready = columnKey === 'ready_to_publish'
  return {
    columns: [
      { key: 'backlog', title: '待计划', description: 'Needs plan.', count: 0, cards: [] },
      { key: 'needs_review', title: '待审核', description: 'Plan.', count: ready ? 0 : 1, cards: ready ? [] : [card(replyAsset, columnKey)] },
      { key: 'ready_to_publish', title: '待发布', description: 'Ready.', count: ready ? 1 : 0, cards: ready ? [card(replyAsset, columnKey)] : [] },
      { key: 'live', title: '已发布', description: 'Live.', count: 0, cards: [] },
      { key: 'blocked', title: '异常', description: 'Blocked.', count: 0, cards: [] },
    ],
    summary: { total_assets: 1, total_tasks: 0, total_documents: 1 },
    generated_at: '2026-05-01T00:00:00Z',
  }
}

function card(replyAsset: ReturnType<typeof replyBlockAsset>, columnKey: string) {
  return {
    id: `asset:${replyAsset.id}`,
    asset: replyAsset,
    column_key: columnKey,
    task_kind_code: 'x_reply_block',
    task_kind_label: 'X 回复块',
    task_kind_action: 'generate_x_reply_candidates',
    task_count: 0,
    document_count: 1,
    platform_count: 0,
    failed_count: 0,
    ready_to_publish_count: replyAsset.reply_items.length,
    live_count: 0,
    visibility_issue_count: 0,
    status_counts: replyAsset.status_counts,
    document_status_counts: { generated: 1 },
    next_action: 'Review X replies.',
    updated_at: '2026-05-01T00:00:00Z',
  }
}

function xAuthBlocked() {
  return {
    generated_at: '2026-05-01T00:00:00Z',
    items: [{
      account_id: 102,
      platform: 'x',
      channel_key: 'official',
      display_name: 'X Official Account',
      login_url: 'https://x.com/i/flow/login',
      publish_path: 'manual_only',
      api_status: 'blocked',
      browser_status: 'manual_only',
      api_supported: true,
      can_publish_via_api: false,
      can_use_browser_assist: false,
      private_web_adapter_enabled: false,
      blockers: ['invalid_refresh_token'],
      next_action: 'Resolve blocker: invalid_refresh_token',
      oauth_status: 'invalid_refresh_token',
      requires_authorization: true,
      auth_message: 'Value passed for the token was invalid.',
      last_checked_at: '2026-05-01T00:00:00Z',
    }],
  }
}

function xAuthAuthorized() {
  return {
    generated_at: '2026-05-01T00:00:00Z',
    items: [{
      account_id: 102,
      platform: 'x',
      channel_key: 'official',
      display_name: 'X Official Account',
      login_url: 'https://x.com/i/flow/login',
      publish_path: 'official_api',
      api_status: 'ready',
      browser_status: 'manual_only',
      api_supported: true,
      can_publish_via_api: true,
      can_use_browser_assist: false,
      private_web_adapter_enabled: false,
      blockers: [],
      next_action: 'API publish can proceed after task-level Human Gate.',
      oauth_status: 'authorized',
      requires_authorization: false,
      auth_message: 'X OAuth refresh token is valid.',
      last_checked_at: '2026-05-01T00:00:00Z',
    }],
  }
}
