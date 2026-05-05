// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReleasesPage from './ReleasesPage'

const apiMock = vi.hoisted(() => ({
  getReleaseCandidates: vi.fn(),
  getReleaseTasks: vi.fn(),
  getReleaseTasksPage: vi.fn(),
  getOnlineReleaseRecords: vi.fn(),
  createReleaseTask: vi.fn(),
  getReleaseTaskBranchOptions: vi.fn(),
  updateReleaseTask: vi.fn(),
  createReleaseTaskPr: vi.fn(),
  deployReleaseTaskToStaging: vi.fn(),
  syncReleaseTaskDeploymentStatuses: vi.fn(),
  getProjectPolicies: vi.fn(),
  prepareRelease: vi.fn(),
  openReleasePr: vi.fn(),
  syncReleasePrStatuses: vi.fn(),
  getSdkPackageReleases: vi.fn(),
  initializeSdkReleaseTrain: vi.fn(),
  dryRunSdkPackageRelease: vi.fn(),
  publishSdkPackageRelease: vi.fn(),
  retrySdkPackageRelease: vi.fn(),
  syncSdkPackageReleaseStatuses: vi.fn(),
  getScheduledCloudRunJobsStatus: vi.fn(),
  publishScheduledCloudRunJobs: vi.fn(),
  syncScheduledCloudRunJobs: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

vi.mock('../apiReleaseTasks', () => ({
  getReleaseTasksPage: apiMock.getReleaseTasksPage,
}))

function candidate(overrides: Record<string, unknown> = {}) {
  const release = {
    id: 6,
    requirement_id: 9,
    workflow_run_id: 9,
    state: 'merged',
    project_id: null,
    project_key: 'synapse-network-growing',
    project_display_name: 'Synapse-Network-Growing',
    target_project_path: '/repo',
    status: 'merged',
    branch_name: 'ops/req-9-quality-gates',
    planned_branch_name: null,
    actual_branch_name: null,
    branch_reuse_status: null,
    base_branch: 'main',
    commit_sha: 'abc123',
    compare_url: null,
    pr_url: 'https://github.com/SynapseNetworkAI/Synapse-Network-Growing/pull/31',
    pr_number: 31,
    pr_status: 'merged',
    merged_at: '2026-04-21T11:19:24Z',
    merge_commit_sha: 'abc123',
    last_pr_status_synced_at: '2026-04-22T01:00:00Z',
    pr_sync_failure_summary: null,
    notes: null,
    blocker_kind: null,
    delivery_blocker_type: null,
    delivery_failure_excerpt: null,
    delivery_failure_raw_output: null,
    repairable: false,
    repairability: 'manual_only',
    repair_attempt_count: 0,
    next_action: null,
    workspace_blocker: null,
    workspace_mode: 'shared_checkout',
    prepared_at: null,
    delivered_at: '2026-04-21T11:20:00Z',
    created_at: '2026-04-21T10:00:00Z',
    updated_at: '2026-04-22T01:00:00Z',
    ...(overrides.release as Record<string, unknown> | undefined),
  }
  return {
    requirement: {
      id: 9,
      title: 'Quality gate release',
      project_display_name: 'Synapse-Network-Growing',
      project_key: 'synapse-network-growing',
      active_workflow_run_id: 9,
      active_workflow_run_summary: { id: 9, workflow_key: 'agent_self_repair', current_state: 'done' },
    },
    validation: { status: 'passed', updated_at: '2026-04-22T01:00:00Z' },
    release,
    ...overrides,
  }
}

function releaseTask(overrides: Record<string, unknown> = {}) {
  return {
    id: 42,
    source_type: 'manual',
    requirement_id: null,
    deployment_record_id: null,
    project_key: 'synapse-network-growing',
    project_display_name: 'Synapse-Network-Growing',
    service_key: 'gateway',
    branch_name: 'codex/manual-release',
    environment: 'staging',
    status: 'requested',
    actor: 'alice',
    operator: null,
    note: 'Manual staging release',
    deployment_status: null,
    deployment_external_run_id: null,
    deployment_external_url: null,
    deployment_failure_summary: null,
    deployment_health_status: null,
    deployment_workflow_file: null,
    deployment_commit_sha: null,
    deployment_started_at: null,
    deployment_finished_at: null,
    deployment_metadata: {},
    pr_gate: {
      branch_exists: true,
      pr_exists: false,
      pr_url: null,
      pr_number: null,
      pr_state: null,
      checks_status: 'unknown',
      checks_summary: null,
      can_create_pr: true,
      can_deploy_staging: false,
      blocked_reason: '未提交 PR',
    },
    created_at: '2026-04-22T01:00:00Z',
    updated_at: '2026-04-22T01:00:00Z',
    ...overrides,
  }
}

function onlineRecord(overrides: Record<string, unknown> = {}) {
  return {
    id: 88,
    project_key: 'synapse-network',
    project_display_name: 'Synapse-Network',
    service_key: 'gateway',
    environment: 'staging',
    action: 'deploy',
    status: 'succeeded',
    branch_name: 'codex/staging-release',
    commit_sha: 'abc123456789',
    actor: 'operator',
    trigger_source: 'release_task',
    workflow_file: 'deploy-staging.yml',
    external_run_id: '24919553458',
    external_url: 'https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/24919553458',
    rollback_target_sha: null,
    health_status: 'passed',
    notes: 'staging deploy succeeded',
    release_task_id: 42,
    metadata_summary: {
      revision: { gateway: 'synapse-gateway-0008' },
      manifest: 'gs://staging-evidence/release.json',
      imageTag: 'gateway:abc123456789',
    },
    metadata: {
      revision: { gateway: 'synapse-gateway-0008' },
      manifest: 'gs://staging-evidence/release.json',
      imageTag: 'gateway:abc123456789',
      deploy_repo_full_name: 'SynapseNetworkAI/Synapse-Network',
      sourceRef: 'codex/staging-release',
    },
    started_at: '2026-04-25T01:40:00Z',
    finished_at: '2026-04-25T01:44:00Z',
    created_at: '2026-04-25T01:40:00Z',
    updated_at: '2026-04-25T01:44:00Z',
    ...overrides,
  }
}

describe('ReleasesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getReleaseCandidates.mockResolvedValue([
      candidate(),
      candidate({
        requirement: {
          id: 10,
          title: 'Closed PR release',
          project_display_name: 'Synapse-Network-Growing',
          project_key: 'synapse-network-growing',
          active_workflow_run_id: null,
          active_workflow_run_summary: null,
        },
        release: {
          id: 7,
          requirement_id: 10,
          workflow_run_id: null,
          state: 'abandoned',
          status: 'pr_closed',
          pr_number: 404,
          pr_status: 'not_found',
          pr_sync_failure_summary: 'PR removed from GitHub or no longer accessible',
        },
      }),
    ])
    apiMock.syncReleasePrStatuses.mockResolvedValue({
      workflow_key: 'release_pr_status_sweep',
      status: 'completed',
      run_started_at: '2026-04-22T01:00:00Z',
      run_id: 33,
      result: { processed_count: 2, merged_ids: [6], closed_ids: [], missing_ids: [7] },
    })
    apiMock.syncReleaseTaskDeploymentStatuses.mockResolvedValue({
      processed_count: 1,
      succeeded_ids: [88],
      failed_ids: [],
      running_ids: [],
      pending_ids: [],
      error_ids: [],
    })
    apiMock.getReleaseTasks.mockResolvedValue([
      releaseTask(),
      releaseTask({
        id: 43,
        source_type: 'requirement_flow',
        requirement_id: 12,
        branch_name: 'ops/req-12-release',
        environment: 'production',
        status: 'completed',
        actor: 'planner',
        operator: 'ops-lead',
        note: 'Production release manually completed',
      }),
    ])
    apiMock.getReleaseTasksPage.mockImplementation(async () => {
      const items = await apiMock.getReleaseTasks()
      return { items, total: items.length, limit: 10, offset: 0 }
    })
    apiMock.getOnlineReleaseRecords.mockResolvedValue([
      onlineRecord(),
    ])
    apiMock.getProjectPolicies.mockResolvedValue([
      {
        id: 1,
        project_id: null,
        project_key: 'synapse-network-growing',
        display_name: 'Synapse-Network-Growing',
        root_path: '/repo',
        status: 'active',
        allowed_write_globs: [],
        forbidden_globs: [],
        required_checks: [],
        release_mode: 'manual',
        requires_manual_approval: true,
        autonomy_mode: 'recommend',
        allow_rebalance: true,
        allow_preemption: false,
        capability_matrix: { shell_access: true, git_read: true, git_write: true, git_push: true, network_access: true, publish: false },
        interrupt_policy: { operator_confirmation_actions: [], auto_pause_on_events: [], auto_abort_on_events: [] },
        scheduler_weight: 1,
        max_parallel_requirements: 1,
        portfolio_budget_points: 100,
        deploy_repo_full_name: null,
        deploy_strategy: 'disabled',
        deploy_trigger_enabled: false,
        staging_host_label: null,
        production_host_label: null,
        staging_workflow_file: 'deploy-staging.yml',
        production_workflow_file: 'deploy-production.yml',
        notes: null,
        created_at: null,
        updated_at: null,
      },
    ])
    apiMock.createReleaseTask.mockResolvedValue(releaseTask({ id: 44, branch_name: 'codex/new-release' }))
    apiMock.getReleaseTaskBranchOptions.mockResolvedValue([
      { name: 'main', commit_sha: 'abc123', protected: true, is_default: true, source: 'github' },
      { name: 'codex/new-release', commit_sha: 'def456', protected: false, is_default: false, source: 'github' },
    ])
    apiMock.updateReleaseTask.mockResolvedValue(releaseTask({ status: 'completed', operator: 'operator' }))
    apiMock.createReleaseTaskPr.mockResolvedValue(releaseTask({
      pr_gate: {
        branch_exists: true,
        pr_exists: true,
        pr_url: 'https://github.com/SynapseNetworkAI/Synapse-Network/pull/77',
        pr_number: 77,
        pr_state: 'open',
        checks_status: 'pending',
        checks_summary: 'PR checks 运行中',
        can_create_pr: false,
        can_deploy_staging: false,
        blocked_reason: 'PR checks 运行中',
      },
    }))
    apiMock.deployReleaseTaskToStaging.mockResolvedValue(
      releaseTask({
        status: 'deploying',
        deployment_record_id: 9,
        deployment_status: 'requested',
        deployment_health_status: 'checking',
        operator: 'operator',
      }),
    )
    apiMock.getSdkPackageReleases.mockResolvedValue([])
    apiMock.initializeSdkReleaseTrain.mockResolvedValue([])
    apiMock.dryRunSdkPackageRelease.mockResolvedValue({})
    apiMock.publishSdkPackageRelease.mockResolvedValue({})
    apiMock.retrySdkPackageRelease.mockResolvedValue({})
    apiMock.syncSdkPackageReleaseStatuses.mockResolvedValue({ processed_count: 0, publishing_ids: [], ready_ids: [], published_ids: [], failed_ids: [], error_ids: [] })
    apiMock.getScheduledCloudRunJobsStatus.mockResolvedValue({
      diagnostics: [],
      updated_at: '2026-05-03T01:00:00Z',
      items: [
        {
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
        },
        {
          job_name: 'synapse-staging-db-migrate',
          family: 'gateway',
          job_type: 'migration',
          cadence: 'release_time',
          command: 'gateway database migration job',
          purpose: 'Gateway DB migration',
          scheduler_job: null,
          freshness_required: false,
          migration_execution_required: true,
          publish_status: 'unknown',
          scheduler_status: 'manual_job',
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
        },
      ],
    })
    apiMock.publishScheduledCloudRunJobs.mockResolvedValue({
      deployment_record_id: 99,
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

  it('shows merged and closed PR sync states', async () => {
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    expect(await screen.findByText('已合并')).toBeTruthy()
    expect(screen.getByText('PR 已关闭')).toBeTruthy()
    expect(screen.getByText(/GitHub: merged/)).toBeTruthy()
    expect(screen.getByText(/PR removed from GitHub/)).toBeTruthy()
  })

  it('runs release status sync from the releases page', async () => {
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    const button = await screen.findByRole('button', { name: '同步状态' })
    await user.click(button)

    await waitFor(() => {
      expect(apiMock.syncReleasePrStatuses).toHaveBeenCalledTimes(1)
      expect(apiMock.syncReleaseTaskDeploymentStatuses).toHaveBeenCalledTimes(1)
      expect(apiMock.getReleaseCandidates).toHaveBeenCalledTimes(2)
    })
  })

  it('keeps release candidates usable if online records projection is temporarily unavailable', async () => {
    apiMock.getOnlineReleaseRecords.mockRejectedValue(new Error('path.requirement_id: Input should be a valid integer'))

    render(<ReleasesPage />, { wrapper: MemoryRouter })

    expect(await screen.findByText(/Quality gate release/)).toBeTruthy()
    expect(screen.getByText('发布列表')).toBeTruthy()
  })

  it('shows release management tasks and hides actions for terminal tasks', async () => {
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))

    expect(screen.getByText('codex/manual-release')).toBeTruthy()
    expect(screen.getAllByText('Service: gateway').length).toBeGreaterThan(0)
    expect(screen.getByText('ops/req-12-release')).toBeTruthy()
    expect(screen.getByText('人工创建')).toBeTruthy()
    expect(screen.getByText('需求流转')).toBeTruthy()
    expect(screen.getByRole('button', { name: '标记为已完成' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '提交 PR' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '发布到 staging' })).toBeNull()
    expect(screen.getAllByRole('button', { name: '详情' }).length).toBeGreaterThanOrEqual(2)
  })

  it('does not show stale GitHub failure logs for a successful release task', async () => {
    apiMock.getReleaseTasks.mockResolvedValue([
      releaseTask({
        id: 42,
        branch_name: 'main',
        status: 'completed',
        deployment_record_id: 40,
        deployment_status: 'succeeded',
        deployment_health_status: 'passed',
        deployment_failure_summary: 'staging deploy succeeded; GitHub Actions run passed.',
        deployment_external_run_id: '25274187647',
        deployment_external_url: 'https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/25274187647',
        deployment_metadata: {
          githubFailureLogStatus: 'ok',
          githubFailureLogExcerpt: 'unauthorized_client attribute condition',
          githubRunConclusion: 'success',
        },
      }),
    ])
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))

    expect(screen.getByText('Deploy: 上线成功')).toBeTruthy()
    expect(screen.getByText('Health: 通过')).toBeTruthy()
    expect(screen.queryByText(/unauthorized_client/)).toBeNull()

    await user.click(screen.getByRole('button', { name: '详情' }))
    const dialog = await screen.findByRole('dialog', { name: '发布任务 #42' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(within(dialog).getByText('Run ID：25274187647')).toBeTruthy()
    expect(within(dialog).queryByText(/GitHub Actions failed step/)).toBeNull()
    expect(within(dialog).queryByText(/attribute condition/)).toBeNull()
  })

  it('creates a PR for staging tasks before deploy is available', async () => {
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))
    await user.click(screen.getByRole('button', { name: '提交 PR' }))

    await waitFor(() => {
      expect(apiMock.createReleaseTaskPr).toHaveBeenCalledWith(42, {
        actor: 'operator',
        note: 'Manual staging release',
      })
      expect(apiMock.deployReleaseTaskToStaging).not.toHaveBeenCalled()
    })
  })

  it('only enables staging deploy after PR checks pass', async () => {
    apiMock.getReleaseTasks.mockResolvedValue([
      releaseTask({
        pr_gate: {
          branch_exists: true,
          pr_exists: true,
          pr_url: 'https://github.com/SynapseNetworkAI/Synapse-Network/pull/91',
          pr_number: 91,
          pr_state: 'open',
          checks_status: 'success',
          checks_summary: '4 checks passed',
          can_create_pr: false,
          can_deploy_staging: true,
          blocked_reason: null,
        },
      }),
    ])
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))
    expect(screen.getByText(/PR Gate: Checks 通过/)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '发布到 staging' }))

    await waitFor(() => {
      expect(apiMock.deployReleaseTaskToStaging).toHaveBeenCalledWith(42, {
        actor: 'operator',
        note: 'Manual staging release',
      })
    })
  })

  it('allows main branch staging deploy without PR gate', async () => {
    apiMock.getReleaseTasks.mockResolvedValue([
      releaseTask({
        branch_name: 'main',
        pr_gate: {
          branch_exists: true,
          pr_exists: false,
          pr_url: null,
          pr_number: null,
          pr_state: 'main',
          checks_status: 'success',
          checks_summary: 'main 分支可直接发布 staging，不需要 PR gate。',
          can_create_pr: false,
          can_deploy_staging: true,
          blocked_reason: null,
        },
      }),
    ])
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))

    expect(screen.queryByRole('button', { name: '提交 PR' })).toBeNull()
    expect(screen.getByText(/PR Gate: main 可直接发布 staging/)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '发布到 staging' }))

    await waitFor(() => {
      expect(apiMock.deployReleaseTaskToStaging).toHaveBeenCalledWith(42, {
        actor: 'operator',
        note: 'Manual staging release',
      })
    })
  })

  it('explains why green draft PRs cannot deploy staging yet', async () => {
    apiMock.getReleaseTasks.mockResolvedValue([
      releaseTask({
        pr_gate: {
          branch_exists: true,
          pr_exists: true,
          pr_url: 'https://github.com/SynapseNetworkAI/Synapse-Network/pull/92',
          pr_number: 92,
          pr_state: 'draft',
          checks_status: 'success',
          checks_summary: '1 checks passed',
          can_create_pr: false,
          can_deploy_staging: false,
          blocked_reason: 'PR 仍是 Draft，请先在 GitHub 标记 Ready for review 后再发布 staging',
        },
      }),
    ])
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))

    expect(screen.getByText(/PR Gate: PR 是 Draft/)).toBeTruthy()
    expect(screen.getByText(/PR 仍是 Draft/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '发布到 staging' })).toBeDisabled()
  })

  it('opens release task details with deployment record and GitHub Actions link', async () => {
    apiMock.getReleaseTasks.mockResolvedValue([
      releaseTask({
        deployment_record_id: 88,
        deployment_status: 'requested',
        deployment_external_run_id: '123456',
        deployment_external_url: 'https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/123456',
        deployment_health_status: 'pending',
        deployment_workflow_file: 'deploy-staging.yml',
        deployment_commit_sha: 'abc123',
        deployment_started_at: '2026-04-22T01:02:00Z',
        deployment_metadata: { deployScope: 'gateway' },
        pr_gate: {
          branch_exists: true,
          pr_exists: true,
          pr_url: 'https://github.com/SynapseNetworkAI/Synapse-Network/pull/99',
          pr_number: 99,
          pr_state: 'open',
          checks_status: 'success',
          checks_summary: '3 checks passed',
          can_create_pr: false,
          can_deploy_staging: false,
          blocked_reason: null,
        },
      }),
    ])
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))
    await user.click(screen.getByRole('button', { name: '详情' }))

    expect(screen.getByText('Deployment Record')).toBeTruthy()
    expect(screen.getByText('Record ID：88')).toBeTruthy()
    expect(screen.getByText('Workflow：deploy-staging.yml')).toBeTruthy()
    expect(screen.getByRole('link', { name: '打开 GitHub Actions 日志' })).toHaveAttribute(
      'href',
      'https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/123456',
    )
  })

  it('shows successful deployment records in the online records tab', async () => {
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '上线记录' }))

    expect(screen.getByText('Online Records')).toBeTruthy()
    expect(screen.getByText(/这里只展示成功上线账本/)).toBeTruthy()
    expect(screen.getByText('codex/staging-release')).toBeTruthy()
    expect(screen.getByText('abc1234567')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Run 24919553458' })).toHaveAttribute(
      'href',
      'https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/24919553458',
    )
  })

  it('opens online record details with evidence and rollback guidance', async () => {
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => ({ opener: null }) as Window)
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '上线记录' }))
    await user.click(screen.getByRole('button', { name: '详情' }))

    expect(screen.getByText('上线记录 #88')).toBeTruthy()
    expect(screen.getByText('Deployment Evidence')).toBeTruthy()
    expect(screen.getByText('Workflow：deploy-staging.yml')).toBeTruthy()
    expect(screen.getByText('Release Task：#42')).toBeTruthy()
    expect(screen.getByText('回滚说明')).toBeTruthy()
    expect(screen.getByText(/Runtime rollback 应选择这里的历史成功上线记录/)).toBeTruthy()
    expect(screen.getAllByText(/gs:\/\/staging-evidence\/release.json/).length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: '打开 GitHub Actions 日志' }))
    expect(openSpy).toHaveBeenCalledWith(
      'https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/24919553458',
      '_blank',
      'noopener,noreferrer',
    )
    await user.click(screen.getAllByRole('button', { name: '打开 PR' }).at(-1)!)
    expect(openSpy).toHaveBeenCalledWith(
      'https://github.com/SynapseNetworkAI/Synapse-Network/pulls?q=is%3Apr+head%3Acodex%2Fstaging-release',
      '_blank',
      'noopener,noreferrer',
    )
    openSpy.mockRestore()
  })

  it('falls back to metadata GitHub Actions URL for online record details', async () => {
    apiMock.getOnlineReleaseRecords.mockResolvedValue([
      onlineRecord({
        external_run_id: null,
        external_url: null,
        metadata_summary: { githubRunUrl: 'https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/555' },
        metadata: {
          githubRunUrl: 'https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/555',
          deploy_repo_full_name: 'SynapseNetworkAI/Synapse-Network',
          sourceRef: 'codex/staging-release',
        },
      }),
    ])
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => ({ opener: null }) as Window)
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '上线记录' }))
    await user.click(screen.getByRole('button', { name: '详情' }))
    await user.click(screen.getByRole('button', { name: '打开 GitHub Actions 日志' }))

    expect(openSpy).toHaveBeenCalledWith(
      'https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/555',
      '_blank',
      'noopener,noreferrer',
    )
    openSpy.mockRestore()
  })

  it('does not show PR or staging actions when the branch is missing', async () => {
    apiMock.getReleaseTasks.mockResolvedValue([
      releaseTask({
        pr_gate: {
          branch_exists: false,
          pr_exists: false,
          pr_url: null,
          pr_number: null,
          pr_state: null,
          checks_status: 'unknown',
          checks_summary: null,
          can_create_pr: false,
          can_deploy_staging: false,
          blocked_reason: '分支不存在，请重新选择有效远端分支',
        },
      }),
    ])
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))

    expect(screen.getByText(/PR Gate: 分支不存在/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: '提交 PR' })).toBeNull()
    expect(screen.queryByRole('button', { name: '发布到 staging' })).toBeNull()
  })

  it('creates a manual release task from the release management modal', async () => {
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))
    await user.click(screen.getByRole('button', { name: '新建发布任务' }))
    await user.selectOptions(screen.getByLabelText('项目 / 服务'), 'synapse-network::gateway')
    await waitFor(() => {
      expect(apiMock.getReleaseTaskBranchOptions).toHaveBeenCalledWith({
        project_key: 'synapse-network',
        service_key: 'gateway',
      })
    })
    await user.type(screen.getByLabelText('筛选分支'), 'new')
    expect(screen.queryByRole('option', { name: /main/ })).toBeNull()
    expect(screen.getByRole('option', { name: /codex\/new-release/ })).toBeTruthy()
    await user.selectOptions(screen.getByLabelText('分支'), 'codex/new-release')
    await user.click(screen.getByRole('button', { name: '创建发布任务' }))

    await waitFor(() => {
      expect(apiMock.createReleaseTask).toHaveBeenCalledWith({
        project_key: 'synapse-network',
        project_display_name: 'Synapse-Network',
        service_key: 'gateway',
        branch_name: 'codex/new-release',
        environment: 'staging',
        actor: 'operator',
        note: null,
      })
    })
  })

  it('offers Synapse-Network-Provider as a staging release target', async () => {
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))
    await user.click(screen.getByRole('button', { name: '新建发布任务' }))
    expect(screen.getByRole('option', { name: 'Synapse-Network-Provider · Provider Service' })).toBeTruthy()

    await user.selectOptions(screen.getByLabelText('项目 / 服务'), 'synapse-network-provider::provider-service')
    await waitFor(() => {
      expect(apiMock.getReleaseTaskBranchOptions).toHaveBeenCalledWith({
        project_key: 'synapse-network-provider',
        service_key: 'provider-service',
      })
    })
    await user.selectOptions(screen.getByLabelText('分支'), 'main')
    await user.click(screen.getByRole('button', { name: '创建发布任务' }))

    await waitFor(() => {
      expect(apiMock.createReleaseTask).toHaveBeenCalledWith({
        project_key: 'synapse-network-provider',
        project_display_name: 'Synapse-Network-Provider',
        service_key: 'provider-service',
        branch_name: 'main',
        environment: 'staging',
        actor: 'operator',
        note: null,
      })
    })
  })

  it('offers Synapse-Network docs front as a staging release target', async () => {
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))
    await user.click(screen.getByRole('button', { name: '新建发布任务' }))
    expect(screen.getByRole('option', { name: 'Synapse-Network · Docs Front' })).toBeTruthy()

    await user.selectOptions(screen.getByLabelText('项目 / 服务'), 'synapse-network::docs-front')
    await waitFor(() => {
      expect(apiMock.getReleaseTaskBranchOptions).toHaveBeenCalledWith({
        project_key: 'synapse-network',
        service_key: 'docs-front',
      })
    })
    await user.selectOptions(screen.getByLabelText('分支'), 'codex/new-release')
    await user.click(screen.getByRole('button', { name: '创建发布任务' }))

    await waitFor(() => {
      expect(apiMock.createReleaseTask).toHaveBeenCalledWith({
        project_key: 'synapse-network',
        project_display_name: 'Synapse-Network',
        service_key: 'docs-front',
        branch_name: 'codex/new-release',
        environment: 'staging',
        actor: 'operator',
        note: null,
      })
    })
  })

  it('shows production safety copy and marks requested task failed', async () => {
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))
    await user.click(screen.getByRole('button', { name: '新建发布任务' }))
    await user.selectOptions(screen.getByLabelText('发布环境'), 'production')
    expect(screen.getByText(/不会自动部署生产/)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '关闭' }))

    await user.click(screen.getByRole('button', { name: '标记为失败' }))
    await waitFor(() => {
      expect(apiMock.updateReleaseTask).toHaveBeenCalledWith(42, {
        status: 'failed',
        operator: 'operator',
        note: 'Manual staging release',
      })
    })
  })

  it('opens the task modal without project policies and triggers staging deploy separately', async () => {
    apiMock.getProjectPolicies.mockResolvedValue([])
    apiMock.getReleaseTasks.mockResolvedValue([
      releaseTask({
        pr_gate: {
          branch_exists: true,
          pr_exists: true,
          pr_url: 'https://github.com/SynapseNetworkAI/Synapse-Network/pull/90',
          pr_number: 90,
          pr_state: 'open',
          checks_status: 'success',
          checks_summary: '3 checks passed',
          can_create_pr: false,
          can_deploy_staging: true,
          blocked_reason: null,
        },
      }),
    ])
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '发布管理' }))
    await user.click(screen.getByRole('button', { name: '新建发布任务' }))

    expect(screen.getByText(/创建任务不会自动上线/)).toBeTruthy()
    expect(await screen.findByText(/分支从发布仓库的 GitHub branch list 读取/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '创建发布任务' })).toBeTruthy()

    await user.click(screen.getByRole('button', { name: '关闭' }))
    await user.click(screen.getByRole('button', { name: '发布到 staging' }))

    await waitFor(() => {
      expect(apiMock.deployReleaseTaskToStaging).toHaveBeenCalledWith(42, {
        actor: 'operator',
        note: 'Manual staging release',
      })
    })
  })

})
