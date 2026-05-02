// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DistributionAssetsPanel, DistributionSettingsPanel, DistributionTasksPanel } from './SocialDistributionPanels'
import { ToastProvider } from './workbench'

const apiMock = vi.hoisted(() => ({
  getSocialDistributionTasks: vi.fn(),
  markSocialDistributionTaskLive: vi.fn(),
  markSocialDistributionTaskRemoved: vi.fn(),
  updateSocialDistributionTask: vi.fn(),
  getSocialContentAssets: vi.fn(),
  getSocialContentAsset: vi.fn(),
  createSocialContentAsset: vi.fn(),
  generateSocialDistributionTasks: vi.fn(),
  approveAndGenerateSocialDistributionTasks: vi.fn(),
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
    events: [],
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
    apiMock.getSocialDistributionTasks.mockResolvedValue({
      groups: [{ asset: asset(), tasks: [task()] }],
      flat: [task()],
      total_assets: 1,
      total_tasks: 1,
    })
    apiMock.markSocialDistributionTaskLive.mockResolvedValue(task({ status: 'live', published_url: 'https://dev.to/synapsenetwork/agent-payments' }))
    apiMock.markSocialDistributionTaskRemoved.mockResolvedValue(task({ status: 'removed', manual_result_note: 'Moderator removed duplicate post.' }))
    apiMock.updateSocialDistributionTask.mockResolvedValue(task({ status: 'skipped' }))
    apiMock.getSocialContentAssets.mockResolvedValue([asset()])
    apiMock.getSocialContentAsset.mockResolvedValue(asset())
    apiMock.createSocialContentAsset.mockResolvedValue(asset())
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

  it('groups tasks by content asset and supports copy/live workflow', async () => {
    const user = userEvent.setup()
    const clipboardWrite = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: clipboardWrite } })
    renderWithToast(<DistributionTasksPanel formatDateTime={formatDateTime} />)

    expect(await screen.findByText('How AI agents should pay for APIs')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '详情' }))
    expect(screen.getByRole('dialog', { name: 'DEV Community' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '一键复制标题和正文' }))

    await waitFor(() => {
      expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining('Title:\nHow AI agents should pay for APIs'))
    })
  })

  it('creates assets and approves before serial task generation', async () => {
    const user = userEvent.setup()
    renderWithToast(<DistributionAssetsPanel formatDateTime={formatDateTime} />)

    expect(await screen.findByText('How AI agents should pay for APIs')).toBeInTheDocument()
    await user.click(screen.getByText('How AI agents should pay for APIs'))
    const dialog = screen.getByRole('dialog', { name: 'How AI agents should pay for APIs' })
    expect(dialog).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: '批准并生成分发任务' }))

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
