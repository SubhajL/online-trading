import { describe, expect, test, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import HistoryPage from './page'

const mockUseOrderHistory = vi.fn()

vi.mock('@/hooks/useOrderHistory', () => ({
  useOrderHistory: () => mockUseOrderHistory(),
}))

describe('HistoryPage', () => {
  test('renders revamp mobile loading state', () => {
    const originalFlag = process.env.NEXT_PUBLIC_UI_REVAMP
    process.env.NEXT_PUBLIC_UI_REVAMP = '1'
    mockUseOrderHistory.mockReturnValue({
      filteredOrders: [],
      loading: true,
      error: null,
      stats: {
        totalTrades: 0,
        buyOrders: 0,
        sellOrders: 0,
        totalVolume: 0,
      },
      dateRange: 'all',
      setDateRange: vi.fn(),
    })

    render(<HistoryPage />)
    const mobileView = screen.getByTestId('history-mobile-view')
    expect(within(mobileView).getByText('Loading history…')).toBeInTheDocument()

    process.env.NEXT_PUBLIC_UI_REVAMP = originalFlag
  })

  test('renders with CSS module classes', () => {
    mockUseOrderHistory.mockReturnValue({
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
    })
    render(<HistoryPage />)
    expect(screen.getByText('Trade History')).toBeInTheDocument()
  })

  test('renders revamp mobile empty state', () => {
    const originalFlag = process.env.NEXT_PUBLIC_UI_REVAMP
    process.env.NEXT_PUBLIC_UI_REVAMP = '1'
    mockUseOrderHistory.mockReturnValue({
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
    })

    render(<HistoryPage />)
    const mobileView = screen.getByTestId('history-mobile-view')
    expect(within(mobileView).getByText('No trades match these filters')).toBeInTheDocument()

    process.env.NEXT_PUBLIC_UI_REVAMP = originalFlag
  })

  test('renders date range buttons', () => {
    mockUseOrderHistory.mockReturnValue({
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
    })
    render(<HistoryPage />)
    expect(screen.getByText('24H')).toBeInTheDocument()
    expect(screen.getByText('7D')).toBeInTheDocument()
    expect(screen.getByText('30D')).toBeInTheDocument()
    expect(screen.getByText('All')).toBeInTheDocument()
  })
})
