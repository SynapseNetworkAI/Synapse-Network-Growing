// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../components/workbench'
import PublishingPage from './PublishingPage'

const apiMock = vi.hoisted(() => ({
  getSocialAccounts: vi.fn(),
  getSocialPosts: vi.fn(),
  createSocialPost: vi.fn(),
  generateSocialPostDraft: vi.fn(),
  updateSocialPost: vi.fn(),
  publishSocialPostToX: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

function draft(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    platform: 'x',
    account_id: 1,
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
    raw_agent_output: { source: 'test' },
    published_at: null,
    external_post_id: null,
    external_url: null,
    failure_summary: null,
    events: [],
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
        created_at: '2026-04-25T00:00:00Z',
        updated_at: '2026-04-25T00:00:00Z',
      },
    ])
    apiMock.getSocialPosts.mockResolvedValue([draft()])
    apiMock.createSocialPost.mockResolvedValue(draft({ id: 8 }))
    apiMock.generateSocialPostDraft.mockResolvedValue(draft({ id: 8, status: 'approved', generated_by: 'social_content_agent_v1', reviewed_by: 'operator' }))
    apiMock.updateSocialPost.mockResolvedValue(draft({ status: 'approved' }))
    apiMock.publishSocialPostToX.mockResolvedValue(draft({ status: 'published', external_post_id: '1801', external_url: 'https://x.com/SynapseNetworkA/status/1801' }))
  })

  it('shows the minimal generated draft surface and hides legacy content metadata', async () => {
    renderPage()

    expect(await screen.findByText('官方账号内容发布')).toBeInTheDocument()
    expect(screen.getByText('Synapse Agent Ops now has a human-gated X publishing surface.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '发布到 X' })).toBeInTheDocument()
    expect(screen.queryByText('目标受众')).not.toBeInTheDocument()
    expect(screen.queryByText('CTA')).not.toBeInTheDocument()
    expect(screen.queryByText('Agent 生成理由')).not.toBeInTheDocument()
    expect(screen.queryByText('legacy builders')).not.toBeInTheDocument()
    expect(screen.queryByText('legacy follow')).not.toBeInTheDocument()
    expect(screen.queryByText('legacy rationale')).not.toBeInTheDocument()
    expect(screen.getByText('第 1 / 1 页 · 共 1 条草稿')).toBeInTheDocument()
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

  it('asks Agent to generate publish-ready text without publishing', async () => {
    const user = userEvent.setup()
    const prompt = 'Write a concise launch note about staging release governance.'
    renderPage()

    await user.click(await screen.findByRole('button', { name: '让 Agent 写草稿' }))
    expect(screen.queryByLabelText('标题')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('最终发布正文')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('目标 / Prompt'), prompt)
    await user.click(screen.getByRole('button', { name: '生成草稿' }))

    await waitFor(() => {
      expect(apiMock.generateSocialPostDraft).toHaveBeenCalledWith(expect.objectContaining({
        account_id: 1,
        prompt,
        actor: 'operator',
      }))
    })
    expect(apiMock.createSocialPost).not.toHaveBeenCalled()
    expect(apiMock.publishSocialPostToX).not.toHaveBeenCalled()
  })
})
