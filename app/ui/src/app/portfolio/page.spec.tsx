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
  test('renders with CSS module classes', () => {
    render(<PortfolioPage />)
    expect(screen.getByText('Portfolio Overview')).toBeInTheDocument()
  })

  test('applies appLayout CSS module class to root div', () => {
    const { container } = render(<PortfolioPage />)
    const rootDiv = container.firstChild as HTMLElement
    expect(rootDiv.className).toContain('appLayout')
  })

  test('renders portfolio summary cards', () => {
    render(<PortfolioPage />)
    const summaryHeadings = screen.getAllByText(/Total Portfolio Value|Total P&L|Open Positions/)
    expect(summaryHeadings.length).toBeGreaterThan(0)
  })
})
