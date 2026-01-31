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
    it('renders container and headers', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      expect(screen.getByTestId('order-history')).toBeInTheDocument()
      expect(screen.getByText('Time')).toBeInTheDocument()
      expect(screen.getByText('Symbol')).toBeInTheDocument()
      expect(screen.getByText('Side')).toBeInTheDocument()
      expect(screen.getByText('Type')).toBeInTheDocument()
      expect(screen.getByText('Qty')).toBeInTheDocument()
      expect(screen.getByText('Price')).toBeInTheDocument()
      expect(screen.getByText('Status')).toBeInTheDocument()
      expect(screen.getByText('Action')).toBeInTheDocument()
    })

    it('shows empty state when no orders', () => {
      render(<OrderHistory orders={[]} onCancel={mockOnCancel} />)
      expect(screen.getByText('No orders yet')).toBeInTheDocument()
    })

    it('shows loading state', () => {
      render(<OrderHistory orders={mockOrders} loading onCancel={mockOnCancel} />)
      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
      expect(screen.queryByTestId('order-row-order-1')).not.toBeInTheDocument()
    })
  })

  describe('filtering', () => {
    it('filters by symbol substring', async () => {
      const user = userEvent.setup()
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      await user.type(screen.getByTestId('symbol-filter'), 'ETH')
      expect(screen.queryByTestId('order-row-order-1')).not.toBeInTheDocument()
      expect(screen.getByTestId('order-row-order-2')).toBeInTheDocument()
    })

    it('filters by status', async () => {
      const user = userEvent.setup()
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      await user.selectOptions(screen.getByTestId('status-filter'), 'CANCELED')
      expect(screen.getByTestId('order-row-order-3')).toBeInTheDocument()
      expect(screen.queryByTestId('order-row-order-1')).not.toBeInTheDocument()
      expect(screen.queryByTestId('order-row-order-2')).not.toBeInTheDocument()
    })
  })

  describe('sorting', () => {
    it('sorts newest first by createdAt', () => {
      render(<OrderHistory orders={mockOrders} onCancel={mockOnCancel} />)

      const rows = screen.getAllByTestId(/order-row-/)
      expect(rows[0]).toHaveAttribute('data-testid', 'order-row-order-1')
      expect(rows[1]).toHaveAttribute('data-testid', 'order-row-order-2')
      expect(rows[2]).toHaveAttribute('data-testid', 'order-row-order-3')
    })
  })

  describe('actions', () => {
    it('renders cancel button for cancelable statuses', () => {
      const cancelableOrder: Order = {
        ...mockOrders[0],
        orderId: 'order-new' as OrderId,
        status: 'NEW',
      }

      render(<OrderHistory orders={[cancelableOrder]} onCancel={mockOnCancel} />)
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('invokes onCancel when cancel is clicked', async () => {
      const user = userEvent.setup()
      const cancelableOrder: Order = {
        ...mockOrders[0],
        orderId: 'order-new' as OrderId,
        status: 'NEW',
      }

      render(<OrderHistory orders={[cancelableOrder]} onCancel={mockOnCancel} />)
      await user.click(screen.getByRole('button', { name: 'Cancel' }))
      expect(mockOnCancel).toHaveBeenCalledWith(cancelableOrder)
    })
  })
})
