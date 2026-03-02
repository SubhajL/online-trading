import { describe, expect, test, vi, beforeEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { usePositions } from './usePositions'
import type { Position } from '@/types'

// Mock the dependencies
vi.mock('@/services/api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}))

vi.mock('./useApiCache', () => ({
  useApiCache: vi.fn(),
}))

const mockSubscribe = vi.fn()
vi.mock('@/services/websocket', () => ({
  websocketService: {
    subscribe: (...args: unknown[]) => mockSubscribe(...args),
  },
}))

import { useApiCache } from './useApiCache'
import { apiClient } from '@/services/api'

describe('usePositions', () => {
  const mockPositions: Position[] = [
    {
      symbol: 'BTCUSDT' as any,
      side: 'LONG',
      quantity: 0.1,
      entryPrice: 40000,
      markPrice: 42000,
      pnl: 200,
      pnlPercent: 5,
      venue: 'SPOT',
    },
    {
      symbol: 'ETHUSDT' as any,
      side: 'SHORT',
      quantity: 2,
      entryPrice: 2500,
      markPrice: 2400,
      pnl: 200,
      pnlPercent: 4,
      venue: 'USD_M',
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    mockSubscribe.mockReturnValue(vi.fn())
  })

  test('fetches positions from trading endpoint successfully', async () => {
    const mockRefetch = vi.fn()
    vi.mocked(useApiCache).mockReturnValue({
      data: mockPositions,
      loading: false,
      error: null,
      refetch: mockRefetch,
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => usePositions())

    expect(result.current.positions).toEqual(mockPositions)
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe(null)
  })

  test('fetcher parses Position[] response from /trading/positions', async () => {
    let capturedFetcher: (() => Promise<Position[]>) | null = null

    vi.mocked(useApiCache).mockImplementation((_cacheKey, fetcher) => {
      capturedFetcher = fetcher
      return {
        data: [],
        loading: false,
        error: null,
        refetch: vi.fn(),
        clearCache: vi.fn(),
      }
    })

    vi.mocked(apiClient.get).mockResolvedValue(mockPositions)

    renderHook(() => usePositions())

    expect(capturedFetcher).not.toBeNull()
    const result = await capturedFetcher!()

    expect(apiClient.get).toHaveBeenCalledWith('/trading/positions', { params: undefined })
    expect(result).toEqual(mockPositions)
  })

  test('fetcher maps BFF position payload to Position shape', async () => {
    let capturedFetcher: (() => Promise<Position[]>) | null = null
    vi.mocked(useApiCache).mockImplementation((_cacheKey, fetcher) => {
      capturedFetcher = fetcher
      return {
        data: [],
        loading: false,
        error: null,
        refetch: vi.fn(),
        clearCache: vi.fn(),
      }
    })

    vi.mocked(apiClient.get).mockResolvedValue([
      {
        symbol: 'BTCUSDT',
        side: 'LONG',
        quantity: 0.5,
        entryPrice: 50000,
        currentPrice: 51000,
        pnl: 500,
        pnlPercent: 2,
        venue: 'SPOT',
        timestamp: 1700000000000,
      },
    ])

    renderHook(() => usePositions())
    expect(capturedFetcher).not.toBeNull()
    const result = await capturedFetcher!()

    expect(result).toEqual([
      {
        symbol: 'BTCUSDT',
        side: 'LONG',
        quantity: 0.5,
        entryPrice: 50000,
        markPrice: 51000,
        pnl: 500,
        pnlPercent: 2,
        venue: 'SPOT',
      },
    ])
  })

  test('ignores websocket updates when payload is null or undefined', () => {
    let wsCallback: ((position: Position | null | undefined) => void) | undefined
    mockSubscribe.mockImplementation((_event: string, callback: typeof wsCallback) => {
      wsCallback = callback
      return vi.fn()
    })

    vi.mocked(useApiCache).mockReturnValue({
      data: mockPositions,
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => usePositions())
    expect(result.current.positions).toHaveLength(2)

    act(() => {
      wsCallback?.(null)
      wsCallback?.(undefined)
    })

    expect(result.current.positions).toHaveLength(2)
    expect(result.current.positions).toEqual(mockPositions)
  })

  test('handles empty positions array gracefully', () => {
    vi.mocked(useApiCache).mockReturnValue({
      data: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => usePositions())

    expect(result.current.positions).toEqual([])
    expect(result.current.totalValue).toBe(0)
    expect(result.current.totalPnl).toBe(0)
  })

  test('calculates total portfolio value correctly', () => {
    vi.mocked(useApiCache).mockReturnValue({
      data: mockPositions,
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => usePositions())

    // BTC: 0.1 * 42000 = 4200
    // ETH: 2 * 2400 = 4800
    // Total: 9000
    expect(result.current.totalValue).toBe(9000)
  })

  test('calculates total PnL correctly', () => {
    vi.mocked(useApiCache).mockReturnValue({
      data: mockPositions,
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => usePositions())

    // Total PnL: 200 + 200 = 400
    expect(result.current.totalPnl).toBe(400)
  })

  test('groups positions by venue properly', () => {
    vi.mocked(useApiCache).mockReturnValue({
      data: mockPositions,
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => usePositions())

    expect(result.current.positionsByVenue.SPOT).toHaveLength(1)
    expect(result.current.positionsByVenue.USD_M).toHaveLength(1)
    expect(result.current.positionsByVenue.SPOT?.[0]?.symbol).toBe('BTCUSDT')
    expect(result.current.positionsByVenue.USD_M?.[0]?.symbol).toBe('ETHUSDT')
  })

  test('filters positions by venue when specified', () => {
    const spotPositions = mockPositions.filter(p => p.venue === 'SPOT')

    vi.mocked(useApiCache).mockReturnValue({
      data: spotPositions,
      loading: false,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => usePositions('SPOT'))

    expect(result.current.positions).toHaveLength(1)
    expect(result.current.positions[0].venue).toBe('SPOT')
  })

  test('handles loading state properly', () => {
    vi.mocked(useApiCache).mockReturnValue({
      data: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => usePositions())

    expect(result.current.loading).toBe(true)
    expect(result.current.positions).toEqual([])
  })

  test('handles error state properly', () => {
    const mockError = new Error('Failed to fetch positions')

    vi.mocked(useApiCache).mockReturnValue({
      data: null,
      loading: false,
      error: mockError,
      refetch: vi.fn(),
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => usePositions())

    expect(result.current.error).toBe('Failed to fetch positions')
    expect(result.current.positions).toEqual([])
  })

  test('uses cache to avoid redundant API calls', () => {
    const mockRefetch = vi.fn()

    vi.mocked(useApiCache).mockReturnValue({
      data: mockPositions,
      loading: false,
      error: null,
      refetch: mockRefetch,
      clearCache: vi.fn(),
    })

    renderHook(() => usePositions())

    // Check that useApiCache was called with correct cache key
    expect(useApiCache).toHaveBeenCalledWith('positions-all', expect.any(Function), { ttl: 10000 })
  })

  test('provides refresh function to update positions', async () => {
    const mockRefetch = vi.fn().mockResolvedValue(undefined)

    vi.mocked(useApiCache).mockReturnValue({
      data: mockPositions,
      loading: false,
      error: null,
      refetch: mockRefetch,
      clearCache: vi.fn(),
    })

    const { result } = renderHook(() => usePositions())

    await result.current.refresh()

    expect(mockRefetch).toHaveBeenCalled()
  })
})
