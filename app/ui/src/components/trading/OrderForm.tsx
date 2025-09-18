import { useState, useEffect } from 'react'
import type { OrderSide, OrderType } from '@/types'
import { validateOrderForm } from './validateOrderForm'
import './OrderForm.css'

export type OrderFormValues = {
  symbol: string
  side: OrderSide
  type: OrderType
  quantity: number
  price?: number
}

type OrderFormProps = {
  onSubmit: (values: OrderFormValues) => void | Promise<void>
  className?: string
}

export function OrderForm({ onSubmit, className = '' }: OrderFormProps) {
  const [values, setValues] = useState<OrderFormValues>({
    symbol: '',
    side: 'BUY',
    type: 'MARKET',
    quantity: 0,
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    const handleKeyboard = (e: KeyboardEvent) => {
      if (e.altKey) {
        if (e.key === 'b') {
          setValues(prev => ({ ...prev, side: 'BUY' }))
        } else if (e.key === 's') {
          setValues(prev => ({ ...prev, side: 'SELL' }))
        }
      }
    }

    window.addEventListener('keydown', handleKeyboard)
    return () => window.removeEventListener('keydown', handleKeyboard)
  }, [])

  const handleChange = (field: keyof OrderFormValues, value: string | number) => {
    setValues(prev => ({ ...prev, [field]: value }))
    setErrors(prev => ({ ...prev, [field]: '' }))
    setSubmitError(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitError(null)

    const validationErrors = validateOrderForm(values)
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors)
      return
    }

    setIsSubmitting(true)
    try {
      await onSubmit(values)
      // Reset form on success
      setValues({
        symbol: '',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0,
      })
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Failed to place order')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <form className={`order-form ${className}`} onSubmit={handleSubmit}>
      <div className="form-group">
        <label htmlFor="symbol">Symbol</label>
        <input
          id="symbol"
          type="text"
          value={values.symbol}
          onChange={e => handleChange('symbol', e.target.value.toUpperCase())}
          disabled={isSubmitting}
          placeholder="BTCUSDT"
        />
        {errors.symbol && <span className="error-message">{errors.symbol}</span>}
      </div>

      <div className="form-group">
        <label id="side-label">Side</label>
        <div className="radio-group" role="radiogroup" aria-labelledby="side-label">
          <label className="radio-label">
            <input
              type="radio"
              name="side"
              value="BUY"
              checked={values.side === 'BUY'}
              onChange={e => handleChange('side', e.target.value as OrderSide)}
              disabled={isSubmitting}
            />
            Buy
          </label>
          <label className="radio-label">
            <input
              type="radio"
              name="side"
              value="SELL"
              checked={values.side === 'SELL'}
              onChange={e => handleChange('side', e.target.value as OrderSide)}
              disabled={isSubmitting}
            />
            Sell
          </label>
        </div>
      </div>

      <div className="form-group">
        <label htmlFor="orderType">Order Type</label>
        <select
          id="orderType"
          value={values.type}
          onChange={e => handleChange('type', e.target.value as OrderType)}
          disabled={isSubmitting}
        >
          <option value="MARKET">Market</option>
          <option value="LIMIT">Limit</option>
        </select>
      </div>

      <div className="form-group">
        <label htmlFor="quantity">Quantity</label>
        <input
          id="quantity"
          type="number"
          step="any"
          value={values.quantity === 0 ? '' : values.quantity}
          onChange={e => handleChange('quantity', parseFloat(e.target.value) || 0)}
          disabled={isSubmitting}
          placeholder="0.00"
        />
        {errors.quantity && <span className="error-message">{errors.quantity}</span>}
      </div>

      {values.type === 'LIMIT' && (
        <div className="form-group">
          <label htmlFor="price">Price</label>
          <input
            id="price"
            type="number"
            step="any"
            value={values.price || ''}
            onChange={e => handleChange('price', parseFloat(e.target.value) || 0)}
            disabled={isSubmitting}
            placeholder="0.00"
          />
          {errors.price && <span className="error-message">{errors.price}</span>}
        </div>
      )}

      {submitError && (
        <div className="submit-error" role="alert">
          {submitError}
        </div>
      )}

      <button
        type="submit"
        className={`submit-button ${values.side === 'BUY' ? 'buy' : 'sell'}`}
        disabled={isSubmitting}
      >
        {isSubmitting ? 'Placing Order...' : 'Place Order'}
      </button>
    </form>
  )
}
