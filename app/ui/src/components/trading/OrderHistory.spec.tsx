import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { OrderHistory } from './OrderHistory'
import type { Order, OrderId, Symbol } from '@/types'

describe('OrderHistory', () => {
  const mockOrders: Order[] = [
    {
      orderId: 'order-1' as OrderId,
      symbol: 'BTCUSDT' as Symbol,
      side: 'BUY',
      type: 'LIMIT',
      quantity: 0.5,
      price: 45000,
      status: 'FILLED',
      venue: 'SPOT',
      createdAt: '2024-01-01T10:00:00Z',
      updatedAt: '2024-01-01T10:05:00Z',
      executedQuantity: 0.5,
      avgPrice: 44950,
    },
    {
      orderId: 'order-2' as OrderId,
      symbol: 'ETHUSDT' as Symbol,
      side: 'SELL',
      type: 'MARKET',
      quantity: 10,
      status: 'FILLED',
      venue: 'SPOT',
      createdAt: '2024-01-01T09:00:00Z',
      updatedAt: '2024-01-01T09:00:01Z',
      executedQuantity: 10,
      avgPrice: 2950,
    },
    {
      orderId: 'order-3' as OrderId,
      symbol: 'BTCUSDT' as Symbol,
      side: 'BUY',
      type: 'STOP_LIMIT',
      quantity: 0.2,
      price: 46000,
      stopPrice: 45500,
      status: 'CANCELED',
      venue: 'USD_M',
      createdAt: '2024-01-01T08:00:00Z',
      updatedAt: '2024-01-01T08:30:00Z',
      executedQuantity: 0,
    },
  ]

  const mockOnCancel = vi.fn()

  describe('rendering', () => {
    it('should render order history', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      expect(screen.getByTestId('order-history')).toBeInTheDocument()
    })

    it('should show table headers', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      expect(screen.getByText('Time')).toBeInTheDocument()
      expect(screen.getByText('Symbol')).toBeInTheDocument()
      expect(screen.getByText('Side')).toBeInTheDocument()
      expect(screen.getByText('Type')).toBeInTheDocument()
      expect(screen.getByText('Price')).toBeInTheDocument()
      expect(screen.getByText('Quantity')).toBeInTheDocument()
      expect(screen.getByText('Status')).toBeInTheDocument()
    })

    it('should render all orders', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      expect(screen.getAllByText('BTCUSDT')).toHaveLength(2)
      expect(screen.getByText('ETHUSDT')).toBeInTheDocument()
    })
  })

  describe('order details', () => {
    it('should display order side with correct styling', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      const buyElements = screen.getAllByText('BUY')
      buyElements.forEach(el => {
        expect(el).toHaveClass('text-green-500')
      })

      const sellElement = screen.getByText('SELL')
      expect(sellElement).toHaveClass('text-red-500')
    })

    it('should display order types', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      expect(screen.getByText('LIMIT')).toBeInTheDocument()
      expect(screen.getByText('MARKET')).toBeInTheDocument()
      expect(screen.getByText('STOP_LIMIT')).toBeInTheDocument()
    })

    it('should display prices correctly', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      // Limit order with price
      expect(screen.getByText('$45,000.00')).toBeInTheDocument()
      // Market order shows executed price
      expect(screen.getByText('$2,950.00')).toBeInTheDocument()
      // Stop limit with stop price
      expect(screen.getByText('$46,000.00 (S: $45,500.00)')).toBeInTheDocument()
    })

    it('should display quantities', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      expect(screen.getByText('0.5')).toBeInTheDocument()
      expect(screen.getByText('10')).toBeInTheDocument()
      expect(screen.getByText('0 / 0.2')).toBeInTheDocument() // Canceled order shows executed/total
    })

    it('should show executed quantity for partial fills', () => {
      const partialOrder: Order = {
        ...mockOrders[0],
        orderId: 'partial-1' as OrderId,
        status: 'PARTIALLY_FILLED',
        executedQuantity: 0.3,
      }

      render(<OrderHistory orders={[partialOrder]} onCancel={mockOnCancel} />)

      expect(screen.getByText('0.3 / 0.5')).toBeInTheDocument()
    })
  })

  describe('status display', () => {
    it('should show status badges with correct styling', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      const filledBadges = screen.getAllByText('FILLED')
      filledBadges.forEach(badge => {
        expect(badge).toHaveClass('bg-green-500/10', 'text-green-500')
      })

      const canceledBadge = screen.getByText('CANCELED')
      expect(canceledBadge).toHaveClass('bg-gray-500/10', 'text-gray-500')
    })

    it('should show all status types correctly', () => {
      const statusOrders: Order[] = [
        { ...mockOrders[0], orderId: 'new' as OrderId, status: 'NEW' },
        { ...mockOrders[0], orderId: 'partial' as OrderId, status: 'PARTIALLY_FILLED' },
        { ...mockOrders[0], orderId: 'rejected' as OrderId, status: 'REJECTED' },
        { ...mockOrders[0], orderId: 'expired' as OrderId, status: 'EXPIRED' },
      ]

      render(<OrderHistory orders={statusOrders} onCancel={mockOnCancel} />)

      expect(screen.getByText('NEW')).toHaveClass('bg-blue-500/10', 'text-blue-500')
      expect(screen.getByText('PARTIALLY_FILLED')).toHaveClass(
        'bg-yellow-500/10',
        'text-yellow-500',
      )
      expect(screen.getByText('REJECTED')).toHaveClass('bg-red-500/10', 'text-red-500')
      expect(screen.getByText('EXPIRED')).toHaveClass('bg-gray-500/10', 'text-gray-500')
    })
  })

  describe('actions', () => {
    it('should show cancel button for cancelable orders', () => {
      const cancelableOrder: Order = {
        ...mockOrders[0],
        status: 'NEW',
      }

      render(<OrderHistory orders={[cancelableOrder]} onCancel={mockOnCancel} />)

      expect(screen.getByTestId('cancel-order-button')).toBeInTheDocument()
    })

    it('should not show cancel button for completed orders', () => {
      render(<OrderHistory orders={[mockOrders[0]]} onCancel={mockOnCancel} />)

      expect(screen.queryByTestId('cancel-order-button')).not.toBeInTheDocument()
    })

    it('should call onCancel when cancel clicked', async () => {
      const user = userEvent.setup()
      const cancelableOrder: Order = {
        ...mockOrders[0],
        status: 'NEW',
      }

      render(<OrderHistory orders={[cancelableOrder]} onCancel={mockOnCancel} />)

      const cancelButton = screen.getByTestId('cancel-order-button')
      await user.click(cancelButton)

      expect(mockOnCancel).toHaveBeenCalledWith(cancelableOrder)
    })
  })

  describe('time display', () => {
    it('should format timestamps correctly', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      // Check that rows exist with proper test IDs
      expect(screen.getByTestId('order-row-order-1')).toBeInTheDocument()
      expect(screen.getByTestId('order-row-order-2')).toBeInTheDocument()
      expect(screen.getByTestId('order-row-order-3')).toBeInTheDocument()
    })
  })

  describe('empty state', () => {
    it('should show empty message when no orders', () => {
      render(<OrderHistory orders={[]} onCancel={mockOnCancel} />)

      expect(screen.getByText('No orders yet')).toBeInTheDocument()
    })
  })

  describe('loading state', () => {
    it('should show loading spinner', () => {
      render(<OrderHistory orders={[]} loading onCancel={mockOnCancel} />)

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    })

    it('should hide orders when loading', () => {
      render(<OrderHistory orders={mockOrders} loading onCancel={mockOnCancel} />)

      expect(screen.queryByText('BTCUSDT')).not.toBeInTheDocument()
    })
  })

  describe('venue display', () => {
    it('should show venue badges', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      const spotBadges = screen.getAllByText('SPOT')
      expect(spotBadges).toHaveLength(2)
      expect(spotBadges[0]).toHaveClass('bg-blue-500/10', 'text-blue-500')

      const futuresBadge = screen.getByText('USD_M')
      expect(futuresBadge).toHaveClass('bg-purple-500/10', 'text-purple-500')
    })
  })

  describe('filtering', () => {
    it('should filter by symbol', async () => {
      const user = userEvent.setup()
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      const filterInput = screen.getByPlaceholderText('Filter by symbol...')
      await user.type(filterInput, 'ETH')

      expect(screen.queryByText('BTCUSDT')).not.toBeInTheDocument()
      expect(screen.getByText('ETHUSDT')).toBeInTheDocument()
    })

    it('should filter by status', async () => {
      const user = userEvent.setup()
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      const statusFilter = screen.getByTestId('status-filter')
      await user.selectOptions(statusFilter, 'FILLED')

      expect(screen.queryByText('CANCELED')).not.toBeInTheDocument()
      expect(screen.getAllByText('FILLED')).toHaveLength(2)
    })
  })

  describe('sorting', () => {
    it('should sort by time by default (newest first)', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      const rows = screen.getAllByTestId(/order-row-/)
      // First row should be order-1 (10:00:00)
      expect(rows[0]).toHaveAttribute('data-testid', 'order-row-order-1')
      // Second row should be order-2 (09:00:00)
      expect(rows[1]).toHaveAttribute('data-testid', 'order-row-order-2')
      // Third row should be order-3 (08:00:00)
      expect(rows[2]).toHaveAttribute('data-testid', 'order-row-order-3')
    })
  })

  it('shows error state', () => {
    const errorMessage = 'Failed to load order history'
    render(<OrderHistory orders={[]} error={errorMessage} onCancel={mockOnCancel} />)

    expect(screen.getByText(errorMessage)).toBeInTheDocument()
    expect(screen.getByTestId('order-history-error')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<OrderHistory orders={[]} className="custom-history" onCancel={mockOnCancel} />)

    const container = screen.getByTestId('order-history')
    expect(container).toHaveClass('order-history', 'custom-history')
  })

  it('shows partial fill percentage', () => {
    const partialOrder: Order = {
      ...mockOrders[0],
      orderId: 'partial' as OrderId,
      status: 'PARTIALLY_FILLED',
      executedQuantity: 0.3,
      quantity: 0.5,
    }
    render(<OrderHistory orders={[partialOrder]} onCancel={mockOnCancel} />)

    // 0.3 executed out of 0.5 = 60%
    expect(screen.getByText('0.3 / 0.5')).toBeInTheDocument()
    expect(screen.getByText('(60%)')).toBeInTheDocument()
  })

  it('handles pagination', async () => {
    const user = userEvent.setup()
    const manyOrders = Array.from({ length: 25 }, (_, i) => ({
      ...mockOrders[0],
      orderId: `order-${i}` as OrderId,
    }))

    render(<OrderHistory orders={manyOrders} pageSize={10} onCancel={mockOnCancel} />)

    // Should show first 10 orders
    expect(screen.getByTestId('order-row-order-0')).toBeInTheDocument()
    expect(screen.getByTestId('order-row-order-9')).toBeInTheDocument()
    expect(screen.queryByTestId('order-row-order-10')).not.toBeInTheDocument()

    // Navigate to next page
    const nextButton = screen.getByRole('button', { name: /next/i })
    await user.click(nextButton)

    expect(screen.queryByTestId('order-row-order-0')).not.toBeInTheDocument()
    expect(screen.getByTestId('order-row-order-10')).toBeInTheDocument()
  })
})
