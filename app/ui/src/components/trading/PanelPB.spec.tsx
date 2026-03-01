import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PanelPB } from './PanelPB'
import { useBalances } from '@/hooks/useBalances'
import { useOrders } from '@/hooks/useOrders'
import { ToastProvider } from '@/context/ToastContext'
import type { Balance } from '@/types'

vi.mock('@/hooks/useBalances')
vi.mock('@/hooks/useOrders')

describe('PanelPB', () => {
  const mockBalances: Balance[] = [
    { asset: 'USDT', free: 10000, locked: 0, total: 10000, venue: 'SPOT', usdValue: 10000 },
    { asset: 'BTC', free: 0.5, locked: 0.1, total: 0.6, venue: 'SPOT', usdValue: 27000 },
  ]

  const mockUseBalances = {
    balances: mockBalances,
    loading: false,
    error: null,
    refresh: vi.fn(),
    applyOptimistic: vi.fn(() => 'optimistic-token'),
    rollback: vi.fn(),
  }

  const mockUseOrders = {
    placeOrder: vi.fn(),
    cancelOrder: vi.fn(),
    loading: false,
    error: null,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useBalances).mockReturnValue(mockUseBalances)
    vi.mocked(useOrders).mockReturnValue(mockUseOrders)
  })

  describe('rendering', () => {
    it('should render trading panel', () => {
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      expect(screen.getByTestId('trading-panel')).toBeInTheDocument()
    })

    it('should display symbol', () => {
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      expect(screen.getByText(/BTCUSDT/)).toBeInTheDocument()
    })

    it('should show order form fields', () => {
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      expect(screen.getByLabelText('Side')).toBeInTheDocument()
      expect(screen.getByLabelText('Type')).toBeInTheDocument()
      expect(screen.getByLabelText('Quantity')).toBeInTheDocument()
    })

    it('should show buy and sell buttons', () => {
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      expect(screen.getByTestId('buy-button')).toBeInTheDocument()
      expect(screen.getByTestId('sell-button')).toBeInTheDocument()
    })

    it('should show balance information', () => {
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      expect(screen.getByText(/Available:/)).toBeInTheDocument()
      expect(screen.getByText(/10,000/)).toBeInTheDocument() // USDT balance
    })
  })

  describe('order types', () => {
    it('should show price field for limit orders', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      const typeSelect = screen.getByLabelText('Type')
      await user.selectOptions(typeSelect, 'LIMIT')

      expect(screen.getByLabelText('Price')).toBeInTheDocument()
    })

    it('should hide price field for market orders', () => {
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      expect(screen.queryByLabelText('Price')).not.toBeInTheDocument()
    })

    it('should show stop price for stop orders', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      const typeSelect = screen.getByLabelText('Type')
      await user.selectOptions(typeSelect, 'STOP_LIMIT')

      expect(screen.getByLabelText('Stop Price')).toBeInTheDocument()
      expect(screen.getByLabelText('Price')).toBeInTheDocument()
    })
  })

  describe('form submission', () => {
    it('should place buy market order', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      const quantityInput = screen.getByLabelText('Quantity')
      await user.clear(quantityInput)
      await user.type(quantityInput, '0.001')

      const buyButton = screen.getByTestId('buy-button')
      await user.click(buyButton)

      expect(mockUseOrders.placeOrder).toHaveBeenCalledWith({
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.001,
      })
    })

    it('should place sell limit order', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      await user.selectOptions(screen.getByLabelText('Type'), 'LIMIT')
      await user.clear(screen.getByLabelText('Quantity'))
      await user.type(screen.getByLabelText('Quantity'), '0.001')
      await user.clear(screen.getByLabelText('Price'))
      await user.type(screen.getByLabelText('Price'), '45000')

      const sellButton = screen.getByTestId('sell-button')
      await user.click(sellButton)

      expect(mockUseOrders.placeOrder).toHaveBeenCalledWith({
        symbol: 'BTCUSDT',
        side: 'SELL',
        type: 'LIMIT',
        quantity: 0.001,
        price: 45000,
      })
    })

    it('should place stop limit order with all fields', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      await user.selectOptions(screen.getByLabelText('Type'), 'STOP_LIMIT')
      await user.clear(screen.getByLabelText('Quantity'))
      await user.type(screen.getByLabelText('Quantity'), '0.002')
      await user.clear(screen.getByLabelText('Price'))
      await user.type(screen.getByLabelText('Price'), '44000')
      await user.clear(screen.getByLabelText('Stop Price'))
      await user.type(screen.getByLabelText('Stop Price'), '44500')

      const buyButton = screen.getByTestId('buy-button')
      await user.click(buyButton)

      expect(mockUseOrders.placeOrder).toHaveBeenCalledWith({
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'STOP_LIMIT',
        quantity: 0.002,
        price: 44000,
        stopPrice: 44500,
      })
    })
  })

  describe('validation', () => {
    it('should show error for empty quantity', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      const buyButton = screen.getByTestId('buy-button')
      await user.click(buyButton)

      expect(screen.getByText(/Quantity is required/)).toBeInTheDocument()
    })

    it('should show error for negative quantity', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      await user.type(screen.getByLabelText('Quantity'), '-0.001')
      await user.click(screen.getByTestId('buy-button'))

      expect(screen.getByText(/Quantity must be positive/)).toBeInTheDocument()
    })

    it('should show error for missing price on limit order', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      await user.selectOptions(screen.getByLabelText('Type'), 'LIMIT')
      await user.type(screen.getByLabelText('Quantity'), '0.001')
      await user.click(screen.getByTestId('buy-button'))

      expect(screen.getByText(/Price is required for limit orders/)).toBeInTheDocument()
    })

    it('should show error for insufficient balance', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" price={50000} />
        </ToastProvider>,
      )

      await user.clear(screen.getByLabelText('Quantity'))
      await user.type(screen.getByLabelText('Quantity'), '1') // 1 BTC at $50,000 = $50,000 > $10,000 balance
      await user.click(screen.getByTestId('buy-button'))

      expect(screen.getByText(/Insufficient balance/)).toBeInTheDocument()
    })
  })

  describe('loading state', () => {
    it('should disable form during order placement', async () => {
      vi.mocked(useOrders).mockReturnValue({
        ...mockUseOrders,
        loading: true,
      })

      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      expect(screen.getByLabelText('Quantity')).toBeDisabled()
      expect(screen.getByTestId('buy-button')).toBeDisabled()
      expect(screen.getByTestId('sell-button')).toBeDisabled()
    })

    it('should show loading spinner when placing order', () => {
      vi.mocked(useOrders).mockReturnValue({
        ...mockUseOrders,
        loading: true,
      })

      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    })
  })

  describe('error handling', () => {
    it('should display order error', () => {
      vi.mocked(useOrders).mockReturnValue({
        ...mockUseOrders,
        error: 'Order rejected: Insufficient balance',
      })

      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      expect(screen.getByText(/Order rejected: Insufficient balance/)).toBeInTheDocument()
    })

    it('should display balance loading error', () => {
      vi.mocked(useBalances).mockReturnValue({
        ...mockUseBalances,
        error: 'Failed to fetch balances',
      })

      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      expect(screen.getByText(/Failed to fetch balances/)).toBeInTheDocument()
    })
  })

  describe('balance calculations', () => {
    it('should calculate and display max buy amount', () => {
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" price={50000} />
        </ToastProvider>,
      )

      const maxButton = screen.getByText('Max')
      expect(maxButton).toBeInTheDocument()
    })

    it('should fill quantity with max amount on max button click', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" price={50000} />
        </ToastProvider>,
      )

      const maxButton = screen.getByText('Max')
      await user.click(maxButton)

      const quantityInput = screen.getByLabelText('Quantity') as HTMLInputElement
      expect(parseFloat(quantityInput.value)).toBeCloseTo(0.2, 4) // 10000 USDT / 50000 = 0.2 BTC
    })
  })

  describe('quick amount buttons', () => {
    it('should show percentage buttons', () => {
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      expect(screen.getByText('25%')).toBeInTheDocument()
      expect(screen.getByText('50%')).toBeInTheDocument()
      expect(screen.getByText('75%')).toBeInTheDocument()
      expect(screen.getByText('100%')).toBeInTheDocument()
    })

    it('should set quantity based on percentage', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" price={50000} />
        </ToastProvider>,
      )

      await user.click(screen.getByText('50%'))

      const quantityInput = screen.getByLabelText('Quantity') as HTMLInputElement
      expect(parseFloat(quantityInput.value)).toBeCloseTo(0.1, 4) // 50% of 0.2 BTC max
    })
  })

  describe('form reset', () => {
    it('should reset form after successful order', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      await user.type(screen.getByLabelText('Quantity'), '0.001')
      await user.click(screen.getByTestId('buy-button'))

      await waitFor(() => {
        const quantityInput = screen.getByLabelText('Quantity') as HTMLInputElement
        expect(quantityInput.value).toBe('')
      })
    })

    it('should clear errors on form change', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      // Trigger error
      await user.click(screen.getByTestId('buy-button'))
      expect(screen.getByText(/Quantity is required/)).toBeInTheDocument()

      // Type quantity
      await user.type(screen.getByLabelText('Quantity'), '0.001')

      // Error should be cleared
      expect(screen.queryByText(/Quantity is required/)).not.toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('should have proper form labels', () => {
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      expect(screen.getByLabelText('Side')).toHaveAttribute('id', 'order-side')
      expect(screen.getByLabelText('Type')).toHaveAttribute('id', 'order-type')
      expect(screen.getByLabelText('Quantity')).toHaveAttribute('id', 'order-quantity')
    })

    it('should announce errors to screen readers', async () => {
      const user = userEvent.setup()
      render(
        <ToastProvider>
          <PanelPB symbol="BTCUSDT" />
        </ToastProvider>,
      )

      await user.click(screen.getByTestId('buy-button'))

      const error = screen.getByText(/Quantity is required/)
      expect(error).toHaveAttribute('role', 'alert')
    })
  })
})
