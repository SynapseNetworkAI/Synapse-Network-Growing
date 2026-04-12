import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OptimizationSignals from '../src/pages/OptimizationSignals'

const mockApi = {
  getOptimizationSignals: vi.fn(),
  refreshOptimizationSignals: vi.fn(),
  autoIntakeOptimizationSignals: vi.fn(),
  dismissOptimizationSignal: vi.fn(),
  createRequirementFromSignal: vi.fn(),
}

vi.mock('../src/api', async () => {
  const actual = await vi.importActual('../src/api')
  return {
    ...actual,
    api: {
      ...actual.api,
      getOptimizationSignals: (...args: unknown[]) => mockApi.getOptimizationSignals(...args),
      refreshOptimizationSignals: (...args: unknown[]) => mockApi.refreshOptimizationSignals(...args),
      autoIntakeOptimizationSignals: (...args: unknown[]) => mockApi.autoIntakeOptimizationSignals(...args),
      dismissOptimizationSignal: (...args: unknown[]) => mockApi.dismissOptimizationSignal(...args),
      createRequirementFromSignal: (...args: unknown[]) => mockApi.createRequirementFromSignal(...args),
    },
  }
})

const SIGNALS = [
  {
    id: 1,
    dedupe_key: 'bug-report::synapse-network::validation-passed',
    signal_type: 'bug_report',
    source_kind: 'artifact',
    status: 'open',
    title: 'Defect signal: Synapse-Network validation_passed',
    summary: 'Repeated bug reports detected in Synapse-Network.',
    severity: 'high',
    confidence: 0.93,
    project_key: 'synapse-network',
    project_root_path: '/Users/cliff/workspace/agent/Synapse-Network',
    routing_target_path: '/Users/cliff/workspace/agent/Synapse-Network',
    evidence: [{ requirement_id: 1 }, { requirement_id: 2 }],
    occurrence_count: 2,
    latest_evidence_at: '2026-04-11T12:00:00Z',
    converted_requirement_id: null,
    incident_family: 'verification',
    incident_code: 'automated_validation_failure',
    recovery_status: 'bugfix_loop_active',
    recovery_narrative: 'Automated validation failed and the workflow should continue through bugfix plus re-validation.',
    score_breakdown: {
      total: 78.4,
      impact: 34,
      risk: 22,
      urgency: 15,
      implementation_cost: 8,
    },
    recommended_priority: 'high',
    auto_intake_eligible: true,
    intake_recommendation: 'auto_create',
    created_at: '2026-04-11T12:00:00Z',
    updated_at: '2026-04-11T12:00:00Z',
  },
]

function makeSignal(id: number) {
  return {
    ...SIGNALS[0],
    id,
    title: `Signal ${id}`,
    dedupe_key: `signal-${id}`,
    latest_evidence_at: `2026-04-11T12:${String(id).padStart(2, '0')}:00Z`,
    created_at: `2026-04-11T12:${String(id).padStart(2, '0')}:00Z`,
    updated_at: `2026-04-11T12:${String(id).padStart(2, '0')}:00Z`,
  }
}

describe('OptimizationSignals', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getOptimizationSignals.mockResolvedValue(SIGNALS)
    mockApi.refreshOptimizationSignals.mockResolvedValue(SIGNALS)
    mockApi.autoIntakeOptimizationSignals.mockResolvedValue({
      created: [{ signal_id: 1, requirement_id: 88, title: 'Defect signal', score: 78.4 }],
      skipped: [],
    })
    mockApi.dismissOptimizationSignal.mockResolvedValue({ ...SIGNALS[0], status: 'dismissed' })
    mockApi.createRequirementFromSignal.mockResolvedValue({
      requirement: { id: 88 },
    })
  })

  it('renders optimization signals', async () => {
    render(<MemoryRouter><OptimizationSignals /></MemoryRouter>)

    await waitFor(() => {
      expect(mockApi.getOptimizationSignals).toHaveBeenCalledWith('open')
      expect(screen.getByTestId('optimization-signal-card-1')).toBeInTheDocument()
    })

    expect(screen.getByText('occurrences: 2')).toBeInTheDocument()
    expect(screen.getByText(/Repeated bug reports detected/)).toBeInTheDocument()
    expect(screen.getByText('score 78.4')).toBeInTheDocument()
    expect(screen.getByText('推荐优先级: high')).toBeInTheDocument()
    expect(screen.getByText(/Incident: verification \/ automated_validation_failure/)).toBeInTheDocument()
    expect(screen.getByText(/Recovery Narrative/)).toBeInTheDocument()
  })

  it('refreshes, auto-intakes, and converts a signal into a requirement', async () => {
    render(<MemoryRouter><OptimizationSignals /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('optimization-signal-create-1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('optimization-signal-refresh'))
    await waitFor(() => {
      expect(mockApi.refreshOptimizationSignals).toHaveBeenCalledTimes(1)
    })

    fireEvent.click(screen.getByTestId('optimization-signal-auto-intake'))
    await waitFor(() => {
      expect(mockApi.autoIntakeOptimizationSignals).toHaveBeenCalledWith({ max_created: 1 })
    })

    fireEvent.click(screen.getByTestId('optimization-signal-create-1'))
    await waitFor(() => {
      expect(mockApi.createRequirementFromSignal).toHaveBeenCalledWith(1, {})
    })
  })

  it('shows an error state when the backend request times out', async () => {
    mockApi.getOptimizationSignals.mockRejectedValueOnce(new Error('Request timed out after 12s'))

    render(<MemoryRouter><OptimizationSignals /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('optimization-signals-error')).toHaveTextContent('Request timed out after 12s')
    })
  })

  it('paginates optimization signals and keeps the current page after refresh', async () => {
    const manySignals = Array.from({ length: 11 }, (_, index) => makeSignal(index + 1))
    mockApi.getOptimizationSignals.mockResolvedValue(manySignals)
    mockApi.refreshOptimizationSignals.mockResolvedValue(manySignals)

    render(<MemoryRouter><OptimizationSignals /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('optimization-signals-pagination')).toBeInTheDocument()
    })

    const pagination = screen.getByTestId('optimization-signals-pagination')
    fireEvent.click(within(pagination).getByRole('button', { name: '2' }))

    await waitFor(() => {
      expect(screen.getByText('11–11 / 11 条信号')).toBeInTheDocument()
      expect(screen.getByTestId('optimization-signal-card-11')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('optimization-signal-refresh'))

    await waitFor(() => {
      expect(mockApi.refreshOptimizationSignals).toHaveBeenCalledTimes(1)
      expect(screen.getByText('11–11 / 11 条信号')).toBeInTheDocument()
      expect(screen.getByTestId('optimization-signal-card-11')).toBeInTheDocument()
    })
  })
})
