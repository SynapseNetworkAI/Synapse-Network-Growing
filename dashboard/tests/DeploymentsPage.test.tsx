import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DeploymentsPage from '../src/pages/DeploymentsPage'

const mockApi = {
  getDeploymentOverview: vi.fn(),
  syncRequirementReviewPr: vi.fn(),
  publishRequirement: vi.fn(),
  deployRequirementToStaging: vi.fn(),
  promoteRequirementToProduction: vi.fn(),
  rollbackRequirementDeployment: vi.fn(),
}

vi.mock('../src/api', async () => {
  const actual = await vi.importActual('../src/api')
  return {
    ...actual,
    api: {
      ...actual.api,
      getDeploymentOverview: (...args: unknown[]) => mockApi.getDeploymentOverview(...args),
      syncRequirementReviewPr: (...args: unknown[]) => mockApi.syncRequirementReviewPr(...args),
      publishRequirement: (...args: unknown[]) => mockApi.publishRequirement(...args),
      deployRequirementToStaging: (...args: unknown[]) => mockApi.deployRequirementToStaging(...args),
      promoteRequirementToProduction: (...args: unknown[]) => mockApi.promoteRequirementToProduction(...args),
      rollbackRequirementDeployment: (...args: unknown[]) => mockApi.rollbackRequirementDeployment(...args),
    },
  }
})

const OVERVIEW = {
  project_overviews: [
    {
      project_policy_id: 1,
      project_key: 'synapse-network',
      display_name: 'Synapse-Network',
      deploy_repo_full_name: 'cliff-personal/Synapse-Network',
      deploy_strategy: 'github_actions_ssh',
      deploy_trigger_enabled: true,
      staging_host_label: 'staging-vm',
      production_host_label: 'prod-vm',
      environment_statuses: [
        {
          environment: 'staging',
          project_key: 'synapse-network',
          deploy_repo_full_name: 'cliff-personal/Synapse-Network',
          host_label: 'staging-vm',
          deploy_strategy: 'github_actions_ssh',
          trigger_enabled: true,
          current_commit_sha: 'abc123',
          current_branch: 'main',
          last_success_at: '2026-04-13T12:00:00Z',
          health_status: 'healthy',
          last_trigger_source: 'ops_console',
          last_external_url: 'https://github.com/cliff-personal/Synapse-Network/actions/runs/10',
          last_record_id: 10,
        },
        {
          environment: 'production',
          project_key: 'synapse-network',
          deploy_repo_full_name: 'cliff-personal/Synapse-Network',
          host_label: 'prod-vm',
          deploy_strategy: 'github_actions_ssh',
          trigger_enabled: true,
          current_commit_sha: 'abc100',
          current_branch: 'main',
          last_success_at: '2026-04-12T12:00:00Z',
          health_status: 'healthy',
          last_trigger_source: 'ops_console',
          last_external_url: null,
          last_record_id: 9,
        },
      ],
      recent_records: [
        {
          id: 10,
          requirement_id: 1,
          project_policy_id: 1,
          project_key: 'synapse-network',
          environment: 'staging',
          action: 'deploy',
          status: 'succeeded',
          commit_sha: 'abc123',
          branch_name: 'ops/release-candidate',
          workflow_file: 'deploy-staging.yml',
          external_run_id: null,
          external_url: 'https://github.com/cliff-personal/Synapse-Network/actions/runs/10',
          actor: 'operator',
          trigger_source: 'ops_console',
          rollback_target_sha: null,
          health_status: 'healthy',
          notes: null,
          metadata: {},
          started_at: '2026-04-13T12:00:00Z',
          finished_at: '2026-04-13T12:02:00Z',
          created_at: '2026-04-13T12:00:00Z',
          updated_at: '2026-04-13T12:02:00Z',
        },
      ],
    },
  ],
  release_candidates: [
    {
      requirement_id: 1,
      title: 'Prepare staging release',
      status: 'done',
      priority: 'high',
      source: 'manual',
      source_ref: null,
      project_key: 'synapse-network',
      project_display_name: 'Synapse-Network',
      target_project_path: '/Users/cliff/workspace/agent/Synapse-Network',
      updated_at: '2026-04-13T12:03:00Z',
      delivery_state: {
        branch_name: 'ops/release-candidate',
        branch_strategy: 'requirement_branch',
        base_branch: 'main',
        review_status: 'ready',
        publish_status: 'review_ready',
        release_mode: 'manual',
        requires_manual_approval: true,
        required_checks: ['pytest -q'],
        confirmed_checks: [],
        pending_checks: ['pytest -q'],
        publish_blockers: [],
        review_surface_summary: 'Review bundle ready.',
        rollback_hint_markdown: 'Rollback to last stable sha if needed.',
        review_ready_at: null,
        published_at: null,
        publish_note: null,
        vcs_status: 'ahead',
        vcs_remote_name: 'origin',
        vcs_repositories: [],
        compare_url: 'https://github.com/cliff-personal/Synapse-Network/compare/main...ops/release-candidate',
        pr_status: 'draft',
        pr_number: 12,
        pr_url: 'https://github.com/cliff-personal/Synapse-Network/pull/12',
        head_branch: 'ops/release-candidate',
        latest_commit_sha: 'abc123',
        latest_remote_sha: 'abc123',
        review_bundle_generated_at: null,
        last_pushed_at: '2026-04-13T12:01:00Z',
        pr_metadata: null,
        promotion_checklist: [
          { key: 'checks', label: 'Checks green', detail: 'pytest -q must pass', status: 'pending' },
        ],
        staging_status: {
          environment: 'staging',
          project_key: 'synapse-network',
          deploy_repo_full_name: 'cliff-personal/Synapse-Network',
          host_label: 'staging-vm',
          deploy_strategy: 'github_actions_ssh',
          trigger_enabled: true,
          current_commit_sha: 'abc123',
          current_branch: 'main',
          last_success_at: '2026-04-13T12:00:00Z',
          health_status: 'healthy',
          last_trigger_source: 'ops_console',
          last_external_url: null,
          last_record_id: 10,
        },
        production_status: null,
        last_deployed_sha: 'abc123',
        last_deployed_at: '2026-04-13T12:02:00Z',
        deploy_readiness: {
          ready: true,
          blockers: [],
          project_key: 'synapse-network',
          deploy_repo_full_name: 'cliff-personal/Synapse-Network',
          deliverable_commit_sha: 'abc123',
        },
      },
      deployment_records: [],
    },
  ],
}

