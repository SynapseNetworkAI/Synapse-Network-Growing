// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScheduledJobsPanel from './ScheduledJobsPanel'

const apiMock = vi.hoisted(() => ({
  getScheduledCloudRunJobsStatus: vi.fn(),
  getScheduledCloudRunJobRecords: vi.fn(),
  createScheduledCloudRunJobTask: vi.fn(),
  publishScheduledCloudRunJobTask: vi.fn(),
  cancelScheduledCloudRunJobTask: vi.fn(),
  syncScheduledCloudRunJobs: vi.fn(),
  getReleaseTaskBranchOptions: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

function job(overrides: Record<string, unknown> = {}) {
  return {
    job_name: 'synapse-staging-deposit-indexer',
    family: 'gateway',
    job_type: 'periodic',
    cadence: 'every_minute',
    command: 'python -m src.worker deposit-indexer --once',
    purpose: '确认充值入账',
    scheduler_job: 'synapse-staging-deposit-indexer-schedule',
    freshness_required: true,
    migration_execution_required: false,
    publish_status: 'unknown',
    scheduler_status: 'configured_from_docs',
    health_status: 'unknown',
    image_digest: null,
    effective_image: null,
    latest_execution: null,
    last_published_at: null,
    last_deployment_record_id: null,
    external_url: null,
    failure_summary: null,
    diagnostic: null,
    metadata: {},
    ...overrides,
  }
}

describe('ScheduledJobsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getScheduledCloudRunJobsStatus.mockResolvedValue({
      diagnostics: [],
      updated_at: '2026-05-03T01:00:00Z',
      items: [
        job(),
        job({
          job_name: 'synapse-staging-db-migrate',
          job_type: 'migration',
          cadence: 'release_time',
          command: 'gateway database migration job',
          purpose: 'Gateway DB migration',
          scheduler_job: null,
          freshness_required: false,
          migration_execution_required: true,
          scheduler_status: 'manual_job',
        }),
      ],
    })
    apiMock.getScheduledCloudRunJobRecords.mockResolvedValue({
      total: 1,
      limit: 20,
      offset: 0,
      items: [
        {
          id: 99,
          deployment_record_id: null,
          job_name: 'synapse-staging-deposit-indexer',
          jobs: ['synapse-staging-deposit-indexer'],
          family: 'gateway',
          job_type: 'periodic',
          environment: 'staging',
          publish_mode: 'single_job',
          source_ref_type: 'branch',
          source_ref: 'main',
          status: 'requested',
          health_status: 'checking',
          actor: 'operator',
          created_by: 'operator',
          executed_by: null,
          workflow_file: 'deploy-staging-jobs.yml',
          external_run_id: null,
          external_url: 'https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/99',
          failure_summary: null,
          notes: 'Publish gateway Cloud Run Jobs to staging.',
          created_at: '2026-05-03T01:00:00Z',
          updated_at: '2026-05-03T01:00:00Z',
          started_at: '2026-05-03T01:00:00Z',
          finished_at: null,
          metadata: {},
        },
      ],
    })
    apiMock.getReleaseTaskBranchOptions.mockResolvedValue([
      { name: 'main', commit_sha: 'abc123', protected: true, is_default: true, source: 'github' },
      { name: 'codex/jobs', commit_sha: 'def456', protected: false, is_default: false, source: 'github' },
    ])
    apiMock.createScheduledCloudRunJobTask.mockResolvedValue({
      id: 100,
      deployment_record_id: null,
      job_name: 'synapse-staging-deposit-indexer',
      jobs: ['synapse-staging-deposit-indexer'],
      family: 'gateway',
      job_type: 'periodic',
      environment: 'staging',
      publish_mode: 'single_job',
      source_ref_type: 'branch',
      source_ref: 'main',
      status: 'requested',
      health_status: 'pending',
      actor: 'operator',
      created_by: 'operator',
      executed_by: null,
      workflow_file: null,
      external_run_id: null,
      external_url: null,
      failure_summary: null,
      notes: null,
      created_at: '2026-05-03T01:00:00Z',
      updated_at: '2026-05-03T01:00:00Z',
      started_at: null,
      finished_at: null,
      metadata: {},
    })
    apiMock.publishScheduledCloudRunJobTask.mockResolvedValue({
      deployment_record_id: 99,
      task_id: 99,
      family: 'gateway',
      environment: 'staging',
      publish_mode: 'single_job',
      job_name: 'synapse-staging-deposit-indexer',
      status: 'requested',
      external_url: 'https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/99',
      jobs: ['synapse-staging-deposit-indexer'],
      message: 'ok',
    })
    apiMock.syncScheduledCloudRunJobs.mockResolvedValue({
      processed_count: 1,
      succeeded_ids: [],
      failed_ids: [],
      running_ids: [99],
      pending_ids: [],
      error_ids: [],
    })
  })

  it('creates one selected Cloud Run job release task before dispatch', async () => {
    const user = userEvent.setup()
    render(<ScheduledJobsPanel />)

    expect(await screen.findByText('定时任务发布记录')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '发布 gateway jobs' })).toBeNull()
    expect(screen.queryByRole('button', { name: '发布 gateway-admin jobs' })).toBeNull()
    expect(screen.queryByRole('button', { name: '发布 all jobs' })).toBeNull()
    await user.click(screen.getByRole('button', { name: '创建定时任务发布' }))

    await waitFor(() => {
      expect(apiMock.getReleaseTaskBranchOptions).toHaveBeenCalledWith({
        project_key: 'synapse-network',
        service_key: 'gateway',
      })
    })
    expect(screen.getAllByText('环境').length).toBeGreaterThan(0)
    expect(screen.getByText('GitHub 分支')).toBeTruthy()
    expect(screen.getAllByText('任务名称').length).toBeGreaterThan(0)

    await user.selectOptions(
      screen.getByDisplayValue('选择要发布的 Cloud Run Job'),
      'synapse-staging-deposit-indexer',
    )
    await user.click(screen.getByRole('button', { name: '确认创建' }))

    await waitFor(() => {
      expect(apiMock.createScheduledCloudRunJobTask).toHaveBeenCalledWith({
        job_name: 'synapse-staging-deposit-indexer',
        environment: 'staging',
        source_ref_type: 'branch',
        source_ref: 'main',
        actor: 'operator',
        run_smoke_jobs: false,
        run_migrations: false,
      })
    })
    expect(apiMock.publishScheduledCloudRunJobTask).not.toHaveBeenCalled()
  })

  it('publishes a requested task from the records list', async () => {
    const user = userEvent.setup()
    render(<ScheduledJobsPanel />)

    expect(await screen.findByText('定时任务发布记录')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '发布到 staging' }))

    await waitFor(() => {
      expect(apiMock.publishScheduledCloudRunJobTask).toHaveBeenCalledWith(99, { actor: 'operator' })
    })
  })

  it('prefills the single-job form from a row and requires migration confirmation', async () => {
    const user = userEvent.setup()
    render(<ScheduledJobsPanel />)

    expect(await screen.findByText('定时任务发布记录')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '查看定时任务列表' }))
    await waitFor(() => {
      expect(screen.getAllByText('synapse-staging-db-migrate').length).toBeGreaterThan(0)
    })
    await user.click(screen.getAllByRole('button', { name: '创建发布任务' })[1])

    const taskSelect = await screen.findByLabelText('任务名称')
    expect((taskSelect as HTMLSelectElement).value).toBe('synapse-staging-db-migrate')
    expect(screen.getByText('该任务是 migration job。发布流程会执行它，必须确认后才能继续。')).toBeTruthy()
    expect(screen.getByRole('button', { name: '确认创建' })).toBeDisabled()
  })
})
