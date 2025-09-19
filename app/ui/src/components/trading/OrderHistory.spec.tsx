import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { OrderHistory } from './OrderHistory'
import type { Order } from '@/types'

describe('OrderHistory', () => {
  const mockOrders: Order[] = [
    {
      orderId: 'ORD001' as any,
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.1,
      status: 'FILLED',
      venue: 'SPOT',
      createdAt: '2024-01-15T10:30:00Z',
      updatedAt: '2024-01-15T10:30:05Z',
      executedQuantity: 0.1,
      avgPrice: 42000,
    },
    {
      orderId: 'ORD002' as any,
      symbol: 'ETHUSDT' as any,
      side: 'SELL',
      type: 'LIMIT',
      quantity: 1,
      price: 2500,
      status: 'CANCELED',
      venue: 'USD_M',
      createdAt: '2024-01-15T11:00:00Z',
      updatedAt: '2024-01-15T11:05:00Z',
      executedQuantity: 0,
    },
    {
      orderId: 'ORD003' as any,
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      type: 'LIMIT',
      quantity: 0.5,
      price: 41000,
      status: 'PARTIALLY_FILLED',
      venue: 'SPOT',
      createdAt: '2024-01-15T12:00:00Z',
      updatedAt: '2024-01-15T12:00:30Z',
      executedQuantity: 0.3,
      avgPrice: 41050,
    },
  ]

  it('renders order history table', () => {
    render(<OrderHistory orders={mockOrders} />)

    expect(screen.getByTestId('order-history')).toBeInTheDocument()
    expect(screen.getByText('Order History')).toBeInTheDocument()
  })

  it('displays all orders', () => {
    render(<OrderHistory orders={mockOrders} />)

    expect(screen.getByText('ORD001')).toBeInTheDocument()
    expect(screen.getByText('ORD002')).toBeInTheDocument()
    expect(screen.getByText('ORD003')).toBeInTheDocument()
  })

  it('displays order details', () => {
    // Use only the first order to avoid sorting issues
    const singleOrder = [mockOrders[0]!]
    render(<OrderHistory orders={singleOrder} />)

    expect(screen.getByText('BTCUSDT')).toBeInTheDocument()
    expect(screen.getByText('BUY')).toBeInTheDocument()
    expect(screen.getByText('MARKET')).toBeInTheDocument()
    expect(screen.getByText('0.1')).toBeInTheDocument()
    expect(screen.getByText('FILLED')).toBeInTheDocument()
    expect(screen.getByText('SPOT')).toBeInTheDocument()
  })

  it('shows empty state when no orders', () => {
    render(<OrderHistory orders={[]} />)

    expect(screen.getByText('No order history')).toBeInTheDocument()
  })

  it('formats dates correctly', () => {
    render(<OrderHistory orders={[mockOrders[0]!]} />)

    // Should show formatted date
    expect(screen.getByText(/Jan 15, 2024/)).toBeInTheDocument()
    // Time will vary based on timezone, just check format
    expect(screen.getByText(/\d{2}:\d{2}:\d{2}/)).toBeInTheDocument()
  })

  it('displays executed quantity and average price for filled orders', () => {
    render(<OrderHistory orders={[mockOrders[0]!]} />)

    expect(screen.getByText('0.1 / 0.1')).toBeInTheDocument() // executed / total
    expect(screen.getByText('42,000')).toBeInTheDocument() // avg price
  })

  it('displays price for limit orders', () => {
    render(<OrderHistory orders={[mockOrders[1]!]} />)

    expect(screen.getByText('2,500')).toBeInTheDocument()
  })

  it('shows N/A for market order price', () => {
    render(<OrderHistory orders={[mockOrders[0]!]} />)

    // Market orders should show N/A for limit price
    const naElements = screen.getAllByText('N/A')
    expect(naElements.length).toBeGreaterThan(0)
  })

  it('applies correct status styling', () => {
    render(<OrderHistory orders={mockOrders} />)

    const filledStatus = screen.getByText('FILLED')
    expect(filledStatus).toHaveClass('status-badge', 'filled')

    const canceledStatus = screen.getByText('CANCELED')
    expect(canceledStatus).toHaveClass('status-badge', 'canceled')

    const partialStatus = screen.getByText('PARTIALLY_FILLED')
    expect(partialStatus).toHaveClass('status-badge', 'partially-filled')
  })

  it('shows loading state', () => {
    render(<OrderHistory orders={[]} loading />)

    expect(screen.getByTestId('order-history-loading')).toBeInTheDocument()
    expect(screen.getByText('Loading order history...')).toBeInTheDocument()
  })

  it('shows error state', () => {
    const errorMessage = 'Failed to load order history'
    render(<OrderHistory orders={[]} error={errorMessage} />)

    expect(screen.getByText(errorMessage)).toBeInTheDocument()
    expect(screen.getByTestId('order-history-error')).toBeInTheDocument()
  })

  it('filters orders by status', async () => {
    const user = userEvent.setup()
    render(<OrderHistory orders={mockOrders} />)

    const filterSelect = screen.getByLabelText('Filter by status')
    await user.selectOptions(filterSelect, 'FILLED')

    // Only filled orders should be visible
    expect(screen.getByText('ORD001')).toBeInTheDocument()
    expect(screen.queryByText('ORD002')).not.toBeInTheDocument()
    expect(screen.queryByText('ORD003')).not.toBeInTheDocument()
  })

  it('sorts orders by date', () => {
    render(<OrderHistory orders={mockOrders} />)

    const orderIds = screen.getAllByTestId(/order-id-/)
    // Should be sorted by date descending (newest first)
    expect(orderIds[0]).toHaveTextContent('ORD003')
    expect(orderIds[1]).toHaveTextContent('ORD002')
    expect(orderIds[2]).toHaveTextContent('ORD001')
  })

  it('applies custom className', () => {
    render(<OrderHistory orders={[]} className="custom-history" />)

    const container = screen.getByTestId('order-history')
    expect(container).toHaveClass('order-history', 'custom-history')
  })

  it('shows partial fill percentage', () => {
    render(<OrderHistory orders={[mockOrders[2]!]} />)

    // 0.3 executed out of 0.5 = 60%
    expect(screen.getByText('0.3 / 0.5')).toBeInTheDocument()
    expect(screen.getByText('(60%)')).toBeInTheDocument()
  })

  it('handles pagination', async () => {
    const user = userEvent.setup()
    const manyOrders = Array.from({ length: 25 }, (_, i) => ({
      ...mockOrders[0],
      orderId: `ORD${i}` as any,
    }))

    render(<OrderHistory orders={manyOrders} pageSize={10} />)

    // Should show first 10 orders
    expect(screen.getByText('ORD0')).toBeInTheDocument()
    expect(screen.getByText('ORD9')).toBeInTheDocument()
    expect(screen.queryByText('ORD10')).not.toBeInTheDocument()

    // Navigate to next page
    const nextButton = screen.getByRole('button', { name: /next/i })
    await user.click(nextButton)

    expect(screen.queryByText('ORD0')).not.toBeInTheDocument()
    expect(screen.getByText('ORD10')).toBeInTheDocument()
  })
})
