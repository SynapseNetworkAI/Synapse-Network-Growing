// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import BugsPage from './BugsPage'

const apiMock = vi.hoisted(() => ({
  getBugs: vi.fn(),
  getBugDetail: vi.fn(),
  claimBug: vi.fn(),
  claimAndRunBug: vi.fn(),
  materializeBugRequirement: vi.fn(),
  linkBugFix: vi.fn(),
  addBugVerification: vi.fn(),
  closeBug: vi.fn(),
  reopenBug: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

function bug(overrides: Record<string, unknown> = {}) {
  return {
    id: 44,
    bug_key: 'manual_bug_report::synapse-network-provider::fp_demo',
    source_key: 'manual_bug_report',
    source_kind: 'manual_input',
    status: 'open',
    title: 'Provider status page stays stale',
    summary: 'Status does not update after refresh.',
    severity: 'high',
    fingerprint: 'fp_demo',
    project_key: 'synapse-network-provider',
    project_root_path: '/Users/cliff/workspace/agent/Synapse-Network-Provider',
    source_ref: 'manual:test',
    environment: 'local',
    occurrence_count: 2,
    evidence: [{ log_excerpt: 'refresh stayed stale' }],
    metadata: { latest_fix: { branch_name: 'codex/fix-status', commit_sha: 'deadbeef1234' } },
    scorecard: {},
    converted_requirement_id: null,
    materialized_requirement_id: null,
    discovery_status: 'pending',
    discovery_recommendation: null,
    first_seen_at: '2026-05-30T00:00:00Z',
    last_seen_at: '2026-05-30T00:00:00Z',
    created_at: '2026-05-30T00:00:00Z',
    updated_at: '2026-05-30T00:00:00Z',
    ...overrides,
  }
}

function detail(overrides: Record<string, unknown> = {}) {
  const row = bug()
  return {
    bug: row,
    latest_fix_attempt: {
      id: 8,
      bug_id: row.id,
      status: 'fixing',
      agent_id: 'codex',
      branch_name: 'codex/fix-status',
      commit_sha: 'deadbeef1234',
      pr_url: 'https://github.com/SynapseNetworkAI/Synapse-Network-Provider/pull/12',
      workflow_run_id: 77,
      requirement_id: null,
      lease_expires_at: null,
      verification_summary: 'Waiting for verification.',
      verification_commands: [],
      verification_screenshots: [],
      failure_reason: null,
      created_at: '2026-05-30T00:00:00Z',
      updated_at: '2026-05-30T00:00:00Z',
      verified_at: null,
    },
    fix_attempts: [],
    events: [
      {
        id: 1,
        bug_id: row.id,
        event_type: 'claimed',
        actor: 'codex',
        from_status: 'open',
        to_status: 'fixing',
        message: '',
        metadata: {},
        created_at: '2026-05-30T00:00:00Z',
      },
    ],
    agent_context: {
      bug_id: row.id,
      bug_key: row.bug_key,
      project_key: row.project_key,
      target_project_path: row.project_root_path,
      title: row.title,
      summary: row.summary,
      repro_steps: ['Open provider status page', 'Click refresh'],
      expected_behavior: 'Status updates.',
      actual_behavior: 'Status is stale.',
      evidence: row.evidence,
      acceptance_checks: ['pytest -q tests/test_provider_status.py'],
      linked_requirement_id: null,
      allowed_next_actions: ['claim', 'link_fix', 'verify'],
    },
    ...overrides,
  }
}

function renderPage(initialEntries = ['/bugs']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <BugsPage />
    </MemoryRouter>,
  )
}

describe('BugsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getBugs.mockResolvedValue({
      items: [bug()],
      total: 138,
      limit: 20,
      offset: 0,
      status_counts: { open: 2, fixing: 1, verified: 1, closed: 1 },
      severity_counts: { high: 2, critical: 1 },
    })
    apiMock.getBugDetail.mockResolvedValue(detail())
    apiMock.claimBug.mockResolvedValue({ bug: bug({ status: 'fixing' }), fix_attempt: detail().latest_fix_attempt, agent_context: detail().agent_context })
    apiMock.claimAndRunBug.mockResolvedValue(detail({ bug: bug({ status: 'fixing' }) }))
    apiMock.materializeBugRequirement.mockResolvedValue(detail())
    apiMock.linkBugFix.mockResolvedValue(detail())
    apiMock.addBugVerification.mockResolvedValue(detail({ bug: bug({ status: 'verified' }) }))
    apiMock.closeBug.mockResolvedValue(detail({ bug: bug({ status: 'closed' }), latest_fix_attempt: { ...detail().latest_fix_attempt, status: 'verified', verification_commands: [{ command: 'pytest -q tests/test_provider_status.py', status: 'passed' }], verification_screenshots: [{ path: '/tmp/proof.png', label: 'proof' }] } }))
    apiMock.reopenBug.mockResolvedValue(detail({ bug: bug({ status: 'reopened' }) }))
  })

  it('shows paginated metrics and rows', async () => {
    renderPage(['/bugs?page=2&page_size=20'])

    expect(await screen.findByText('Bug List')).toBeInTheDocument()
    expect(screen.getByText('Provider status page stays stale')).toBeInTheDocument()
    expect(screen.getByText('Open bugs')).toBeInTheDocument()
    expect(screen.getByText('共 138 个 bug · 显示 21-40 · 第 2 / 7 页')).toBeInTheDocument()
    expect(apiMock.getBugs).toHaveBeenCalledWith(expect.objectContaining({ limit: 20, offset: 20 }))
  })

  it('uses standard pagination controls for page size and jump navigation', async () => {
    const user = userEvent.setup()
    renderPage(['/bugs?page=2&page_size=20'])

    await screen.findByText('Provider status page stays stale')
    await user.click(screen.getByRole('button', { name: '下一页' }))
    await waitFor(() => expect(apiMock.getBugs).toHaveBeenCalledWith(expect.objectContaining({ limit: 20, offset: 40 })))

    await user.clear(screen.getByLabelText('跳至页码'))
    await user.type(screen.getByLabelText('跳至页码'), '4')
    await user.click(screen.getByRole('button', { name: '跳转' }))
    await waitFor(() => expect(apiMock.getBugs).toHaveBeenCalledWith(expect.objectContaining({ limit: 20, offset: 60 })))

    await user.selectOptions(screen.getByLabelText('每页条数'), '50')
    await waitFor(() => expect(apiMock.getBugs).toHaveBeenCalledWith(expect.objectContaining({ limit: 50, offset: 0 })))
  })

  it('opens detail modal with workflow and close readiness state', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '详情' }))
    const dialog = await screen.findByRole('dialog', { name: 'Provider status page stays stale' })
    expect(within(dialog).getByText('Agent Context')).toBeInTheDocument()
    expect(within(dialog).getByText('/Users/cliff/workspace/agent/Synapse-Network-Provider')).toBeInTheDocument()
    expect(within(dialog).getByText('打开 Workflow')).toBeInTheDocument()
    expect(within(dialog).getByText('Evidence incomplete')).toBeInTheDocument()
  })

  it('can claim-and-run and link fix evidence from the modal', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '详情' }))
    await user.click(await screen.findByRole('button', { name: 'Agent 领取并启动修复' }))
    await waitFor(() => expect(apiMock.claimAndRunBug).toHaveBeenCalledWith(44, { agent_id: 'codex' }))

    await user.clear(screen.getByPlaceholderText('branch name'))
    await user.type(screen.getByPlaceholderText('branch name'), 'codex/fix-bug-list')
    await user.click(screen.getByRole('button', { name: '链接修复分支 / Commit' }))
    await waitFor(() => expect(apiMock.linkBugFix).toHaveBeenCalled())
  })
})
