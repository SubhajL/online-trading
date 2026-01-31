import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useOrders } from './useOrders'
import { _testOnlyExports as cacheExports } from './useApiCache'
import type { Order, OrderId, Symbol, Venue } from '@/types'

vi.mock('@/services/websocket', () => {
  return {
    websocketService: {
      onConnectionStateChange: (cb: any) => {
        cb({ connected: false, connecting: false, reconnectAttempts: 0 })
        return () => {}
      },
      subscribe: vi.fn(() => () => {}),
      emitWithAck: vi.fn(),
      isConnected: () => false,
    },
  }
})

vi.mock('@/services/api', () => {
  return {
    apiClient: {
      get: vi.fn(),
    },
  }
})

import { apiClient } from '@/services/api'

describe('useOrders', () => {
  const baseOrders: Order[] = [
    {
      orderId: 'o1' as OrderId,
      symbol: 'BTCUSDT' as Symbol,
      side: 'BUY',
      type: 'MARKET',
      quantity: 1,
      status: 'NEW',
      venue: 'SPOT',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    },
    {
      orderId: 'o2' as OrderId,
      symbol: 'BTCUSDT' as Symbol,
      side: 'BUY',
      type: 'MARKET',
      quantity: 1,
      status: 'NEW',
      venue: 'USD_M',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    },
    {
      orderId: 'o3' as OrderId,
      symbol: 'ETHUSDT' as Symbol,
      side: 'SELL',
      type: 'LIMIT',
      quantity: 2,
      price: 2500,
      status: 'FILLED',
      venue: 'SPOT',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    },
  ]

  const mockGet = vi.mocked(apiClient.get)

  beforeEach(() => {
    cacheExports.cache.clear()
    cacheExports.inFlightRequests.clear()
    vi.clearAllMocks()

    mockGet.mockImplementation(async (_endpoint: string, options?: any) => {
      const params = options?.params ?? {}
      const venue = params.venue as Venue | undefined
      const status = params.status as string | undefined
      const symbol = params.symbol as string | undefined
      const limit = params.limit as number | undefined
      const offset = params.offset as number | undefined

      let result = baseOrders
      if (venue) result = result.filter(o => o.venue === venue)
      if (status) result = result.filter(o => o.status === status)
      if (symbol) result = result.filter(o => o.symbol === symbol)

      if (typeof offset === 'number' || typeof limit === 'number') {
        const start = typeof offset === 'number' ? offset : 0
        const end = typeof limit === 'number' ? start + limit : undefined
        result = result.slice(start, end)
      }

      return { orders: result }
    })
  })

  it('fetches orders on mount', async () => {
    const { result } = renderHook(() => useOrders())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBeNull()
    expect(result.current.orders).toEqual(baseOrders)
  })

  it('passes venue filter to API', async () => {
    const { result } = renderHook(() => useOrders({ venue: 'USD_M' }))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(mockGet).toHaveBeenCalledWith('/orders', { params: { venue: 'USD_M' } })
    result.current.orders.forEach(order => {
      expect(order.venue).toBe('USD_M')
    })
  })

  it('caches results by cache key', async () => {
    const { result: result1 } = renderHook(() => useOrders({ venue: 'SPOT' }))
    await waitFor(() => {
      expect(result1.current.loading).toBe(false)
    })

    const { result: result2 } = renderHook(() => useOrders({ venue: 'SPOT' }))
    expect(result2.current.loading).toBe(false)
    expect(result2.current.orders).toEqual(result1.current.orders)
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('refresh triggers refetch', async () => {
    const { result } = renderHook(() => useOrders({ venue: 'SPOT' }))
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    await act(async () => {
      await result.current.refresh()
    })

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('supports pagination params', async () => {
    const { result } = renderHook(() => useOrders({ limit: 1, offset: 1 }))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(mockGet).toHaveBeenCalledWith('/orders', { params: { limit: 1, offset: 1 } })
    expect(result.current.orders).toEqual([baseOrders[1]])
  })
})
