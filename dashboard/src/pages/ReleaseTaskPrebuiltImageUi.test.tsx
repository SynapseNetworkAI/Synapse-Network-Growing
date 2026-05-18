// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ReleaseTask } from '../api'
import { ReleaseTaskDetailModal } from './ReleaseTaskDetailPanel'
import { ReleaseTasksTable } from './ReleaseTasksTable'

function releaseTask(overrides: Partial<ReleaseTask> & { task_metadata?: Record<string, unknown> } = {}) {
  return {
    id: 42,
    source_type: 'manual',
    requirement_id: null,
    deployment_record_id: null,
    project_key: 'synapse-network',
    project_display_name: 'Synapse-Network',
    service_key: 'docs-front',
    branch_name: 'main',
    environment: 'staging',
    status: 'requested',
    actor: 'operator',
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
      pr_state: 'main',
      checks_status: 'success',
      checks_summary: 'main 分支可直接发布 staging，不需要 PR gate。',
      can_create_pr: false,
      can_deploy_staging: true,
      blocked_reason: null,
    },
    created_at: '2026-05-16T12:00:00Z',
    updated_at: '2026-05-16T12:00:00Z',
    ...overrides,
  } as ReleaseTask & { task_metadata?: Record<string, unknown> }
}

function renderTable(task: ReleaseTask & { task_metadata?: Record<string, unknown> }) {
  render(
    <ReleaseTasksTable
      tasks={[task]}
      total={1}
      limit={10}
      offset={0}
      loading={false}
      busyAction={null}
      gateStatusByTaskId={{}}
      onUpdateStatus={vi.fn()}
      onCreatePr={vi.fn()}
      onDeployStaging={vi.fn()}
      onDeployProduction={vi.fn()}
      onRefreshGate={vi.fn()}
      onRefresh={vi.fn()}
      onOpenDetails={vi.fn()}
      onPage={vi.fn()}
    />,
  )
}

describe('frontend prebuilt image release UI', () => {
  it('shows Cloud Build cost guidance and local worktree command for frontend staging tasks', () => {
    const task = releaseTask()
    renderTable(task)

    expect(screen.getByText(/未绑定 Prebuilt image/)).toBeTruthy()
    expect(screen.getByText(/预计多约 5 分钟/)).toBeTruthy()

    render(
      <ReleaseTaskDetailModal
        task={task}
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        onAttachPrebuiltImage={vi.fn()}
      />,
    )

    expect(screen.getByText('Local worktree build command')).toBeTruthy()
    expect(screen.getByText(/scripts\/deploy\/local_build_frontend_image\.sh/)).toBeTruthy()
    expect(screen.getByText(/--service docs-front/)).toBeTruthy()
    expect(screen.getByText(/--environment staging/)).toBeTruthy()
    expect(screen.getByText(/--release-task-id 42/)).toBeTruthy()
  })

  it('shows attached frontend prebuilt digest and commit summary', () => {
    renderTable(releaseTask({
      task_metadata: {
        prebuiltImageDigest: `us-central1-docker.pkg.dev/fabled-archive-494108-k5/synapse-staging/docs-front@sha256:${'a'.repeat(64)}`,
        sourceCommitSha: 'b'.repeat(40),
      },
    }))

    expect(screen.getByText(/Prebuilt image attached/)).toBeTruthy()
    expect(screen.getByText(/sha256:aaaaaaaaaaaa/)).toBeTruthy()
    expect(screen.getByText(/commit bbbbbbbbbbbb/)).toBeTruthy()
  })
})
