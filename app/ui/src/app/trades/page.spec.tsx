import { describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import TradesPage from './page'

vi.mock('@/hooks/useOrders', () => ({
  useOrders: () => ({
    orders: [],
    loading: false,
    error: null,
    cancelOrder: vi.fn(),
  }),
}))

describe('TradesPage', () => {
  test('renders with CSS module classes', () => {
    render(<TradesPage />)
    expect(screen.getByText('Active Trades')).toBeInTheDocument()
  })

  test('applies appLayout CSS module class to root div', () => {
    const { container } = render(<TradesPage />)
    const rootDiv = container.firstChild as HTMLElement
    expect(rootDiv.className).toContain('appLayout')
  })

  test('renders filter tabs with CSS module classes', () => {
    render(<TradesPage />)
    expect(screen.getByText(/All \(/)).toBeInTheDocument()
    expect(screen.getByText(/Open \(/)).toBeInTheDocument()
    expect(screen.getByText(/Filled \(/)).toBeInTheDocument()
    expect(screen.getByText(/Canceled \(/)).toBeInTheDocument()
  })

  test('renders stats cards', () => {
    render(<TradesPage />)
    expect(screen.getByText('Total Trades')).toBeInTheDocument()
    expect(screen.getByText('Open Orders')).toBeInTheDocument()
    expect(screen.getByText('Filled Orders')).toBeInTheDocument()
    expect(screen.getByText('Canceled Orders')).toBeInTheDocument()
  })
})
