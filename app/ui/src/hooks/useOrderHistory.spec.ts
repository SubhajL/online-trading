import { describe, expect, test, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useOrderHistory } from './useOrderHistory'

// Mock dependencies
vi.mock('@/services/api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}))

vi.mock('./useApiCache', () => ({
  useApiCache: vi.fn(),
}))

import { useApiCache } from './useApiCache'

describe('useOrderHistory', () => {
  const mockOrders: Order[] = [
    {
      orderId: 'ORD001' as any,
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.1,
      status: 'FILLED',
      venue: 'SPOT',
      createdAt: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(), // 1 day ago
      updatedAt: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
      executedQuantity: 0.1,
      avgPrice: 40000,
    },
    {
      orderId: 'ORD002' as any,
      symbol: 'ETHUSDT' as any,
      side: 'SELL',
      type: 'LIMIT',
      quantity: 1.5,
      price: 2500,
      status: 'FILLED',
      venue: 'SPOT',
      createdAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(), // 5 days ago
      updatedAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
      executedQuantity: 1.5,
      avgPrice: 2500,
    },
    {
      orderId: 'ORD003' as any,
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      type: 'LIMIT',
      quantity: 0.2,
      price: 38000,
      status: 'FILLED',
      venue: 'USD_M',
      createdAt: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(), // 10 days ago
      updatedAt: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
      executedQuantity: 0.2,
      avgPrice: 38000,
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('fetches historical orders with correct filters', () => {
    vi.mocked(useApiCache).mockReturnValue({
      data: mockOrders,
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() =>
      useOrderHistory({
        status: 'FILLED',
        venue: 'SPOT',
        limit: 100,
      }),
    )

    expect(useApiCache).toHaveBeenCalledWith(
      'order-history-FILLED-SPOT-100',
      expect.any(Function),
      { ttl: 30000 },
    )
    expect(result.current.orders).toEqual(mockOrders)
  })

  test('applies date range filtering accurately', () => {
    vi.mocked(useApiCache).mockReturnValue({
      data: mockOrders,
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => useOrderHistory())

    // Initial state should be 'all' with all orders
    expect(result.current.dateRange).toBe('all')
    expect(result.current.filteredOrders).toHaveLength(3)

    // Test setting date range updates state
    act(() => {
      result.current.setDateRange('1d')
    })
    expect(result.current.dateRange).toBe('1d')

    // Test setting different ranges
    act(() => {
      result.current.setDateRange('7d')
    })
    expect(result.current.dateRange).toBe('7d')

    act(() => {
      result.current.setDateRange('30d')
    })
    expect(result.current.dateRange).toBe('30d')
  })

  test('calculates volume statistics correctly', () => {
    vi.mocked(useApiCache).mockReturnValue({
      data: mockOrders,
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => useOrderHistory())

    expect(result.current.stats.totalTrades).toBe(3)
    expect(result.current.stats.totalVolume).toBe(4000 + 3750 + 7600) // 15350
    expect(result.current.stats.buyOrders).toBe(2)
    expect(result.current.stats.sellOrders).toBe(1)
  })

  test('handles pagination for large datasets', () => {
    const largeDataset = Array.from({ length: 250 }, (_, i) => ({
      ...mockOrders[0],
      orderId: `ORD${String(i + 1).padStart(3, '0')}` as any,
      createdAt: new Date(Date.now() - i * 60 * 60 * 1000).toISOString(),
    }))

    vi.mocked(useApiCache).mockReturnValue({
      data: largeDataset,
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => useOrderHistory({ limit: 100 }))

    expect(result.current.orders).toHaveLength(250)
    expect(result.current.hasMore).toBe(true)
    expect(result.current.pageSize).toBe(100)
  })

  test('refreshes data when filters change', () => {
    const mockRefetch = vi.fn()

    vi.mocked(useApiCache).mockReturnValue({
      data: mockOrders,
      loading: false,
      error: null,
      refetch: mockRefetch,
      clearCache: vi.fn(),
    })

    const { rerender } = renderHook(({ venue }) => useOrderHistory({ venue }), {
      initialProps: { venue: undefined },
    })

    // Change venue filter
    rerender({ venue: 'SPOT' })

    expect(useApiCache).toHaveBeenCalledWith('order-history-SPOT', expect.any(Function), {
      ttl: 30000,
    })
  })

  test('groups orders by symbol for summary', () => {
    vi.mocked(useApiCache).mockReturnValue({
      data: mockOrders,
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => useOrderHistory())

    expect(result.current.ordersBySymbol['BTCUSDT']).toHaveLength(2)
    expect(result.current.ordersBySymbol['ETHUSDT']).toHaveLength(1)
  })

  test('filters orders by date correctly', () => {
    const now = Date.now()
    const ordersWithDates = [
      { ...mockOrders[0], createdAt: new Date(now - 0.5 * 24 * 60 * 60 * 1000).toISOString() }, // 0.5 days ago
      { ...mockOrders[1], createdAt: new Date(now - 3 * 24 * 60 * 60 * 1000).toISOString() }, // 3 days ago
      { ...mockOrders[2], createdAt: new Date(now - 10 * 24 * 60 * 60 * 1000).toISOString() }, // 10 days ago
    ]

    vi.mocked(useApiCache).mockReturnValue({
      data: ordersWithDates,
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result, rerender } = renderHook(() => useOrderHistory())

    // Test 1 day filter
    act(() => {
      result.current.setDateRange('1d')
    })
    rerender()
    const oneDay = result.current.filteredOrders
    expect(oneDay.length).toBeGreaterThanOrEqual(1)

    // Test 7 day filter
    act(() => {
      result.current.setDateRange('7d')
    })
    rerender()
    const sevenDays = result.current.filteredOrders
    expect(sevenDays.length).toBeGreaterThanOrEqual(2)

    // Test all filter
    act(() => {
      result.current.setDateRange('all')
    })
    rerender()
    expect(result.current.filteredOrders).toHaveLength(3)
  })

  test('handles empty order history gracefully', () => {
    vi.mocked(useApiCache).mockReturnValue({
      data: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => useOrderHistory())

    expect(result.current.orders).toEqual([])
    expect(result.current.filteredOrders).toEqual([])
    expect(result.current.stats.totalTrades).toBe(0)
    expect(result.current.stats.totalVolume).toBe(0)
  })

  test('handles loading and error states', () => {
    // Test loading state
    vi.mocked(useApiCache).mockReturnValue({
      data: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result: loadingResult } = renderHook(() => useOrderHistory())
    expect(loadingResult.current.loading).toBe(true)

    // Test error state
    const mockError = new Error('Failed to fetch order history')
    vi.mocked(useApiCache).mockReturnValue({
      data: null,
      loading: false,
      error: mockError,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result: errorResult } = renderHook(() => useOrderHistory())
    expect(errorResult.current.error).toBe('Failed to fetch order history')
  })
})
