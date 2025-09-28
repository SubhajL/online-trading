import { useMemo, useRef, useState } from 'react'
import { apiClient } from '@/services/api'
import type { ApiClient } from '@/services/api.client'
import type { Order, OrderStatus, Venue } from '@/types'
import { useApiCache } from './useApiCache'

type DateRange = '1d' | '7d' | '30d' | '90d' | 'all'

type OrderFilters = {
  venue?: Venue
  status?: OrderStatus
  symbol?: string
  limit?: number
}

type OrderStats = {
  totalTrades: number
  totalVolume: number
  buyOrders: number
  sellOrders: number
}

type UseOrderHistoryReturn = {
  orders: Order[]
  filteredOrders: Order[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  stats: OrderStats
  ordersBySymbol: Record<string, Order[]>
  dateRange: DateRange
  setDateRange: (range: DateRange) => void
  hasMore: boolean
  pageSize: number
}

export function useOrderHistory(filters?: OrderFilters, client?: ApiClient): UseOrderHistoryReturn {
  const apiClientRef = useRef(client || apiClient)
  const [dateRange, setDateRange] = useState<DateRange>('all')

  const cacheKey = useMemo(() => {
    const parts = ['order-history']
    if (filters?.status) parts.push(filters.status)
    if (filters?.venue) parts.push(filters.venue)
    if (filters?.limit) parts.push(String(filters.limit))
    return parts.join('-')
  }, [filters?.status, filters?.venue, filters?.limit])

  const fetcher = useMemo(
    () => async () => {
      const params: { status: OrderStatus; venue?: Venue; symbol?: string; limit?: number } = {
        status: 'FILLED',
      } // Default to filled orders for history
      if (filters?.venue) params.venue = filters.venue
      if (filters?.status) params.status = filters.status
      if (filters?.symbol) params.symbol = filters.symbol
      if (filters?.limit) params.limit = filters.limit

      const data = await apiClientRef.current.get<{ orders: Order[] }>('/orders', { params })
      return data.orders
    },
    [filters],
  )

  const { data, loading, error, refetch } = useApiCache<Order[]>(
    cacheKey,
    fetcher,
    { ttl: 30000 }, // 30 seconds cache
  )

  const orders = data || []

  // Filter orders by date range
  const filteredOrders = useMemo(() => {
    if (dateRange === 'all') return orders

    const now = new Date()
    const cutoffDate = new Date()

    switch (dateRange) {
      case '1d':
        cutoffDate.setDate(now.getDate() - 1)
        break
      case '7d':
        cutoffDate.setDate(now.getDate() - 7)
        break
      case '30d':
        cutoffDate.setDate(now.getDate() - 30)
        break
      case '90d':
        cutoffDate.setDate(now.getDate() - 90)
        break
    }

    return orders.filter(order => new Date(order.createdAt) >= cutoffDate)
  }, [orders, dateRange])

  // Calculate statistics
  const stats = useMemo(() => {
    const buyOrders = filteredOrders.filter(o => o.side === 'BUY')
    const sellOrders = filteredOrders.filter(o => o.side === 'SELL')
    const totalVolume = filteredOrders.reduce((sum, order) => {
      const price = order.avgPrice || order.price || 0
      const quantity = order.executedQuantity || 0
      return sum + price * quantity
    }, 0)

    return {
      totalTrades: filteredOrders.length,
      totalVolume,
      buyOrders: buyOrders.length,
      sellOrders: sellOrders.length,
    }
  }, [filteredOrders])

  // Group orders by symbol
  const ordersBySymbol = useMemo(() => {
    const grouped: Record<string, Order[]> = {}

    filteredOrders.forEach(order => {
      const symbol = order.symbol.toString()
      if (!grouped[symbol]) {
        grouped[symbol] = []
      }
      grouped[symbol].push(order)
    })

    return grouped
  }, [filteredOrders])

  const pageSize = filters?.limit || 100
  const hasMore = orders.length >= pageSize

  return {
    orders,
    filteredOrders,
    loading,
    error: error?.message || null,
    refresh: async () => {
      await refetch()
    },
    stats,
    ordersBySymbol,
    dateRange,
    setDateRange,
    hasMore,
    pageSize,
  }
}
