import { describe, it, expect } from 'vitest'
import { validateOrderForm } from './validateOrderForm'
import type { OrderFormValues } from './OrderForm'

describe('validateOrderForm', () => {
  it('validates empty form', () => {
    const values: OrderFormValues = {
      symbol: '',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0,
    }

    const errors = validateOrderForm(values)

    expect(errors).toEqual({
      symbol: 'Symbol is required',
      quantity: 'Quantity is required',
    })
  })

  it('validates symbol format', () => {
    const values: OrderFormValues = {
      symbol: 'BTC-USDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.1,
    }

    const errors = validateOrderForm(values)

    expect(errors.symbol).toBe('Invalid symbol format')
  })

  it('accepts valid symbol format', () => {
    const values: OrderFormValues = {
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.1,
    }

    const errors = validateOrderForm(values)

    expect(errors.symbol).toBeUndefined()
  })

  it('validates negative quantity', () => {
    const values: OrderFormValues = {
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: -10,
    }

    const errors = validateOrderForm(values)

    expect(errors.quantity).toBe('Quantity must be positive')
  })

  it('validates zero quantity', () => {
    const values: OrderFormValues = {
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0,
    }

    const errors = validateOrderForm(values)

    expect(errors.quantity).toBe('Quantity is required')
  })

  it('requires price for limit orders', () => {
    const values: OrderFormValues = {
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'LIMIT',
      quantity: 0.1,
    }

    const errors = validateOrderForm(values)

    expect(errors.price).toBe('Price is required for limit orders')
  })

  it('validates negative price for limit orders', () => {
    const values: OrderFormValues = {
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'LIMIT',
      quantity: 0.1,
      price: -100,
    }

    const errors = validateOrderForm(values)

    expect(errors.price).toBe('Price must be positive')
  })

  it('does not require price for market orders', () => {
    const values: OrderFormValues = {
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.1,
    }

    const errors = validateOrderForm(values)

    expect(errors.price).toBeUndefined()
  })

  it('returns empty errors for valid market order', () => {
    const values: OrderFormValues = {
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.1,
    }

    const errors = validateOrderForm(values)

    expect(errors).toEqual({})
  })

  it('returns empty errors for valid limit order', () => {
    const values: OrderFormValues = {
      symbol: 'BTCUSDT',
      side: 'SELL',
      type: 'LIMIT',
      quantity: 0.1,
      price: 42000,
    }

    const errors = validateOrderForm(values)

    expect(errors).toEqual({})
  })

  it('validates zero price for limit orders', () => {
    const values: OrderFormValues = {
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'LIMIT',
      quantity: 0.1,
      price: 0,
    }

    const errors = validateOrderForm(values)

    expect(errors.price).toBe('Price is required for limit orders')
  })

  it('accepts numeric symbols', () => {
    const values: OrderFormValues = {
      symbol: '1INCHUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 10,
    }

    const errors = validateOrderForm(values)

    expect(errors.symbol).toBeUndefined()
  })
})
