import { describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import HistoryPage from './page'

vi.mock('@/hooks/useOrderHistory', () => ({
  useOrderHistory: () => ({
    filteredOrders: [],
    loading: false,
    error: null,
    stats: {
      totalTrades: 0,
      buyOrders: 0,
      sellOrders: 0,
      totalVolume: 0,
    },
    dateRange: 'all',
    setDateRange: vi.fn(),
  }),
}))

describe('HistoryPage', () => {
  test('renders with CSS module classes', () => {
    render(<HistoryPage />)
    expect(screen.getByText('Trade History')).toBeInTheDocument()
  })

  test('renders date range buttons', () => {
    render(<HistoryPage />)
    expect(screen.getByText('24H')).toBeInTheDocument()
    expect(screen.getByText('7D')).toBeInTheDocument()
    expect(screen.getByText('30D')).toBeInTheDocument()
    expect(screen.getByText('All')).toBeInTheDocument()
  })
})
