import { useState } from 'react'
import { apiClient } from '@/services/api'
import type { OrderFormValues } from '@/types'

type UseOrdersReturn = {
  placeOrder: (order: OrderFormValues) => Promise<void>
  cancelOrder: (orderId: string) => Promise<void>
  loading: boolean
  error: string | null
}

export function useOrders(): UseOrdersReturn {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const placeOrder = async (order: OrderFormValues) => {
    try {
      setLoading(true)
      setError(null)

      await apiClient.post('/orders', order)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to place order')
      throw err
    } finally {
      setLoading(false)
    }
  }

  const cancelOrder = async (orderId: string) => {
    try {
      setLoading(true)
      setError(null)

      await apiClient.delete(`/orders/${orderId}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel order')
      throw err
    } finally {
      setLoading(false)
    }
  }

  return {
    placeOrder,
    cancelOrder,
    loading,
    error,
  }
}
