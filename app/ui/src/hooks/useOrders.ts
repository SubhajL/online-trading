import { useMemo, useRef, useState, useEffect } from 'react'
import { apiClient } from '@/services/api'
import type { ApiClient } from '@/services/api.client'
import type { Order, OrderStatus, Venue, OrderFormValues } from '@/types'
import { useApiCache } from './useApiCache'
import { websocketService } from '@/services/websocket'

type OrderFilters = {
  venue?: Venue
  status?: OrderStatus
  symbol?: string
  limit?: number
  offset?: number
}

type UseOrdersReturn = {
  orders: Order[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  placeOrder: (order: OrderFormValues) => Promise<void>
  cancelOrder: (orderId: string) => Promise<void>
  actionLoading: boolean
}

export function useOrders(filters?: OrderFilters, client?: ApiClient): UseOrdersReturn {
  const apiClientRef = useRef(client || apiClient)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [wsOrders, setWsOrders] = useState<Map<string, Order>>(new Map())

  // Determine if we should use WebSocket for this query
  const isActiveOrdersQuery =
    !filters?.status || filters.status === 'NEW' || filters.status === 'PARTIALLY_FILLED'

  const cacheKey = useMemo(() => {
    const parts = ['orders']
    if (filters?.venue) parts.push(filters.venue)
    if (filters?.status) parts.push(filters.status)
    if (filters?.symbol) parts.push(filters.symbol)
    if (filters?.limit) parts.push(`limit-${filters.limit}`)
    if (filters?.offset) parts.push(`offset-${filters.offset}`)
    return parts.join('-')
  }, [filters?.venue, filters?.status, filters?.symbol, filters?.limit, filters?.offset])

  const fetcher = useMemo(
    () => async () => {
      const params: OrderFilters = {}
      if (filters?.venue) params.venue = filters.venue
      if (filters?.status) params.status = filters.status
      if (filters?.symbol) params.symbol = filters.symbol
      if (filters?.limit) params.limit = filters.limit
      if (filters?.offset) params.offset = filters.offset

      const data = await apiClientRef.current.get<{ orders: Order[] }>('/orders', { params })
      return data.orders
    },
    [filters],
  )

  const { data, loading, error, refetch } = useApiCache<Order[]>(
    cacheKey,
    fetcher,
    { ttl: 10000 }, // 10 seconds cache for orders
  )

  // Subscribe to WebSocket order events for active orders
  useEffect(() => {
    if (!isActiveOrdersQuery) return

    const unsubscribes: Array<() => void> = []

    // Subscribe to order placed events
    unsubscribes.push(
      websocketService.subscribe('order.placed', (order: Order) => {
        if (
          (!filters?.venue || order.venue === filters.venue) &&
          (!filters?.symbol || order.symbol === filters.symbol)
        ) {
          setWsOrders(prev => {
            const updated = new Map(prev)
            updated.set(order.orderId, order)
            return updated
          })
        }
      }),
    )

    // Subscribe to order updated events
    unsubscribes.push(
      websocketService.subscribe('order.updated', (order: Order) => {
        setWsOrders(prev => {
          const updated = new Map(prev)
          if (prev.has(order.orderId)) {
            updated.set(order.orderId, order)
          }
          return updated
        })
      }),
    )

    // Subscribe to order canceled events
    unsubscribes.push(
      websocketService.subscribe('order.canceled', (order: Order) => {
        setWsOrders(prev => {
          const updated = new Map(prev)
          updated.delete(order.orderId)
          return updated
        })
      }),
    )

    return () => {
      unsubscribes.forEach(fn => fn())
    }
  }, [isActiveOrdersQuery, filters?.venue, filters?.symbol])

  // Merge REST and WebSocket orders
  const orders = useMemo(() => {
    if (!isActiveOrdersQuery || !data) return data || []

    // Create a map of REST orders
    const orderMap = new Map<string, Order>()
    data.forEach(order => {
      orderMap.set(order.orderId, order)
    })

    // Override/add WebSocket orders
    wsOrders.forEach((wsOrder, orderId) => {
      orderMap.set(orderId, wsOrder)
    })

    return Array.from(orderMap.values())
  }, [data, wsOrders, isActiveOrdersQuery])

  const placeOrder = async (order: OrderFormValues) => {
    try {
      setActionLoading(true)
      setActionError(null)
      await apiClientRef.current.post('/orders', order)
      // Refresh orders list after placing
      await refetch()
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to place order'
      setActionError(errorMsg)
      throw err
    } finally {
      setActionLoading(false)
    }
  }

  const cancelOrder = async (orderId: string) => {
    try {
      setActionLoading(true)
      setActionError(null)
      await apiClientRef.current.delete(`/orders/${orderId}`)
      // Refresh orders list after canceling
      await refetch()
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to cancel order'
      setActionError(errorMsg)
      throw err
    } finally {
      setActionLoading(false)
    }
  }

  return {
    orders,
    loading,
    error: error?.message || actionError || null,
    refresh: async () => {
      await refetch()
    },
    placeOrder,
    cancelOrder,
    actionLoading,
  }
}
