// @vitest-environment jsdom

import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { MissionWorkbenchPanel } from './MissionWorkbenchPanel'

const socialDraft = {
  id: 'social_draft:21',
  parent_id: 'lane:growth_lead:synapse_public_preview_traction',
  level: 2,
  type: 'publishing_draft',
  title: 'AI agents need a payment primitive',
  status: 'needs_review',
  lane: 'growth_lead',
  goal_key: 'synapse_public_preview_traction',
  stage_statuses: {
    opportunity: 'waiting',
    candidate: 'missing',
    requirement: 'missing',
    workflow: 'missing',
    pr: 'missing',
    release: 'missing',
    online_record: 'missing',
  },
  process_key: 'social_draft',
  process_stages: [
    { key: 'generated', label: 'Generated', status: 'completed' },
    { key: 'needs_review', label: 'Needs Review', status: 'waiting' },
    { key: 'approved', label: 'Approved/Edited', status: 'missing' },
    { key: 'published', label: 'Published', status: 'missing' },
    { key: 'metrics', label: 'Metrics', status: 'missing' },
  ],
  next_action: 'Review, edit, publish, or reject the X draft.',
  deep_link: '/publishing?tab=drafts',
  detail_api: '/api/social/posts/21',
  updated_at: '2026-04-29T00:00:00Z',
  evidence_label: '900 chars',
  children: [],
}

const workbench = {
  root: {
    id: 'goal:synapse_public_preview_traction',
    parent_id: null,
    level: 0,
    type: 'company_goal',
    title: 'Launch Synapse Network public preview',
    status: 'active',
    lane: null,
    goal_key: 'synapse_public_preview_traction',
    stage_statuses: socialDraft.stage_statuses,
    process_key: null,
    process_stages: [],
    next_action: 'Open active company goal.',
    deep_link: '/planning?tab=goals',
    detail_api: '/api/planning/goals/1',
    updated_at: '2026-04-29T00:00:00Z',
    evidence_label: '',
    children: [
      {
        id: 'lane:growth_lead:synapse_public_preview_traction',
        parent_id: 'goal:synapse_public_preview_traction',
        level: 1,
        type: 'mission_lane',
        title: 'Growth Lead',
        status: 'waiting',
        lane: 'growth_lead',
        goal_key: 'synapse_public_preview_traction',
        stage_statuses: socialDraft.stage_statuses,
        process_key: null,
        process_stages: [],
        next_action: 'Open Publishing.',
        deep_link: '/publishing',
        detail_api: null,
        updated_at: null,
        evidence_label: '',
        children: [socialDraft],
      },
    ],
  },
  unassigned: { count: 0, items: [] },
  summary: { active_goal_count: 1, work_item_count: 2 },
  manifest: { id: 1, updated_at: '2026-04-29T00:00:00Z' },
}

describe('MissionWorkbenchPanel', () => {
  it('renders the process rail supplied by each work item', () => {
    render(
      <MemoryRouter>
        <MissionWorkbenchPanel workbench={workbench} />
      </MemoryRouter>,
    )

    const row = screen.getByTestId('mission-workbench-row-social_draft:21')
    expect(within(row).getByText('Generated')).toBeInTheDocument()
    expect(within(row).getByText('Needs Review')).toBeInTheDocument()
    expect(within(row).queryByText('Requirement')).not.toBeInTheDocument()
    expect(within(row).queryByText('Release')).not.toBeInTheDocument()
  })

  it('shows published X post evidence in the centered detail modal', () => {
    const publishedDraft = {
      ...socialDraft,
      id: 'social_draft:21',
      status: 'published',
      evidence_label: 'X post 2049401935174975542',
      external_post_id: '2049401935174975542',
      external_url: 'https://x.com/SynapseNetworkA/status/2049401935174975542',
      published_at: '2026-04-29T08:14:32Z',
      process_stages: [
        { key: 'generated', label: 'Generated', status: 'completed' },
        { key: 'needs_review', label: 'Needs Review', status: 'completed' },
        { key: 'approved', label: 'Approved/Edited', status: 'completed' },
        { key: 'published', label: 'Published', status: 'completed' },
        { key: 'metrics', label: 'Metrics', status: 'missing' },
      ],
    }
    const publishedWorkbench = {
      ...workbench,
      root: {
        ...workbench.root,
        children: [
          {
            ...workbench.root.children[0],
            children: [publishedDraft],
          },
        ],
      },
    }

    render(
      <MemoryRouter>
        <MissionWorkbenchPanel workbench={publishedWorkbench} />
      </MemoryRouter>,
    )

    const row = screen.getByTestId('mission-workbench-row-social_draft:21')
    fireEvent.click(within(row).getByRole('button', { name: '详情' }))

    expect(screen.getByRole('dialog', { name: /Mission item detail/ })).toBeInTheDocument()
    expect(screen.getByText('X Post ID: 2049401935174975542')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open on X' })).toHaveAttribute(
      'href',
      'https://x.com/SynapseNetworkA/status/2049401935174975542',
    )
  })
})
