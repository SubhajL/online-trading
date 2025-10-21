import { describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import PortfolioPage from './page'

vi.mock('@/hooks/usePositions', () => ({
  usePositions: () => ({
    positions: [],
    loading: false,
    error: null,
    totalValue: 0,
    totalPnl: 0,
  }),
}))

vi.mock('@/hooks/useBalances', () => ({
  useBalances: () => ({
    balances: [],
    loading: false,
    error: null,
  }),
}))

describe('PortfolioPage', () => {
  test('renders portfolio content', () => {
    render(<PortfolioPage />)
    expect(screen.getByText('Portfolio Overview')).toBeInTheDocument()
  })

  test('includes main landmark with id and tabIndex', () => {
    render(<PortfolioPage />)
    const mainElement = screen.getByRole('main')
    expect(mainElement.id).toBe('main-content')
    expect(mainElement.tabIndex).toBe(-1)
  })

  test('renders portfolio summary cards', () => {
    render(<PortfolioPage />)
    const summaryHeadings = screen.getAllByText(/Total Portfolio Value|Total P&L|Open Positions/)
    expect(summaryHeadings.length).toBeGreaterThan(0)
  })
})
