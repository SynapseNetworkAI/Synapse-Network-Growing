// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DistributionAssetsPanel, DistributionSettingsPanel, DistributionTasksPanel } from './SocialDistributionPanels'
import { ToastProvider } from './workbench'

const apiMock = vi.hoisted(() => ({
  getSocialDistributionBoard: vi.fn(),
  getSocialDistributionTasks: vi.fn(),
  markSocialDistributionTaskLive: vi.fn(),
  markSocialDistributionTaskRemoved: vi.fn(),
  updateSocialDistributionTask: vi.fn(),
  getSocialContentAssets: vi.fn(),
  getSocialContentAsset: vi.fn(),
  createSocialContentTask: vi.fn(),
  createSocialContentAsset: vi.fn(),
  generateSocialDistributionContentPlan: vi.fn(),
  expandSocialDistributionCanonicalArticle: vi.fn(),
  approveSocialDistributionCanonicalArticle: vi.fn(),
  generateSocialDistributionTasks: vi.fn(),
  approveAndGenerateSocialDistributionTasks: vi.fn(),
  publishSocialDistributionTaskToX: vi.fn(),
  getSocialDistributionTaskXAuthStatus: vi.fn(),
  startSocialXOAuth: vi.fn(),
  runSocialAssetPlanner: vi.fn(),
  getDistributionAccounts: vi.fn(),
  updateDistributionAccount: vi.fn(),
  getSocialTrends: vi.fn(),
  getSocialPostMetricSummary: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

const formatDateTime = (value: string | null | undefined) => value ?? '-'

function account(overrides: Record<string, unknown> = {}) {
  return {
    id: 101,
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
    notes: 'Long-form developer tutorial distribution.',
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
    ...overrides,
  }
}

function task(overrides: Record<string, unknown> = {}) {
  return {
    id: 201,
    asset_id: 301,
    account_id: 101,
    platform: 'devto',
    channel_key: 'dev.to',
    action: 'post',
    account_display_name: 'DEV Community',
    signup_url: 'https://dev.to/enter',
    status: 'draft_ready',
    platform_title: 'How AI agents should pay for APIs',
    platform_body: 'A practical developer guide to agent-native payment rails.',
    operator_checklist: 'Human Gate: manually publish on DEV.\nCanonical URL reminder.',
    submission_url: 'https://dev.to/enter',
    published_url: null,
    external_post_id: null,
    failure_summary: null,
    manual_result_note: null,
    metadata: { serial_generation: true },
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
    ...overrides,
  }
}

function asset(overrides: Record<string, unknown> = {}) {
  return {
    id: 301,
    asset_type: 'article',
    source_type: 'manual',
    title: 'How AI agents should pay for APIs',
    body: 'Long article body.',
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
    tasks: [task()],
    events: [{ id: 1, asset_id: 301, task_id: null, event_type: 'content_task_created', actor: 'operator', summary: 'Created.', payload: {}, created_at: '2026-05-01T00:00:00Z' }],
    documents: [
      {
        id: 401,
        asset_id: 301,
        task_id: null,
        document_kind: 'source_plan',
        platform: null,
        channel_key: null,
        title: 'Plan: How AI agents should pay for APIs',
        body_markdown: 'Core angle: AI agents should pay for APIs',
        status: 'generated',
        version: 1,
        metadata: {},
        created_at: '2026-05-01T00:00:00Z',
        updated_at: '2026-05-01T00:00:00Z',
      },
      {
        id: 403,
        asset_id: 301,
        task_id: null,
        document_kind: 'canonical_article',
        platform: null,
        channel_key: null,
        title: 'Canonical article: How AI agents should pay for APIs',
        body_markdown: '# How AI agents should pay for APIs\n\nA complete mother draft.',
        status: 'approved',
        version: 1,
        metadata: { generated_by: 'asset_expansion_agent_v1' },
        created_at: '2026-05-01T00:00:00Z',
        updated_at: '2026-05-01T00:00:00Z',
      },
      {
        id: 402,
        asset_id: 301,
        task_id: 201,
        document_kind: 'platform_draft',
        platform: 'devto',
        channel_key: 'dev.to',
        title: 'How AI agents should pay for APIs',
        body_markdown: 'A practical developer guide to agent-native payment rails.',
        status: 'generated',
        version: 1,
        metadata: {},
        created_at: '2026-05-01T00:00:00Z',
        updated_at: '2026-05-01T00:00:00Z',
      },
    ],
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
    ...overrides,
  }
}

function renderWithToast(node: ReactNode) {
  return render(<ToastProvider>{node}</ToastProvider>)
}

describe('SocialDistributionPanels v2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getSocialDistributionBoard.mockResolvedValue({
      columns: [
        { key: 'backlog', title: '待计划', description: 'Needs plan.', count: 0, cards: [] },
        { key: 'needs_review', title: '待审核', description: 'Plan.', count: 0, cards: [] },
        {
          key: 'ready_to_publish',
          title: '待发布',
          description: 'Ready.',
          count: 1,
          cards: [{
            id: 'asset:301',
            asset: asset(),
            column_key: 'ready_to_publish',
            task_count: 1,
            document_count: 3,
            platform_count: 1,
            failed_count: 0,
            ready_to_publish_count: 1,
            live_count: 0,
            status_counts: { draft_ready: 1 },
            document_status_counts: { generated: 2, approved: 1 },
            next_action: 'Publish manually.',
            updated_at: '2026-05-01T00:00:00Z',
          }],
        },
        { key: 'live', title: '已发布', description: 'Live.', count: 0, cards: [] },
        { key: 'blocked', title: '异常', description: 'Blocked.', count: 0, cards: [] },
      ],
      summary: { total_assets: 1, total_tasks: 1, total_documents: 3 },
      generated_at: '2026-05-01T00:00:00Z',
    })
    apiMock.getSocialDistributionTasks.mockResolvedValue({
      groups: [{ asset: asset(), tasks: [task()] }],
      flat: [task()],
      total_assets: 1,
      total_tasks: 1,
    })
    apiMock.markSocialDistributionTaskLive.mockResolvedValue(task({ status: 'live', published_url: 'https://dev.to/synapsenetwork/agent-payments' }))
    apiMock.markSocialDistributionTaskRemoved.mockResolvedValue(task({ status: 'removed', manual_result_note: 'Moderator removed duplicate post.' }))
    apiMock.updateSocialDistributionTask.mockResolvedValue(task({ status: 'skipped' }))
    apiMock.publishSocialDistributionTaskToX.mockResolvedValue(task({ platform: 'x', channel_key: 'official', status: 'live', external_post_id: '1234567890' }))
    apiMock.getSocialDistributionTaskXAuthStatus.mockResolvedValue({
      status: 'authorized',
      can_publish: true,
      account_id: 1,
      account_handle: 'SynapseNetworkA',
      auth_message: 'authorized',
      requires_authorization: false,
      refresh_token_rotated: false,
    })
    apiMock.startSocialXOAuth.mockResolvedValue({
      auth_url: 'https://twitter.com/i/oauth2/authorize?state=test',
      state: 'test',
      expires_at: '2026-05-01T00:10:00Z',
    })
    apiMock.getSocialContentAssets.mockResolvedValue([asset()])
    apiMock.getSocialContentAsset.mockResolvedValue(asset())
    apiMock.createSocialContentTask.mockResolvedValue(asset({ source_type: 'manual_task' }))
    apiMock.createSocialContentAsset.mockResolvedValue(asset())
    apiMock.generateSocialDistributionContentPlan.mockResolvedValue(asset())
    apiMock.expandSocialDistributionCanonicalArticle.mockResolvedValue(asset({
      status: 'needs_review',
      documents: asset().documents.map((doc) =>
        doc.document_kind === 'canonical_article' ? { ...doc, status: 'needs_review' } : doc,
      ),
    }))
    apiMock.approveSocialDistributionCanonicalArticle.mockResolvedValue(asset())
    apiMock.generateSocialDistributionTasks.mockResolvedValue({
      asset: asset(),
      results: [{ account_id: 101, platform: 'devto', channel_key: 'dev.to', status: 'generated', task_id: 201, error: null }],
      generated_task_ids: [201],
      failed_task_ids: [],
    })
    apiMock.approveAndGenerateSocialDistributionTasks.mockResolvedValue({
      asset: asset({ status: 'ready' }),
      results: [{ account_id: 101, platform: 'devto', channel_key: 'dev.to', status: 'generated', task_id: 201, error: null }],
      generated_task_ids: [201],
      failed_task_ids: [],
    })
    apiMock.runSocialAssetPlanner.mockResolvedValue({
      workflow_key: 'social_asset_planner_sweep',
      local_date: '2026-05-01',
      target_count: 3,
      active_count: 1,
      no_asset_created: false,
      already_satisfied: false,
      selected_asset_type: 'developer_education',
      selected_signal_count: 1,
      reason: null,
      created_asset_id: 301,
      asset: asset({ source_type: 'asset_planner', status: 'proposed' }),
      signals: [],
    })
    apiMock.getDistributionAccounts.mockResolvedValue([account()])
    apiMock.updateDistributionAccount.mockResolvedValue(account({ profile_url: 'https://dev.to/synapsenetwork' }))
  })

  it('renders a Symphony-style task board and supports copy workflow from the card modal', async () => {
    const user = userEvent.setup()
    const clipboardWrite = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: clipboardWrite } })
    renderWithToast(<DistributionTasksPanel formatDateTime={formatDateTime} />)

    expect(await screen.findByText('How AI agents should pay for APIs')).toBeInTheDocument()
    expect(screen.getByTestId('distribution-board-column-ready_to_publish')).toBeInTheDocument()
    await user.click(screen.getByTestId('distribution-board-card-301'))
    expect(screen.getByRole('dialog', { name: 'How AI agents should pay for APIs' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '复制并打开平台' }))
    expect(screen.getByRole('dialog', { name: 'DEV Community' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '一键复制标题和正文' }))

    await waitFor(() => {
      expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining('Title:\nHow AI agents should pay for APIs'))
    })
  })

  it('creates a content task from the Tasks board', async () => {
    const user = userEvent.setup()
    renderWithToast(<DistributionTasksPanel formatDateTime={formatDateTime} />)

    await screen.findByText('How AI agents should pay for APIs')
    await user.click(screen.getByRole('button', { name: '创建内容计划' }))
    await user.type(screen.getByLabelText('任务标题'), '第 1 篇：一人公司最大的问题')
    await user.type(screen.getByLabelText('来源材料 / Markdown'), '核心问题：上下文切换、流程断裂和质量失控。')
    await user.click(screen.getByRole('button', { name: '创建' }))

    await waitFor(() => {
      expect(apiMock.createSocialContentTask).toHaveBeenCalledWith(expect.objectContaining({
        title: '第 1 篇：一人公司最大的问题',
        target_platforms: ['x', 'v2ex', 'hacker_news', 'devto', 'hashnode', 'reddit'],
      }))
    })
  })

  it('renders X thread drafts with weighted counts and thread publish action', async () => {
    const user = userEvent.setup()
    const xTask = task({
      id: 202,
      account_id: 102,
      platform: 'x',
      channel_key: 'official',
      account_display_name: 'X Official Account',
      publish_mode: 'api_human_gated',
      api_capability: 'write_post',
      status: 'needs_review',
      platform_title: 'X thread: Solo company operating system',
      platform_body: '1/2\nSolo company bottleneck is not code speed.\n\n2/2\nThe fix is a control plane plus human-gated distribution.',
      metadata: {
        format_kind: 'x_thread',
        target_length: 'thread of tweets under 280 weighted chars',
        x_format: 'thread',
        tweets: [
          'Solo company bottleneck is not code speed.',
          'The fix is a control plane plus human-gated distribution.',
        ],
        weighted_counts: [43, 62],
      },
    })
    const xAsset = asset({
      tasks: [xTask],
      documents: [
        {
          id: 403,
          asset_id: 301,
          task_id: 202,
          document_kind: 'platform_draft',
          platform: 'x',
          channel_key: 'official',
          title: 'X thread: Solo company operating system',
          body_markdown: '## Thread',
          status: 'needs_review',
          version: 1,
          metadata: xTask.metadata,
          created_at: '2026-05-01T00:00:00Z',
          updated_at: '2026-05-01T00:00:00Z',
        },
      ],
    })
    apiMock.getSocialContentAsset.mockResolvedValue(xAsset)
    apiMock.getSocialDistributionBoard.mockResolvedValueOnce({
      columns: [
        { key: 'backlog', title: '待计划', description: 'Needs plan.', count: 0, cards: [] },
        { key: 'needs_review', title: '待审核', description: 'Plan.', count: 0, cards: [] },
        {
          key: 'ready_to_publish',
          title: '待发布',
          description: 'Ready.',
          count: 1,
          cards: [{
            id: 'asset:301',
            asset: xAsset,
            column_key: 'ready_to_publish',
            task_count: 1,
            document_count: 1,
            platform_count: 1,
            failed_count: 0,
            ready_to_publish_count: 1,
            live_count: 0,
            status_counts: { needs_review: 1 },
            document_status_counts: { needs_review: 1 },
            next_action: 'Publish X thread.',
            updated_at: '2026-05-01T00:00:00Z',
          }],
        },
        { key: 'live', title: '已发布', description: 'Live.', count: 0, cards: [] },
        { key: 'blocked', title: '异常', description: 'Blocked.', count: 0, cards: [] },
      ],
      summary: { total_assets: 1, total_tasks: 1, total_documents: 1 },
      generated_at: '2026-05-01T00:00:00Z',
    })

    renderWithToast(<DistributionTasksPanel formatDateTime={formatDateTime} />)
    await user.click(await screen.findByTestId('distribution-board-card-301'))
    await user.click(screen.getByRole('button', { name: '发布到 X / 详情' }))

    expect(screen.getByRole('dialog', { name: 'X Official Account' })).toBeInTheDocument()
    expect(screen.getByText('推文 1/2')).toBeInTheDocument()
    expect(screen.getByText('43/280')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '一键发布 Thread' })).toBeEnabled()
  })

  it('opens X OAuth authorization instead of publishing when login expired', async () => {
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, 'open').mockReturnValue({} as Window)
    const xTask = task({
      id: 203,
      account_id: 102,
      platform: 'x',
      channel_key: 'official',
      account_display_name: 'X Official Account',
      publish_mode: 'api_human_gated',
      api_capability: 'write_post',
      status: 'needs_review',
      platform_title: 'X Premium long post',
      platform_body: 'A substantial X long post about solo-company operating systems.',
      metadata: {
        format_kind: 'x_long_post',
        target_length: 'X Premium long post, max 4000 chars',
        x_format: 'x_long_post',
        character_count: 62,
      },
    })
    const xAsset = asset({ tasks: [xTask] })
    apiMock.getSocialContentAsset.mockResolvedValue(xAsset)
    apiMock.getSocialDistributionTaskXAuthStatus.mockResolvedValueOnce({
      status: 'needs_authorization',
      can_publish: false,
      account_id: 1,
      account_handle: 'SynapseNetworkA',
      auth_message: 'refresh token expired',
      requires_authorization: true,
      refresh_token_rotated: false,
    })

    renderWithToast(<DistributionTasksPanel formatDateTime={formatDateTime} />)
    await user.click(await screen.findByTestId('distribution-board-card-301'))
    await user.click(screen.getByRole('button', { name: '发布到 X / 详情' }))
    await user.click(screen.getByRole('button', { name: '发布长文到 X' }))

    await waitFor(() => {
      expect(apiMock.getSocialDistributionTaskXAuthStatus).toHaveBeenCalledWith(203)
      expect(apiMock.startSocialXOAuth).toHaveBeenCalledWith(1)
      expect(openSpy).toHaveBeenCalledWith(
        'https://twitter.com/i/oauth2/authorize?state=test',
        '_blank',
        'noopener,noreferrer',
      )
    })
    expect(apiMock.publishSocialDistributionTaskToX).not.toHaveBeenCalled()
    expect(screen.getAllByText('X 授权页已打开。完成授权后回到这里，再点击发送。').length).toBeGreaterThan(0)
  })

  it('publishes X long post after auth preflight succeeds', async () => {
    const user = userEvent.setup()
    const xTask = task({
      id: 204,
      account_id: 102,
      platform: 'x',
      channel_key: 'official',
      account_display_name: 'X Official Account',
      publish_mode: 'api_human_gated',
      api_capability: 'write_post',
      status: 'needs_review',
      platform_title: 'X Premium long post',
      platform_body: 'A substantial X long post about solo-company operating systems.',
      metadata: {
        format_kind: 'x_long_post',
        target_length: 'X Premium long post, max 4000 chars',
        x_format: 'x_long_post',
        character_count: 62,
      },
    })
    apiMock.getSocialContentAsset.mockResolvedValue(asset({ tasks: [xTask] }))

    renderWithToast(<DistributionTasksPanel formatDateTime={formatDateTime} />)
    await user.click(await screen.findByTestId('distribution-board-card-301'))
    await user.click(screen.getByRole('button', { name: '发布到 X / 详情' }))
    await user.click(screen.getByRole('button', { name: '发布长文到 X' }))

    await waitFor(() => {
      expect(apiMock.getSocialDistributionTaskXAuthStatus).toHaveBeenCalledWith(204)
      expect(apiMock.publishSocialDistributionTaskToX).toHaveBeenCalledWith(204, { actor: 'operator' })
    })
  })

  it('runs the Asset Planner from the Tasks board', async () => {
    const user = userEvent.setup()
    renderWithToast(<DistributionTasksPanel formatDateTime={formatDateTime} />)

    await screen.findByText('How AI agents should pay for APIs')
    await user.click(screen.getByRole('button', { name: '从信号生成内容计划' }))

    await waitFor(() => {
      expect(apiMock.runSocialAssetPlanner).toHaveBeenCalled()
    })
  })

  it('creates assets and approves before serial task generation', async () => {
    const user = userEvent.setup()
    renderWithToast(<DistributionAssetsPanel formatDateTime={formatDateTime} />)

    expect(await screen.findByText('How AI agents should pay for APIs')).toBeInTheDocument()
    await user.click(screen.getByText('How AI agents should pay for APIs'))
    const dialog = screen.getByRole('dialog', { name: 'How AI agents should pay for APIs' })
    expect(dialog).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: '批准并生成平台任务' }))

    await waitFor(() => {
      expect(apiMock.approveAndGenerateSocialDistributionTasks).toHaveBeenCalledWith(301, {
        account_ids: [101],
        action: 'post',
        actor: 'operator',
      })
    })
  })

  it('runs the Asset Planner from the Assets panel', async () => {
    const user = userEvent.setup()
    renderWithToast(<DistributionAssetsPanel formatDateTime={formatDateTime} />)

    await screen.findByText('How AI agents should pay for APIs')
    await user.click(screen.getByRole('button', { name: '运行 Asset Planner' }))

    await waitFor(() => {
      expect(apiMock.runSocialAssetPlanner).toHaveBeenCalled()
    })
  })

  it('edits channel governance in settings', async () => {
    const user = userEvent.setup()
    renderWithToast(<DistributionSettingsPanel formatDateTime={formatDateTime} />)

    expect(await screen.findByText('DEV Community')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '编辑' }))
    await user.clear(screen.getByLabelText('Profile URL'))
    await user.type(screen.getByLabelText('Profile URL'), 'https://dev.to/synapsenetwork')
    await user.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(apiMock.updateDistributionAccount).toHaveBeenCalledWith(
        101,
        expect.objectContaining({ profile_url: 'https://dev.to/synapsenetwork' }),
      )
    })
  })
})
