// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReleasesPage from './ReleasesPage'

const apiMock = vi.hoisted(() => ({
  getReleaseCandidates: vi.fn(),
  getReleaseTasksPage: vi.fn(),
  getReleaseTaskGateStatus: vi.fn(),
  deployReleaseTask: vi.fn(),
  getOnlineReleaseRecords: vi.fn(),
  getProjectPolicies: vi.fn(),
  getSdkPackageReleases: vi.fn(),
  getScheduledCloudRunJobsStatus: vi.fn(),
}))

vi.mock('../api', () => ({
  api: {
    getReleaseCandidates: apiMock.getReleaseCandidates,
    getOnlineReleaseRecords: apiMock.getOnlineReleaseRecords,
    getProjectPolicies: apiMock.getProjectPolicies,
    getSdkPackageReleases: apiMock.getSdkPackageReleases,
    getScheduledCloudRunJobsStatus: apiMock.getScheduledCloudRunJobsStatus,
  },
}))

vi.mock('../apiReleaseTasks', () => ({
  getReleaseTasksPage: apiMock.getReleaseTasksPage,
  getReleaseTaskGateStatus: apiMock.getReleaseTaskGateStatus,
  deployReleaseTask: apiMock.deployReleaseTask,
}))

function releaseTask(overrides: Record<string, unknown> = {}) {
  return {
    id: 42,
    source_type: 'manual',
    requirement_id: null,
    deployment_record_id: null,
    project_key: 'synapse-network',
    project_display_name: 'Synapse-Network',
    service_key: 'user-front',
    branch_name: 'main',
    environment: 'production',
    status: 'requested',
    actor: 'operator',
    operator: null,
    note: 'Manual staging release',
    deployment_status: null,
    deployment_external_run_id: null,
    deployment_external_url: null,
    deployment_commit_sha: null,
    deployment_health_status: null,
    deployment_failure_summary: null,
    deployment_workflow_file: null,
    deployment_metadata: null,
    pr_gate: {
      branch_exists: true,
      pr_exists: false,
      pr_url: null,
      pr_number: null,
      pr_state: 'production',
      checks_status: 'unknown',
      checks_summary: null,
      can_create_pr: false,
      can_deploy_staging: false,
      can_deploy_production: false,
      resolved_commit_sha: null,
      staging_deployment_record_id: null,
      blocked_reason: 'Production gate pending.',
    },
    created_at: '2026-05-15T10:00:00Z',
    updated_at: '2026-05-15T10:00:00Z',
    ...overrides,
  }
}

describe('ReleasesPage production deploy', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getReleaseCandidates.mockResolvedValue([])
    apiMock.getOnlineReleaseRecords.mockResolvedValue([])
    apiMock.getProjectPolicies.mockResolvedValue([])
    apiMock.getSdkPackageReleases.mockResolvedValue([])
    apiMock.getScheduledCloudRunJobsStatus.mockResolvedValue({
      items: [],
      diagnostics: [],
    })
    apiMock.getReleaseTasksPage.mockResolvedValue({
      items: [releaseTask()],
      total: 1,
      limit: 10,
      offset: 0,
    })
  })

  it('uses live production gate and does not reload the task page after deploy', async () => {
    apiMock.getReleaseTaskGateStatus.mockResolvedValue({
      branch_exists: true,
      pr_exists: false,
      pr_url: null,
      pr_number: null,
      pr_state: 'production',
      checks_status: 'success',
      checks_summary: 'Staging deployment #71 passed.',
      can_create_pr: false,
      can_deploy_staging: false,
      can_deploy_production: true,
      resolved_commit_sha: 'prod-main-sha',
      staging_deployment_record_id: 71,
      blocked_reason: null,
    })
    apiMock.deployReleaseTask.mockResolvedValueOnce(
      releaseTask({
        status: 'deploying',
        deployment_record_id: 99,
        deployment_status: 'requested',
        deployment_health_status: 'checking',
        deployment_metadata: { dispatchPending: true, dispatchStatus: 'pending' },
      }),
    )
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))
    await user.click(await screen.findByRole('button', { name: '发布到 production' }))

    expect(await screen.findByText('prod-main-sha')).toBeTruthy()
    expect(screen.getByText('Deployment #71')).toBeTruthy()
    const initialTaskPageCalls = apiMock.getReleaseTasksPage.mock.calls.length
    await user.type(screen.getByLabelText('输入确认短语'), 'DEPLOY_PRODUCTION')
    await user.click(screen.getByRole('button', { name: '确认发布到 production' }))

    await waitFor(() => {
      expect(apiMock.deployReleaseTask).toHaveBeenCalledWith(42, {
        actor: 'operator',
        note: 'Manual staging release',
        confirm_phrase: 'DEPLOY_PRODUCTION',
      })
    })
    expect(apiMock.getReleaseTasksPage).toHaveBeenCalledTimes(initialTaskPageCalls)
    await waitFor(() => {
      expect(screen.queryByText('确认发布到 production')).toBeNull()
    })
    expect(screen.getByText('Deploy: 待执行')).toBeTruthy()
    expect(screen.getByText('Health: 检查中')).toBeTruthy()
  })
})
