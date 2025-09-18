import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { OrderForm } from './OrderForm'
import type { OrderFormValues } from './OrderForm'

describe('OrderForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders order form with all fields', () => {
    render(<OrderForm onSubmit={mockOnSubmit} />)

    expect(screen.getByLabelText('Symbol')).toBeInTheDocument()
    expect(screen.getByLabelText('Side')).toBeInTheDocument()
    expect(screen.getByLabelText('Order Type')).toBeInTheDocument()
    expect(screen.getByLabelText('Quantity')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /place order/i })).toBeInTheDocument()
    // Price field is only shown for LIMIT orders
    expect(screen.queryByLabelText('Price')).not.toBeInTheDocument()
  })

  it('shows buy and sell options', () => {
    render(<OrderForm onSubmit={mockOnSubmit} />)

    expect(screen.getByRole('radio', { name: /buy/i })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /sell/i })).toBeInTheDocument()
  })

  it('shows market and limit order types', () => {
    render(<OrderForm onSubmit={mockOnSubmit} />)

    const orderTypeSelect = screen.getByLabelText('Order Type')
    expect(orderTypeSelect).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /market/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /limit/i })).toBeInTheDocument()
  })

  it('hides price field for market orders', async () => {
    const user = userEvent.setup()
    render(<OrderForm onSubmit={mockOnSubmit} />)

    const orderTypeSelect = screen.getByLabelText('Order Type')
    await user.selectOptions(orderTypeSelect, 'MARKET')

    expect(screen.queryByLabelText('Price')).not.toBeInTheDocument()
  })

  it('shows price field for limit orders', async () => {
    const user = userEvent.setup()
    render(<OrderForm onSubmit={mockOnSubmit} />)

    const orderTypeSelect = screen.getByLabelText('Order Type')
    await user.selectOptions(orderTypeSelect, 'LIMIT')

    expect(screen.getByLabelText('Price')).toBeInTheDocument()
  })

  it('validates required fields', async () => {
    const user = userEvent.setup()
    render(<OrderForm onSubmit={mockOnSubmit} />)

    const submitButton = screen.getByRole('button', { name: /place order/i })
    await user.click(submitButton)

    expect(await screen.findByText('Symbol is required')).toBeInTheDocument()
    expect(await screen.findByText('Quantity is required')).toBeInTheDocument()
    expect(mockOnSubmit).not.toHaveBeenCalled()
  })

  it('validates quantity is positive', async () => {
    const user = userEvent.setup()
    render(<OrderForm onSubmit={mockOnSubmit} />)

    const symbolInput = screen.getByLabelText('Symbol')
    const quantityInput = screen.getByLabelText('Quantity')

    await user.type(symbolInput, 'BTCUSDT')
    await user.type(quantityInput, '-10')

    const submitButton = screen.getByRole('button', { name: /place order/i })
    await user.click(submitButton)

    expect(await screen.findByText('Quantity must be positive')).toBeInTheDocument()
    expect(mockOnSubmit).not.toHaveBeenCalled()
  })

  it('validates price for limit orders', async () => {
    const user = userEvent.setup()
    render(<OrderForm onSubmit={mockOnSubmit} />)

    const symbolInput = screen.getByLabelText('Symbol')
    const quantityInput = screen.getByLabelText('Quantity')
    const orderTypeSelect = screen.getByLabelText('Order Type')

    await user.type(symbolInput, 'BTCUSDT')
    await user.type(quantityInput, '0.1')
    await user.selectOptions(orderTypeSelect, 'LIMIT')

    const submitButton = screen.getByRole('button', { name: /place order/i })
    await user.click(submitButton)

    expect(await screen.findByText('Price is required for limit orders')).toBeInTheDocument()
    expect(mockOnSubmit).not.toHaveBeenCalled()
  })

  it('submits valid market order', async () => {
    const user = userEvent.setup()
    render(<OrderForm onSubmit={mockOnSubmit} />)

    const symbolInput = screen.getByLabelText('Symbol')
    const quantityInput = screen.getByLabelText('Quantity')

    await user.type(symbolInput, 'BTCUSDT')
    await user.type(quantityInput, '0.1')

    const submitButton = screen.getByRole('button', { name: /place order/i })
    await user.click(submitButton)

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith({
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.1,
      })
    })
  })

  it('submits valid limit order', async () => {
    const user = userEvent.setup()
    render(<OrderForm onSubmit={mockOnSubmit} />)

    const symbolInput = screen.getByLabelText('Symbol')
    const quantityInput = screen.getByLabelText('Quantity')
    const orderTypeSelect = screen.getByLabelText('Order Type')

    await user.type(symbolInput, 'BTCUSDT')
    await user.type(quantityInput, '0.1')
    await user.selectOptions(orderTypeSelect, 'LIMIT')

    const priceInput = screen.getByLabelText('Price')
    await user.type(priceInput, '42000')

    const sellRadio = screen.getByRole('radio', { name: /sell/i })
    await user.click(sellRadio)

    const submitButton = screen.getByRole('button', { name: /place order/i })
    await user.click(submitButton)

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith({
        symbol: 'BTCUSDT',
        side: 'SELL',
        type: 'LIMIT',
        quantity: 0.1,
        price: 42000,
      })
    })
  })

  it('resets form after successful submission', async () => {
    const user = userEvent.setup()
    render(<OrderForm onSubmit={mockOnSubmit} />)

    const symbolInput = screen.getByLabelText('Symbol')
    const quantityInput = screen.getByLabelText('Quantity')

    await user.type(symbolInput, 'BTCUSDT')
    await user.type(quantityInput, '0.1')

    const submitButton = screen.getByRole('button', { name: /place order/i })
    await user.click(submitButton)

    await waitFor(() => {
      expect(symbolInput).toHaveValue('')
      expect(quantityInput).toHaveValue(null) // number inputs show null for empty
    })
  })

  it('disables form while submitting', async () => {
    const user = userEvent.setup()
    mockOnSubmit.mockReturnValue(new Promise(resolve => setTimeout(resolve, 100)))

    render(<OrderForm onSubmit={mockOnSubmit} />)

    const symbolInput = screen.getByLabelText('Symbol')
    const quantityInput = screen.getByLabelText('Quantity')

    await user.type(symbolInput, 'BTCUSDT')
    await user.type(quantityInput, '0.1')

    const submitButton = screen.getByRole('button', { name: /place order/i })
    await user.click(submitButton)

    expect(submitButton).toBeDisabled()
    expect(symbolInput).toBeDisabled()
    expect(quantityInput).toBeDisabled()
  })

  it('shows loading state while submitting', async () => {
    const user = userEvent.setup()
    mockOnSubmit.mockReturnValue(new Promise(resolve => setTimeout(resolve, 100)))

    render(<OrderForm onSubmit={mockOnSubmit} />)

    const symbolInput = screen.getByLabelText('Symbol')
    const quantityInput = screen.getByLabelText('Quantity')

    await user.type(symbolInput, 'BTCUSDT')
    await user.type(quantityInput, '0.1')

    const submitButton = screen.getByRole('button', { name: /place order/i })
    await user.click(submitButton)

    expect(screen.getByText(/placing order/i)).toBeInTheDocument()
  })

  it('handles submission errors', async () => {
    const user = userEvent.setup()
    const errorMessage = 'Insufficient balance'
    mockOnSubmit.mockRejectedValue(new Error(errorMessage))

    render(<OrderForm onSubmit={mockOnSubmit} />)

    const symbolInput = screen.getByLabelText('Symbol')
    const quantityInput = screen.getByLabelText('Quantity')

    await user.type(symbolInput, 'BTCUSDT')
    await user.type(quantityInput, '0.1')

    const submitButton = screen.getByRole('button', { name: /place order/i })
    await user.click(submitButton)

    expect(await screen.findByText(errorMessage)).toBeInTheDocument()
    expect(submitButton).not.toBeDisabled()
  })

  it('validates symbol format', async () => {
    const user = userEvent.setup()
    render(<OrderForm onSubmit={mockOnSubmit} />)

    const symbolInput = screen.getByLabelText('Symbol')
    const quantityInput = screen.getByLabelText('Quantity')

    await user.type(symbolInput, 'BTC-USDT')
    await user.type(quantityInput, '0.1')

    const submitButton = screen.getByRole('button', { name: /place order/i })
    await user.click(submitButton)

    expect(await screen.findByText('Invalid symbol format')).toBeInTheDocument()
    expect(mockOnSubmit).not.toHaveBeenCalled()
  })

  it('supports keyboard shortcuts', async () => {
    const user = userEvent.setup()
    render(<OrderForm onSubmit={mockOnSubmit} />)

    // Press Alt+B for Buy
    await user.keyboard('{Alt>}b{/Alt}')
    expect(screen.getByRole('radio', { name: /buy/i })).toBeChecked()

    // Press Alt+S for Sell
    await user.keyboard('{Alt>}s{/Alt}')
    expect(screen.getByRole('radio', { name: /sell/i })).toBeChecked()
  })
})
