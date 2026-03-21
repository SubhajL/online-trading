import { useState, useEffect } from 'react'
import { useBalances } from '@/hooks/useBalances'
import { useOrders } from '@/hooks/useOrders'
import { useToast } from '@/context/ToastContext'
import type { OrderFormValues, OrderSide, OrderType } from '@/types'

type PanelPBProps = {
  symbol: string
  price?: number
}

const QUICK_AMOUNTS = [
  { label: '25%', value: 0.25 },
  { label: '50%', value: 0.5 },
  { label: '75%', value: 0.75 },
  { label: '100%', value: 1 },
]

export function PanelPB({ symbol, price = 0 }: PanelPBProps) {
  const {
    balances,
    loading: balancesLoading,
    error: balancesError,
    applyOptimistic,
    rollback,
  } = useBalances('SPOT')
  const { placeOrder, loading: orderLoading, error: orderError } = useOrders()
  const { showSuccess, showError } = useToast()

  const [orderForm, setOrderForm] = useState<OrderFormValues>({
    symbol,
    side: 'BUY',
    type: 'MARKET',
    quantity: 0,
  })

  // Keep string representation for form inputs
  const [quantityStr, setQuantityStr] = useState('')
  const [stopLossPriceStr, setStopLossPriceStr] = useState('')
  const [takeProfitPriceStr, setTakeProfitPriceStr] = useState('')

  const [validationError, setValidationError] = useState<string | null>(null)

  useEffect(() => {
    setOrderForm(prev => ({ ...prev, symbol }))
  }, [symbol])

  const validateOrder = (order: OrderFormValues): boolean => {
    setValidationError(null)

    if (!order.quantity || order.quantity === 0) {
      setValidationError('Quantity is required')
      return false
    }

    if (order.quantity < 0) {
      setValidationError('Quantity must be positive')
      return false
    }

    if (order.type === 'LIMIT' && !order.price) {
      setValidationError('Price is required for limit orders')
      return false
    }

    if (!order.stopLossPrice) {
      setValidationError('Stop loss price is required')
      return false
    }

    if (!order.takeProfitPrice) {
      setValidationError('Take profit price is required')
      return false
    }

    // Check balance
    const usdtBalance = balances.find(b => b.asset === 'USDT')?.free || 0
    const effectivePrice = order.price || price

    // For buy orders, check USDT balance
    if (order.side === 'BUY') {
      // Market orders without a price cannot check balance properly
      if (order.type === 'MARKET' && effectivePrice === 0) {
        // Skip balance check for market orders without price info
        return true
      }
      const requiredAmount = order.quantity * effectivePrice
      if (requiredAmount > usdtBalance) {
        setValidationError('Insufficient balance')
        return false
      }
    }

    return true
  }

  const handleSubmit = async (side: OrderSide) => {
    const order = { ...orderForm, side }

    if (!validateOrder(order)) return

    const effectivePrice = order.price || price
    const token = applyOptimistic(order, effectivePrice)

    try {
      await placeOrder(order)
      showSuccess(`${side} order placed for ${order.quantity} ${symbol}`)
      setOrderForm({
        symbol,
        side: 'BUY',
        type: 'MARKET',
        quantity: 0,
      })
      setQuantityStr('')
      setStopLossPriceStr('')
      setTakeProfitPriceStr('')
      setValidationError(null)
    } catch (err) {
      rollback(token)
      const message = err instanceof Error ? err.message : 'Order failed'
      showError(message)
    }
  }

  const handleQuantityChange = (value: string) => {
    setQuantityStr(value)
    const numValue = parseFloat(value) || 0
    setOrderForm(prev => ({ ...prev, quantity: numValue }))
    setValidationError(null)
  }

  const handleTypeChange = (type: Extract<OrderType, 'MARKET' | 'LIMIT'>) => {
    setOrderForm(prev => ({ ...prev, type }))
  }

  const handlePriceChange = (value: number) => {
    setOrderForm(prev => ({ ...prev, price: value }))
  }

  const handleStopLossPriceChange = (value: number) => {
    setStopLossPriceStr(value > 0 ? String(value) : '')
    setOrderForm(prev => ({ ...prev, stopLossPrice: value || undefined }))
  }

  const handleTakeProfitPriceChange = (value: number) => {
    setTakeProfitPriceStr(value > 0 ? String(value) : '')
    setOrderForm(prev => ({ ...prev, takeProfitPrice: value || undefined }))
  }

  const calculateMaxQuantity = (): number => {
    const usdtBalance = balances.find(b => b.asset === 'USDT')?.free || 0
    const effectivePrice = orderForm.price || price
    return effectivePrice > 0 ? usdtBalance / effectivePrice : 0
  }

  const handleQuickAmount = (percentage: number) => {
    const maxQty = calculateMaxQuantity()
    const value = (maxQty * percentage).toFixed(4)
    handleQuantityChange(value)
  }

  const isLoading = orderLoading || balancesLoading
  const error = orderError || balancesError || validationError

  return (
    <div data-testid="trading-panel" className="bg-gray-900 rounded-lg p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">{symbol}</h3>
        {price > 0 && (
          <span className="text-sm text-gray-400">Current: ${price.toLocaleString()}</span>
        )}
      </div>

      {/* Order Type */}
      <div>
        <label htmlFor="order-type" className="block text-sm font-medium text-gray-300 mb-1">
          Type
        </label>
        <select
          id="order-type"
          value={orderForm.type}
          onChange={e => handleTypeChange(e.target.value as Extract<OrderType, 'MARKET' | 'LIMIT'>)}
          disabled={isLoading}
          className="w-full px-3 py-2 bg-gray-800 text-white rounded-md border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        >
          <option value="MARKET">Market</option>
          <option value="LIMIT">Limit</option>
        </select>
      </div>

      {/* Price field (for limit orders) */}
      {(orderForm.type === 'LIMIT' || orderForm.type === 'STOP_LIMIT') && (
        <div>
          <label htmlFor="order-price" className="block text-sm font-medium text-gray-300 mb-1">
            Price
          </label>
          <input
            id="order-price"
            type="number"
            value={orderForm.price || ''}
            onChange={e => handlePriceChange(parseFloat(e.target.value) || 0)}
            disabled={isLoading}
            placeholder="0.00"
            step="0.01"
            min="0"
            className="w-full px-3 py-2 bg-gray-800 text-white rounded-md border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
        </div>
      )}

      <div>
        <label htmlFor="order-stop-loss" className="block text-sm font-medium text-gray-300 mb-1">
          Stop Loss
        </label>
        <input
          id="order-stop-loss"
          type="number"
          value={stopLossPriceStr}
          onChange={e => handleStopLossPriceChange(parseFloat(e.target.value) || 0)}
          disabled={isLoading}
          placeholder="0.00"
          step="0.01"
          min="0"
          className="w-full px-3 py-2 bg-gray-800 text-white rounded-md border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
      </div>

      <div>
        <label htmlFor="order-take-profit" className="block text-sm font-medium text-gray-300 mb-1">
          Take Profit
        </label>
        <input
          id="order-take-profit"
          type="number"
          value={takeProfitPriceStr}
          onChange={e => handleTakeProfitPriceChange(parseFloat(e.target.value) || 0)}
          disabled={isLoading}
          placeholder="0.00"
          step="0.01"
          min="0"
          className="w-full px-3 py-2 bg-gray-800 text-white rounded-md border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
      </div>

      {/* Quantity */}
      <div>
        <label htmlFor="order-quantity" className="block text-sm font-medium text-gray-300 mb-1">
          Quantity
        </label>
        <div className="relative">
          <input
            id="order-quantity"
            type="number"
            value={quantityStr}
            onChange={e => handleQuantityChange(e.target.value)}
            disabled={isLoading}
            placeholder="0.0000"
            step="0.0001"
            min="0"
            className="w-full px-3 py-2 bg-gray-800 text-white rounded-md border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          <button
            type="button"
            onClick={() => handleQuickAmount(1)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-blue-500 hover:text-blue-400"
          >
            Max
          </button>
        </div>
      </div>

      {/* Quick amount buttons */}
      <div className="flex gap-2">
        {QUICK_AMOUNTS.map(({ label, value }) => (
          <button
            key={label}
            type="button"
            onClick={() => handleQuickAmount(value)}
            disabled={isLoading}
            className="flex-1 py-1 text-sm bg-gray-800 text-gray-300 rounded hover:bg-gray-700 disabled:opacity-50"
          >
            {label}
          </button>
        ))}
      </div>

      {/* Balance info */}
      <div className="text-sm text-gray-400">
        <span>Available: </span>
        <span className="text-white">
          {balances
            .find(b => b.asset === 'USDT')
            ?.free.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            }) || '0.00'}{' '}
          USDT
        </span>
      </div>

      {/* Error display */}
      {error && (
        <div role="alert" className="text-sm text-red-500 bg-red-500/10 rounded p-2">
          {error}
        </div>
      )}

      {/* Hidden inputs for testing */}
      <input type="hidden" id="order-side" value={orderForm.side} aria-label="Side" />

      {/* Buy/Sell buttons */}
      <div className="grid grid-cols-2 gap-3">
        <button
          data-testid="buy-button"
          onClick={() => handleSubmit('BUY')}
          disabled={isLoading}
          className="py-3 bg-green-600 text-white font-medium rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Buy
        </button>
        <button
          data-testid="sell-button"
          onClick={() => handleSubmit('SELL')}
          disabled={isLoading}
          className="py-3 bg-red-600 text-white font-medium rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Sell
        </button>
      </div>

      {/* Loading spinner */}
      {isLoading && (
        <div className="flex justify-center">
          <div
            data-testid="loading-spinner"
            className="animate-spin rounded-full h-6 w-6 border-t-2 border-b-2 border-blue-500"
          />
        </div>
      )}
    </div>
  )
}
