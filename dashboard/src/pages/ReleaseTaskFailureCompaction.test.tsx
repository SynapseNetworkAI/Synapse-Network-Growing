// @vitest-environment jsdom

import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ReleaseTask } from '../api'
import {
  ReleaseTaskCompactFailure,
  ReleaseTaskDetailModal,
  ReleaseTaskFailureSnippet,
  releaseTaskFailureSummary,
} from './ReleaseTaskDetailPanel'

function releaseTask(overrides: Partial<ReleaseTask> = {}): ReleaseTask {
  return {
    id: 78,
    source_type: 'manual',
    requirement_id: null,
    deployment_record_id: 78,
    project_key: 'synapse-network',
    project_display_name: 'Synapse-Network',
    service_key: 'gateway',
    branch_name: 'main',
    environment: 'staging',
    status: 'failed',
    actor: 'operator',
    operator: 'operator',
    note: 'Manual staging release',
    deployment_status: 'failed',
    deployment_external_run_id: null,
    deployment_external_url: null,
    deployment_failure_summary: 'Local runner staging deploy failure.',
    deployment_health_status: 'failed',
    deployment_workflow_file: 'local_deploy_runner',
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
      can_create_pr: false,
      can_deploy_staging: true,
      blocked_reason: null,
    },
    created_at: '2026-05-04T01:00:00Z',
    updated_at: '2026-05-04T01:00:00Z',
    ...overrides,
  }
}

describe('Release task failure compaction', () => {
  it('compacts long multiline failures into a bounded summary', () => {
    const result = releaseTaskFailureSummary(
      [
        'Local runner staging deploy failure.',
        'staging drift guard failed:',
        'PERMISSION_DENIED secretmanager.versions.access repeated repeated repeated repeated repeated repeated repeated repeated repeated',
        'UNIQUE_FULL_FAILURE_TAIL',
      ].join('\n'),
      120,
    )

    expect(result.truncated).toBe(true)
    expect(result.text.length).toBeLessThanOrEqual(120)
    expect(result.text).not.toContain('UNIQUE_FULL_FAILURE_TAIL')
  })

  it('shows compact failure text with a details hint', () => {
    render(
      <ReleaseTaskCompactFailure value="Local runner staging deploy failure. repeated repeated repeated repeated repeated repeated repeated repeated repeated repeated repeated repeated repeated repeated repeated repeated repeated repeated repeated UNIQUE_FULL_FAILURE_TAIL" />,
    )

    expect(screen.getByText('详情查看完整失败日志')).toBeTruthy()
    expect(screen.queryByText(/UNIQUE_FULL_FAILURE_TAIL/)).toBeNull()
  })

  it('keeps local runner excerpts compact outside details', () => {
    const longExcerpt = [
      'Run staging smoke check',
      'curl returned 403 while reading a protected endpoint repeated repeated repeated repeated repeated repeated repeated repeated repeated repeated',
      'Local runner log line with detailed remediation context',
      'UNIQUE_ACTIONS_EXCERPT_TAIL',
    ].join('\n')

    render(<ReleaseTaskFailureSnippet task={releaseTask({ deployment_metadata: { githubFailureLogExcerpt: longExcerpt } })} />)

    expect(screen.getByText('详情查看完整失败日志')).toBeTruthy()
    expect(screen.queryByText(/UNIQUE_ACTIONS_EXCERPT_TAIL/)).toBeNull()
  })

  it('shows full failure details inside the centered modal', () => {
    const longFailure = 'Local runner staging deploy failure. UNIQUE_FULL_FAILURE_TAIL'
    const longExcerpt = 'Run staging smoke check\nUNIQUE_ACTIONS_EXCERPT_TAIL'

    render(
      <ReleaseTaskDetailModal
        task={releaseTask({
          deployment_failure_summary: longFailure,
          deployment_metadata: { githubFailureLogStatus: 'ok', githubFailureLogExcerpt: longExcerpt },
        })}
        onClose={vi.fn()}
        onRefresh={vi.fn()}
      />,
    )

    const dialog = screen.getByRole('dialog', { name: '发布任务 #78' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(within(dialog).getByText(/UNIQUE_FULL_FAILURE_TAIL/)).toBeTruthy()
    expect(within(dialog).getAllByText(/UNIQUE_ACTIONS_EXCERPT_TAIL/).length).toBeGreaterThanOrEqual(1)
  })
})
