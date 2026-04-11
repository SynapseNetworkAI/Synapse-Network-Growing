import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OptimizationSignals from '../src/pages/OptimizationSignals'

const mockApi = {
  getOptimizationSignals: vi.fn(),
  refreshOptimizationSignals: vi.fn(),
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
    created_at: '2026-04-11T12:00:00Z',
    updated_at: '2026-04-11T12:00:00Z',
  },
]

describe('OptimizationSignals', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getOptimizationSignals.mockResolvedValue(SIGNALS)
    mockApi.refreshOptimizationSignals.mockResolvedValue(SIGNALS)
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
  })

  it('refreshes and converts a signal into a requirement', async () => {
    render(<MemoryRouter><OptimizationSignals /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('optimization-signal-create-1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('optimization-signal-refresh'))
    await waitFor(() => {
      expect(mockApi.refreshOptimizationSignals).toHaveBeenCalledTimes(1)
    })

    fireEvent.click(screen.getByTestId('optimization-signal-create-1'))
    await waitFor(() => {
      expect(mockApi.createRequirementFromSignal).toHaveBeenCalledWith(1, {})
    })
  })
})
