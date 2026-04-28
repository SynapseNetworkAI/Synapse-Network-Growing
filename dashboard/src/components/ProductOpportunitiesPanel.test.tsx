// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ProductOpportunitiesPanel } from './ProductOpportunitiesPanel'

const opportunity = {
  id: 7,
  title: 'Track docs and staging conversion from X growth',
  problem: 'X growth needs downstream conversion evidence.',
  suggested_goal_key: 'growth_conversion_tracking',
  recommended_lane: 'both',
  risk_level: 'normal',
  success_metric: 'docs clicks and staging visits are visible',
  next_action: 'Create a goal',
  status: 'proposed',
}

describe('ProductOpportunitiesPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders product planner proposals and creates a goal through human review', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ items: [opportunity], total: 1 }),
    } as Response)
    const onChanged = vi.fn()
    const user = userEvent.setup()

    render(<ProductOpportunitiesPanel onChanged={onChanged} />)

    expect(await screen.findByText('Track docs and staging conversion from X growth')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Create Goal' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/planning/product-opportunities/7/create-goal', expect.objectContaining({ method: 'POST' }))
      expect(onChanged).toHaveBeenCalled()
    })
  })
})