describe('DeploymentsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getDeploymentOverview.mockResolvedValue(OVERVIEW)
    mockApi.syncRequirementReviewPr.mockResolvedValue({})
    mockApi.publishRequirement.mockResolvedValue({})
    mockApi.deployRequirementToStaging.mockResolvedValue({})
    mockApi.promoteRequirementToProduction.mockResolvedValue({})
    mockApi.rollbackRequirementDeployment.mockResolvedValue({})
  })

  it('renders environment overview and release candidates', async () => {
    render(<MemoryRouter><DeploymentsPage /></MemoryRouter>)

    await waitFor(() => expect(mockApi.getDeploymentOverview).toHaveBeenCalledTimes(1))

    expect(screen.getByTestId('deployments-page')).toBeInTheDocument()
    expect(screen.getByTestId('deployment-project-synapse-network')).toHaveTextContent('staging-vm')
    expect(screen.getByTestId('deployment-candidate-1')).toHaveTextContent('Prepare staging release')
    expect(screen.getByRole('link', { name: /#1 Prepare staging release/i })).toHaveAttribute('href', '/requirements/1')
  })

  it('triggers staging deploy from the release center', async () => {
    render(<MemoryRouter><DeploymentsPage /></MemoryRouter>)

    await waitFor(() => expect(mockApi.getDeploymentOverview).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: 'Deploy To Staging' }))

    await waitFor(() => {
      expect(mockApi.deployRequirementToStaging).toHaveBeenCalledWith(1, {
        actor: 'operator',
        note: null,
      })
    })
  })
})
