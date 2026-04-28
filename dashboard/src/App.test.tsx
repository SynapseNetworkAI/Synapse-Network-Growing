// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./pages/CommandCenterPage', () => ({ default: () => <div>Command Center Page</div> }))
vi.mock('./pages/RequirementPool', () => ({ default: () => <div>Requirements Page</div> }))
vi.mock('./pages/RequirementDetail', () => ({ default: () => <div>Requirement Detail Page</div> }))
vi.mock('./pages/WorkflowRunsPage', () => ({ default: () => <div>Workflow Runs Page</div> }))
vi.mock('./pages/WorkflowRunDetailPage', () => ({ default: () => <div>Workflow Detail Page</div> }))
vi.mock('./pages/PlanningPage', () => ({ default: () => <div>Planning Page</div> }))
vi.mock('./pages/HumanGatesPage', () => ({ default: () => <div>Human Gates Page</div> }))
vi.mock('./pages/WorkflowDefinitionsPage', () => ({ default: () => <div>Workflow Factory Page</div> }))
vi.mock('./pages/AtomRegistryPage', () => ({ default: () => <div>Atom Registry Page</div> }))
vi.mock('./pages/IntakePage', () => ({ default: () => <div>Signals Page</div> }))
vi.mock('./pages/KnowledgePage', () => ({ default: () => <div>Knowledge Page</div> }))
vi.mock('./pages/NotificationsPage', () => ({ default: () => <div>Notifications Page</div> }))
vi.mock('./pages/SchedulesPage', () => ({ default: () => <div>Schedules Page</div> }))
vi.mock('./pages/ReleasesPage', () => ({ default: () => <div>Releases Page</div> }))
vi.mock('./pages/ReleaseDetailPage', () => ({ default: () => <div>Release Detail Page</div> }))
vi.mock('./pages/PublishingPage', () => ({ default: () => <div>Publishing Page</div> }))
vi.mock('./pages/PublishingTrendResultsPage', () => ({ default: () => <div>Trend Results Page</div> }))
vi.mock('./pages/ProjectsPage', () => ({ default: () => <div>Projects Page</div> }))
vi.mock('./pages/ProjectDetailPage', () => ({ default: () => <div>Project Detail Page</div> }))
vi.mock('./pages/ErrorsPage', () => ({ default: () => <div>Errors Page</div> }))
vi.mock('./pages/ErrorDetailPage', () => ({ default: () => <div>Error Detail Page</div> }))

function renderApp(path = '/command-center') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe('App top navigation shell', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ needs_human: 3, pending_gate_count: 3 }),
    })))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders only the four primary workflow entries and no sidebar navigation', async () => {
    const { container } = renderApp('/command-center')

    const primaryNav = screen.getByRole('navigation', { name: 'Primary navigation' })
    expect(within(primaryNav).getByRole('link', { name: 'Command Center' })).toHaveAttribute('href', '/command-center')
    expect(within(primaryNav).getByRole('link', { name: 'Planning' })).toHaveAttribute('href', '/planning')
    expect(within(primaryNav).getByRole('link', { name: 'Publishing' })).toHaveAttribute('href', '/publishing')
    expect(within(primaryNav).getByRole('link', { name: 'Releases' })).toHaveAttribute('href', '/releases')
    expect(within(primaryNav).queryByRole('link', { name: 'Requirements' })).not.toBeInTheDocument()
    expect(within(primaryNav).queryByRole('link', { name: 'Workflows' })).not.toBeInTheDocument()
    expect(container.querySelector('aside')).toBeNull()
    await screen.findByText('Needs Human 3')
  })

  it('keeps low-frequency routes reachable through command search and direct links', async () => {
    renderApp('/workflows')

    expect(screen.getByText('Workflow Runs Page')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Cmd\+K \/ Search/i }))

    const dialog = screen.getByRole('dialog', { name: 'Command search' })
    expect(within(dialog).getByRole('link', { name: /Requirements/ })).toHaveAttribute('href', '/requirements')
    expect(within(dialog).getByRole('link', { name: /Workflows/ })).toHaveAttribute('href', '/workflows')
    expect(within(dialog).getByRole('link', { name: /Schedules/ })).toHaveAttribute('href', '/schedules')
    await waitFor(() => expect(screen.getByText('Needs Human 3')).toBeInTheDocument())
  })
})
